"""
模型路由 — 提供可用模型列表、环境状态与默认生成参数。
"""
from __future__ import annotations

from fastapi import APIRouter

from config import MODEL_CONFIG, DEFAULT_PARAMS, DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, OLLAMA_API_KEY

router = APIRouter(tags=["models"])


@router.get("/api/models")
def list_models():
    return [{"key": k, **v} for k, v in MODEL_CONFIG.items()]


@router.get("/api/env-check")
def env_check():
    return {
        "deepseek": bool(DEEPSEEK_API_KEY),
        "dashscope": bool(DASHSCOPE_API_KEY),
        "ollama": bool(OLLAMA_API_KEY),
    }


@router.get("/api/default-params")
def default_params():
    """返回默认生成参数，供前端创建存档时使用。"""
    return DEFAULT_PARAMS
