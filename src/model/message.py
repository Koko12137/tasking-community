import time
from uuid import uuid4
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCallRequest(BaseModel):
    """ToolCallRequest 请求模型，表示对工具的调用请求"""
    
    id: str = Field(default=..., description="The unique id of the tool call request.")
    """工具调用请求的唯一标识符，必填"""

    type: str = Field(default="function", description="The type of the tool call request.")
    """工具调用请求的类型，默认值为 "function" """

    name: str = Field(default=..., description="The name of the tool call request.")
    """工具调用请求的名称，必填"""

    args: dict[str, Any] = Field(default_factory=dict[str, Any], description="The arguments of the tool call request.")
    """工具调用请求的参数字典，默认值为空字典"""


class StopReason(Enum):
    """LLM 推理停止原因枚举"""
    
    STOP = "stop"
    """因为正常停止而结束"""
    
    TOOL_CALL = "tool_call"
    """因为工具调用而结束"""

    LENGTH = "length"
    """因为长度限制而结束"""

    CONTENT_FILTER = "content_filter"
    """因为内容过滤而结束"""

    NONE = "none"
    """没有停止原因"""
    

class CompletionUsage(BaseModel):
    """LLM 模型推理的 Token 使用情况"""
    
    prompt_tokens: int = Field(description="The number of prompt tokens.", default=-100)
    """提示词消耗的 token 数量，默认值 -100 表示不可用"""
    
    completion_tokens: int = Field(description="The number of completion tokens.", default=-100)
    """生成内容消耗的 token 数量，默认值 -100 表示不可用"""
    
    total_tokens: int = Field(description="The total number of tokens.", default=-100)
    """总共消耗的 token 数量，默认值 -100 表示不可用"""


class Message(BaseModel):
    """Message 是对话上下文中的基本单元，表示一次交流的信息。"""
    
    uid: str = Field(default_factory=lambda: str(uuid4()), description="The unique identifier of the message.")
    """Message 的唯一标识符，不需要手动设置，自动生成 UUID"""
    
    role: Role = Field(default=..., description="The role of the message.")
    """Message 的角色，必填： Role.SYSTEM / Role.USER / Role.ASSISTANT / Role.TOOL"""
    
    content: str = Field(default="")
    """Message 的文本内容，当文本内容为空时，可以使用 `multimodal_content` 字段传递多模态内容"""
    
    multimodal_content: list[dict[str, str]] = Field(
        default_factory=list[dict[str, str]], description="The multimodal content of the message."
    )
    """Message 的多模态内容列表，每个元素为一个字典，包含多模态内容的类型和数据。`content` 字段为空时，可以使用该字段传递多模态内容"""
    
    tool_call_id: str = Field(default="", description="The unique id of the tool call when the message is a tool call result.")
    """Tool Call 的唯一标识符，当消息为工具调用结果时，设置该字段为对应的工具调用 ID，为空字符串表示非工具调用结果消息"""
    
    tool_calls: list[ToolCallRequest] = Field(default_factory=list[ToolCallRequest], description="The tool calls of the message.")
    """Message 的工具调用列表，每个元素为一个 ToolCallRequest 对象"""

    is_error: bool = Field(description="Whether the tool call result is an error.", default=False)
    """Message 的工具调用结果是否为错误"""

    stop_reason: StopReason = Field(description="The stop reason of the message.", default=StopReason.NONE)
    """Message 的停止原因"""

    usage: CompletionUsage = Field(default_factory=CompletionUsage, description="The usage of the message.")
    """Message 的 Token 使用情况"""

    timestamp: str = Field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))
    """Message 的时间戳"""
    
    metadata: dict[str, Any] = Field(description="The meta data of the message.", default_factory=dict)
    """Message 的元数据，可以存储一些自定义的键值对信息"""

    def to_dict(self) -> dict[str, Any]:
        """将 Message 对象转换为字典格式"""
        return self.model_dump()
