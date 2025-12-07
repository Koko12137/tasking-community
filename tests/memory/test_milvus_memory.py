"""
MilvusVectorMemory 真实数据库测试套件

使用真实的 AsyncMilvusClient 和本地 Milvus Lite 数据库测试 src.memory.milvus.MilvusVectorMemory 类
"""

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from pymilvus import AsyncMilvusClient

# pylint: disable=import-error
from src.database.milvus import MilvusDatabase, EmbeddingInfo
from src.llm.interface import IEmbedModel
from src.model import Provider


@dataclass
class VectorMemoryData:
    """测试用记忆数据类，实现 MemoryProtocol"""
    content: str
    category: str = "test"
    id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """将记忆对象转为字典形式"""
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VectorMemoryData":
        """从字典形式创建记忆对象"""
        return cls(
            id=data["id"],
            content=data["content"],
            category=data.get("category", "test"),
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
        raise NotImplementedError("Mock model does not support completion")

    async def embed(self, text: str, dimensions: int, **kwargs: Any) -> list[float]:
        """生成固定的嵌入向量（基于文本哈希）"""
        hash_val = hash(text)
        return [(hash_val % (i + 1)) / 100.0 for i in range(dimensions)]

    async def embed_batch(
        self,
        texts: list[str],
        dimensions: int,
        **kwargs: Any,
    ) -> list[list[float]]:
        """批量嵌入"""
        return [await self.embed(text, dimensions) for text in texts]


@pytest.fixture
def temp_db_path() -> str:  # type: ignore[misc]
    """创建临时数据库路径"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_milvus.db")
    yield db_path
    # 清理
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def async_milvus_client(temp_db_path: str) -> AsyncMilvusClient:  # type: ignore[misc]
    """创建真实的 AsyncMilvusClient 连接"""
    # AsyncMilvusClient 直接初始化即可用于本地 Milvus Lite
    client = AsyncMilvusClient(temp_db_path)
    yield client
    # AsyncMilvusClient 没有 close 方法


@pytest.fixture(autouse=True)
def mock_syncify():
    """Mock syncify to avoid event loop issues - 自动应用到所有测试"""
    with patch("src.database.milvus.syncify") as mock_syncify:
        # 在异步测试中，syncify应该是一个空操作（no-op）
        # 因为我们已经在异步环境中，不需要运行同步包装器
        mock_syncify.return_value = MagicMock()
        yield mock_syncify


@pytest.fixture
def mock_embed_model() -> MockEmbedModel:
    """创建 Mock 嵌入模型"""
    return MockEmbedModel()


@pytest.fixture
def embeddings_config(mock_embed_model: MockEmbedModel) -> Dict[str, EmbeddingInfo]:
    """创建 EmbeddingInfo 配置"""
    return {
        "test_embedding": EmbeddingInfo(
            dimension=128,
            model=mock_embed_model,
            search_params={"metric_type": "L2", "index_type": "FLAT"},
        )
    }


@pytest.fixture
def temp_collection_name() -> str:
    """创建临时集合名"""
    return f"test_collection_{str(uuid4())[:8]}"


async def create_test_collection(
    client: AsyncMilvusClient,
    collection_name: str,
    dimension: int = 128,
) -> AsyncMilvusClient:
    """创建测试集合"""
    from pymilvus import DataType

    # 定义 schema - 确保包含所有必要的字段
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=1024)
    schema.add_field(field_name="category", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="test_embedding", datatype=DataType.FLOAT_VECTOR, dim=dimension)

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

    async def test_init_with_real_client(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: Dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试使用真实 AsyncMilvusClient 初始化"""
        # 先创建集合
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 创建 MilvusVectorMemory 实例
        memory = MilvusDatabase(
            client=async_milvus_client,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        assert memory._milvus_client == async_milvus_client
        assert memory._collection_name == temp_collection_name
        assert memory._embeddings == embeddings_config
        assert memory._memory_cls == VectorMemoryData

        # 清理：删除集合
        try:
            await async_milvus_client.drop_collection(temp_collection_name)
        except Exception:
            pass

    async def test_add_and_search_memory_real_db(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: Dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试在真实数据库中添加和搜索记忆"""
        # 创建集合
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 加载集合
        await async_milvus_client.load_collection(temp_collection_name)

        # 刷新集合以确保数据可见
        await async_milvus_client.flush(temp_collection_name)

        # 创建 MilvusVectorMemory 实例
        memory = MilvusDatabase(
            client=async_milvus_client,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        # 添加记忆
        test_memory = VectorMemoryData(content="测试内容", category="test")
        await memory.add(test_memory)

        # 刷新以确保数据被索引
        await async_milvus_client.flush(temp_collection_name)

        # 搜索记忆
        results = await memory.search(
            query="测试内容",
            top_k=5,
            threshold=1000.0,  # L2 距离，阈值设大一些以确保能找到结果
            filter_expr="",
        )

        # 验证结果
        assert len(results) >= 1, f"Expected at least 1 result, got {len(results)}"
        memory_obj, distance = results[0]
        assert isinstance(memory_obj, VectorMemoryData)
        assert memory_obj.id == test_memory.id
        assert memory_obj.content == "测试内容"
        assert memory_obj.category == "test"
        print(f"Found memory with distance: {distance}")

    async def test_delete_memory_real_db(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: Dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试在真实数据库中删除记忆"""
        # 创建集合
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 加载集合
        await async_milvus_client.load_collection(temp_collection_name)

        # 刷新集合
        await async_milvus_client.flush(temp_collection_name)

        # 创建 MilvusVectorMemory 实例
        memory = MilvusDatabase(
            client=async_milvus_client,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        # 添加记忆
        test_memory = VectorMemoryData(content="待删除内容", category="delete_test")
        await memory.add(test_memory)

        # 刷新以确保数据被索引
        await async_milvus_client.flush(temp_collection_name)

        # 验证添加成功
        results = await memory.search(
            query="待删除内容",
            top_k=5,
            threshold=1000.0,
            filter_expr="",
        )
        assert len(results) >= 1, f"Expected at least 1 result before deletion, got {len(results)}"

        # 删除记忆
        await memory.delete(test_memory.id)

        # 再次刷新以确保删除操作生效
        await async_milvus_client.flush(temp_collection_name)

        # 验证删除成功
        results = await memory.search(
            query="待删除内容",
            top_k=5,
            threshold=1000.0,
            filter_expr="",
        )
        assert len(results) == 0, f"Expected 0 results after deletion, got {len(results)}"
        print("Memory deletion verified successfully")

    async def test_update_memory_real_db(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: Dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试在真实数据库中更新记忆"""
        # 创建集合
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 加载集合
        await async_milvus_client.load_collection(temp_collection_name)

        # 刷新集合
        await async_milvus_client.flush(temp_collection_name)

        # 创建 MilvusVectorMemory 实例
        memory = MilvusDatabase(
            client=async_milvus_client,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        # 添加初始记忆
        test_memory = VectorMemoryData(content="原始内容", category="original")
        await memory.add(test_memory)

        # 刷新以确保数据被索引
        await async_milvus_client.flush(temp_collection_name)

        # 更新记忆
        updated_memory = VectorMemoryData(
            id=test_memory.id,
            content="更新后内容",
            category="updated",
        )
        await memory.update(updated_memory)

        # 再次刷新以确保更新操作生效
        await async_milvus_client.flush(temp_collection_name)

        # 验证更新成功 - 搜索更新后的内容
        results = await memory.search(
            query="更新后内容",
            top_k=5,
            threshold=1000.0,
            filter_expr="",
        )
        assert len(results) >= 1, f"Expected at least 1 result after update, got {len(results)}"
        memory_obj, _ = results[0]
        assert memory_obj.content == "更新后内容"
        assert memory_obj.category == "updated"
        print(f"Memory updated successfully: {memory_obj.content}")

    async def test_search_with_category_filter_real_db(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: Dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试在真实数据库中使用类别过滤搜索"""
        # 创建集合
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 加载集合
        await async_milvus_client.load_collection(temp_collection_name)

        # 刷新集合
        await async_milvus_client.flush(temp_collection_name)

        # 创建 MilvusVectorMemory 实例
        memory = MilvusDatabase(
            client=async_milvus_client,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        # 添加不同类别的记忆
        memories = [
            VectorMemoryData(content="Python编程", category="tech"),
            VectorMemoryData(content="Java编程", category="tech"),
            VectorMemoryData(content="红烧肉做法", category="food"),
        ]

        for mem in memories:
            await memory.add(mem)

        # 刷新以确保所有数据被索引
        await async_milvus_client.flush(temp_collection_name)

        # 搜索所有记忆
        all_results = await memory.search(
            query="编程",
            top_k=10,
            threshold=1000.0,
            filter_expr="",
        )
        print(f"All results count: {len(all_results)}")

        # 只搜索 tech 类别
        results = await memory.search(
            query="编程",
            top_k=10,
            threshold=1000.0,
            filter_expr='category == "tech"',
        )

        # 验证所有结果都是 tech 类别
        assert len(results) == 2, f"Expected 2 results for tech category, got {len(results)}"
        for memory_obj, _ in results:
            assert memory_obj.category == "tech", f"Expected tech category, got {memory_obj.category}"
        print("Category filter test passed successfully")

    async def test_full_lifecycle_real_db(
        self,
        async_milvus_client: AsyncMilvusClient,
        embeddings_config: Dict[str, EmbeddingInfo],
        temp_collection_name: str,
    ) -> None:
        """测试在真实数据库中的完整生命周期"""
        # 创建集合
        await create_test_collection(async_milvus_client, temp_collection_name)

        # 加载集合
        await async_milvus_client.load_collection(temp_collection_name)

        # 初始刷新
        await async_milvus_client.flush(temp_collection_name)

        # 创建 MilvusVectorMemory 实例
        memory = MilvusDatabase(
            client=async_milvus_client,
            collection_name=temp_collection_name,
            embeddings=embeddings_config,
            memory_cls=VectorMemoryData,
        )

        # 1. 添加记忆
        test_memory = VectorMemoryData(content="生命周期测试", category="lifecycle")
        await memory.add(test_memory)

        # 2. 搜索验证 - 刷新后搜索
        await async_milvus_client.flush(temp_collection_name)
        results = await memory.search(
            query="生命周期",
            top_k=5,
            threshold=1000.0,  # 阈值设为更大值
            filter_expr="",
        )
        assert len(results) >= 1, f"Expected at least 1 result after adding, got {len(results)}"
        print(f"Found memory after creation: {results[0][0].content}")

        # 3. 更新记忆
        updated_memory = VectorMemoryData(
            id=test_memory.id,
            content="更新后的内容",
            category="lifecycle",
        )
        await memory.update(updated_memory)

        # 4. 再次搜索验证 - 刷新后搜索
        await async_milvus_client.flush(temp_collection_name)
        results = await memory.search(
            query="更新",
            top_k=5,
            threshold=1000.0,  # 阈值设为更大值
            filter_expr="",
        )
        assert len(results) >= 1, f"Expected at least 1 result after update, got {len(results)}"
        print(f"Found memory after update: {results[0][0].content}")

        # 5. 删除记忆
        await memory.delete(test_memory.id)

        # 6. 最终验证 - 刷新后搜索
        await async_milvus_client.flush(temp_collection_name)
        results = await memory.search(
            query="生命周期",
            top_k=5,
            threshold=1000.0,  # 阈值设为更大值
            filter_expr="",
        )
        assert len(results) == 0, f"Expected 0 results after deletion, got {len(results)}"
        print("Full lifecycle test completed successfully")

        # 7. 关闭连接
        await memory.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
