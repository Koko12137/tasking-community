"""Milvus向量数据库实现模块，提供基于Milvus向量数据库的数据库存储和检索功能。"""
import json
from typing import Any, NamedTuple, cast

from asyncer import syncify
from pymilvus import (
    AsyncMilvusClient,
    AnnSearchRequest,
    RRFRanker,
)

from .interface import IVectorDatabase
from ..llm.interface import IEmbedModel
from ..model import MemoryT, TextBlock, ImageBlock, VideoBlock, MultimodalContent


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
    ) -> None:
        """初始化Milvus向量数据库实例。

        Args:
            client (AsyncMilvusClient): Milvus异步客户端实例
            collection_name (str): Milvus集合名称
            embeddings (dict[str, EmbeddingInfo]): 嵌入式语言模型信息字典
            memory_cls (type[MemoryT]): 数据库对象类型
        """
        self._milvus_client = client
        self._collection_name = collection_name
        self._embeddings = embeddings
        self._memory_cls = memory_cls
        # 获取集合
        syncify(self._milvus_client.load_collection)(self._collection_name)

    def get_embedding_llm(self, model_name: str) -> IEmbedModel:
        """获取用于数据库的嵌入式语言模型实例。

        Args:
            model_name: 嵌入式语言模型名称

        Returns:
            嵌入式语言模型实例
        """
        return self._embeddings[model_name].model

    async def add(self, memory: MemoryT) -> None:
        """添加数据库到Milvus向量数据库。

        支持多模态内容，直接使用 content 进行嵌入。
        """
        # 将 memory 的 content 转为向量表示（支持多模态）
        vectors: dict[str, list[float | int]] = {}
        for name, info in self._embeddings.items():
            # 确保 content 是 list[MultimodalContent] 格式
            content = self._ensure_multimodal_content(memory.content)
            vector = await info.model.embed(content, info.dimension)
            vectors[name] = vector

        # 将 memory 转为字典表示
        memory_dict = memory.to_dict()

        # 如果 content 是多模态列表，序列化为 JSON 字符串存储
        memory_dict = self._serialize_content(memory_dict)

        await self._milvus_client.insert(
            collection_name=self._collection_name,
            data={**memory_dict, **vectors},
        )

    async def delete(self, memory_id: str) -> None:
        """从Milvus向量数据库中删除数据库。"""
        await self._milvus_client.delete(
            collection_name=self._collection_name,
            ids=[memory_id],
        )

    async def update(self, memory: MemoryT) -> None:
        """更新Milvus向量数据库中的数据库。

        支持多模态内容，直接使用 content 进行嵌入。
        """
        # 将 memory 的 content 转为向量表示（支持多模态）
        vectors: dict[str, list[float | int]] = {}
        for name, info in self._embeddings.items():
            # 确保 content 是 list[MultimodalContent] 格式
            content = self._ensure_multimodal_content(memory.content)
            vector = await info.model.embed(content, info.dimension)
            vectors[name] = vector

        # 将 memory 转为字典表示
        memory_dict = memory.to_dict()

        # 如果 content 是多模态列表，序列化为 JSON 字符串存储
        memory_dict = self._serialize_content(memory_dict)

        await self._milvus_client.upsert(
            collection_name=self._collection_name,
            data={**memory_dict, **vectors},
        )

    async def close(self) -> None:
        """关闭Milvus连接，释放资源。"""
        await self._milvus_client.release_collection(self._collection_name)


    async def query(
        self,
        filter_expr: str,
        output_fields: list[str] | None = None,
        limit: int | None = None,
    ) -> list[MemoryT]:
        """根据 ID 查询 Milvus 向量数据库中的数据库条目。

        Args:
            memory_id: 数据库条目 ID

        Returns:
            数据库条目实例，如果未找到则返回 None
        """
        hits = await self._milvus_client.query(
            collection_name=self._collection_name,
            expr=filter_expr,
            output_fields=output_fields,
            limit=limit,
        )

        memories: list[MemoryT] = []
        for item in hits:
            entity_data: dict[str, Any] = {
                "id": item.get("id"),
                "content": item.get("content"),
                "category": item.get("category"),
            }

            # 反序列化 content
            if "content" in entity_data:
                entity_data["content"] = self._deserialize_content(
                    entity_data["content"]
                )

            memory = self._memory_cls.from_dict(entity_data)
            memories.append(cast(MemoryT, memory))
        return memories

    async def search(
        self,
        query: list[MultimodalContent],
        top_k: int,
        threshold: float,
        filter_expr: str = ""
    ) -> list[tuple[MemoryT, float]]:
        """在Milvus向量数据库中搜索与查询最相关的数据库条目。

        Args:
            query: 查询内容（文本或多模态内容列表）
            top_k: 返回的最相关条目数量
            threshold: 相关性阈值
            filter_expr: 过滤条件表达式字符串

        Returns:
            相关数据库条目列表及其相关性分数
        """
        # 查询请求
        anns: list[AnnSearchRequest] = []
        for name, info in self._embeddings.items():
            # 将查询转为向量表示（支持多模态）
            vector = await info.model.embed(query, info.dimension)
            # 在AnnSearchRequest中设置过滤表达式
            ann_request = AnnSearchRequest(
                data=[vector],
                anns_field=name,
                param=info.search_params,
                limit=top_k,
                expr=filter_expr if filter_expr else None
            )
            anns.append(ann_request)

        # 设置 Ranker
        ranker = RRFRanker()

        # 混合搜索
        hits_list = await self._milvus_client.hybrid_search(
            collection_name=self._collection_name,
            reqs=anns,
            ranker=ranker,
            limit=top_k,
            output_fields=["id", "content", "category"],
        )

        return self._process_search_results(hits_list, threshold)

    def _ensure_multimodal_content(self, content: Any) -> list[MultimodalContent]:
        """确保内容是 list[MultimodalContent] 格式。

        如果 content 是字符串，尝试转换为 TextBlock。
        如果 content 已经是 list[MultimodalContent]，直接返回。
        如果 content 是其他格式，尝试转换为字符串再转换为 TextBlock。

        Args:
            content: 输入的内容（可能是字符串、TextBlock 或 MultimodalContent 列表）

        Returns:
            list[MultimodalContent]: 标准化后的多模态内容列表
        """
        # 如果已经是 list[MultimodalContent]，直接返回
        if isinstance(content, list):
            # 检查列表中的元素是否已经是 MultimodalContent 类型
            if content and isinstance(content[0], (TextBlock, ImageBlock, VideoBlock)):
                return cast(list[MultimodalContent], content)
            # 如果列表为空或不是 MultimodalContent 类型，转换为 TextBlock 列表
            try:
                return [TextBlock(text=str(item)) for item in content]
            except (TypeError, ValueError):
                # 转换失败，返回空列表
                return []

        # 如果是字符串，转换为 TextBlock
        if isinstance(content, str):
            return [TextBlock(text=content)]

        # 其他类型，尝试转换为字符串再转换为 TextBlock
        try:
            return [TextBlock(text=str(content))]
        except (TypeError, ValueError):
            # 转换失败，返回空列表
            return []

    def _serialize_content(self, memory_dict: dict[str, Any]) -> dict[str, Any]:
        """序列化多模态内容为 JSON 字符串。

        如果 content 是列表（多模态），转换为 JSON 字符串以便存储。

        Args:
            memory_dict: 数据库字典

        Returns:
            处理后的数据库字典
        """
        content = memory_dict.get("content")
        if isinstance(content, list):
            memory_dict["content"] = json.dumps(content, ensure_ascii=False)
        return memory_dict

    def _deserialize_content(self, content: Any) -> list[MultimodalContent]:
        """反序列化内容。

        如果 content 是 JSON 字符串且表示列表，解析为列表。
        如果无法解析，返回包含该内容的 TextBlock 列表。

        Args:
            content: 存储的内容

        Returns:
            反序列化后的多模态内容
        """
        if isinstance(content, str):
            # 尝试解析为 JSON（多模态内容）
            if content.startswith("[") and content.endswith("]"):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, list):
                        return cast(list[MultimodalContent], parsed)
                except (json.JSONDecodeError, ValueError):
                    pass
            # 无法解析为 JSON，返回包含原内容的 TextBlock
            return [TextBlock(text=content)]

        # 非字符串类型，转换为字符串并返回 TextBlock
        if content:
            return [TextBlock(text=str(content))]

        # 空内容返回空列表
        return []

    def _process_search_results(
        self,
        hits_list: list[Any],
        threshold: float
    ) -> list[tuple[MemoryT, float]]:
        """处理搜索结果。

        Args:
            hits_list: Milvus 返回的搜索结果
            threshold: 相关性阈值

        Returns:
            处理后的数据库和分数列表
        """
        memories: list[tuple[MemoryT, float]] = []

        for hits in hits_list:
            for item in hits:
                distance, entity_data = self._extract_hit_data(item)

                if distance is None or distance > threshold:
                    continue

                # 反序列化 content
                if "content" in entity_data:
                    entity_data["content"] = self._deserialize_content(
                        entity_data["content"]
                    )

                memory = self._memory_cls.from_dict(entity_data)
                memories.append((cast(MemoryT, memory), distance))

        return memories

    def _extract_hit_data(
        self,
        item: Any
    ) -> tuple[float | None, dict[str, Any]]:
        """从搜索结果项中提取距离和实体数据。

        Args:
            item: 搜索结果项（可能是 dict 或 Hit 对象）

        Returns:
            (distance, entity_data) 元组
        """
        if isinstance(item, dict):
            # 处理字典格式返回
            distance = item.get('distance')
            entity_data = item.get('entity', {})
            return distance, entity_data

        # 处理 Hit 对象格式返回
        distance = getattr(item, 'distance', None)
        entity_data: dict[str, Any] = {}

        if hasattr(item, 'entity'):
            entity = item.entity
            entity_data = {
                "id": entity.get("id") if hasattr(entity, 'get') else None,
                "content": entity.get("content") if hasattr(entity, 'get') else None,
                "category": entity.get("category") if hasattr(entity, 'get') else None,
            }

        return distance, entity_data
