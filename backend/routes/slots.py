"""
存档路由 — 对话存档的增删改查接口。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config import SLOT_COUNT, MODEL_CONFIG
from models import (
    CreateSlotRequest,
    DeleteMessageRequest,
    EditMessageRequest,
    DualToggleRequest,
    SlotDetail,
    ExportData,
    ImportSlotRequest,
    UpdateSlotRequest,
)
from helpers import error, resolve_slot, check_api_key, validate_model_key
from state import get_slot_mgr

logger = logging.getLogger(__name__)

router = APIRouter(tags=["slots"])


class ApiKeyUpdateRequest(BaseModel):
    api_key: str = Field(max_length=256)
    target: str = "model1"


class TitleUpdateRequest(BaseModel):
    title: str = Field(max_length=128)


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
        if not m2:
            error("missing_model2", "双模型配置缺少模型 2", 400)
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
                "model": m2.model,
                "system_prompt": m2.system_prompt,
                "api_key": m2.api_key,
                "params": m2.params.model_dump() if m2.params else {},
            },
        }

    success = get_slot_mgr().create_slot(
        slot_index, req.model, req.system_prompt, req.api_key,
        req.params.model_dump() if req.params else None, req.title,
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
        params=data.get("params", {}) or {},
    ).model_dump()


@router.post("/api/slots/{slot_index}/chat/clear")
def clear_slot_chat(slot_index: int):
    resolve_slot(slot_index)  # 校验存档存在
    mgr = get_slot_mgr()
    if not mgr.clear_all_messages(slot_index):
        error("clear_failed", "清空对话失败", 500)
    return {"ok": True}


@router.delete("/api/slots/{slot_index}/chat/messages")
def delete_messages(slot_index: int, req: DeleteMessageRequest):
    """删除消息。

    优先使用 from_id（按消息 ID 删除），
    回退到 from_index / to_index（按数组下标删除）。
    """
    mgr = get_slot_mgr()
    resolve_slot(slot_index)

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
    resolve_slot(slot_index)

    if not req.content:
        error("empty_content", "消息内容不能为空", 400)

    if req.message_id is not None:
        if req.message_id <= 0:
            error("invalid_message_id", "消息 ID 无效", 400)
        success = mgr.update_message_content(slot_index, req.message_id, req.content)
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
    if not mgr.update_message_content(slot_index, target["id"], req.content):
        error("message_not_found", f"消息 #{target['id']} 不存在", 404)
    return {"ok": True}


@router.patch("/api/slots/{slot_index}/title")
def update_slot_title(slot_index: int, req: TitleUpdateRequest):
    """更新存档标题。"""
    resolve_slot(slot_index)
    title = req.title.strip()
    if not title:
        error("empty_title", "标题不能为空", 400)
    if not get_slot_mgr().update_slot_meta(slot_index, {"title": title}):
        error("update_failed", "标题更新失败", 500)
    return {"ok": True}


@router.patch("/api/slots/{slot_index}/api-key")
def update_slot_api_key(slot_index: int, req: ApiKeyUpdateRequest):
    """更新存档的 API Key（连接失败后补填用）。

    主模型密钥写入 slot.api_key；双模型的模型2密钥写入 dual_config。
    """
    data = resolve_slot(slot_index)
    api_key = req.api_key.strip()
    if not api_key:
        error("empty_api_key", "API Key 不能为空", 400)

    if req.target not in ("model1", "model2"):
        error("invalid_key_target", "API Key 所属模型无效", 400)

    if req.target == "model2":
        dual_config = data.get("dual_config", {}) or {}
        if not dual_config.get("enabled") or not dual_config.get("model2"):
            error("model2_not_found", "模型 2 配置不存在", 400)
        dual_config["model2"]["api_key"] = api_key
        if not get_slot_mgr().update_dual_config(slot_index, dual_config):
            error("update_failed", "API Key 更新失败", 500)
        return {"ok": True}

    if not get_slot_mgr().update_slot_meta(slot_index, {"api_key": api_key}):
        error("update_failed", "API Key 更新失败", 500)
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
    if not get_slot_mgr().update_dual_config(slot_index, dual_config):
        error("update_failed", "回复模式更新失败", 500)
    return {"ok": True, "dual_config": dual_config}


@router.patch("/api/slots/{slot_index}/config")
def update_slot_config(slot_index: int, req: UpdateSlotRequest):
    """模型更换 — 原子更新存档的模型/提示词/参数/密钥等配置（不影响历史消息）。

    单模型与双模型的两个模型完全独立：
    - 顶层字段 `model/system_prompt/api_key/params/model1_name` 仅作用于模型1（单模型即唯一模型）
    - `model2` 嵌套对象仅作用于模型2，切勿交叉覆盖
    """
    import copy
    import json as _json

    data = resolve_slot(slot_index)
    mgr = get_slot_mgr()
    dual_raw = data.get("dual_config", {}) or {}
    is_dual = dual_raw.get("enabled", False)

    # 校验是否有任何更新
    has_update = any(
        v is not None for v in [
            req.model, req.system_prompt, req.api_key, req.title,
            req.params, req.model1_name, req.model2_name, req.model2, req.pass_mode,
        ]
    )
    if not has_update:
        error("no_update", "未提供任何可更新的字段", 400)

    # 单模型存档禁止更新双模型专属字段
    if not is_dual and any(v is not None for v in [req.model2, req.model2_name, req.pass_mode]):
        # model2 相关字段仅在双模型下有效
        if req.model2 is not None or req.model2_name is not None or req.pass_mode is not None:
            error("not_dual_mode", "该存档不是双模型模式，无法更新模型2", 400)
    if not is_dual and req.model1_name is not None:
        # 单模型下 model1_name 无意义，视为忽略但提示
        error("not_dual_mode", "该存档不是双模型模式，无法更新模型名称", 400)

    # 预备更新值（None 表示不更新）
    new_model = None
    new_prompt = None
    new_api_key = None
    new_title = None
    new_params = None
    new_dual = None

    # ——— 标题 ———
    if req.title is not None:
        cleaned = req.title.strip()
        if not cleaned:
            error("empty_title", "标题不能为空", 400)
        new_title = cleaned

    # ——— 模型1（或单模型） ———
    # model
    if req.model is not None:
        cfg = validate_model_key(req.model)
        # 密钥有效性：若请求同时带了 api_key 则用新的，否则用存档旧的
        effective_key = req.api_key if req.api_key is not None else data.get("api_key", "")
        # check_api_key 内部会优先检查环境变量
        check_api_key(cfg["provider"], effective_key if effective_key is not None else "")
        new_model = req.model

    # api_key（仅在未随 model 一起校验时需要单独校验）
    if req.api_key is not None:
        # 去空白
        provided_key = req.api_key.strip() if isinstance(req.api_key, str) else ""
        if req.model is None:
            # 未更换模型，仅更换密钥：用现有模型校验
            cur_model = data.get("model", "")
            if cur_model:
                cfg_cur = validate_model_key(cur_model)
                check_api_key(cfg_cur["provider"], provided_key)
            # 若存档无模型（异常情况），则跳过校验，直接存储
        new_api_key = provided_key

    # system_prompt
    if req.system_prompt is not None:
        # 允许空字符串，但需通过 Pydantic 长度校验（已在模型层完成）
        new_prompt = req.system_prompt

    # params
    if req.params is not None:
        new_params = req.params.model_dump()

    # ——— 双模型独立处理 ———
    if is_dual:
        # 深拷贝，避免直接修改原始对象
        new_dual = copy.deepcopy(dual_raw)
        # 确保 model2 结构存在
        if "model2" not in new_dual or not isinstance(new_dual["model2"], dict):
            new_dual["model2"] = {}
        # 保证 params 为 dict
        if "params" not in new_dual["model2"] or not isinstance(new_dual["model2"]["params"], dict):
            new_dual["model2"]["params"] = {}

        # model1_name / model2_name / pass_mode 彼此独立
        if req.model1_name is not None:
            cleaned = req.model1_name.strip()
            # 允许空字符串（回退显示为 1号/2号），但限制长度已由 Pydantic 保证
            new_dual["model1_name"] = cleaned
        if req.model2_name is not None:
            cleaned = req.model2_name.strip()
            new_dual["model2_name"] = cleaned
        if req.pass_mode is not None:
            if req.pass_mode not in ("user", "assistant"):
                error("invalid_pass_mode", "传入模式无效", 400)
            new_dual["pass_mode"] = req.pass_mode

        # model2 嵌套独立更新
        if req.model2 is not None:
            m2 = req.model2
            existing_m2 = dual_raw.get("model2") or {}
            # model
            if m2.model is not None:
                cfg2 = validate_model_key(m2.model)
                effective_m2_key = m2.api_key if m2.api_key is not None else existing_m2.get("api_key", "")
                check_api_key(cfg2["provider"], effective_m2_key if effective_m2_key is not None else "")
                new_dual["model2"]["model"] = m2.model
            # system_prompt
            if m2.system_prompt is not None:
                new_dual["model2"]["system_prompt"] = m2.system_prompt
            # api_key
            if m2.api_key is not None:
                provided_m2_key = m2.api_key.strip() if isinstance(m2.api_key, str) else ""
                if m2.model is None:
                    # 未同时更换模型，仅换密钥：用现有模型校验
                    cur_m2_model = existing_m2.get("model", "")
                    if cur_m2_model:
                        cfg2_cur = validate_model_key(cur_m2_model)
                        check_api_key(cfg2_cur["provider"], provided_m2_key)
                new_dual["model2"]["api_key"] = provided_m2_key
            # params
            if m2.params is not None:
                new_dual["model2"]["params"] = m2.params.model_dump()
    else:
        # 单模型：若误传了 dual 相关字段（前面已拦截 model2 相关），此处保持 new_dual 为 None（不更新）
        pass

    # 执行原子更新
    success = mgr.update_slot(
        slot_index,
        model=new_model,
        system_prompt=new_prompt,
        api_key=new_api_key,
        title=new_title,
        params=new_params,
        dual_config=new_dual,
    )
    if not success:
        error("update_failed", "更新存档配置失败", 500)

    # 返回最新配置供前端同步
    fresh = mgr.get_slot(slot_index)
    if fresh is None:
        error("slot_not_found", "存档不存在", 404)
    fresh_dual = fresh.get("dual_config", {}) or {}
    return {
        "ok": True,
        "model": fresh.get("model", ""),
        "system_prompt": fresh.get("system_prompt", ""),
        "title": fresh.get("title", ""),
        "params": fresh.get("params", {}) or {},
        "dual_config": fresh_dual,
        "dual_enabled": fresh_dual.get("enabled", False),
    }


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


@router.get("/api/slots/{slot_index}/backup")
def export_backup(slot_index: int):
    """导出可完整恢复存档的 JSON 备份。"""
    data = resolve_slot(slot_index)
    return {
        "version": 1,
        "index": slot_index,
        "model": data.get("model", ""),
        "system_prompt": data.get("system_prompt", ""),
        "api_key": data.get("api_key", ""),
        "title": data.get("title", ""),
        "params": data.get("params", {}) or {},
        "dual_config": data.get("dual_config", {}) or {},
        "messages": data.get("history", []),
    }


@router.post("/api/slots/{slot_index}/backup")
def import_backup(slot_index: int, req: ImportSlotRequest):
    """将 JSON 备份导入空存档位。"""
    if slot_index < 0 or slot_index >= SLOT_COUNT:
        error("invalid_slot", f"无效的存档位: {slot_index}", 400)
    mgr = get_slot_mgr()
    if mgr.get_slot(slot_index) is not None:
        error("slot_in_use", f"存档位 #{slot_index + 1} 已被使用", 409)

    cfg = validate_model_key(req.model)
    check_api_key(cfg["provider"], req.api_key)
    dual_config = req.dual_config.model_dump() if req.dual_config else {}
    if dual_config.get("enabled"):
        model2 = dual_config.get("model2") or {}
        model2_cfg = validate_model_key(model2.get("model", ""))
        check_api_key(model2_cfg["provider"], model2.get("api_key", ""))

    if not mgr.create_slot(
        slot_index, req.model, req.system_prompt, req.api_key,
        req.params.model_dump() if req.params else None,
        req.title, dual_config=dual_config,
    ):
        error("import_failed", "导入存档失败", 500)

    messages = [
        {
            "role": message.role,
            "content": message.content,
            "source": message.source,
        }
        for message in req.messages
    ]
    if messages and not mgr.append_messages(slot_index, messages):
        mgr.delete_slot(slot_index)
        error("import_failed", "导入存档消息失败", 500)
    return {"ok": True}
