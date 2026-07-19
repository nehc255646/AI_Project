"""
AI Client layer — async OpenAI-compatible streaming for multiple providers.

Changes:
  - AsyncOpenAI for non-blocking I/O (fix #5)
  - Unified _stream_openai_compatible for DeepSeek / DashScope (fix #3)
  - Ollama health-check with 30 s cooldown cache (fix #4)
  - Retry logic for transient OpenAI API failures
"""
import asyncio
import json
import logging
import time
from typing import AsyncGenerator, List, Dict

import httpx
from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    OLLAMA_API_KEY,
    OLLAMA_URL,
    OLLAMA_CLOUD_URL,
    MODEL_CONFIG,
)

logger = logging.getLogger(__name__)

_OLLAMA_CHECK_CACHE: dict = {"ok": False, "at": 0.0}
_OLLAMA_CACHE_TTL = 30  # seconds

# API 调用重试配置
_API_RETRY_MAX = 2
_API_RETRY_DELAY = 1.0  # 初始延迟（秒），指数退避


class AIClient:
    def __init__(self):
        self._deepseek: AsyncOpenAI | None = None
        self._dashscope: AsyncOpenAI | None = None
        self._ollama_client: httpx.AsyncClient | None = None

    def _get_ollama_client(self) -> httpx.AsyncClient:
        if not self._ollama_client:
            self._ollama_client = httpx.AsyncClient(timeout=120)
        return self._ollama_client

    # ── Lazy client init ──

    def _client_deepseek(self) -> AsyncOpenAI:
        if not self._deepseek:
            if not DEEPSEEK_API_KEY:
                raise ValueError("DEEPSEEK_API_KEY 未在环境变量中设置")
            self._deepseek = AsyncOpenAI(
                api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=60
            )
        return self._deepseek

    def _client_dashscope(self) -> AsyncOpenAI:
        if not self._dashscope:
            if not DASHSCOPE_API_KEY:
                raise ValueError("DASHSCOPE_API_KEY 未在环境变量中设置")
            self._dashscope = AsyncOpenAI(
                api_key=DASHSCOPE_API_KEY, base_url=DASHSCOPE_BASE_URL, timeout=60
            )
        return self._dashscope

    # ── Ollama health check with cooldown cache (#4) ──

    async def _check_ollama(self) -> bool:
        now = time.time()
        if now - _OLLAMA_CHECK_CACHE["at"] < _OLLAMA_CACHE_TTL:
            return _OLLAMA_CHECK_CACHE["ok"]
        hosts = ("127.0.0.1", "localhost")
        async def _try_host(host: str) -> bool:
            try:
                url = f"http://{host}:11434/api/tags"
                r = await self._get_ollama_client().get(url, timeout=5)
                return r.status_code == 200
            except Exception:
                return False
        results = await asyncio.gather(*(_try_host(h) for h in hosts), return_exceptions=True)
        ok = any(r is True for r in results)
        _OLLAMA_CHECK_CACHE["ok"] = ok
        _OLLAMA_CHECK_CACHE["at"] = now
        return ok

    # ── Public entry: async generator (#5) ──

    async def stream_chat(
        self, messages: List[Dict], model_key: str, api_key: str = "",
        max_tokens: int | None = None, params: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """Async generator yielding response text chunks (SSE-friendly)."""
        cfg = MODEL_CONFIG.get(model_key)
        if not cfg:
            raise ValueError(f"不支持的模型: {model_key}")

        provider = cfg["provider"]
        model_id = cfg["id"]

        if max_tokens is None:
            max_tokens = cfg.get("max_tokens")

        # 用户参数中的 num_predict 优先于模型配置的 max_tokens
        if params and "num_predict" in params:
            max_tokens = params["num_predict"]

        thinking_disabled = cfg.get("thinking_disabled", False)

        if provider == "ollama":
            async for chunk in self._stream_ollama(
                messages, model_id, max_tokens, thinking_disabled, params, api_key
            ):
                yield chunk
        else:
            base_url = (
                DEEPSEEK_BASE_URL if provider == "deepseek" else DASHSCOPE_BASE_URL
            )
            async for chunk in self._stream_openai_compatible(
                messages, model_id, base_url, api_key, max_tokens, thinking_disabled, params
            ):
                yield chunk

    # ── Unified OpenAI-compatible streaming (#3) ──

    async def _stream_openai_compatible(
        self,
        messages: List[Dict],
        model_id: str,
        base_url: str,
        api_key: str = "",
        max_tokens: int | None = None,
        thinking_disabled: bool = False,
        params: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        if api_key:
            client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60)
        elif "dashscope" in base_url:
            client = self._client_dashscope()
        else:
            client = self._client_deepseek()

        kwargs = dict(model=model_id, messages=messages, stream=True)

        # 用户参数（OpenAI 兼容参数）
        if params:
            for key in ("temperature", "top_p", "presence_penalty", "frequency_penalty"):
                if key in params:
                    kwargs[key] = params[key]
            if "max_tokens" not in kwargs and params.get("num_predict") is not None:
                kwargs["max_tokens"] = params["num_predict"]

        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        # extra_body：非标准参数 + 禁用思考
        extra_body = {}
        if thinking_disabled:
            if "dashscope" in base_url:
                extra_body["enable_thinking"] = False
            else:
                extra_body["thinking"] = {"type": "disabled"}
        if params:
            for key in ("min_p", "top_k"):
                if key in params:
                    extra_body[key] = params[key]
        if extra_body:
            kwargs["extra_body"] = extra_body

        # 带重试的 API 调用
        last_exception = None
        for attempt in range(_API_RETRY_MAX + 1):
            try:
                stream = await client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return  # 成功完成
            except RateLimitError as e:
                logger.warning(f"API 速率限制 (尝试 {attempt + 1}): {e}")
                last_exception = e
                if attempt < _API_RETRY_MAX:
                    await asyncio.sleep(_API_RETRY_DELAY * (2 ** attempt))
                else:
                    raise ConnectionError(f"API 请求频率过高，请稍后重试: {e}") from e
            except APITimeoutError as e:
                logger.warning(f"API 请求超时 (尝试 {attempt + 1}): {e}")
                last_exception = e
                if attempt < _API_RETRY_MAX:
                    await asyncio.sleep(_API_RETRY_DELAY)
                else:
                    raise ConnectionError(f"API 请求超时，请检查网络连接: {e}") from e
            except APIError as e:
                logger.error(f"API 返回错误 (尝试 {attempt + 1}): {e}")
                status = e.status_code
                if status == 401:
                    raise ValueError("API 认证失败，请检查 API Key 是否正确") from e
                elif status == 403:
                    raise ValueError("API 权限不足，请检查账户权限") from e
                elif status == 429:
                    raise ConnectionError("请求过于频繁，请稍后重试") from e
                elif status >= 500:
                    if attempt < _API_RETRY_MAX:
                        await asyncio.sleep(_API_RETRY_DELAY * (2 ** attempt))
                        continue
                    raise ConnectionError(f"API 服务暂时不可用 ({status})") from e
                raise  # 其他 API 错误直接抛出
            except httpx.TimeoutException as e:
                logger.warning(f"HTTP 请求超时 (尝试 {attempt + 1}): {e}")
                last_exception = e
                if attempt < _API_RETRY_MAX:
                    await asyncio.sleep(_API_RETRY_DELAY)
                else:
                    raise ConnectionError(f"请求超时，请检查网络连接") from e
            except httpx.NetworkError as e:
                logger.warning(f"网络错误 (尝试 {attempt + 1}): {e}")
                last_exception = e
                if attempt < _API_RETRY_MAX:
                    await asyncio.sleep(_API_RETRY_DELAY * (2 ** attempt))
                else:
                    raise ConnectionError(f"网络连接失败，请检查网络: {e}") from e

        # 所有重试耗尽
        raise ConnectionError(f"API 请求失败 (已重试 {_API_RETRY_MAX} 次): {last_exception}")

    # ── Ollama streaming (kept separate due to different API shape) ──

    async def _stream_ollama(
        self, messages: List[Dict], model_id: str,
        max_tokens: int | None = None,
        thinking_disabled: bool = False,
        params: dict | None = None,
        api_key: str = "",
    ) -> AsyncGenerator[str, None]:
        # 优先检测本地 Ollama，不可用才走云端
        local_ok = await self._check_ollama()
        if local_ok:
            url = OLLAMA_URL
        elif api_key or OLLAMA_API_KEY:
            url = OLLAMA_CLOUD_URL
            key = api_key or OLLAMA_API_KEY
        else:
            raise ConnectionError(
                "NEED_KEY:无法连接到本地 Ollama，请提供 Ollama Cloud API Key 以使用云端"
            )

        payload = {"model": model_id, "messages": messages, "stream": True}

        # 将参数放入 options（Ollama 风格）
        options = {}
        if params:
            for key in ("temperature", "top_p", "top_k", "min_p",
                         "repeat_penalty", "presence_penalty",
                         "frequency_penalty", "num_ctx", "num_predict"):
                if key in params:
                    options[key] = params[key]
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options

        if thinking_disabled:
            payload["think"] = False
        client = self._get_ollama_client()
        headers = {}
        if url == OLLAMA_CLOUD_URL:
            headers["Authorization"] = f"Bearer {key}"
        async with client.stream(
            "POST", url, json=payload, headers=headers or None
        ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "message" in chunk and "content" in chunk["message"]:
                        yield chunk["message"]["content"]
