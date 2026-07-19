"""
Chat route — SSE streaming for conversation.

Changes (2025-09):
  - JSON-only input (file upload removed)
  - append_messages 替代全量 save_slot_history，消除并发写冲突
  - SSE done 事件返回 user_message_id / assistant_message_id
  - 流式渲染增量写入 textContent（修复 O(n²)）
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from config import (
    MODEL_CONFIG,
    CONTEXT_WINDOW_SIZE,
)
from helpers import resolve_slot
from models import ChatRequest
from state import get_ai_client, get_slot_mgr

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/api/chat")
async def chat(req: ChatRequest):
    """SSE streaming chat — 接收 JSON，返回流式响应。"""
    data = resolve_slot(req.slot_index)

    history: list = data.get("history", [])
    system_prompt: str = data.get("system_prompt", "使用中文回答")
    model: str = data.get("model", "DeepSeek-v4-flash")
    api_key: str = data.get("api_key", "")
    params: dict = data.get("params", {}) or {}
    cfg = MODEL_CONFIG.get(model)

    user_content = req.message or "(空消息)"

    # 在内存中追加用户消息（后续用于构建 AI 上下文）
    history.append({"role": "user", "content": user_content})

    # 构建 AI 上下文（截断至上下文窗口大小）
    context_history = (
        history[-CONTEXT_WINDOW_SIZE:]
        if len(history) > CONTEXT_WINDOW_SIZE
        else history
    )
    messages = [{"role": "system", "content": system_prompt}, *context_history]

    # 预检查：模型配置是否存在
    max_tokens = cfg.get("max_tokens") if cfg else None
    if not cfg:
        logger.error(f"对话请求使用了不存在的模型配置: {model}")

    async def stream():
        chunks = []
        try:
            async for chunk in get_ai_client().stream_chat(
                messages, model, api_key=api_key,
                max_tokens=max_tokens,
                params=params,
            ):
                chunks.append(chunk)
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            full_response = "".join(chunks)

            # append-only 写入（原子操作，非全量替换）
            msg_ids = get_slot_mgr().append_messages(req.slot_index, [
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": full_response},
            ])

            # 更新内存中的历史（保持与后端同步）
            history.append({"role": "assistant", "content": full_response})

            # 自动标题（复用开头已加载的 data，无需再查库）
            if not data.get("title", ""):
                get_slot_mgr().update_slot_meta(
                    req.slot_index, {"title": f"存档{req.slot_index + 1}"}
                )

            done_event = {
                'type': 'done',
                'user_message_id': msg_ids[0] if msg_ids and len(msg_ids) > 0 else None,
                'assistant_message_id': msg_ids[1] if msg_ids and len(msg_ids) > 1 else None,
            }
            yield f"data: {json.dumps(done_event)}\n\n"

        except ConnectionError as e:
            logger.error(f"Ollama connection error: {e}")
            err = str(e)
            if err.startswith("NEED_KEY:"):
                code = "ollama_need_key"
                content = err[len("NEED_KEY:"):].strip()
            else:
                code = "ollama_unreachable"
                content = err
            yield f"data: {json.dumps({'type': 'error', 'code': code, 'content': content})}\n\n"

        except ValueError as e:
            logger.error(f"Config error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'code': 'config_error', 'content': str(e)})}\n\n"

        except Exception as e:
            logger.error(f"Chat error: {e}")
            err_str = str(e)
            if "401" in err_str or "unauthorized" in err_str.lower() or "invalid_api_key" in err_str.lower():
                yield f"data: {json.dumps({'type': 'error', 'code': 'auth_failed', 'content': 'API 认证失败，请检查 API Key 是否正确'})}\n\n"
            elif "429" in err_str or "rate_limit" in err_str.lower() or "too_many_requests" in err_str.lower():
                yield f"data: {json.dumps({'type': 'error', 'code': 'rate_limited', 'content': '请求过于频繁，请稍后重试'})}\n\n"
            elif "insufficient_quota" in err_str.lower() or "exceeded" in err_str.lower():
                yield f"data: {json.dumps({'type': 'error', 'code': 'quota_exceeded', 'content': 'API 额度不足，请检查账户余额'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'code': 'unknown', 'content': f'请求失败: {err_str}'})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
