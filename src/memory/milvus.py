from typing import Any, NamedTuple

from asyncer import syncify
from pymilvus import (
    AsyncMilvusClient, 
    AnnSearchRequest, 
    Function, 
    FunctionType
)

from .interface import IVectorMemory
from .const import MemoryT
from ..llm.interface import IEmbedModel


EmbeddingInfo = NamedTuple(
    "EmbeddingInfo",
    [
        ("dimension", int),
        ("model", IEmbedModel),
        ("search_params", dict[str, Any]),
    ],
)


class MilvusVectorMemory(IVectorMemory[MemoryT]):
    """Milvus向量记忆实现类，基于Milvus向量数据库进行记忆存储和检索"""
    _milvus_client: AsyncMilvusClient
    _collection_name: str
    _embeddings: dict[str, EmbeddingInfo]
    _memory_cls: type[MemoryT]
    
    def __init__(
        self, 
        client: AsyncMilvusClient,
        collection_name: str,
        embeddings: dict[str, EmbeddingInfo],
        memory_cls: type[MemoryT],
        **kwargs: Any
    ) -> None:
        """初始化Milvus向量记忆实例
        
        Args:
            client (AsyncMilvusClient): Milvus异步客户端实例
            collection_name (str): Milvus集合名称
            embeddings (dict[str, EmbeddingInfo]): 嵌入式语言模型信息字典
            memory_cls (type[MemoryT]): 记忆对象类型
            **kwargs: 其他配置参数，用于初始化Milvus客户端
        """
        self._milvus_client = client
        self._collection_name = collection_name
        self._embeddings = embeddings
        self._memory_cls = memory_cls
        # 获取集合
        syncify(self._milvus_client.load_collection)(self._collection_name)
    
    def get_embedding_llm(self, model_name: str) -> IEmbedModel:
        """获取用于记忆的嵌入式语言模型实例
        
        Args:
            model_name: 嵌入式语言模型名称
            
        Returns:
            嵌入式语言模型实例
        """
        return self._embeddings[model_name].model
    
    async def add_memory(self, memory: MemoryT) -> None:
        """添加记忆到Milvus向量数据库"""
        # 将 memory 的 content 转为向量表示
        vectors: dict[str, list[float]] = {}
        for name, info in self._embeddings.items():
            vector = await info.model.embed(memory.content, info.dimension)
            vectors[name] = vector
        # 将 memory 转为字典表示
        memory_dict = memory.to_dict()
        await self._milvus_client.insert(
            collection_name=self._collection_name,
            data={**memory_dict, **vectors},
        )
    
    async def delete_memory(self, memory_id: str) -> None:
        """从Milvus向量数据库中删除记忆"""
        await self._milvus_client.delete(
            collection_name=self._collection_name,
            ids=[memory_id],
        )
    
    async def update_memory(self, memory: MemoryT) -> None:
        """更新Milvus向量数据库中的记忆"""
        # 将 memory 的 content 转为向量表示
        vectors: dict[str, list[float]] = {}
        for name, info in self._embeddings.items():
            vector = await info.model.embed(memory.content, info.dimension)
            vectors[name] = vector
        # 将 memory 转为字典表示
        memory_dict = memory.to_dict()
        await self._milvus_client.upsert(
            collection_name=self._collection_name,
            data={**memory_dict, **vectors},
        )
    
    async def close(self) -> None:
        """关闭Milvus连接，释放资源"""
        await self._milvus_client.release_collection(self._collection_name)
        
    async def search_memory(
        self, 
        query: str, 
        top_k: int, 
        threshold: float, 
        filter: str
    ) -> list[tuple[MemoryT, float]]:
        """在Milvus向量数据库中搜索与查询最相关的记忆条目"""
        # 查询请求
        anns: dict[str, AnnSearchRequest] = {}
        for name, info in self._embeddings.items():
            # 将查询转为向量表示
            vector = await info.model.embed(query, info.dimension)
            anns[name] = AnnSearchRequest(
                data=[vector],
                anns_field=name,
                param=info.search_params,
                limit=top_k,
            )
            
        # 设置 Ranker
        ranker = Function(
            name="rrf",
            input_field_names=[], # Must be an empty list
            function_type=FunctionType.RERANK,
            params={
                "reranker": "rrf", 
                "k": 100,
            }
        )
            
        # 混合搜索
        hits = await self._milvus_client.hybrid_search(
            collection_name=self._collection_name,
            reqs=list(anns.values()),
            ranker=ranker,
            limit=top_k,
        )
        memories: list[tuple[MemoryT, float]] = []
        for hit in hits:
            for item in hit:
                if item['distance'] <= threshold:
                    memories.append(
                        (self._memory_cls.from_dict(item['entity']), item['distance'])
                    )
        return memories
