from typing import TypeVar, Protocol, Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .message import Message, MultimodalContent, TextBlock, ImageBlock, VideoBlock


class MemoryProtocol(Protocol):
    """记忆对象必须实现的协议（如包含唯一标识、序列化方法等）"""

    @property
    def id(self) -> str:
        """唯一标识符"""
        ...

    @property
    def content(self) -> list[MultimodalContent]:
        """记忆内容，可以是多模态内容"""
        ...

    def to_dict(self) -> dict[str, Any]:
        """将记忆对象转为字典形式"""
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'MemoryProtocol':
        """从字典形式创建记忆对象"""
        ...


# 记忆数据类型，允许不同的记忆类型分类自定义
MemoryT = TypeVar('MemoryT', bound=MemoryProtocol)
"""记忆数据类型变量，必须实现MemoryProtocol协议。

需要支持:
- `id` 属性（唯一标识符）
- `content` 属性（多模态内容）
- `to_dict` 方法
- `from_dict` 类方法
"""


class MemoryItem(BaseModel):
    """MemoryItem 是记忆结构体的基类，包含与记忆相关的基本元数据。所有记忆都应包括以下字段:
    - id: 记忆条目的唯一标识符
    - user_id: 与记忆关联的用户 ID
    - project_id: 与记忆关联的项目 ID
    - trace_id: 用于追踪记忆的跟踪 ID
    """
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier for the memory item")
    """唯一标识记忆条目的 ID，默认使用 UUID 生成"""

    user_id: str = Field(..., description="Identifier for the user associated with the episode")
    """与该对话记忆关联的用户 ID"""

    project_id: str = Field(..., description="Identifier for the project associated with the episode")
    """与该对话记忆关联的项目 ID"""

    trace_id: str = Field(..., description="Trace identifier for tracking the episode")
    """用于追踪该对话记忆的跟踪 ID"""


class EpisodeMemory(MemoryItem):
    """EpisodeMemory 表示一次对话的事件记忆结构体，包含与该对话相关的元数据和消息数据。
    事件型记忆指的是在对话过程中发生的特定事件或交互，以及对应的结果。
    """
    
    task_id: str = Field(..., description="Identifier for the task associated with the episode")
    """与该对话记忆关联的任务 ID"""

    episode_id: str = Field(..., description="Unique identifier for the episode")
    """唯一标识一次对话记忆的 ID"""

    raw_data: list[Message] = Field(..., description="Data representing the memory of the episode")
    """表示该对话记忆的消息数据列表"""

    content: list[MultimodalContent] = Field(..., description="Content of the episode memory")
    """对话记忆的提取事件内容"""

    timestamp: str = Field(..., description="Timestamp when the memory was created or last updated")
    """记忆创建或最后更新的时间戳"""
    
    def to_dict(self) -> dict[str, Any]:
        """将 EpisodeMemory 实例转换为字典表示形式"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "episode_id": self.episode_id,
            "raw_data": [message.model_dump() for message in self.raw_data],
            "content": [block.model_dump() for block in self.content],
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EpisodeMemory":
        """从字典表示形式创建 EpisodeMemory 实例"""
        content: list[MultimodalContent] = []
        for item in data["content"]:
            if item['type'] == 'text':
                content.append(TextBlock.model_validate(item))
            elif item['type'] == 'image_url':
                content.append(ImageBlock.model_validate(item))
            elif item['type'] == 'video_url':
                content.append(VideoBlock.model_validate(item))
            else:
                raise ValueError(f"Unknown content type: {item['type']}")

        return cls(
            id=data["id"],
            user_id=data["user_id"],
            project_id=data["project_id"],
            trace_id=data["trace_id"],
            task_id=data["task_id"],
            episode_id=data["episode_id"],
            raw_data=[Message.model_validate(msg) for msg in data["raw_data"]],
            content=content,
            timestamp=data["timestamp"],
        )

class ProcedureMemory(MemoryItem):
    """ProcedureMemory 表示一个程序记忆结构体，包含与该过程相关的元数据和消息数据。
    程序型记忆指的是在执行特定任务或过程时的命令要求。
    """

    procedure_id: str = Field(..., description="Unique identifier for the procedure")
    """唯一标识一个程序型记忆的 ID"""

    raw_data: list[Message] = Field(..., description="Data representing the memory of the procedure")
    """表示该对话的消息数据列表"""

    content: list[MultimodalContent] = Field(..., description="Serialized representation of the procedure memory")
    """程序记忆的提取到的命令要求"""

    timestamp: str = Field(..., description="Timestamp when the memory was created or last updated")
    """记忆创建或最后更新的时间戳"""
    
    def to_dict(self) -> dict[str, Any]:
        """将 ProcedureMemory 实例转换为字典表示形式"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "trace_id": self.trace_id,
            "procedure_id": self.procedure_id,
            "raw_data": [message.model_dump() for message in self.raw_data],
            "content": [block.model_dump() for block in self.content],
            "timestamp": self.timestamp,
        }
        
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProcedureMemory":
        """从字典表示形式创建 ProcedureMemory 实例"""
        content: list[MultimodalContent] = []
        for item in data["content"]:
            if item['type'] == 'text':
                content.append(TextBlock.model_validate(item))
            elif item['type'] == 'image_url':
                content.append(ImageBlock.model_validate(item))
            elif item['type'] == 'video_url':
                content.append(VideoBlock.model_validate(item))
            else:
                raise ValueError(f"Unknown content type: {item['type']}")
        
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            project_id=data["project_id"],
            trace_id=data["trace_id"],
            procedure_id=data["procedure_id"],
            raw_data=[Message.model_validate(msg) for msg in data["raw_data"]],
            content=content,
            timestamp=data["timestamp"],
        )


