"""
Slots route — CRUD for conversation slots.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from config import SLOT_COUNT
from models import (
    CreateSlotRequest,
    DeleteMessageRequest,
    EditMessageRequest,
    SlotDetail,
    ExportData,
)
from helpers import error, resolve_slot, check_api_key, validate_model_key
from state import get_slot_mgr

logger = logging.getLogger(__name__)

router = APIRouter(tags=["slots"])


@router.get("/api/slots")
def list_slots():
    return get_slot_mgr().list_slots()


@router.post("/api/slots/{slot_index}")
def create_slot(slot_index: int, req: CreateSlotRequest):
    if slot_index < 0 or slot_index >= SLOT_COUNT:
        error("invalid_slot", f"无效的存档位: {slot_index}", 400)

    if get_slot_mgr().get_slot(slot_index) is not None:
        error("slot_in_use", f"存档位 #{slot_index + 1} 已被使用", 409)

    cfg = validate_model_key(req.model)
    check_api_key(cfg["provider"], req.api_key)

    success = get_slot_mgr().create_slot(
        slot_index, req.model, req.system_prompt, req.api_key, req.params, req.title
    )
    if not success:
        error("create_failed", "创建存档失败", 500)
    return {"ok": True}


@router.delete("/api/slots/{slot_index}")
def delete_slot(slot_index: int):
    if not get_slot_mgr().delete_slot(slot_index):
        error("slot_not_found", "存档不存在", 404)
    return {"ok": True}


@router.get("/api/slots/{slot_index}/chat")
def get_slot_chat(slot_index: int):
    data = resolve_slot(slot_index)
    return SlotDetail(
        index=slot_index,
        model=data.get("model", ""),
        system_prompt=data.get("system_prompt", ""),
        title=data.get("title", ""),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        history=data.get("history", []),
    ).model_dump()


@router.post("/api/slots/{slot_index}/chat/clear")
def clear_slot_chat(slot_index: int):
    resolve_slot(slot_index)  # ensure exists
    mgr = get_slot_mgr()
    mgr.clear_all_messages(slot_index)
    return {"ok": True}


@router.delete("/api/slots/{slot_index}/chat/messages")
def delete_messages(slot_index: int, req: DeleteMessageRequest):
    """删除消息。

    优先使用 from_id（按消息 ID 删除），
    回退到 from_index / to_index（按数组下标，旧版兼容）。
    """
    mgr = get_slot_mgr()

    if req.from_id is not None:
        if req.from_id <= 0:
            error("invalid_message_id", "消息 ID 无效", 400)
        success = mgr.delete_messages_from(slot_index, req.from_id)
        if not success:
            error("delete_failed", "删除消息失败", 500)
        return {"ok": True}

    # Legacy: 按数组下标删除
    data = resolve_slot(slot_index)
    history: list = data.get("history", [])
    total = len(history)

    if req.from_index is None or req.to_index is None:
        error("invalid_range", "请提供 from_id 或 from_index/to_index", 400)
    if req.from_index < 0 or req.to_index >= total or req.from_index > req.to_index:
        error(
            "invalid_range",
            f"消息索引无效: [{req.from_index}, {req.to_index}]，历史共 {total} 条",
            400,
        )

    new_history = history[: req.from_index] + history[req.to_index + 1 :]
    mgr.save_slot_history(slot_index, new_history)
    return {"ok": True, "deleted": req.to_index - req.from_index + 1}


@router.patch("/api/slots/{slot_index}/chat/messages")
def edit_message(slot_index: int, req: EditMessageRequest):
    """编辑消息。优先使用 message_id 定位。"""
    mgr = get_slot_mgr()

    if not req.content:
        error("empty_content", "消息内容不能为空", 400)

    if req.message_id is not None:
        if req.message_id <= 0:
            error("invalid_message_id", "消息 ID 无效", 400)
        success = mgr.update_message_content(req.message_id, req.content)
        if not success:
            error("message_not_found", f"消息 #{req.message_id} 不存在", 404)
        return {"ok": True}

    # Legacy: 按下标编辑
    data = resolve_slot(slot_index)
    history: list = data.get("history", [])
    if req.index is None or req.index < 0 or req.index >= len(history):
        error("invalid_index", f"消息索引 {req.index} 无效", 400)
    history[req.index]["content"] = req.content
    mgr.save_slot_history(slot_index, history)
    return {"ok": True}


@router.patch("/api/slots/{slot_index}/title")
def update_slot_title(slot_index: int, req: dict):
    """更新存档标题。"""
    resolve_slot(slot_index)
    title = (req.get("title") or "").strip()
    if not title:
        error("empty_title", "标题不能为空", 400)
    get_slot_mgr().update_slot_meta(slot_index, {"title": title})
    return {"ok": True}


@router.patch("/api/slots/{slot_index}/api-key")
def update_slot_api_key(slot_index: int, req: dict):
    """更新存档的 API Key（用于 Ollama 连接失败后补填）。"""
    resolve_slot(slot_index)
    api_key = (req.get("api_key") or "").strip()
    if not api_key:
        error("empty_api_key", "API Key 不能为空", 400)
    get_slot_mgr().update_slot_meta(slot_index, {"api_key": api_key})
    return {"ok": True}


@router.get("/api/slots/{slot_index}/chat/export")
def export_chat(slot_index: int):
    data = resolve_slot(slot_index)
    return ExportData(
        title=data.get("title", "未命名对话"),
        model=data.get("model", ""),
        system_prompt=data.get("system_prompt", ""),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        messages=data.get("history", []),
    ).model_dump()
