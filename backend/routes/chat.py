"""
Chat route — SSE streaming for conversation.

支持单模型和双模型（多角色）对话模式。
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from config import MODEL_CONFIG, CONTEXT_WINDOW_SIZE
from helpers import resolve_slot
from models import ChatRequest
from state import get_ai_client, get_slot_mgr

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# ── 固定图标 ──
MODEL1_ICON = "🎭"
MODEL2_ICON = "🌟"


def _clean(items: list) -> list:
    """只保留 role/content 字段，避免把数据库字段泄漏给模型。"""
    return [
        {"role": m.get("role"), "content": m.get("content")}
        for m in items
    ]


def _auto_title(slot_index: int, system_prompt: str) -> str:
    """从系统提示词自动生成存档标题，空提示词时退化为 存档N。"""
    prompt_line = (system_prompt or "").strip().replace("\n", " ").strip()
    if prompt_line:
        return prompt_line[:20]
    return f"存档{slot_index + 1}"


@router.post("/api/chat")
async def chat(req: ChatRequest):
    """SSE streaming chat — 接收 JSON，返回流式响应。"""
    data = resolve_slot(req.slot_index)

    history: list = data.get("history", [])
    system_prompt: str = data.get("system_prompt", "使用中文回答")
    model: str = data.get("model", "DeepSeek-v4-flash")
    api_key: str = data.get("api_key", "")
    params: dict = data.get("params", {}) or {}
    dual_config: dict = data.get("dual_config", {}) or {}
    user_content = req.message or "(空消息)"

    # ── 是否双模型 ──
    dual_enabled = dual_config.get("enabled", False)
    response_mode = dual_config.get("response_mode", "both")  # model1 | model2 | both
    first_model = dual_config.get("first_model", "model1")    # 谁先回复

    # 判断实际要跑哪些模型
    run_model1 = dual_enabled and response_mode in ("model1", "both")
    run_model2 = dual_enabled and response_mode in ("model2", "both")

    # 双模型时的名字包装
    model1_name = dual_config.get("model1_name", "")
    model2_name = dual_config.get("model2_name", "")

    # 在内存中追加用户消息
    history.append({"role": "user", "content": user_content})

    async def stream():
        completed = False
        rollback_start_id = None

        try:
            user_msg_id = None
            msg_ids = []

            # ── 单模型模式（原有逻辑） ──
            if not dual_enabled or (not run_model1 and not run_model2):
                # 退化为单模型（未开启双模型，或双模型无有效回复模式）
                actual_model = model
                actual_prompt = system_prompt
                actual_key = api_key
                actual_params = params

                cfg = MODEL_CONFIG.get(actual_model)
                max_tokens = cfg.get("max_tokens") if cfg else None

                context_history = (
                    history[-CONTEXT_WINDOW_SIZE:]
                    if len(history) > CONTEXT_WINDOW_SIZE
                    else history
                )
                messages = [{"role": "system", "content": actual_prompt}, *_clean(context_history)]

                chunks = []
                # 先保存用户消息，拿到 ID
                saved_ids = get_slot_mgr().append_messages(req.slot_index, [
                    {"role": "user", "content": user_content},
                ])
                user_msg_id = saved_ids[0] if saved_ids else None
                if rollback_start_id is None and saved_ids:
                    rollback_start_id = saved_ids[0]

                async for chunk in get_ai_client().stream_chat(
                    messages, actual_model, api_key=actual_key,
                    max_tokens=max_tokens, params=actual_params,
                ):
                    chunks.append(chunk)
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

                full_response = "".join(chunks)
                msg_ids = get_slot_mgr().append_messages(req.slot_index, [
                    {"role": "assistant", "content": full_response, "source": "single"},
                ])
                history.append({"role": "assistant", "content": full_response})

                if not data.get("title", ""):
                    get_slot_mgr().update_slot_meta(
                        req.slot_index, {"title": _auto_title(req.slot_index, actual_prompt)}
                    )

                done_event = {
                    'type': 'done',
                    'user_message_id': user_msg_id,
                    'assistant_message_id': msg_ids[0] if msg_ids else None,
                }
                yield f"data: {json.dumps(done_event)}\n\n"
                completed = True
                return

            # ── 双模型模式 ──

            # 先保存用户消息
            saved_ids = get_slot_mgr().append_messages(req.slot_index, [
                {"role": "user", "content": user_content},
            ])
            user_msg_id = saved_ids[0] if saved_ids else None
            if rollback_start_id is None and saved_ids:
                rollback_start_id = saved_ids[0]

            # 决定模型顺序
            model_order = ["model1", "model2"]
            if first_model == "model2":
                model_order = ["model2", "model1"]

            first_resp = None    # 第一个模型的回复内容
            first_role = None    # 第一个模型的角色名

            for role in model_order:
                if role == "model1" and not run_model1:
                    continue
                if role == "model2" and not run_model2:
                    continue

                is_current_first = (first_resp is None)  # 第一个跑的模型

                # 按角色选择配置
                if role == "model1":
                    cfg_key = model
                    cfg_system = system_prompt
                    cfg_key_raw = api_key
                    cfg_params = params
                    role_name = model1_name
                    role_icon = MODEL1_ICON
                else:
                    m2 = dual_config.get("model2") or {}
                    cfg_key = m2.get("model", model)
                    cfg_system = m2.get("system_prompt", system_prompt)
                    cfg_key_raw = m2.get("api_key", api_key)
                    cfg_params = m2.get("params", params)
                    role_name = model2_name
                    role_icon = MODEL2_ICON

                cfg = MODEL_CONFIG.get(cfg_key)
                max_tokens = cfg.get("max_tokens") if cfg else None

                # ── 构建消息上下文 ──
                if is_current_first:
                    # 第一个模型：正常历史（含本轮用户消息）
                    ctx = history[-CONTEXT_WINDOW_SIZE:] if len(history) > CONTEXT_WINDOW_SIZE else history
                    messages = [{"role": "system", "content": cfg_system}, *_clean(ctx)]
                else:
                    # 第二个模型：
                    #   history 目前 = [...历史..., {user: 本轮}, {assistant: 第一模型回复}]
                    #   排除最后两条，取之前的历史
                    ctx = history[-(CONTEXT_WINDOW_SIZE + 2):] if len(history) > CONTEXT_WINDOW_SIZE + 2 else history
                    prev = ctx[:-2] if len(ctx) >= 2 else []
                    messages = [{"role": "system", "content": cfg_system}, *_clean(prev)]
                    # 用户原始消息（独立一条）
                    messages.append({"role": "user", "content": user_content})
                    # 第一个模型的回答传入
                    first_name = model2_name if first_role == "model2" else model1_name
                    pass_mode = dual_config.get("pass_mode", "user")  # "user" | "assistant"
                    if pass_mode == "assistant":
                        messages.append({"role": "assistant", "content": f"{first_name}: {first_resp}"})
                    else:
                        # 合并进上一条 user 消息，避免连续两条 user 消息
                        messages[-1]["content"] = f"{user_content}\n\n[{first_name} 的回复]\n{first_resp}"

                # 发出 model_start 事件
                yield f"data: {json.dumps({
                    'type': 'model_start',
                    'role': role,
                    'name': role_name,
                    'icon': role_icon,
                })}\n\n"

                chunks = []
                try:
                    async for chunk in get_ai_client().stream_chat(
                        messages, cfg_key, api_key=cfg_key_raw,
                        max_tokens=max_tokens, params=cfg_params,
                    ):
                        chunks.append(chunk)
                        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk, 'role': role})}\n\n"
                except Exception as e:
                    # 后续模型失败：保留已保存的用户消息与第一个模型回复；
                    # 但 NEED_KEY 需整体回滚，避免补 Key 重试时消息重复。
                    if (
                        not str(e).startswith("NEED_KEY:")
                        and not is_current_first
                        and rollback_start_id is not None
                    ):
                        rollback_start_id = None
                    raise

                full_response = "".join(chunks)

                # 保存到数据库
                saved = get_slot_mgr().append_messages(req.slot_index, [
                    {"role": "assistant", "content": full_response, "source": role},
                ])
                msg_ids.extend(saved)
                history.append({"role": "assistant", "content": full_response})

                # 记住第一个模型的回答，供第二个模型拼入上下文
                if is_current_first:
                    first_resp = full_response
                    first_role = role

                # 发出 model_done 事件
                yield f"data: {json.dumps({
                    'type': 'model_done',
                    'role': role,
                    'name': role_name,
                    'icon': role_icon,
                    'message_id': saved[0] if saved else None,
                })}\n\n"

            # 自动标题
            if not data.get("title", ""):
                get_slot_mgr().update_slot_meta(
                    req.slot_index, {"title": _auto_title(req.slot_index, system_prompt)}
                )

            # 最终 done 事件
            yield f"data: {json.dumps({
                'type': 'done',
                'user_message_id': user_msg_id,
                'message_ids': msg_ids,
                'dual': True,
            })}\n\n"
            completed = True

        except GeneratorExit:
            raise

        except ConnectionError as e:
            logger.error(f"Ollama connection error: {e}")
            err = str(e)
            if err.startswith("NEED_KEY:"):
                code = "ollama_need_key"
                content = err[len("NEED_KEY:"):].strip()
            else:
                code = "ollama_unreachable"
                content = err
            yield f"data: {json.dumps({
                'type': 'error',
                'code': code,
                'content': content,
                'user_message_id': user_msg_id,
            })}\n\n"

        except ValueError as e:
            logger.error(f"Config error: {e}")
            yield f"data: {json.dumps({
                'type': 'error',
                'code': 'config_error',
                'content': str(e),
                'user_message_id': user_msg_id,
            })}\n\n"

        except Exception as e:
            logger.error(f"Chat error: {e}")
            err_str = str(e)
            if "401" in err_str or "unauthorized" in err_str.lower() or "invalid_api_key" in err_str.lower():
                yield f"data: {json.dumps({'type': 'error', 'code': 'auth_failed', 'content': 'API 认证失败，请检查 API Key 是否正确', 'user_message_id': user_msg_id})}\n\n"
            elif "429" in err_str or "rate_limit" in err_str.lower() or "too_many_requests" in err_str.lower():
                yield f"data: {json.dumps({'type': 'error', 'code': 'rate_limited', 'content': '请求过于频繁，请稍后重试', 'user_message_id': user_msg_id})}\n\n"
            elif "insufficient_quota" in err_str.lower() or "exceeded" in err_str.lower():
                yield f"data: {json.dumps({'type': 'error', 'code': 'quota_exceeded', 'content': 'API 额度不足，请检查账户余额', 'user_message_id': user_msg_id})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'code': 'unknown', 'content': f'请求失败: {err_str}', 'user_message_id': user_msg_id})}\n\n"

        finally:
            if not completed and rollback_start_id is not None:
                try:
                    get_slot_mgr().delete_messages_from(req.slot_index, rollback_start_id)
                    logger.info(
                        f"流中断，已回滚存档 #{req.slot_index + 1} 的消息（起点 #{rollback_start_id}）"
                    )
                except Exception as e:
                    logger.warning(f"回滚失败: {e}")

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
