"""
AI 客户端层 — 统一通过 OpenAI 兼容接口调用。

支持流式对话、连通性测试、API 临时故障的自动重试（指数退避）。
供应商 / 模型由数据库目录解析后再传入。
"""
import asyncio
import logging
import time
from typing import AsyncGenerator, Dict, List, Tuple

import httpx
from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

_API_RETRY_MAX = 2
_API_RETRY_DELAY = 1.0


class AIClientError(Exception):
    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


class AIClient:
    def __init__(self):
        self._clients: Dict[Tuple[str, str], AsyncOpenAI] = {}

    async def close(self) -> None:
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
        self._clients.clear()

    def _get_client(self, base_url: str, api_key: str, timeout: float = 60) -> AsyncOpenAI:
        cache_key = (base_url, api_key, timeout)
        if cache_key not in self._clients:
            self._clients[cache_key] = AsyncOpenAI(
                api_key=api_key, base_url=base_url, timeout=timeout,
            )
        return self._clients[cache_key]

    def _build_kwargs(
        self,
        messages: List[Dict],
        model_id: str,
        max_tokens: int | None,
        params: dict | None,
        stream: bool,
    ) -> dict:
        kwargs = dict(model=model_id, messages=messages, stream=stream)
        if params:
            for k in ("temperature", "top_p", "presence_penalty", "frequency_penalty"):
                if k in params:
                    kwargs[k] = params[k]
        if params and params.get("num_predict") is not None:
            requested = params["num_predict"]
            cap = max_tokens if max_tokens is not None else requested
            max_tokens = min(requested, cap)
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return kwargs

    async def stream_chat(
        self,
        messages: List[Dict],
        model_id: str,
        base_url: str,
        api_key: str,
        max_tokens: int | None = None,
        params: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """异步生成器，逐块产出回复文本（适配 SSE）。"""
        client = self._get_client(base_url, api_key)
        kwargs = self._build_kwargs(messages, model_id, max_tokens, params, stream=True)

        last_exception = None
        started = False
        for attempt in range(_API_RETRY_MAX + 1):
            try:
                stream = await client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        started = True
                        yield chunk.choices[0].delta.content
                return
            except (RateLimitError, APITimeoutError, APIError,
                    httpx.TimeoutException, httpx.NetworkError) as e:
                if started:
                    logger.warning(f"流式响应已开始后中断（不重试，避免内容重复）: {e}")
                    raise AIClientError("回复生成中途中断，请重试", "stream_interrupted") from e
                last_exception = e

                if isinstance(e, RateLimitError) or getattr(e, "status_code", None) == 429:
                    logger.warning(f"API 速率限制 (尝试 {attempt + 1}): {e}")
                    if attempt < _API_RETRY_MAX:
                        await asyncio.sleep(_API_RETRY_DELAY * (2 ** attempt))
                        continue
                    raise AIClientError("API 请求频率过高，请稍后重试", "rate_limited") from e

                if isinstance(e, (APITimeoutError, httpx.TimeoutException)):
                    logger.warning(f"API 请求超时 (尝试 {attempt + 1}): {e}")
                    if attempt < _API_RETRY_MAX:
                        await asyncio.sleep(_API_RETRY_DELAY)
                        continue
                    raise AIClientError("API 请求超时，请检查网络连接", "timeout") from e

                if isinstance(e, APIError):
                    status = e.status_code
                    if status == 401:
                        raise AIClientError("API 认证失败，请到「模型配置」检查该供应商的密钥", "auth_failed") from e
                    if status == 403:
                        raise AIClientError("API 权限不足，请检查账户权限", "permission_denied") from e
                    if status >= 500:
                        logger.error(f"API 服务错误 (尝试 {attempt + 1}): {e}")
                        if attempt < _API_RETRY_MAX:
                            await asyncio.sleep(_API_RETRY_DELAY * (2 ** attempt))
                            continue
                        raise AIClientError(f"API 服务暂时不可用 ({status})", "service_unavailable") from e
                    raise

                logger.warning(f"网络错误 (尝试 {attempt + 1}): {e}")
                if attempt < _API_RETRY_MAX:
                    await asyncio.sleep(_API_RETRY_DELAY * (2 ** attempt))
                    continue
                raise AIClientError(f"网络连接失败，请检查网络: {e}", "network_error") from e

        raise AIClientError(
            f"API 请求失败 (已重试 {_API_RETRY_MAX} 次): {last_exception}",
            "request_failed",
        )

    async def test_hello(self, model_id: str, base_url: str, api_key: str) -> dict:
        """向模型发一条 hello，仅供用户参考连通性。"""
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=20)
        started = time.perf_counter()
        try:
            resp = await client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=32,
                stream=False,
            )
            text = ""
            if resp.choices:
                text = (resp.choices[0].message.content or "").strip()
            latency = int((time.perf_counter() - started) * 1000)
            preview = text[:200]
            return {"ok": True, "latency_ms": latency, "preview": preview}
        except RateLimitError as e:
            return {"ok": False, "error": f"速率限制: {e}"}
        except (APITimeoutError, httpx.TimeoutException):
            return {"ok": False, "error": "请求超时，请检查网络或基础 URL"}
        except APIError as e:
            status = e.status_code
            if status == 401:
                return {"ok": False, "error": "认证失败，请检查 API 密钥"}
            if status == 403:
                return {"ok": False, "error": "权限不足"}
            if status == 404:
                return {"ok": False, "error": "接口或模型不存在，请检查基础 URL 与 model-id"}
            return {"ok": False, "error": f"API 错误 ({status}): {e}"}
        except httpx.NetworkError as e:
            return {"ok": False, "error": f"网络连接失败: {e}"}
        except Exception as e:
            logger.warning(f"模型测试失败: {e}", exc_info=True)
            return {"ok": False, "error": str(e) or "测试失败"}
        finally:
            try:
                await client.close()
            except Exception:
                pass
