"""Pydantic request / response models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── Request models ──


class ChatRequest(BaseModel):
    slot_index: int
    message: str = ""


class DualModelConfig(BaseModel):
    """双模型配置 — 第二模型的所有信息。"""
    model: str = "DeepSeek-v4-flash"
    system_prompt: str = "使用中文回答"
    api_key: str = ""
    params: Optional[dict] = None


class CreateSlotRequest(BaseModel):
    model: str = "DeepSeek-v4-flash"
    system_prompt: str = "使用中文回答"
    api_key: str = ""
    title: str = ""  # 自定义标题，为空则后端自动生成
    params: Optional[dict] = None  # 生成参数，为空则使用后端默认值
    # 双模型字段
    dual_enabled: bool = False
    model1_name: str = ""
    model2_name: str = ""
    model2: Optional[DualModelConfig] = None
    pass_mode: str = "user"  # "user" | "assistant" — 另一模型消息以什么角色传入


class DualToggleRequest(BaseModel):
    """切换双模型的回复模式。"""
    response_mode: str = "both"  # "model1" | "model2" | "both"
    first_model: str = "model1"  # "model1" | "model2" 谁先回复


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
    history: list = Field(default_factory=list)  # [{id, role, content, source}, ...]
    title: str = ""
    params: Optional[dict] = None
    # 双模型信息
    dual_enabled: bool = False
    dual_config: Optional[dict] = None
    response_mode: str = "both"
    first_model: str = "model1"


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
