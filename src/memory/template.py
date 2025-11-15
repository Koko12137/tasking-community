
from src.memory import IMemory
from src.llm import IEmbeddingLLM


class TemplateMemory(IMemory):
    """模板记忆实现，作为 `Task` 执行的指导模板"""
    
    def __init__(self) -> None:
        """初始化模板记忆实例"""
        pass
    
    def get_embedding_llm(self) -> IEmbeddingLLM:
        """获取用于记忆的嵌入式语言模型
        
        Returns:
            嵌入式语言模型实例
        """
        raise NotImplementedError("TemplateMemory does not implement get_embedding_llm")
    
    def clear_memory(self) -> None:
        """清空所有记忆"""
        raise NotImplementedError("TemplateMemory does not implement clear_memory")