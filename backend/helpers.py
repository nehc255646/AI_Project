"""
路由模块共享的辅助函数。
"""
from __future__ import annotations

import os
import re

from fastapi import HTTPException

from config import SLOT_COUNT, DUMMY_API_KEY, DEFAULT_MAX_TOKENS
from state import get_slot_mgr

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def error(code: str, message: str, status: int = 400, detail: str = "") -> None:
    """抛出结构化错误（HTTPException）。"""
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": message, "detail": detail},
    )


def resolve_slot(slot_index: int) -> dict:
    """校验存档位是否存在并返回其数据。"""
    if slot_index < 0 or slot_index >= SLOT_COUNT:
        error("invalid_slot", f"存档位 {slot_index} 无效（0-{SLOT_COUNT - 1}）", 400)
    data = get_slot_mgr().get_slot(slot_index)
    if data is None:
        error("slot_not_found", f"存档 #{slot_index + 1} 不存在", 404)
    return data


def normalize_base_url(url: str) -> str:
    u = (url or "").strip()
    if not (u.startswith("http://") or u.startswith("https://")):
        error("invalid_base_url", "基础 URL 必须以 http:// 或 https:// 开头", 400)
    return u.rstrip("/")


def validate_slug(slug: str) -> str:
    s = (slug or "").strip()
    if not SLUG_RE.match(s):
        error(
            "invalid_slug",
            "提供商 ID 须以小写字母或数字开头，只能包含小写字母、数字、连字符或下划线",
            400,
        )
    return s


def public_provider(row: dict) -> dict:
    """对外返回供应商（不含密钥明文）。"""
    slug = row.get("slug") or ""
    models = []
    for m in row.get("models") or []:
        mid = m.get("model_id") or ""
        models.append({
            "id": m.get("id"),
            "model_id": mid,
            "display_name": (m.get("display_name") or "").strip() or mid,
            "key": m.get("key") or f"{slug}:{mid}",
        })
    use_env = bool(row.get("use_env_key"))
    env_name = (row.get("api_key_env") or "").strip()
    stored = bool((row.get("api_key") or "").strip())
    if use_env:
        key_ready = bool(env_name and os.environ.get(env_name))
    else:
        key_ready = True
    return {
        "id": row.get("id"),
        "slug": slug,
        "display_name": row.get("display_name") or slug,
        "base_url": row.get("base_url") or "",
        "use_env_key": use_env,
        "api_key_env": env_name,
        "has_api_key": stored,
        "key_ready": key_ready,
        "models": models,
        "sort_order": row.get("sort_order") or 0,
        "created_at": row.get("created_at") or "",
        "updated_at": row.get("updated_at") or "",
    }


def resolve_secret(row: dict) -> str:
    """从目录行解析调用用的 API Key。环境变量缺失时抛 ValueError。"""
    if row.get("use_env_key"):
        env_name = (row.get("api_key_env") or "").strip()
        if not env_name:
            raise ValueError("该供应商已勾选从环境变量读取，但未填写变量名")
        val = os.environ.get(env_name, "")
        if not val:
            raise ValueError(f"环境变量 {env_name} 未设置或为空")
        return val
    key = (row.get("api_key") or "").strip()
    return key or DUMMY_API_KEY


def validate_model_key(model_key: str) -> dict:
    """验证模型存在于目录中，返回解析后的配置。"""
    cfg = get_slot_mgr().resolve_model_key(model_key)
    if not cfg:
        error("unknown_model", f"模型不存在或已从目录删除: {model_key}", 400)
    return {
        "provider": cfg.get("slug") or "",
        "id": cfg.get("model_id") or "",
        "max_tokens": DEFAULT_MAX_TOKENS,
        "key": model_key,
        "base_url": cfg.get("base_url") or "",
        "display_name": (cfg.get("display_name") or "").strip() or (cfg.get("model_id") or ""),
        "provider_name": cfg.get("provider_name") or "",
        "row": cfg,
    }


def get_runtime(model_key: str, *, http: bool = True) -> dict:
    """解析对话 / 测试用的运行时配置。"""
    from clients import AIClientError

    row = get_slot_mgr().resolve_model_key(model_key)
    if not row:
        msg = f"模型不存在或已从目录删除: {model_key}"
        if http:
            error("unknown_model", msg, 400)
        raise AIClientError(msg, "unknown_model")
    try:
        api_key = resolve_secret(row)
    except ValueError as e:
        if http:
            error("missing_api_key", str(e), 400)
        raise AIClientError(str(e), "missing_api_key") from e
    return {
        "model_id": row.get("model_id") or "",
        "base_url": row.get("base_url") or "",
        "api_key": api_key,
        "max_tokens": DEFAULT_MAX_TOKENS,
    }
