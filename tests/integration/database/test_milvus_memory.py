"""
MilvusVectorMemory 真实数据库测试套件

使用真实的 AsyncMilvusClient 和本地 Milvus Lite 数据库测试 src.memory.milvus.MilvusVectorMemory 类
"""

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from collections.abc import Generator, AsyncGenerator
from typing import Any, cast
from uuid import uuid4

import csv
import numpy as np
from loguru import logger
from pymilvus import AsyncMilvusClient
from pymilvus import DataType as MilvusDataType

import pytest
import pytest_asyncio

# pylint: disable=import-error
from tasking.model import TextBlock, MultimodalContent
from tasking.database.interface import IVectorDBManager
from tasking.database.milvus import MilvusDatabase, EmbeddingInfo
from tasking.llm.interface import IEmbedModel, LLMConfig  # 导入 LLMConfig
from tasking.llm import Provider


class MockVectorDBManager(IVectorDBManager[AsyncMilvusClient]):
    """Mock VectorDB Manager for test"""

    def __init__(self, client: AsyncMilvusClient):
        self._client = client

    async def get_vector_database(self, context: dict[str, Any]) -> AsyncMilvusClient:
        """Get milvus client from context"""
        return self._client

    async def close(self, context: dict[str, Any]) -> None:
        """Close the database client"""
        pass


