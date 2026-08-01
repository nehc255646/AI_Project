"""
路由模块共享的辅助函数。
"""
from __future__ import annotations

from fastapi import HTTPException

from config import SLOT_COUNT, MODEL_CONFIG
from state import get_slot_mgr


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


def validate_model_key(model_key: str) -> dict:
    """验证模型配置，返回配置 dict 或抛出错误。"""
    cfg = MODEL_CONFIG.get(model_key)
    if not cfg:
        error("unknown_model", f"不支持的模型: {model_key}", 400)
    provider = cfg.get("provider", "")
    if provider not in ("deepseek", "dashscope", "ollama"):
        error("invalid_provider", f"模型 {model_key} 的 provider 配置无效: {provider}", 500)
    return cfg


def check_api_key(provider: str, api_key: str) -> None:
    """校验 API Key 是否已配置（Ollama 除外，连接失败时再提示）。"""
    from config import DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, OLLAMA_API_KEY

    if provider == "ollama":
        return

    env_map = {"deepseek": DEEPSEEK_API_KEY, "dashscope": DASHSCOPE_API_KEY}
    name_map = {"deepseek": "DeepSeek", "dashscope": "DashScope"}

    env_key = env_map.get(provider, "")
    if env_key:
        return
    if not api_key or not api_key.strip():
        provider_name = name_map.get(provider, provider)
        error(
            "missing_api_key",
            f"{provider_name} API Key 未在环境变量中设置，请在创建存档时提供有效的 API Key",
            400,
        )
