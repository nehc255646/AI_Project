"""Pydantic request / response models."""

from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel


# ── Request models ──


class ChatRequest(BaseModel):
    slot_index: int
    message: str = ""


class CreateSlotRequest(BaseModel):
    model: str = "DeepSeek-v4-flash"
    system_prompt: str = "使用中文回答"
    api_key: str = ""
    title: str = ""  # 自定义标题，为空则后端自动生成
    params: Optional[dict] = None  # 生成参数，为空则使用后端默认值


class DeleteMessageRequest(BaseModel):
    """Delete a range of messages.

    Supports two modes:
      - from_id: delete from this message ID onward (preferred)
      - from_index / to_index: delete by array index (legacy)
    """

    from_index: Optional[int] = None
    to_index: Optional[int] = None
    from_id: Optional[int] = None  # New: 按消息 ID 删除


class EditMessageRequest(BaseModel):
    """Edit a message.

    Supports two modes:
      - message_id: target by stable message ID (preferred)
      - index: target by array index (legacy)
    """

    index: Optional[int] = None
    message_id: Optional[int] = None  # New: 按消息 ID
    content: str


# ── Response models ──


class SlotDetail(BaseModel):
    index: int
    model: str
    system_prompt: str
    created_at: str
    updated_at: str
    history: list = []  # [{id, role, content}, ...]
    title: str = ""
    params: Optional[dict] = None


class ApiError(BaseModel):
    """Structured error response."""

    code: str  # machine-readable
    message: str  # human-readable in Chinese
    detail: str = ""


class ExportData(BaseModel):
    """Conversation export payload."""

    title: str
    model: str
    system_prompt: str
    created_at: str
    updated_at: str
    messages: list


def now_iso() -> str:
    return datetime.datetime.now().isoformat()
