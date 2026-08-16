"""
对话路由 — 基于 SSE 流式的对话接口。

支持单模型与双模型（多角色）两种对话模式。
"""
from __future__ import annotations

import json
import logging
import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from config import MODEL_CONFIG, CONTEXT_WINDOW_SIZE
from helpers import resolve_slot, error
from models import ChatRequest
from state import get_ai_client, get_slot_mgr

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])
_slot_locks: dict[int, asyncio.Lock] = {}


def _slot_lock(slot_index: int) -> asyncio.Lock:
    if slot_index not in _slot_locks:
        _slot_locks[slot_index] = asyncio.Lock()
    return _slot_locks[slot_index]


async def _db_call(method, *args):
    return await asyncio.to_thread(method, *args)


async def _locked_stream(slot_index: int, source):
    async with _slot_lock(slot_index):
        lock_conn = None
        try:
            lock_conn = await _db_call(get_slot_mgr().acquire_slot_lock, slot_index)
            if lock_conn is None:
                yield _sse({
                    "type": "error",
                    "code": "slot_busy",
                    "content": "该存档正在生成回复，请稍后重试",
                })
                return
            async for event in source:
                yield event
        finally:
            if lock_conn is not None:
                await _db_call(get_slot_mgr().release_slot_lock, lock_conn, slot_index)

# ── 固定图标 ──
MODEL1_ICON = "🎭"
MODEL2_ICON = "🌟"

# 继续回复时附加给模型的引导词（仅本次请求使用，不入库）
CONTINUE_PROMPT = "请继续你刚才的回复，接着上一条的内容往下说，不要重复已说过的内容。"

# 双模型「继续」时模拟用户留空，让两个角色正常继续对话的引导词
DUAL_CONTINUE_PROMPT = "（用户没有发送新消息，请两位角色自然地继续刚才的对话，推进当前话题。）"


