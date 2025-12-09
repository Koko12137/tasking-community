import time
from uuid import uuid4
from enum import Enum
from typing import Any, TypeAlias

from pydantic import BaseModel, Field, field_validator


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


class TextBlock(BaseModel):
    """TextBlock 是对文本内容的封装，包含文本及其元数据"""
    
    type: str = Field(default="text", description="The type of the content block.")
    """内容块的类型，固定值为 `text`"""

    text: str = Field(default=..., description="The text content of the block.")
    """文本内容，必填"""


class ImageBlock(BaseModel):
    """ImageBlock 是对图像内容的封装，包含图像 URL 及其元数据"""
    
    type: str = Field(default="image_url", description="The type of the content block.")
    """内容块的类型，固定值为 `image_url`"""

    image_base64: str = Field(default="", description="The base64 encoded image content.")
    """图像的 Base64 编码内容，默认为空字符串"""
    
    image_type: str = Field(default="jpeg", description="The type of the image.")
    """图像的类型，默认值为 `jpeg`"""

    image_url: str = Field(default="", description="The URL of the image.")
    """图像的 URL 地址，默认为空字符串"""

    detail: str = Field(default="low", description="The detail description of the image.")
    """对图片模态内容理解的精细度，默认取值为 `low`，`high` 表示高精细度理解"""

    @field_validator("detail")
    def validate_detail(cls, v: str) -> str:
        """验证 detail 字段的取值是否合法"""
        if v not in {"low", "high"}:
            raise ValueError("detail must be 'low' or 'high'")
        return v

    @field_validator("image_base64", "image_url")
    def validate_image_content(cls, v: str, info: Any) -> str:
        """验证 image_base64 和 image_url 字段不能同时为空"""
        if info.field_name == "image_base64":
            other_value = info.data.get("image_url", "")
        else:
            other_value = info.data.get("image_base64", "")
        if not v and not other_value:
            raise ValueError("Either image_base64 or image_url must be provided")
        return v


class VideoBlock(BaseModel):
    """VideoUrlBlock 是对视频内容的封装，包含视频 URL 及其元数据"""
    
    type: str = Field(default="video_url", description="The type of the content block.")
    """内容块的类型，固定值为 `video_url`"""

    video_base64: str = Field(default="", description="The base64 encoded video content.")
    """视频的 Base64 编码内容，默认为空字符串"""

    video_type: str = Field(default="mp4", description="The type of the video.")
    """视频的类型，默认值为 `mp4`"""

    video_url: str = Field(default="", description="The URL of the video.")
    """视频的 URL 地址，默认为空字符串"""

    fps: int = Field(default=1, description="The frames per second of the video.")
    """视频的每秒帧数，默认值为 1"""

    @field_validator("video_base64", "video_url")
    def validate_video_content(cls, v: str, info: Any) -> str:
        """验证 video_base64 和 video_url 字段不能同时为空"""
        if info.field_name == "video_base64":
            other_value = info.data.get("video_url", "")
        else:
            other_value = info.data.get("video_base64", "")
        if not v and not other_value:
            raise ValueError("Either video_base64 or video_url must be provided")
        return v

    @field_validator("fps")
    def validate_fps(cls, v: int) -> int:
        """验证 fps 字段的取值必须大于 0"""
        if v <= 0:
            raise ValueError("fps must be greater than 0")
        return v


MultimodalContent: TypeAlias = TextBlock | ImageBlock | VideoBlock
"""MultimodalContent 是文本块、图像块和视频块的联合类型别名"""


class Message(BaseModel):
    """Message 是对话上下文中的基本单元，表示一次交流的信息。"""

    uid: str = Field(default_factory=lambda: str(uuid4()), description="The unique identifier of the message.")
    """Message 的唯一标识符，不需要手动设置，自动生成 UUID"""

    role: Role = Field(default=..., description="The role of the message.")
    """Message 的角色，必填： Role.SYSTEM / Role.USER / Role.ASSISTANT / Role.TOOL"""

    content: list[MultimodalContent] = Field(
        default_factory=list[MultimodalContent],
        description="The content of the message."
    )
    """Message 的内容列表，可以包含文本块、图像块和视频块"""

    tool_call_id: str = Field(default="", description="The unique id of the tool call when the message is a tool call result.")
    """Tool Call 的唯一标识符，当消息为工具调用结果时，设置该字段为对应的工具调用 ID，为空字符串表示非工具调用结果消息"""

    tool_calls: list[ToolCallRequest] = Field(default_factory=list[ToolCallRequest], description="The tool calls of the message.")
    """Message 的工具调用列表，每个元素为一个 ToolCallRequest 对象"""

    is_error: bool = Field(description="Whether the tool call result is an error.", default=False)
    """Message 的工具调用结果是否为错误"""

    stop_reason: StopReason = Field(description="The stop reason of the message.", default=StopReason.NONE)
    """Message 的停止原因，默认值为 StopReason.NONE，表示没有停止，可选值包括：
    - StopReason.STOP
    - StopReason.TOOL_CALL
    - StopReason.LENGTH
    - StopReason.CONTENT_FILTER
    """

    usage: CompletionUsage = Field(default_factory=CompletionUsage, description="The usage of the message.")
    """Message 的 Token 使用情况"""

    timestamp: str = Field(
        default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    )
    """Message 的时间戳"""

    metadata: dict[str, Any] = Field(description="The meta data of the message.", default_factory=dict)
    """Message 的元数据，可以存储一些自定义的键值对信息"""

    def to_dict(self) -> dict[str, Any]:
        """将 Message 对象转换为字典格式"""
        return self.model_dump()


class DeltaToolCall(BaseModel):
    """DeltaToolCall 是对工具调用增量的封装，包含工具调用的名称和参数增量"""
    index: int = Field(default=..., description="The index of the tool call.")
    """工具调用的索引位置，必填"""

    name: str = Field(default=..., description="The name of the tool call.")
    """工具调用的名称，必填"""

    args: dict[str, Any] = Field(default_factory=dict[str, Any], description="The arguments of the tool call.")
    """工具调用的参数字典，默认值为空字典"""
    
    type: str = Field(default="function", description="The type of the tool call.")
    """工具调用的类型，默认值为 "function" """


class MessageChunk(BaseModel):
    """MessageChunk 是对消息流式传输的分块表示，包含消息 ID 和增量内容"""

    message_id: str = Field(default=..., description="The unique identifier of the message.")
    """所属 Message 的唯一标识符，必填"""

    delta: list[MultimodalContent] = Field(
        default_factory=list[MultimodalContent],
        description="The incremental content of the message chunk."
    )
    """消息分块的增量内容列表，可以包含文本块、图像块和视频块"""

    refusal: str | None = None
    """The refusal message generated by the model."""

    role: Role = Field(default=..., description="The role of the author of this message.")
    """The role of the author of this message."""

    tool_calls: list[DeltaToolCall] = Field(
        default_factory=list[DeltaToolCall],
        description="The tool calls of the message chunk."
    )
    """消息分块的工具调用列表，每个元素为一个 DeltaToolCall 对象"""
