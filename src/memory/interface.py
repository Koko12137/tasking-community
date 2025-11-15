from abc import ABC, abstractmethod

from src.llm import IEmbeddingLLM


class IMemory(ABC):
    """记忆接口，提供记忆相关的方法"""
    
    @abstractmethod
    def get_embedding_llm(self) -> IEmbeddingLLM:
        """获取用于记忆的嵌入式语言模型
        
        Returns:
            嵌入式语言模型实例
        """
        pass
    
    @abstractmethod
    def clear_memory(self) -> None:
        """清空所有记忆"""
        pass