def _sse(data: dict) -> str:
    """构造 SSE 数据帧；ensure_ascii=False 避免中文被转义，减小传输体积。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _exception_error_event(e: Exception, ref_key: str, ref_value) -> dict:
    """把异常映射为统一的 SSE error 事件（供 /api/chat 与 continue 复用）。"""
    error_code = getattr(e, "error_code", None)
    if error_code:
        return {
            "type": "error",
            "code": error_code,
            "content": str(e),
            ref_key: ref_value,
        }
    if isinstance(e, ConnectionError):
        err = str(e)
        return {"type": "error", "code": "network_error", "content": err, ref_key: ref_value}
    if isinstance(e, ValueError):
        return {'type': 'error', 'code': 'config_error', 'content': str(e), ref_key: ref_value}
    if isinstance(e, RuntimeError) and str(e).startswith("数据库"):
        return {'type': 'error', 'code': 'database_error', 'content': '存档写入失败，请稍后重试', ref_key: ref_value}
    err_str = str(e)
    low = err_str.lower()
    if "401" in err_str or "unauthorized" in low or "invalid_api_key" in low:
        return {'type': 'error', 'code': 'auth_failed',
                'content': 'API 认证失败，请检查 API Key 是否正确', ref_key: ref_value}
    if "429" in err_str or "rate_limit" in low or "too_many_requests" in low:
        return {'type': 'error', 'code': 'rate_limited',
                'content': '请求过于频繁，请稍后重试', ref_key: ref_value}
    if "insufficient_quota" in low or "exceeded" in low:
        return {'type': 'error', 'code': 'quota_exceeded',
                'content': 'API 额度不足，请检查账户余额', ref_key: ref_value}
    return {'type': 'error', 'code': 'unknown',
            'content': f'请求失败: {err_str}', ref_key: ref_value}


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


async def _stream_dual_turn(
    slot_index: int,
    data: dict,
    history: list,
    user_content: str,
    persist_user: bool = True,
    error_ref_key: str = "user_message_id",
) -> AsyncGenerator[str, None]:
    """双模型（或按 response_mode 单侧）回复一轮，产出 SSE 事件。

    persist_user=True：先把用户消息落库（普通发消息），回滚起点 = 用户消息 ID；
    persist_user=False：用户消息只进入内存上下文（继续回复），不落库，
    回滚起点 = 本轮第一条已保存的 assistant 消息。
    """
    dual_config = data.get("dual_config", {}) or {}
    model = data.get("model", "deepseek:deepseek-v4-flash")
    system_prompt = data.get("system_prompt", "使用中文回答")
    api_key = data.get("api_key", "")
    params = data.get("params", {}) or {}
    response_mode = dual_config.get("response_mode", "both")
    first_model = dual_config.get("first_model", "model1")
    model1_name = dual_config.get("model1_name", "")
    model2_name = dual_config.get("model2_name", "")

    run_model1 = response_mode in ("model1", "both")
    run_model2 = response_mode in ("model2", "both")

    user_msg_id = None
    msg_ids = []
    rollback_start_id = None
    completed = False
    failed_role = "model1"

    try:
        # 用户消息：仅普通发消息时落库并作为回滚起点
        if persist_user:
            saved_ids = await _db_call(get_slot_mgr().append_messages, slot_index, [
                {"role": "user", "content": user_content},
            ])
            if not saved_ids:
                raise RuntimeError("数据库写入用户消息失败")
            user_msg_id = saved_ids[0] if saved_ids else None
            if saved_ids:
                rollback_start_id = saved_ids[0]

        # 用户消息加入内存上下文（继续回复时不落库，仅本次生成可见）
        history.append({"role": "user", "content": user_content})

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
            failed_role = role

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
            yield _sse({
                'type': 'model_start',
                'role': role,
                'name': role_name,
                'icon': role_icon,
            })

            chunks = []
            try:
                async for chunk in get_ai_client().stream_chat(
                    messages, cfg_key, api_key=cfg_key_raw,
                    max_tokens=max_tokens, params=cfg_params,
                ):
                    chunks.append(chunk)
                    yield _sse({'type': 'chunk', 'content': chunk, 'role': role})
            except Exception as e:
                # 模型2调用失败时保留已完成的模型1回复。
                if (
                    not is_current_first
                    and rollback_start_id is not None
                ):
                    rollback_start_id = None
                raise

            full_response = "".join(chunks)

            # 保存到数据库
            saved = await _db_call(get_slot_mgr().append_messages, slot_index, [
                {"role": "assistant", "content": full_response, "source": role},
            ])
            if not saved:
                raise RuntimeError("数据库写入模型回复失败")
            msg_ids.extend(saved)
            # 继续回复模式：回滚起点设为本轮第一条 assistant 消息
            if rollback_start_id is None and saved:
                rollback_start_id = saved[0]

            history.append({"role": "assistant", "content": full_response})

            # 记住第一个模型的回答，供第二个模型拼入上下文
            if is_current_first:
                first_resp = full_response
                first_role = role

            # 发出 model_done 事件
            yield _sse({
                'type': 'model_done',
                'role': role,
                'name': role_name,
                'icon': role_icon,
                'message_id': saved[0] if saved else None,
            })

        # 自动标题
        if not data.get("title", ""):
            if not await _db_call(
                get_slot_mgr().update_slot_meta,
                slot_index, {"title": _auto_title(slot_index, system_prompt)}
            ):
                logger.warning(f"自动更新存档 #{slot_index + 1} 标题失败")

        # 最终 done 事件
        completed = True
        yield _sse({
            'type': 'done',
            'user_message_id': user_msg_id,
            'message_ids': msg_ids,
            'dual': True,
            'continue_turn': not persist_user,
        })

    except GeneratorExit:
        raise

    except Exception as e:
        ref_value = (
            user_msg_id
            if error_ref_key == "user_message_id"
            else (msg_ids[-1] if msg_ids else None)
        )
        event = _exception_error_event(e, error_ref_key, ref_value)
        event["key_target"] = failed_role
        yield _sse(event)

    finally:
        if not completed and rollback_start_id is not None:
            try:
                await _db_call(
                    get_slot_mgr().delete_messages_from,
                    slot_index,
                    rollback_start_id,
                )
                logger.info(
                    f"流中断，已回滚存档 #{slot_index + 1} 的消息（起点 #{rollback_start_id}）"
                )
            except Exception as e:
                logger.warning(f"回滚失败: {e}")


@router.post("/api/chat")
async def chat(req: ChatRequest):
    """流式对话 — 接收 JSON，返回 SSE 流式响应。"""
    data = await _db_call(resolve_slot, req.slot_index)

    history: list = data.get("history", [])
    system_prompt: str = data.get("system_prompt", "使用中文回答")
    model: str = data.get("model", "deepseek:deepseek-v4-flash")
    api_key: str = data.get("api_key", "")
    params: dict = data.get("params", {}) or {}
    dual_config: dict = data.get("dual_config", {}) or {}
    user_content = req.message or "(空消息)"

    # ── 是否双模型 ──
    dual_enabled = dual_config.get("enabled", False)
    response_mode = dual_config.get("response_mode", "both")  # model1 | model2 | both
    first_model = dual_config.get("first_model", "model1")    # 谁先回复

    # 校验双模型配置，避免非法值静默退化为单模型
    if dual_enabled and response_mode not in ("model1", "model2", "both"):
        error("invalid_response_mode", "回复模式无效", 400)
    if dual_enabled and first_model not in ("model1", "model2"):
        error("invalid_first_model", "先回复模型无效", 400)

    # 判断实际要跑哪些模型
    run_model1 = dual_enabled and response_mode in ("model1", "both")
    run_model2 = dual_enabled and response_mode in ("model2", "both")

    # 双模型时的名字包装
    model1_name = dual_config.get("model1_name", "")
    model2_name = dual_config.get("model2_name", "")

    async def stream():
        completed = False
        rollback_start_id = None

        try:
            user_msg_id = None
            msg_ids = []

            # ── 单模型模式 ──
            if not dual_enabled or (not run_model1 and not run_model2):
                # 退化为单模型（未开启双模型，或双模型无有效回复模式）
                # 在内存中追加用户消息（单模型路径）
                history.append({"role": "user", "content": user_content})
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
                saved_ids = await _db_call(get_slot_mgr().append_messages, req.slot_index, [
                    {"role": "user", "content": user_content},
                ])
                if not saved_ids:
                    raise RuntimeError("数据库写入用户消息失败")
                user_msg_id = saved_ids[0] if saved_ids else None
                if rollback_start_id is None and saved_ids:
                    rollback_start_id = saved_ids[0]

                async for chunk in get_ai_client().stream_chat(
                    messages, actual_model, api_key=actual_key,
                    max_tokens=max_tokens, params=actual_params,
                ):
                    chunks.append(chunk)
                    yield _sse({'type': 'chunk', 'content': chunk})

                full_response = "".join(chunks)
                msg_ids = await _db_call(get_slot_mgr().append_messages, req.slot_index, [
                    {"role": "assistant", "content": full_response, "source": "single"},
                ])
                if not msg_ids:
                    raise RuntimeError("数据库写入模型回复失败")
                history.append({"role": "assistant", "content": full_response})

                if not data.get("title", ""):
                    if not await _db_call(
                        get_slot_mgr().update_slot_meta,
                        req.slot_index, {"title": _auto_title(req.slot_index, actual_prompt)}
                    ):
                        logger.warning(f"自动更新存档 #{req.slot_index + 1} 标题失败")

                done_event = {
                    'type': 'done',
                    'user_message_id': user_msg_id,
                    'assistant_message_id': msg_ids[0] if msg_ids else None,
                }
                yield _sse(done_event)
                completed = True
                return

            # ── 双模型模式（共享助手：自行落库、发事件、处理错误与回滚） ──
            gen = _stream_dual_turn(
                req.slot_index, data, history, user_content,
                persist_user=True, error_ref_key="user_message_id",
            )
            try:
                async for event in gen:
                    yield event
            finally:
                await gen.aclose()
            completed = True

        except GeneratorExit:
            raise

        except ConnectionError as e:
            logger.error(f"AI 服务连接错误: {e}")
            yield _sse(_exception_error_event(e, "user_message_id", user_msg_id))

        except ValueError as e:
            logger.error(f"Config error: {e}")
            yield _sse(_exception_error_event(e, "user_message_id", user_msg_id))

        except Exception as e:
            logger.error(f"Chat error: {e}")
            yield _sse(_exception_error_event(e, "user_message_id", user_msg_id))

        finally:
            if not completed and rollback_start_id is not None:
                try:
                    await _db_call(
                        get_slot_mgr().delete_messages_from,
                        req.slot_index,
                        rollback_start_id,
                    )
                    logger.info(
                        f"流中断，已回滚存档 #{req.slot_index + 1} 的消息（起点 #{rollback_start_id}）"
                    )
                except Exception as e:
                    logger.warning(f"回滚失败: {e}")

    return StreamingResponse(
        _locked_stream(req.slot_index, stream()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/slots/{slot_index}/chat/continue")
async def continue_chat(slot_index: int):
    """继续回复。

    单模型：不新增用户消息，让最后一条 AI 回复继续生成（合并回原消息）。
    双模型：相当于用户留空，两个模型按 response_mode / first_model / pass_mode
    正常回复一轮（各新增一条回复，不落库用户消息）。
    """
    data = await _db_call(resolve_slot, slot_index)
    history: list = data.get("history", [])
    dual_config = data.get("dual_config", {}) or {}

    if dual_config.get("enabled", False):
        if dual_config.get("response_mode", "both") not in ("model1", "model2", "both"):
            error("invalid_response_mode", "回复模式无效", 400)
        if dual_config.get("first_model", "model1") not in ("model1", "model2"):
            error("invalid_first_model", "先回复模型无效", 400)

    # ── 双模型：跳过用户消息，两个模型正常回复一轮 ──
    if dual_config.get("enabled", False):
        async def stream():
            gen = _stream_dual_turn(
                slot_index, data, history, DUAL_CONTINUE_PROMPT,
                persist_user=False, error_ref_key="message_id",
            )
            try:
                async for event in gen:
                    yield event
            finally:
                await gen.aclose()

        return StreamingResponse(
            _locked_stream(slot_index, stream()),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── 单模型：延续最后一条回复（合并式） ──
    last_msg = None
    for m in reversed(history):
        if m.get("role") == "assistant":
            last_msg = m
            break
    if last_msg is None:
        error("nothing_to_continue", "暂无可继续的回复", 400)

    message_id = last_msg.get("id")
    original_content = last_msg.get("content") or ""

    cfg_key = data.get("model", "") or ""
    cfg_system = data.get("system_prompt") or "使用中文回答"
    cfg_key_raw = data.get("api_key") or ""
    cfg_params = data.get("params") or {}

    cfg = MODEL_CONFIG.get(cfg_key)
    max_tokens = cfg.get("max_tokens") if cfg else None

    # 上下文：历史（截断到窗口，含最后一条 assistant）+ 继续指令（仅本次请求，不入库）
    context_history = (
        history[-CONTEXT_WINDOW_SIZE:]
        if len(history) > CONTEXT_WINDOW_SIZE
        else history
    )
    messages = [{"role": "system", "content": cfg_system}, *_clean(context_history)]
    messages.append({"role": "user", "content": CONTINUE_PROMPT})

    async def stream():
        # 生成完成前不落库，取消/失败无需回滚；仅在完成后合并内容
        try:
            yield _sse({
                'type': 'continue_start',
                'role': 'single',
                'name': '',
                'icon': '🤖',
                'message_id': message_id,
            })

            chunks = []
            async for chunk in get_ai_client().stream_chat(
                messages, cfg_key, api_key=cfg_key_raw,
                max_tokens=max_tokens, params=cfg_params,
            ):
                chunks.append(chunk)
                yield _sse({'type': 'chunk', 'content': chunk, 'role': 'single'})

            full_response = "".join(chunks)
            # 生成完成后合并回最后一条 assistant 消息
            if full_response and message_id:
                updated = await _db_call(
                    get_slot_mgr().update_message_content,
                    slot_index, message_id, original_content + full_response
                )
                if not updated:
                    raise RuntimeError("数据库更新模型回复失败")
                if not await _db_call(get_slot_mgr().touch_slot, slot_index):
                    logger.warning(f"刷新存档 #{slot_index + 1} 时间失败")

            yield _sse({
                'type': 'done',
                'message_id': message_id,
                'role': 'single',
                'continue': True,
            })

        except GeneratorExit:
            raise

        except Exception as e:
            logger.error(f"Continue error: {e}")
            yield _sse(_exception_error_event(e, "message_id", message_id))

    return StreamingResponse(
        _locked_stream(slot_index, stream()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
