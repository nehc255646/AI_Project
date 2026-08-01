"""
应用全局状态 — 由 main.py 启动时初始化，供各路由模块共享。

注意：路由模块必须通过 get_*() 函数读取实例，不能直接导入模块级变量。
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
