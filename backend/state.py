"""
Application state — shared globals for route modules.
Initialized by main.py's lifespan handler, imported by route modules.

NOTE: Route modules MUST use get_*() functions (not direct from-import of
the module-level variables) to ensure they read the live value set by init().
"""
from __future__ import annotations

from typing import Optional

from clients import AIClient
from session_manager import SlotManager

_ai_client: Optional[AIClient] = None
_slot_mgr: Optional[SlotManager] = None


def init(clients: AIClient, mgr: SlotManager) -> None:
    global _ai_client, _slot_mgr
    _ai_client = clients
    _slot_mgr = mgr


def get_ai_client() -> AIClient:
    if _ai_client is None:
        raise RuntimeError(
            "AIClient 尚未初始化 — 服务启动异常，请检查数据库连接和配置文件"
        )
    return _ai_client


def get_slot_mgr() -> SlotManager:
    if _slot_mgr is None:
        raise RuntimeError(
            "SlotManager 尚未初始化 — 服务启动异常，请检查数据库连接和配置文件"
        )
    return _slot_mgr
