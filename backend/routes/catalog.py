"""
供应商 / 模型目录路由。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from helpers import (
    ENV_NAME_RE,
    error,
    get_runtime,
    normalize_base_url,
    public_provider,
    validate_slug,
)
from models import CatalogModelIn, CatalogModelUpdateRequest, ProviderCreateRequest, ProviderUpdateRequest
from state import get_ai_client, get_slot_mgr

logger = logging.getLogger(__name__)

router = APIRouter(tags=["catalog"])


def _slot_label(indices: list[int]) -> str:
    labels = ", ".join(f"#{i + 1}" for i in indices)
    return f"仍被存档 {labels} 引用"


def _require_provider(provider_id: int) -> dict:
    row = get_slot_mgr().get_provider(provider_id)
    if not row:
        error("provider_not_found", "供应商不存在", 404)
    return row


def _require_model(provider_id: int, model_row_id: int) -> dict:
    row = get_slot_mgr().get_catalog_model(model_row_id)
    if not row or row.get("provider_id") != provider_id:
        error("model_not_found", "模型不存在", 404)
    return row


def _validate_key_fields(use_env_key: bool, api_key_env: str) -> str:
    env_name = (api_key_env or "").strip()
    if use_env_key:
        if not env_name:
            error("missing_api_key_env", "勾选从环境变量读取时必须填写变量名", 400)
        if not ENV_NAME_RE.match(env_name):
            error("invalid_api_key_env", "环境变量名不合法", 400)
    return env_name


@router.get("/api/providers")
def list_providers():
    rows = get_slot_mgr().list_providers()
    return [public_provider(r) for r in rows]


@router.post("/api/providers")
def create_provider(req: ProviderCreateRequest):
    slug = validate_slug(req.slug)
    name = req.display_name.strip()
    if not name:
        error("empty_name", "显示名称不能为空", 400)
    base_url = normalize_base_url(req.base_url)
    env_name = _validate_key_fields(req.use_env_key, req.api_key_env)
    models = [{"model_id": m.model_id.strip(), "display_name": m.display_name.strip()} for m in req.models]
    try:
        row = get_slot_mgr().create_provider(
            slug=slug,
            display_name=name,
            base_url=base_url,
            api_key=req.api_key.strip() if req.api_key else "",
            use_env_key=req.use_env_key,
            api_key_env=env_name,
            models=models,
        )
    except ValueError:
        error("duplicate_slug", "提供商 ID 已存在", 409)
    return public_provider(row)


@router.patch("/api/providers/{provider_id}")
def update_provider(provider_id: int, req: ProviderUpdateRequest):
    _require_provider(provider_id)
    display_name = None
    if req.display_name is not None:
        display_name = req.display_name.strip()
        if not display_name:
            error("empty_name", "显示名称不能为空", 400)
    base_url = normalize_base_url(req.base_url) if req.base_url is not None else None
    use_env_key = req.use_env_key
    api_key_env = req.api_key_env
    if use_env_key is not None or api_key_env is not None:
        current = get_slot_mgr().get_provider(provider_id)
        effective_use = current.get("use_env_key") if use_env_key is None else use_env_key
        effective_env = current.get("api_key_env") if api_key_env is None else api_key_env
        env_name = _validate_key_fields(bool(effective_use), effective_env or "")
        if api_key_env is not None:
            api_key_env = env_name
    api_key = req.api_key.strip() if req.api_key is not None else None
    row = get_slot_mgr().update_provider(
        provider_id,
        display_name=display_name,
        base_url=base_url,
        api_key=api_key,
        use_env_key=use_env_key,
        api_key_env=api_key_env,
    )
    if not row:
        error("provider_not_found", "供应商不存在", 404)
    return public_provider(row)


@router.delete("/api/providers/{provider_id}")
def delete_provider(provider_id: int):
    row = _require_provider(provider_id)
    refs = get_slot_mgr().find_slots_referencing_provider_slug(row.get("slug") or "")
    if refs:
        error("in_use", f"无法删除：{_slot_label(refs)}", 409)
    if not get_slot_mgr().delete_provider(provider_id):
        error("provider_not_found", "供应商不存在", 404)
    return {"ok": True}


@router.post("/api/providers/{provider_id}/models")
def add_model(provider_id: int, req: CatalogModelIn):
    _require_provider(provider_id)
    model_id = req.model_id.strip()
    if not model_id:
        error("empty_model_id", "model-id 不能为空", 400)
    try:
        row = get_slot_mgr().add_catalog_model(
            provider_id, model_id, req.display_name.strip(),
        )
    except ValueError as e:
        if str(e) == "provider_not_found":
            error("provider_not_found", "供应商不存在", 404)
        error("duplicate_model", "该供应商下已存在相同的 model-id", 409)
    slug = row.get("slug") or ""
    mid = row.get("model_id") or ""
    return {
        "id": row.get("id"),
        "model_id": mid,
        "display_name": (row.get("display_name") or "").strip() or mid,
        "key": f"{slug}:{mid}",
    }


@router.patch("/api/providers/{provider_id}/models/{model_row_id}")
def update_model(provider_id: int, model_row_id: int, req: CatalogModelUpdateRequest):
    _require_model(provider_id, model_row_id)
    model_id = req.model_id.strip() if req.model_id is not None else None
    display_name = req.display_name if req.display_name is None else req.display_name.strip()
    if model_id is None and display_name is None:
        error("no_update", "未提供任何可更新的字段", 400)
    if model_id is not None and not model_id:
        error("empty_model_id", "model-id 不能为空", 400)
    try:
        row = get_slot_mgr().update_catalog_model(
            model_row_id, model_id=model_id, display_name=display_name,
        )
    except ValueError:
        error("duplicate_model", "该供应商下已存在相同的 model-id", 409)
    if not row:
        error("model_not_found", "模型不存在", 404)
    slug = row.get("slug") or ""
    mid = row.get("model_id") or ""
    return {
        "id": row.get("id"),
        "model_id": mid,
        "display_name": (row.get("display_name") or "").strip() or mid,
        "key": f"{slug}:{mid}",
    }


@router.delete("/api/providers/{provider_id}/models/{model_row_id}")
def delete_model(provider_id: int, model_row_id: int):
    row = _require_model(provider_id, model_row_id)
    key = f"{row.get('slug')}:{row.get('model_id')}"
    refs = get_slot_mgr().find_slots_referencing_model_key(key)
    if refs:
        error("in_use", f"无法删除：{_slot_label(refs)}", 409)
    if not get_slot_mgr().delete_catalog_model(model_row_id):
        error("model_not_found", "模型不存在", 404)
    return {"ok": True}


@router.post("/api/providers/{provider_id}/models/{model_row_id}/test")
async def test_model(provider_id: int, model_row_id: int):
    row = _require_model(provider_id, model_row_id)
    key = f"{row.get('slug')}:{row.get('model_id')}"
    rt = get_runtime(key, http=True)
    return await get_ai_client().test_hello(
        model_id=rt["model_id"],
        base_url=rt["base_url"],
        api_key=rt["api_key"],
    )