class SemanticMemory(MemoryItem):
    """SemanticMemory 表示一个语义记忆结构体，包含与该语义相关的元数据和消息数据。
    语义型记忆指的是对话获得的结构化的知识/事实/概念等。
    """

    semantic_id: str = Field(..., description="Unique identifier for the semantic memory")
    """唯一标识一个语义记忆的 ID"""

    raw_data: list[Message] = Field(..., description="Data representing the memory of the semantic information")
    """表示该语义记忆的消息数据列表"""

    content: list[MultimodalContent] = Field(..., description="Serialized representation of the semantic memory")
    """语义记忆的提取到的结构化知识内容/事实/概念等"""

    timestamp: str = Field(..., description="Timestamp when the memory was created or last updated")
    """记忆创建或最后更新的时间戳"""

    def to_dict(self) -> dict[str, Any]:
        """将 SemanticMemory 实例转换为字典表示形式"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "trace_id": self.trace_id,
            "semantic_id": self.semantic_id,
            "raw_data": [message.model_dump() for message in self.raw_data],
            "content": [block.model_dump() for block in self.content],
            "timestamp": self.timestamp,
        }
        
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticMemory":
        """从字典表示形式创建 SemanticMemory 实例"""
        content: list[MultimodalContent] = []
        for item in data["content"]:
            if item['type'] == 'text':
                content.append(TextBlock.model_validate(item))
            elif item['type'] == 'image_url':
                content.append(ImageBlock.model_validate(item))
            elif item['type'] == 'video_url':
                content.append(VideoBlock.model_validate(item))
            else:
                raise ValueError(f"Unknown content type: {item['type']}")

        return cls(
            id=data["id"],
            user_id=data["user_id"],
            project_id=data["project_id"],
            trace_id=data["trace_id"],
            semantic_id=data["semantic_id"],
            raw_data=[Message.model_validate(msg) for msg in data["raw_data"]],
            content=content,
            timestamp=data["timestamp"],
        )


class StateMemory(MemoryItem):
    """StateMemory 表示一个状态记忆结构体，包含与该状态相关的元数据和消息数据。
    状态型记忆指的是对话过程中涉及的用户状态、环境状态等信息。
    """
    
    task_id: str = Field(..., description="Identifier for the task associated with the state memory")
    """与该状态记忆关联的任务 ID"""

    raw_data: list[Message] = Field(..., description="Data representing the memory of the state information")
    """表示该状态记忆的消息数据列表"""

    content: list[MultimodalContent] = Field(..., description="Serialized representation of the state memory")
    """状态记忆的提取到的用户状态/环境状态等信息"""

    timestamp: str = Field(..., description="Timestamp when the memory was created or last updated")
    """记忆创建或最后更新的时间戳"""

    def to_dict(self) -> dict[str, Any]:
        """将 StateMemory 实例转换为字典表示形式"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "trace_id": self.trace_id,
            "raw_data": [message.model_dump() for message in self.raw_data],
            "content": [block.model_dump() for block in self.content],
            "timestamp": self.timestamp,
        }
        
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateMemory":
        """从字典表示形式创建 StateMemory 实例"""
        content: list[MultimodalContent] = []
        for item in data["content"]:
            if item['type'] == 'text':
                content.append(TextBlock.model_validate(item))
            elif item['type'] == 'image_url':
                content.append(ImageBlock.model_validate(item))
            elif item['type'] == 'video_url':
                content.append(VideoBlock.model_validate(item))
            else:
                raise ValueError(f"Unknown content type: {item['type']}")

        return cls(
            id=data["id"],
            user_id=data["user_id"],
            project_id=data["project_id"],
            trace_id=data["trace_id"],
            task_id=data["task_id"],
            raw_data=[Message.model_validate(msg) for msg in data["raw_data"]],
            content=content,
            timestamp=data["timestamp"],
        )
