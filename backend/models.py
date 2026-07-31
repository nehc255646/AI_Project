"""Pydantic 请求 / 响应模型。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── 请求模型 ──


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
    """删除指定范围的消息。

    支持两种模式：
      - from_id：从该消息 ID 起全部删除（优先）
      - from_index / to_index：按数组下标删除（兼容旧调用）
    """

    from_index: Optional[int] = None
    to_index: Optional[int] = None
    from_id: Optional[int] = None  # 按消息 ID 删除（优先）


class EditMessageRequest(BaseModel):
    """编辑一条消息。

    支持两种模式：
      - message_id：按消息 ID 定位（优先）
      - index：按数组下标定位（兼容旧调用）
    """

    index: Optional[int] = None
    message_id: Optional[int] = None  # 按消息 ID 定位（优先）
    content: str


# ── 响应模型 ──


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
    """结构化错误响应。"""

    code: str  # 机器可读的错误码
    message: str  # 人类可读的中文提示
    detail: str = ""


class ExportData(BaseModel):
    """对话导出数据。"""

    title: str
    model: str
    system_prompt: str
    created_at: str
    updated_at: str
    messages: list
