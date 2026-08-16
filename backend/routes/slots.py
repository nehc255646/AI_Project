"""
存档路由 — 对话存档的增删改查接口。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from config import SLOT_COUNT, MODEL_CONFIG
from models import (
    CreateSlotRequest,
    DeleteMessageRequest,
    EditMessageRequest,
    DualToggleRequest,
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

    # 构建 dual_config
    dual_config = None
    if req.dual_enabled:
        m2 = req.model2
        if m2:
            m2_cfg = validate_model_key(m2.model)
            check_api_key(m2_cfg["provider"], m2.api_key)
        dual_config = {
            "enabled": True,
            "response_mode": "both",
            "first_model": "model1",
            "pass_mode": req.pass_mode or "user",
            "model1_name": req.model1_name or "",
            "model2_name": req.model2_name or "",
            "model2": {
                "model": m2.model if m2 else req.model,
                "system_prompt": m2.system_prompt if m2 else "使用中文回答",
                "api_key": m2.api_key if m2 else "",
                "params": m2.params if m2 and m2.params else {},
            } if m2 else None,
        }

    success = get_slot_mgr().create_slot(
        slot_index, req.model, req.system_prompt, req.api_key, req.params, req.title,
        dual_config=dual_config,
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
    dual_config = data.get("dual_config", {}) or {}
    return SlotDetail(
        index=slot_index,
        model=data.get("model", ""),
        system_prompt=data.get("system_prompt", ""),
        title=data.get("title", ""),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        history=data.get("history", []),
        dual_enabled=dual_config.get("enabled", False),
        dual_config=dual_config,
        response_mode=dual_config.get("response_mode", "both"),
        first_model=dual_config.get("first_model", "model1"),
    ).model_dump()


@router.post("/api/slots/{slot_index}/chat/clear")
def clear_slot_chat(slot_index: int):
    resolve_slot(slot_index)  # 校验存档存在
    mgr = get_slot_mgr()
    mgr.clear_all_messages(slot_index)
    return {"ok": True}


@router.delete("/api/slots/{slot_index}/chat/messages")
def delete_messages(slot_index: int, req: DeleteMessageRequest):
    """删除消息。

    优先使用 from_id（按消息 ID 删除），
    回退到 from_index / to_index（按数组下标删除）。
    """
    mgr = get_slot_mgr()

    if req.from_id is not None:
        if req.from_id <= 0:
            error("invalid_message_id", "消息 ID 无效", 400)
        success = mgr.delete_messages_from(slot_index, req.from_id)
        if not success:
            error("delete_failed", "删除消息失败", 500)
        return {"ok": True}

    # 按数组下标删除（通过消息 ID 精确定位，不影响其余消息 ID）
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

    ids_to_delete = [
        m["id"] for m in history[req.from_index: req.to_index + 1] if m.get("id")
    ]
    if not ids_to_delete:
        error("delete_failed", "无法定位要删除的消息", 500)
    if not mgr.delete_messages_by_ids(slot_index, ids_to_delete):
        error("delete_failed", "删除消息失败", 500)
    return {"ok": True, "deleted": len(ids_to_delete)}


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

    # 按下标编辑（通过消息 ID 更新，保持其余消息 ID 不变）
    data = resolve_slot(slot_index)
    history: list = data.get("history", [])
    if req.index is None or req.index < 0 or req.index >= len(history):
        error("invalid_index", f"消息索引 {req.index} 无效", 400)
    target = history[req.index]
    if not target.get("id"):
        error("message_not_found", "无法定位消息 ID", 404)
    if not mgr.update_message_content(target["id"], req.content):
        error("message_not_found", f"消息 #{target['id']} 不存在", 404)
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
    """更新存档的 API Key（连接失败后补填用）。

    主模型密钥写入 slot.api_key；双模型的模型2密钥写入 dual_config。
    """
    data = resolve_slot(slot_index)
    api_key = (req.get("api_key") or "").strip()
    if not api_key:
        error("empty_api_key", "API Key 不能为空", 400)

    # 更新主模型密钥
    get_slot_mgr().update_slot_meta(slot_index, {"api_key": api_key})

    # 双模型时同步更新模型2密钥
    dual_config = data.get("dual_config", {}) or {}
    if dual_config.get("enabled") and dual_config.get("model2"):
        dual_config["model2"]["api_key"] = api_key
        get_slot_mgr().update_dual_config(slot_index, dual_config)
    return {"ok": True}


@router.patch("/api/slots/{slot_index}/dual-toggle")
def toggle_dual_mode(slot_index: int, req: DualToggleRequest):
    """切换双模型的回复模式。"""
    data = resolve_slot(slot_index)
    dual_config = data.get("dual_config", {}) or {}
    if not dual_config.get("enabled"):
        error("not_dual_mode", "该存档不是双模型模式", 400)

    if req.response_mode not in ("model1", "model2", "both"):
        error("invalid_response_mode", "回复模式无效", 400)
    if req.first_model not in ("model1", "model2"):
        error("invalid_first_model", "先回复模型无效", 400)

    dual_config["response_mode"] = req.response_mode
    dual_config["first_model"] = req.first_model
    get_slot_mgr().update_dual_config(slot_index, dual_config)
    return {"ok": True, "dual_config": dual_config}


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