@dataclass
class VectorMemoryData:
    """测试用记忆数据类，实现 MemoryProtocol"""
    content: list[TextBlock]  # 使用 TextBlock 类型与 MemoryProtocol 兼容
    metadata: dict[str, Any] | None = None  # 添加 metadata 字段
    id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """将记忆对象转为字典形式"""
        return {
            "id": self.id,
            "content": self.content,
            **(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VectorMemoryData":
        """从字典形式创建记忆对象"""
        return cls(
            id=data["id"],
            content=data["content"],
            metadata={k: v for k, v in data.items() if k not in {"id", "content"}},
        )


class MockEmbedModel(IEmbedModel):
    """Mock 嵌入模型，用于测试"""

    def get_provider(self) -> Provider:
        return Provider.OPENAI

    def get_base_url(self) -> str:
        return "http://mock"

    def get_model(self) -> str:
        return "mock-embed"

    async def completion(
        self,
        messages: list[Any],
        completion_config: Any,
        **kwargs: Any,
    ) -> Any:
        """Mock completion method"""
        raise NotImplementedError("Mock model does not support completion")

    async def embed(self, content: list[MultimodalContent], dimensions: int, **kwargs: Any) -> list[float]:
        """生成固定的嵌入向量（基于文本哈希）"""
        # 计算所有内容的哈希值
        content_str = str([item.model_dump() if hasattr(item, 'model_dump') else item for item in content])
        hash_val = hash(content_str)
        # 将哈希值设为随机种子
        np.random.seed(hash_val % (2**32))
        # 生成指定维度的向量 - 使用更优的算法生成更独特的向量
        vector: list[float] = np.random.rand(dimensions).tolist()
        return vector

    async def embed_batch(
        self,
        contents: list[list[MultimodalContent]],  # 与接口一致的参数类型
        dimensions: int,
        **kwargs: Any,
    ) -> list[list[float]]:
        """批量嵌入"""
        # 将多模态内容转换为字符串以便哈希
        content_embeddings: list[list[float]] = []
        for content in contents:
            embedding = await self.embed(content, dimensions, **kwargs)
            content_embeddings.append(embedding)
        return content_embeddings

    @classmethod
    def from_config(cls, config: LLMConfig) -> "MockEmbedModel":
        """从配置创建模型实例"""
        return cls()


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """创建临时数据库路径"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_milvus.db")
    yield db_path
    # 清理
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def async_milvus_client(temp_db_path: str) -> AsyncGenerator[AsyncMilvusClient, None]:
    """创建真实的 AsyncMilvusClient 连接"""
    # AsyncMilvusClient 直接初始化即可用于本地 Milvus Lite
    client = AsyncMilvusClient(temp_db_path)
    yield client
    # AsyncMilvusClient 没有 close 方法


@pytest.fixture
def mock_embed_model() -> MockEmbedModel:
    """创建 Mock 嵌入模型"""
    return MockEmbedModel()


@pytest.fixture
def embeddings_config(mock_embed_model: MockEmbedModel) -> dict[str, EmbeddingInfo]:
    """创建 EmbeddingInfo 配置"""
    return {
        "test_embedding": EmbeddingInfo(
            dimension=2048,  # 使用2048维度
            model=mock_embed_model,
            search_params={"metric_type": "L2", "index_type": "FLAT"},
        )
    }


@pytest.fixture
def temp_collection_name() -> Generator[str, None, None]:
    """创建临时集合名"""
    yield f"test_collection_{str(uuid4())[:8]}"


async def create_test_collection(
    client: AsyncMilvusClient,
    collection_name: str,
    dimension: int = 2048,  # 默认使用2048维度
) -> AsyncMilvusClient:
    """创建测试集合"""
    # 创建 schema 并启用动态字段支持 metadata
    schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field(field_name="id", datatype=MilvusDataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field(field_name="content", datatype=MilvusDataType.VARCHAR, max_length=1024)
    schema.add_field(field_name="test_embedding", datatype=MilvusDataType.FLOAT_VECTOR, dim=dimension)

    # 创建索引参数 - 为向量字段创建索引
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="test_embedding",
        index_type="FLAT",
        metric_type="L2",
    )

    # 创建集合 - 注意：AsyncMilvusClient 的方法是异步的
    try:
        await client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )
        print(f"Collection {collection_name} created successfully")
    except Exception as e:
        # 如果集合已存在，忽略错误
        if "already exists" not in str(e).lower():
            print(f"Warning: Failed to create collection: {e}")
        pass

    return client


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore::RuntimeWarning")
class TestMilvusVectorMemoryRealDB:
    """使用真实数据库测试 MilvusVectorMemory"""

    async def test_embed_determinism(
        self,
        embeddings_config: dict[str, EmbeddingInfo],
    ) -> None:
        """测试嵌入模型的确定性 - 同一内容生成的嵌入向量应该相同"""

        # 测试同一内容生成的嵌入是否相同
        test_content = "测试嵌入模型的确定性"
        # 创建 MultimodalContent 类型的内容列表
        content1 = cast(list[MultimodalContent], [TextBlock(text=test_content)])
        content2 = cast(list[MultimodalContent], [TextBlock(text=test_content)])

        # 获取嵌入模型
        embed_model = embeddings_config["test_embedding"].model

        # 生成两次嵌入
        embedding1 = await embed_model.embed(content1, 2048)
        embedding2 = await embed_model.embed(content2, 2048)

        # 验证两次嵌入结果是否相同
        assert embedding1 == embedding2, "嵌入模型不是确定性的 - 同一内容生成了不同的嵌入向量"
        print(f"嵌入确定性测试通过 - 向量维度: {len(embedding1)}, 向量值: {embedding1[:10]}...")

    async def test_init_with_real_client(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试使用真实 AsyncMilvusClient 初始化"""
        # 先创建集合
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 创建 Mock 管理器
        manager = MockVectorDBManager(async_milvus_client)

        # 创建 MilvusDatabase 实例
        memory = MilvusDatabase(
            manager=manager,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        # 验证初始化
        assert memory._collection_name == temp_collection_name
        assert memory._embeddings == embeddings_config
        assert memory._memory_cls == VectorMemoryData

        # 清理：删除集合
        try:
            await async_milvus_client.drop_collection(temp_collection_name)
        except Exception:
            logger.warning(f"Failed to drop collection {temp_collection_name} during cleanup")

    async def test_add_and_search_memory_real_db(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试在真实数据库中添加和搜索记忆"""
        # 创建集合
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 加载集合
        await async_milvus_client.load_collection(temp_collection_name)

        # 刷新集合以确保数据可见
        await async_milvus_client.flush(temp_collection_name)

        # 创建 Mock 管理器
        manager = MockVectorDBManager(async_milvus_client)

        # 创建 MilvusDatabase 实例
        memory = MilvusDatabase(
            manager=manager,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        # 添加记忆
        test_content = "测试内容"
        test_memory = VectorMemoryData(content=[TextBlock(text=test_content)])  # 使用 TextBlock 实例
        await memory.add({}, test_memory)  # 添加 context 参数

        # 刷新以确保数据被索引
        await async_milvus_client.flush(temp_collection_name)

        # 搜索记忆
        results = await memory.search(
            context={},  # 添加 context 参数
            query=[TextBlock(text=test_content)],  # 使用 TextBlock 实例
            top_k=5,
            threshold=[],  # L2 距离，阈值设大一些以确保能找到结果
            filter_expr="",
        )

        # 验证结果
        assert len(results) >= 1, f"Expected at least 1 result, got {len(results)}"
        memory_obj, distance = results[0]
        assert isinstance(memory_obj, VectorMemoryData)
        assert memory_obj.id == test_memory.id
        assert isinstance(memory_obj.content, list)
        assert len(memory_obj.content) == 1
        print(f"Found memory with distance: {distance}")

    async def test_delete_memory_real_db(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试在真实数据库中删除记忆"""
        # 创建集合
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 加载集合
        await async_milvus_client.load_collection(temp_collection_name)

        # 刷新集合
        await async_milvus_client.flush(temp_collection_name)

        # 创建 Mock 管理器
        manager = MockVectorDBManager(async_milvus_client)

        # 创建 MilvusDatabase 实例
        memory = MilvusDatabase(
            manager=manager,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        # 添加记忆
        test_content = "待删除内容"
        test_memory = VectorMemoryData(content=[TextBlock(text=test_content)])
        await memory.add({}, test_memory)

        # 刷新以确保数据被索引
        await async_milvus_client.flush(temp_collection_name)

        # 验证添加成功
        results = await memory.search(
            context={},
            query=[TextBlock(text=test_content)],
            top_k=5,
            threshold=[],
            filter_expr="",
        )
        assert len(results) >= 1, f"Expected at least 1 result before deletion, got {len(results)}"

        # 删除记忆
        await memory.delete({}, test_memory.id)

        # 再次刷新以确保删除操作生效
        await async_milvus_client.flush(temp_collection_name)

        # 验证删除成功
        results = await memory.search(
            context={},
            query=[TextBlock(text=test_content)],
            top_k=5,
            threshold=[],
            filter_expr="",
        )
        assert len(results) == 0, f"Expected 0 results after deletion, got {len(results)}"
        print("Memory deletion verified successfully")

    async def test_update_memory_real_db(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试在真实数据库中更新记忆"""
        # 创建集合
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 加载集合
        await async_milvus_client.load_collection(temp_collection_name)

        # 刷新集合
        await async_milvus_client.flush(temp_collection_name)

        # 创建 Mock 管理器
        manager = MockVectorDBManager(async_milvus_client)

        # 创建 MilvusDatabase 实例
        memory = MilvusDatabase(
            manager=manager,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        # 添加初始记忆
        original_content = "原始内容"
        test_memory = VectorMemoryData(content=[TextBlock(text=original_content)])
        await memory.add({}, test_memory)

        # 刷新以确保数据被索引
        await async_milvus_client.flush(temp_collection_name)

        # 更新记忆
        updated_content = "更新后内容"
        updated_memory = VectorMemoryData(
            id=test_memory.id,
            content=[TextBlock(text=updated_content)],
        )
        await memory.update({}, updated_memory)  # 添加 context 参数

        # 再次刷新以确保更新操作生效
        await async_milvus_client.flush(temp_collection_name)

        # 验证更新成功 - 搜索更新后的内容
        results = await memory.search(
            context={},
            query=[TextBlock(text=updated_content)],
            top_k=5,
            threshold=[],
            filter_expr="",
        )
        assert len(results) >= 1, f"Expected at least 1 result after update, got {len(results)}"
        memory_obj, _ = results[0]
        assert isinstance(memory_obj.content, list)
        assert len(memory_obj.content) == 1
        print(f"Memory updated successfully: {memory_obj.content}")

    # 移除 category 过滤测试，因为 category 已被删除

    async def test_full_lifecycle_real_db(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试在真实数据库中的完整生命周期"""
        # 创建集合
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 加载集合
        await async_milvus_client.load_collection(temp_collection_name)

        # 初始刷新
        await async_milvus_client.flush(temp_collection_name)

        # 创建 Mock 管理器
        manager = MockVectorDBManager(async_milvus_client)

        # 创建 MilvusDatabase 实例
        memory = MilvusDatabase(
            manager=manager,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        # 1. 添加记忆
        lifecycle_content = "生命周期测试"
        test_memory = VectorMemoryData(content=[TextBlock(text=lifecycle_content)])
        await memory.add({}, test_memory)

        # 2. 搜索验证 - 刷新后搜索
        await async_milvus_client.flush(temp_collection_name)
        results = await memory.search(
            context={},
            query=[TextBlock(text=lifecycle_content)],
            top_k=5,
            threshold=[],  # 阈值设为更大值
            filter_expr="",
        )
        assert len(results) >= 1, f"Expected at least 1 result after adding, got {len(results)}"
        print(f"Found memory after creation: {results[0][0].content}")

        # 3. 更新记忆
        updated_content = "更新后的内容"
        updated_memory = VectorMemoryData(
            id=test_memory.id,
            content=[TextBlock(text=updated_content)],
        )
        await memory.update({}, updated_memory)

        # 4. 再次搜索验证 - 刷新后搜索
        await async_milvus_client.flush(temp_collection_name)
        results = await memory.search(
            context={},
            query=[TextBlock(text=updated_content)],
            top_k=5,
            threshold=[],  # 阈值设为范围值
            filter_expr="",
        )
        assert len(results) >= 1, f"Expected at least 1 result after update, got {len(results)}"
        print(f"Found memory after update: {results[0][0].content}")

        # 5. 删除记忆
        await memory.delete({}, test_memory.id)

        # 6. 最终验证 - 刷新后搜索
        await async_milvus_client.flush(temp_collection_name)
        results = await memory.search(
            context={},
            query=[TextBlock(text=lifecycle_content)],
            top_k=5,
            threshold=[],  # 阈值设为范围值
            filter_expr="",
        )
        assert len(results) == 0, f"Expected 0 results after deletion, got {len(results)}"
        print("Full lifecycle test completed successfully")

        # 7. 清理集合
        await async_milvus_client.drop_collection(temp_collection_name)

    async def test_with_assets_and_metadata_real_db(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试从assets读取文档并使用元数据进行搜索过滤"""

        # 创建集合 - 注意：需要包含metadata字段
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 加载集合
        await async_milvus_client.load_collection(temp_collection_name)
        await async_milvus_client.flush(temp_collection_name)

        # 创建 Mock 管理器
        manager = MockVectorDBManager(async_milvus_client)

        # 创建 MilvusDatabase 实例
        memory = MilvusDatabase(
            manager=manager,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        # 1. 从assets读取文档
        assets_path = "tests/assets/sample_data.csv"
        memories: list[tuple[VectorMemoryData, dict[str, Any]]] = []

        with open(assets_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 创建带有元数据的记忆对象
                content = row["text_content"]
                metadata = {
                    "created_at": row["created_at"],
                    "abstract": "artificial_intelligence"  # 直接存储为字符串类型
                }

                # 创建记忆对象 - 注意：需要将内容转换为MultimodalContent格式
                memory_obj = VectorMemoryData(
                    content=[TextBlock(text=content)],
                    metadata=metadata  # 添加 metadata
                )
                memories.append((memory_obj, metadata))

        # 2. 批量添加到数据库
        for mem, _ in memories:
            # 添加一个有标签数据
            await memory.add({}, mem)
            # 随即添加一个随机标签数据
            random_mem = VectorMemoryData(
                content=[TextBlock(text="随机内容 " + str(uuid4()))],
                metadata={
                    "created_at": "2024-01-01",
                    "abstract": "random_tag"  # 直接存储为字符串类型
                }
            )
            await memory.add({}, random_mem)
            

        await async_milvus_client.flush(temp_collection_name)
        
        # 3. 测试搜索 - 使用元数据过滤
        filter_tag = "artificial_intelligence"
        for mem, meta in memories:
            if "abstract" in meta and filter_tag in meta["abstract"]:
                query_text = mem.content[0].text  # 获取 TextBlock 的 text 属性
                filter_expr = f"abstract == '{filter_tag}'"
                results = await memory.search(
                    context={},
                    query=[TextBlock(text=query_text)],
                    top_k=100,  # 增加top_k值，确保能找到预期结果
                    threshold=[],  # 使用范围阈值
                    filter_expr=filter_expr
                )
                assert len(results) >= 1, f"Expected at least 1 result for filter {filter_expr}"
                found = any(result[0].id == mem.id for result in results)
                assert found, f"Expected to find memory with id {mem.id} using filter {filter_expr}"

        # 4. 测试搜索 - 使用自己的向量搜索自己
        for mem, _ in memories:
            # 搜索查询与内容相同
            if mem.content:
                query_text = mem.content[0].text  # 获取 TextBlock 的 text 属性
                results = await memory.search(
                    context={},
                    query=[TextBlock(text=query_text)],
                    top_k=5,
                    threshold=[],  # 使用范围阈值
                    filter_expr="",      # 不使用过滤表达式
                    output_fields=None
                )
                assert len(results) >= 1, f"Expected to find self for content: {query_text}"
                # 检查把自己找出来
                found_self = any(result[0].id == mem.id for result in results)
                assert found_self, f"Expected to find self for content: {query_text}"

        print("Self-search test passed")

        # 5. 测试删除和重新搜索
        first_memory = memories[0][0]
        await memory.delete({}, first_memory.id)
        await async_milvus_client.flush(temp_collection_name)

        # 验证已删除
        if first_memory.content:
            query_text = first_memory.content[0].text
            results = await memory.search(
                context={},
                query=[TextBlock(text=query_text)],
                top_k=5,
                threshold=[],
                filter_expr=""
            )
            # 检查删除的记忆是否不在结果中
            deleted_found = any(result[0].id == first_memory.id for result in results)
            assert not deleted_found, "Expected deleted memory not to be in search results"

        print("Delete and re-search test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
