from abc import abstractmethod, ABC
from typing import Any

from mcp.types import Tool as McpTool

from .const import Provider
from ..model.message import Message, MultimodalContent
from ..model.queue import IAsyncQueue
from ..model.llm import CompletionConfig
from ..model.setting import LLMConfig


class IModel(ABC):
    """模型的协议"""

    @abstractmethod
    def get_provider(self) -> Provider:
        """获取语言模型的提供商

        返回:
            Provider:
                语言模型的提供商
        """
        pass

    @abstractmethod
    def get_base_url(self) -> str:
        """获取语言模型的基础URL

        返回:
            str:
                语言模型的基础URL
        """
        pass

    @abstractmethod
    def get_model(self) -> str:
        """获取语言模型的模型

        返回:
            str:
                语言模型的模型
        """
        pass


class ILLM(IModel):
    """ILLM 大型语言模型的协议"""

    @abstractmethod
    async def completion(
        self,
        messages: list[Message],
        tools: list[McpTool] | None,
        stream_queue: IAsyncQueue[Message] | None,
        completion_config: CompletionConfig,
        **kwargs: Any,
    ) -> Message:
        """补全消息

        参数:
            messages (list[Message]):
                要补全的消息
            tools (list[McpTool] | None):
                可用的工具列表，如果没有工具则为 None
            stream_queue (IQueue[Message] | None):
                流式数据队列，用于输出补全过程中产生的流式数据，如果不需要流式输出则为 None
            completion_config (CompletionConfig):
                补全消息配置
            **kwargs:
                额外的关键字参数

        返回:
            DataT:
                来自语言模型的补全结果
        """
        pass
    
    @classmethod
    @abstractmethod
    def from_config(cls, config: LLMConfig) -> "ILLM":
        """从配置创建模型实例

        参数:
            config (LLMConfig):
                语言模型配置

        返回:
            ILLM:
                大型语言模型实例
        """
        pass


class IEmbedModel(IModel):
    """IEmbedModel 是用于嵌入文本/多模态数据的语言模型协议"""

    @abstractmethod
    async def embed(self, content: list[MultimodalContent], dimensions: int, **kwargs: Any) -> list[float | int]:
        """嵌入文本并返回嵌入向量

        参数:
            content (list[MultimodalContent]):
                要嵌入的文本或者多模态数据
            dimensions (int):
                嵌入维度
            **kwargs:
                额外参数

        返回:
            list[float | int]:
                文本的嵌入向量
        """
        pass

    @abstractmethod
    async def embed_batch(
        self,
        contents: list[list[MultimodalContent]],
        dimensions: int,
        **kwargs: Any
    ) -> list[list[float | int]]:
        """批量嵌入文本并返回嵌入向量列表

        参数:
            contents (list[list[MultimodalContent]]):
                要嵌入的多模态数据列表
            dimensions (int):
                嵌入维度
            **kwargs:
                额外参数

        返回:
            list[list[float | int]]:
                文本的嵌入向量列表
        """
        pass
    
    @classmethod
    @abstractmethod
    def from_config(cls, config: LLMConfig) -> "IEmbedModel":
        """从配置创建模型实例

        参数:
            config (LLMConfig):
                语言模型配置

        返回:
            IEmbedModel:
                嵌入模型实例
        """
        pass
