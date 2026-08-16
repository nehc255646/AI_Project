"""
AI 客户端层 — 统一通过 OpenAI 兼容接口调用各提供商模型。

支持流式对话、API 临时故障的自动重试（指数退避）、
密钥解析（存档密钥优先，其次环境变量）。
"""
import asyncio
import logging
import os
from typing import AsyncGenerator, Dict, List, Tuple

import httpx
from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError

from config import PROVIDER_CONFIG, MODEL_CONFIG

logger = logging.getLogger(__name__)

# API 调用重试配置
_API_RETRY_MAX = 2
_API_RETRY_DELAY = 1.0  # 初始延迟（秒），指数退避

# 支持把 min_p / top_k 放进 extra_body 的提供商（其他提供商忽略，避免 400）
_EXTRA_BODY_PROVIDERS = {"deepseek", "dashscope"}


def _is_deepseek_model(model_key: str, model_id: str) -> bool:
    """模型清单固定维护；模型名含 deepseek 的条目统一视为可选思考模型。"""
    return "deepseek" in model_id.lower() or "deepseek" in model_key.lower()


class AIClient:
    def __init__(self):
        # 按 (base_url, api_key) 缓存客户端
        self._clients: Dict[Tuple[str, str], AsyncOpenAI] = {}

    async def close(self) -> None:
        """释放所有 OpenAI 兼容客户端（服务关闭时调用）。"""
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
        self._clients.clear()

    def _get_client(self, provider: str, api_key: str) -> AsyncOpenAI:
        cfg = PROVIDER_CONFIG.get(provider)
        if not cfg:
            raise ValueError(f"不支持的提供商: {provider}")
        cache_key = (cfg["base_url"], api_key)
        if cache_key not in self._clients:
            self._clients[cache_key] = AsyncOpenAI(
                api_key=api_key, base_url=cfg["base_url"], timeout=60
            )
        return self._clients[cache_key]

    def _resolve_api_key(self, provider: str, api_key: str) -> str:
        """密钥解析：存档传入的密钥优先，其次环境变量，Ollama 本地用占位密钥。"""
        cfg = PROVIDER_CONFIG.get(provider, {})
        if provider == "ollama_local":
            return cfg.get("dummy_api_key", "ollama")
        if api_key:
            return api_key
        env_name = cfg.get("api_key_env", "")
        env_val = os.environ.get(env_name) if env_name else ""
        if env_val:
            return env_val
        raise ValueError(f"{cfg.get('name', provider)} API Key 未配置，请在创建存档时提供")

    # ── 对外入口：流式对话 ──

    async def stream_chat(
        self, messages: List[Dict], model_key: str, api_key: str = "",
        max_tokens: int | None = None, params: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """异步生成器，逐块产出回复文本（适配 SSE）。"""
        cfg = MODEL_CONFIG.get(model_key)
        if not cfg:
            raise ValueError(f"不支持的模型: {model_key}")

        provider = cfg["provider"]
        model_id = cfg["id"]
        key = self._resolve_api_key(provider, api_key)
        client = self._get_client(provider, key)

        if max_tokens is None:
            max_tokens = cfg.get("max_tokens")
        # 用户参数中的 num_predict 优先于模型配置的 max_tokens
        if params and params.get("num_predict") is not None:
            max_tokens = params["num_predict"]

        kwargs = dict(model=model_id, messages=messages, stream=True)

        # OpenAI 兼容通用参数
        if params:
            for k in ("temperature", "top_p", "presence_penalty", "frequency_penalty"):
                if k in params:
                    kwargs[k] = params[k]

        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        # DeepSeek 支持按存档选择思考模式，其他模型统一禁用思考
        if _is_deepseek_model(model_key, model_id):
            thinking_enabled = (params or {}).get("thinking_enabled", True)
            if provider == "dashscope":
                kwargs.setdefault("extra_body", {}).update({"enable_thinking": thinking_enabled})
            elif provider == "deepseek":
                thinking_type = "enabled" if thinking_enabled else "disabled"
                kwargs.setdefault("extra_body", {}).update({"thinking": {"type": thinking_type}})
            else:
                kwargs["reasoning_effort"] = "high" if thinking_enabled else "none"
        else:
            disable_thinking = PROVIDER_CONFIG.get(provider, {}).get("disable_thinking")
            if disable_thinking:
                for k, v in disable_thinking.items():
                    if k == "extra_body":
                        kwargs.setdefault("extra_body", {}).update(v)
                    else:
                        kwargs[k] = v

        # extra_body：仅部分提供商支持的非标准参数
        extra_body = {}
        if provider in _EXTRA_BODY_PROVIDERS and params:
            for k in ("min_p", "top_k"):
                if k in params:
                    extra_body[k] = params[k]
        if extra_body:
            kwargs.setdefault("extra_body", {}).update(extra_body)

        # 仅请求阶段可重试，流式输出开始后中断直接失败
        last_exception = None
        started = False
        for attempt in range(_API_RETRY_MAX + 1):
            try:
                stream = await client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        started = True
                        yield chunk.choices[0].delta.content
                return  # 成功完成
            except (RateLimitError, APITimeoutError, APIError,
                    httpx.TimeoutException, httpx.NetworkError) as e:
                if started:
                    logger.warning(f"流式响应已开始后中断（不重试，避免内容重复）: {e}")
                    raise ConnectionError("回复生成中途中断，请重试") from e
                last_exception = e

                # 速率限制
                if isinstance(e, RateLimitError) or getattr(e, "status_code", None) == 429:
                    logger.warning(f"API 速率限制 (尝试 {attempt + 1}): {e}")
                    if attempt < _API_RETRY_MAX:
                        await asyncio.sleep(_API_RETRY_DELAY * (2 ** attempt))
                        continue
                    raise ConnectionError("API 请求频率过高，请稍后重试") from e

                # 超时
                if isinstance(e, (APITimeoutError, httpx.TimeoutException)):
                    logger.warning(f"API 请求超时 (尝试 {attempt + 1}): {e}")
                    if attempt < _API_RETRY_MAX:
                        await asyncio.sleep(_API_RETRY_DELAY)
                        continue
                    raise ConnectionError("API 请求超时，请检查网络连接") from e

                # OpenAI 兼容 API 返回错误
                if isinstance(e, APIError):
                    status = e.status_code
                    if status == 401:
                        raise ValueError("API 认证失败，请检查 API Key 是否正确") from e
                    if status == 403:
                        raise ValueError("API 权限不足，请检查账户权限") from e
                    if status >= 500:
                        logger.error(f"API 服务错误 (尝试 {attempt + 1}): {e}")
                        if attempt < _API_RETRY_MAX:
                            await asyncio.sleep(_API_RETRY_DELAY * (2 ** attempt))
                            continue
                        raise ConnectionError(f"API 服务暂时不可用 ({status})") from e
                    raise  # 其他 API 错误直接抛出

                # httpx 网络错误
                logger.warning(f"网络错误 (尝试 {attempt + 1}): {e}")
                if attempt < _API_RETRY_MAX:
                    await asyncio.sleep(_API_RETRY_DELAY * (2 ** attempt))
                    continue
                raise ConnectionError(f"网络连接失败，请检查网络: {e}") from e

        # 所有重试耗尽
        raise ConnectionError(f"API 请求失败 (已重试 {_API_RETRY_MAX} 次): {last_exception}")
