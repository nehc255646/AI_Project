"""Pydantic 请求 / 响应模型。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── 请求模型 ──


class ChatRequest(BaseModel):
    slot_index: int
    message: str = Field(default="", max_length=200_000)


class GenerationParams(BaseModel):
    thinking_enabled: bool = True
    temperature: float = Field(default=1.1, ge=0, le=2)
    min_p: float = Field(default=0.1, ge=0, le=1)
    top_k: int = Field(default=100, ge=0, le=1000)
    top_p: float = Field(default=0.95, ge=0, le=1)
    repeat_penalty: float = Field(default=1.25, ge=0, le=3)
    presence_penalty: float = Field(default=0.4, ge=-2, le=2)
    frequency_penalty: float = Field(default=0.0, ge=-2, le=2)
    num_ctx: int = Field(default=131072, ge=1, le=262144)
    num_predict: int = Field(default=4096, ge=1, le=16384)


class DualModelConfig(BaseModel):
    """双模型配置 — 第二模型的所有信息。"""
    model: str = "deepseek:deepseek-v4-flash"
    system_prompt: str = Field(default="使用中文回答", max_length=100_000)
    api_key: str = Field(default="", max_length=256)
    params: Optional[GenerationParams] = None


class DualConfig(BaseModel):
    enabled: bool = False
    response_mode: Literal["model1", "model2", "both"] = "both"
    first_model: Literal["model1", "model2"] = "model1"
    pass_mode: Literal["user", "assistant"] = "user"
    model1_name: str = Field(default="", max_length=20)
    model2_name: str = Field(default="", max_length=20)
    model2: Optional[DualModelConfig] = None


class CreateSlotRequest(BaseModel):
    model: str = "deepseek:deepseek-v4-flash"
    system_prompt: str = Field(default="使用中文回答", max_length=100_000)
    api_key: str = Field(default="", max_length=256)
    title: str = Field(default="", max_length=128)
    params: Optional[GenerationParams] = None
    # 双模型字段
    dual_enabled: bool = False
    model1_name: str = Field(default="", max_length=20)
    model2_name: str = Field(default="", max_length=20)
    model2: Optional[DualModelConfig] = None
    pass_mode: Literal["user", "assistant"] = "user"


class DualToggleRequest(BaseModel):
    """切换双模型的回复模式。"""
    response_mode: Literal["model1", "model2", "both"] = "both"
    first_model: Literal["model1", "model2"] = "model1"


class DeleteMessageRequest(BaseModel):
    """删除指定范围的消息。

    支持两种模式：
      - from_id：从该消息 ID 起全部删除（优先）
      - from_index / to_index：按数组下标删除
    """

    from_index: Optional[int] = None
    to_index: Optional[int] = None
    from_id: Optional[int] = None  # 按消息 ID 删除（优先）


class EditMessageRequest(BaseModel):
    """编辑一条消息。

    支持两种模式：
      - message_id：按消息 ID 定位（优先）
      - index：按数组下标定位
    """

    index: Optional[int] = None
    message_id: Optional[int] = None  # 按消息 ID 定位（优先）
    content: str = Field(max_length=200_000)


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


class ImportSlotRequest(BaseModel):
    """完整存档备份导入数据。"""
    model: str
    system_prompt: str = Field(default="使用中文回答", max_length=100_000)
    api_key: str = Field(default="", max_length=256)
    title: str = Field(default="", max_length=128)
    params: Optional[GenerationParams] = None
    dual_config: Optional[DualConfig] = None
    messages: list["ImportMessage"] = Field(default_factory=list, max_length=10_000)


class ImportMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=200_000)
    source: Literal["", "single", "model1", "model2"] = ""
