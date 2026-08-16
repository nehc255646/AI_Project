"""
模型路由 — 提供提供商、模型列表、环境状态与默认生成参数。
"""
from __future__ import annotations

import os

from fastapi import APIRouter

from config import MODEL_CONFIG, DEFAULT_PARAMS, PROVIDER_CONFIG, PROVIDER_ORDER

router = APIRouter(tags=["models"])


@router.get("/api/models")
def list_models():
    """返回全部模型（含提供商信息），按提供商顺序排序。"""
    order_index = {p: i for i, p in enumerate(PROVIDER_ORDER)}
    items = []
    for key, cfg in MODEL_CONFIG.items():
        provider = cfg.get("provider", "")
        items.append({
            "key": key,
            "id": cfg.get("id", key),
            "provider": provider,
            "provider_name": PROVIDER_CONFIG.get(provider, {}).get("name", provider),
            "max_tokens": cfg.get("max_tokens"),
            "_order": order_index.get(provider, 999),
        })
    items.sort(key=lambda x: (x["_order"], x["key"]))
    for item in items:
        item.pop("_order", None)
    return items


@router.get("/api/env-check")
def env_check():
    """返回各提供商的环境变量密钥配置状态。"""
    result = {}
    for provider, cfg in PROVIDER_CONFIG.items():
        if provider == "ollama_local":
            result[provider] = True  # 本地无需密钥
        else:
            env_name = cfg.get("api_key_env", "")
            result[provider] = bool(os.environ.get(env_name)) if env_name else False
    return result


@router.get("/api/default-params")
def default_params():
    """返回默认生成参数，供前端创建存档时使用。"""
    return DEFAULT_PARAMS
