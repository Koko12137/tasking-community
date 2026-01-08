from typing import TypeVar, Protocol, Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .message import MultimodalContent, TextBlock, ImageBlock, VideoBlock


class MemoryProtocol(Protocol):
    """记忆对象必须实现的协议（如包含唯一标识、序列化方法等）"""

    @property
    def id(self) -> str:
        """唯一标识符"""
        ...

    @property
    def content(self) -> list[MultimodalContent]:
        """记忆内容，支持文本/图像/视频格式"""
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
    - task_id: 关联的任务 ID
    - content: 记忆的多模态内容（文本/图像/视频等）
    - timestamp: 记忆创建或最后更新的时间戳
    """
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier for the memory item")
    """唯一标识记忆条目的 ID，默认使用 UUID 生成"""
    
    task_id: str = Field(..., description="Identifier for the task associated with the episode")
    """与该对话记忆关联的任务 ID"""

    content: list[MultimodalContent] = Field(..., description="Serialized representation of the state memory")
    """状态记忆的提取到的用户状态/环境状态等信息"""

    timestamp: str = Field(..., description="Timestamp when the memory was created or last updated")
    """记忆创建或最后更新的时间戳"""

    def to_dict(self) -> dict[str, Any]:
        """将 MemoryItem 实例转换为字典表示形式"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "content": [block.model_dump() for block in self.content],
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryItem":
        """从字典表示形式创建 MemoryItem 实例"""
        content: list[MultimodalContent] = []
        for item in data["content"]:
            if item['type'] == 'text':
                content.append(TextBlock.model_validate(item))
            elif item['type'] == 'image':
                content.append(ImageBlock.model_validate(item))
            elif item['type'] == 'video':
                content.append(VideoBlock.model_validate(item))
            else:
                raise ValueError(f"Only text content is supported, got: {item['type']}")
        
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            content=content,
            timestamp=data["timestamp"],
        )


class BlockRecord(MemoryItem):
    """BlockRecord 表示块记忆结构体，包含与特定块相关的元数据和内容。
    块记忆指的是对话中的特定信息块或片段的记忆，如某个消息、命令等。
    """
    memory_id: str = Field(..., description="Identifier for the block associated with the block record")
    """与该块记忆关联的块 ID"""
    
    def to_dict(self) -> dict[str, Any]:
        """将 BlockRecord 实例转换为字典表示形式"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "memory_id": self.memory_id,
            "content": [block.model_dump() for block in self.content],
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BlockRecord":
        """从字典表示形式创建 BlockRecord 实例"""
        content: list[MultimodalContent] = []
        for item in data["content"]:
            if item['type'] == 'text':
                content.append(TextBlock.model_validate(item))
            elif item['type'] == 'image':
                content.append(ImageBlock.model_validate(item))
            elif item['type'] == 'video':
                content.append(VideoBlock.model_validate(item))
            else:
                raise ValueError(f"Only text content is supported, got: {item['type']}")

        return cls(
            id=data["id"],
            task_id=data["task_id"],
            memory_id=data["memory_id"],
            content=content,
            timestamp=data["timestamp"],
        )
        
    @classmethod
    @field_validator('content', mode='before')
    def validate_content(cls, v: list[MultimodalContent]) -> list[MultimodalContent]:
        """保证 content 不为空且长度为 1"""
        if not v:
            raise ValueError("Content cannot be empty for BlockRecord.")
        if len(v) != 1:
            raise ValueError("Content must contain exactly one item for BlockRecord.")
        return v


class StateMemory(MemoryItem):
    """StateMemory 表示状态记忆结构体，包含与用户或环境状态相关的元数据和内容。
    状态型记忆指的是对用户当前状态或环境状态的记忆，如用户偏好、上下文信息等。
    """
    episode_id: str = Field(..., description="Identifier for the episode associated with the state memory")
    """与该状态记忆关联的对话 ID"""
    
    def to_dict(self) -> dict[str, Any]:
        """将 StateMemory 实例转换为字典表示形式"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "episode_id": self.episode_id,
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
            elif item['type'] == 'image':
                content.append(ImageBlock.model_validate(item))
            elif item['type'] == 'video':
                content.append(VideoBlock.model_validate(item))
            else:
                raise ValueError(f"Only text content is supported, got: {item['type']}")

        return cls(
            id=data["id"],
            task_id=data["task_id"],
            episode_id=data["episode_id"],
            content=content,
            timestamp=data["timestamp"],
        )


class EpisodeMemory(MemoryItem):
    """EpisodeMemory 表示一次对话的事件记忆结构体，包含与该对话相关的元数据和消息数据。
    事件型记忆指的是在对话过程中发生的特定事件或交互，以及对应的结果。
    """
    abstract: str = Field(..., description="Abstract or summary of the episode memory")
    """对话记忆的摘要或总结"""
    
    def to_dict(self) -> dict[str, Any]:
        """将 EpisodeMemory 实例转换为字典表示形式"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "abstract": self.abstract,
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
            else:
                raise ValueError(f"Only text content is supported, got: {item['type']}")

        return cls(
            id=data["id"],
            task_id=data["task_id"],
            abstract=data["abstract"],
            content=content,
            timestamp=data["timestamp"],
        )


class ProcedureMemory(MemoryItem):
    """ProcedureMemory 表示一个程序记忆结构体，包含与该过程相关的元数据和消息数据。
    程序型记忆指的是在执行特定任务或过程时的命令要求。
    """

    episode_id: str = Field(..., description="Identifier for the episode associated with the procedure memory")
    """与该程序记忆关联的对话 ID"""
    
    def to_dict(self) -> dict[str, Any]:
        """将 ProcedureMemory 实例转换为字典表示形式"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "episode_id": self.episode_id,
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
            elif item['type'] == 'image':
                content.append(ImageBlock.model_validate(item))
            elif item['type'] == 'video':
                content.append(VideoBlock.model_validate(item))
            else:
                raise ValueError(f"Only text content is supported, got: {item['type']}")
        
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            episode_id=data["episode_id"],
            content=content,
            timestamp=data["timestamp"],
        )
