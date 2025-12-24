"""Milvus向量数据库实现模块，提供基于Milvus向量数据库的数据库存储和检索功能。"""
import json
from typing import Any, NamedTuple, cast

from pymilvus import (
    AsyncMilvusClient,
    AnnSearchRequest,
    RRFRanker,
)

from .interface import IVectorDatabase, IVectorDBManager
from ..llm.interface import IEmbedModel
from ..model import MemoryT, TextBlock, MultimodalContent


class EmbeddingInfo(NamedTuple):
    """嵌入模型信息。

    Attributes:
        dimension: 嵌入向量维度
        model: 嵌入模型实例
        search_params: 搜索参数
    """
    dimension: int
    model: IEmbedModel
    search_params: dict[str, Any]


class MilvusDatabase(IVectorDatabase[MemoryT]):
    """Milvus向量数据库实现类，基于Milvus向量数据库进行记忆存储和检索。
    支持多模态内容的存储和检索，content 可以是纯文本或多模态内容列表。
    """

    _milvus_manager: IVectorDBManager[AsyncMilvusClient]
    _collection_name: str
    _embeddings: dict[str, EmbeddingInfo]
    _memory_cls: type[MemoryT]

    def __init__(
        self,
        manager: IVectorDBManager[AsyncMilvusClient],
        collection_name: str,
        embeddings: dict[str, EmbeddingInfo],
        memory_cls: type[MemoryT],
    ) -> None:
        """初始化Milvus向量数据库实例。

        Args:
            manager: Milvus数据库管理器
            collection_name: Milvus集合名称
            embeddings: 嵌入式语言模型信息字典
            memory_cls: 数据库对象类型
        """
        self._milvus_manager = manager
        self._collection_name = collection_name
        self._embeddings = embeddings
        self._memory_cls = memory_cls

    def get_embedding_llm(self, model_name: str) -> IEmbedModel:
        """获取用于数据库的嵌入式语言模型实例。

        Args:
            model_name: 嵌入式语言模型名称

        Returns:
            嵌入式语言模型实例
        """
        return self._embeddings[model_name].model

    async def add(self, context: dict[str, Any], memory: MemoryT, timeout: float = 1800.0) -> None:
        """添加数据库到Milvus向量数据库。
        支持多模态内容，直接使用 content 进行嵌入。

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            memory: 记忆对象，必须实现MemoryProtocol协议
            timeout: 超时时间（秒），默认1800秒
        """
        # 将 memory 的 content 转为向量表示（支持多模态）
        vectors: dict[str, list[float | int]] = {}
        for name, info in self._embeddings.items():
            vector = await info.model.embed(
                cast(list[MultimodalContent], memory.content), 
                info.dimension
            )
            vectors[name] = vector

        # 将 memory 转为字典表示
        memory_dict = memory.to_dict()
        # 将 content 转为序列化形式存储
        self._serialize_content(memory_dict)
        # 如果 vectors 和 memory_dict 中有重复字段，清除 memory_dict 中的字段
        for key in vectors.keys():
            if key in memory_dict:
                del memory_dict[key]

        # 获取 Milvus 客户端
        client = await self._milvus_manager.get_vector_database(context)
        await client.insert(
            collection_name=self._collection_name,
            data={**memory_dict, **vectors},
            timeout=timeout,
        )

    async def delete(self, context: dict[str, Any], memory_id: str, timeout: float = 1800.0) -> None:
        """从Milvus向量数据库中删除数据库。
        
        Args:
            context: 上下文信息，用于配置或选择数据库实例
            memory_id: 记忆对象的唯一标识符
            timeout: 超时时间（秒），默认1800秒
        """
        # 获取 Milvus 客户端
        client = await self._milvus_manager.get_vector_database(context)
        # 删除指定 ID 的数据库
        await client.delete(
            collection_name=self._collection_name,
            ids=[memory_id],
            timeout=timeout,
        )

    async def update(self, context: dict[str, Any], memory: MemoryT, timeout: float = 1800.0) -> None:
        """更新Milvus向量数据库中的数据库。
        支持多模态内容，直接使用 content 进行嵌入。

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            memory: 记忆对象，必须实现MemoryProtocol协议
            timeout: 超时时间（秒），默认1800秒
        """
        # 将 memory 的 content 转为向量表示（支持多模态）
        vectors: dict[str, list[float | int]] = {}
        for name, info in self._embeddings.items():
            vector = await info.model.embed(
                cast(list[MultimodalContent], memory.content),
                info.dimension
            )
            vectors[name] = vector

        # 将 memory 转为字典表示
        memory_dict = memory.to_dict()
        # 将 content 转为序列化形式存储
        self._serialize_content(memory_dict)
        # 如果 vectors 和 memory_dict 中有重复字段，清除 memory_dict 中的字段
        for key in vectors.keys():
            if key in memory_dict:
                del memory_dict[key]

        # 获取 Milvus 客户端
        client = await self._milvus_manager.get_vector_database(context)
        # 通过 upsert 方法更新数据库
        await client.upsert(
            collection_name=self._collection_name,
            data={**memory_dict, **vectors},
            timeout=timeout,
        )

    async def query(
        self,
        context: dict[str, Any],
        filter_expr: str,
        output_fields: list[str] | None = None,
        limit: int | None = None,
        timeout: float = 1800.0
    ) -> list[MemoryT]:
        """根据 ID 查询 Milvus 向量数据库中的数据库条目。

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            filter_expr: 过滤条件表达式字符串
            output_fields: 要查询的字段列表，如果为None则查询所有字段(*)
            limit: 返回的最大条目数量
            timeout: 超时时间（秒），默认1800秒

        Returns:
            数据库条目实例，如果未找到则返回 None
        """
        # 获取 Milvus 客户端
        client = await self._milvus_manager.get_vector_database(context)
        # 查询请求
        hits = await client.query(
            collection_name=self._collection_name,
            expr=filter_expr,
            output_fields=output_fields,
            limit=limit,
            timeout=timeout,
        )

        memories: list[MemoryT] = []
        for item in hits:
            memory = self._memory_cls.from_dict(item)
            memories.append(cast(MemoryT, memory))
        return memories

    async def search(
        self,
        context: dict[str, Any],
        query: list[MultimodalContent],
        top_k: int,
        threshold: list[float],
        filter_expr: str = "",
        output_fields: list[str] | None = None,
        timeout: float = 1800.0
    ) -> list[tuple[MemoryT, float]]:
        """在Milvus向量数据库中搜索与查询最相关的数据库条目。

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            query: 查询内容（文本或多模态内容列表）
            top_k: 返回的最相关条目数量
            threshold: 相关性阈值
            filter_expr: 过滤条件表达式字符串
            output_fields: 要查询的字段列表，如果为None则查询所有字段(*)
            timeout: 超时时间（秒），默认1800秒

        Returns:
            相关数据库条目列表及其相关性分数
        """
        # 查询请求
        anns: list[AnnSearchRequest] = []
        for name, info in self._embeddings.items():
            # 将查询转为向量表示（支持多模态）
            vector = await info.model.embed(query, info.dimension)
            # 设置搜索参数，添加范围限制
            search_params = info.search_params.copy()
            # if len(threshold) == 0:   # TODO: Milvus 暂时不支持范围搜索
            #     pass
            # elif len(threshold) == 1:
            #     search_params["range_filter"] = 0
            #     search_params["radius"] = threshold[0]
            # elif len(threshold) == 2:
            #     search_params["range_filter"] = threshold[1]
            #     search_params["radius"] = threshold[0]
            # else:
            #     raise ValueError("Threshold must be a tuple of one or two floats.")
            # 在AnnSearchRequest中设置过滤表达式
            ann_request = AnnSearchRequest(
                data=[vector],
                anns_field=name,
                param=search_params,
                limit=top_k,
                expr=filter_expr if filter_expr else None
            )
            anns.append(ann_request)

        # 设置 Ranker
        ranker = RRFRanker()

        # 获取 Milvus 客户端
        client = await self._milvus_manager.get_vector_database(context)
        # If output_fields is None, use ['*'] to return all fields
        if output_fields is None:
            output_fields = ['*']

        # 混合搜索
        hits_list = cast(
            list[dict[str, str | float | dict[str, str | float | dict[str, str]]]],
            await client.hybrid_search(
            collection_name=self._collection_name,
            reqs=anns,
            ranker=ranker,
            limit=top_k,
            output_fields=output_fields,
            timeout=timeout,
        ))

        return self._process_search_results(hits_list)

    def _serialize_content(self, memory_dict: dict[str, Any]) -> None:
        """序列化文本内容为 JSON 字符串。

        Args:
            memory_dict: 数据库字典
        """
        content: list[TextBlock] | None = memory_dict.get("content")
        if content is None:
            raise ValueError("Memory dictionary must contain 'content' field.")
        # 将 content 的每一个元素转换为字典表示
        content_list: list[dict[str, Any]] = []
        for item in content:
            content_list.append(item.model_dump())
        memory_dict["content"] = json.dumps(content_list, ensure_ascii=False)

    def _deserialize_content(self, content: Any) -> list[TextBlock]:
        """反序列化文本内容。

        如果 content 是 JSON 字符串且表示列表，解析为 TextBlock 列表。
        如果无法解析，返回包含该内容的 TextBlock 列表。

        Args:
            content: 存储的内容

        Returns:
            反序列化后的文本内容
        """
        if isinstance(content, str):
            # 尝试解析为 JSON 文本列表
            if content.startswith("[") and content.endswith("]"):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, list):
                        # 转换为 TextBlock 列表
                        text_blocks: list[TextBlock] = []
                        for item in parsed:
                            if isinstance(item, dict) and item["type"] == "text":
                                text_blocks.append(TextBlock(**item))
                        return text_blocks
                except (json.JSONDecodeError, ValueError):
                    pass
            # 无法解析为 JSON，返回包含原内容的 TextBlock
            return [TextBlock(text=content)]

        # 非字符串类型，转换为字符串并返回 TextBlock
        if content:
            return [TextBlock(text=str(content))]

        # 空内容返回空列表
        return []

    def _process_search_results(self, hits_list: list[Any]) -> list[tuple[MemoryT, float]]:
        """处理搜索结果。

        Args:
            hits_list: Milvus 返回的搜索结果

        Returns:
            处理后的数据库和分数列表
        """
        memories: list[tuple[MemoryT, float]] = []

        for hits in hits_list:
            for item in hits:
                distance: float = item.data['distance']
                entity: dict[str, str | list[TextBlock]] = item.data['entity']

                # 反序列化 content
                if "content" in entity:
                    entity["content"] = self._deserialize_content(
                        entity["content"]
                    )

                memory = self._memory_cls.from_dict(entity)
                memories.append((cast(MemoryT, memory), distance))

        return memories
