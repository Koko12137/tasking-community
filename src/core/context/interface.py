from abc import ABC, abstractmethod

from src.model import Message


class IContext(ABC):
    """上下文接口，提供上下文相关的方法"""

    @abstractmethod
    def get_context_data(self) -> list[Message]:
        """获取上下文数据
        
        Returns:
            上下文数据列表
        """
        pass

    @abstractmethod
    def append_context_data(self, data: Message) -> None:
        """新增上下文数据
        
        Args:
            data: 追加的数据
        """
        pass
    
    @abstractmethod
    def clear_context_data(self) -> None:
        """清空上下文数据"""
        pass
