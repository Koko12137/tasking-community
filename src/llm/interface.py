from abc import abstractmethod, ABC
from typing import Any

from ..model import CompletionConfig, Provider, Message


class ILLM(ABC):
    """语言模型的协议"""
    
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
    
    @abstractmethod
    async def completion(
        self,
        messages: list[Message],
        completion_config: CompletionConfig,
        **kwargs: Any,
    ) -> Message:
        """补全消息
        
        参数:
            messages (list[Message]):
                要补全的消息
            completion_config (CompletionConfig):
                补全消息配置
            **kwargs:
                额外的关键字参数

        返回:
            DataT:
                来自语言模型的补全结果
        """
        pass


class IEmbeddingLLM(ILLM):
    """EmbeddingLLM 是用于嵌入文本的语言模型协议"""
    
    @abstractmethod
    async def embed(self, text: str, dimensions: int, **kwargs: Any) -> list[float]:
        """嵌入文本并返回嵌入向量
        
        参数:
            text (str):
                要嵌入的文本
            dimensions (int):
                嵌入维度
            **kwargs:
                额外参数
                
        返回:
            list[float]:
                文本的嵌入向量
        """
        pass
