"""
SQLite 记忆实现测试套件

使用 aiosqlite 内存数据库进行真实数据库交互测试
"""

import unittest
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest
import aiosqlite

# pylint: disable=import-error
# NOTE: E0401 import-error is a pylint configuration issue.
# The tests run correctly with pytest, which resolves the src path.
from src.database.sqlite import SqliteDatabase


@dataclass
class MemoryData:
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
    def from_dict(cls, data: dict[str, Any]) -> "MemoryData":
        """从字典形式创建记忆对象"""
        return cls(
            id=data["id"],
            content=data["content"],
            category=data.get("category", "test"),
        )


class TestSqliteMemoryBase(unittest.TestCase):
    """SQLite 记忆实现基础测试"""

    connection: aiosqlite.Connection
    memory_store: SqliteDatabase[MemoryData]

    @pytest.fixture(autouse=True)
    def setup_fixtures(self, event_loop: Any) -> None:
        """pytest fixture 设置"""
        self.loop = event_loop

    async def asyncSetUp(self) -> None:
        """异步测试设置 - 创建内存数据库和表"""
        self.connection = await aiosqlite.connect(":memory:")
        # 创建测试表
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS test_memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'test'
            )
        """)
        await self.connection.commit()
        self.memory_store = SqliteDatabase[MemoryData](
            connection=self.connection,
            table_name="test_memories",
            memory_cls=MemoryData,
        )

    async def asyncTearDown(self) -> None:
        """异步测试清理"""
        await self.connection.close()


@pytest.mark.asyncio
class TestSqliteMemoryAddAndSearch:
    """测试添加和搜索记忆功能"""

    async def test_add_memory(self) -> None:
        """测试添加记忆"""
        async with aiosqlite.connect(":memory:") as conn:
            await conn.execute("""
                CREATE TABLE test_memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'test'
                )
            """)
            await conn.commit()

            store = SqliteDatabase[MemoryData](
                connection=conn,
                table_name="test_memories",
                memory_cls=MemoryData,
            )

            memory = MemoryData(content="测试内容", category="unit_test")
            await store.add(memory)

            # 验证数据已写入
            async with conn.execute(
                "SELECT * FROM test_memories WHERE id = ?", (memory.id,)
            ) as cursor:
                row = await cursor.fetchone()

            assert row is not None
            assert row[0] == memory.id
            assert row[1] == "测试内容"
            assert row[2] == "unit_test"

    async def test_search_memory_with_filter(self) -> None:
        """测试带过滤条件的搜索"""
        async with aiosqlite.connect(":memory:") as conn:
            await conn.execute("""
                CREATE TABLE test_memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'test'
                )
            """)
            await conn.commit()

            store = SqliteDatabase[MemoryData](
                connection=conn,
                table_name="test_memories",
                memory_cls=MemoryData,
            )

            # 添加多条记忆
            memories = [
                MemoryData(content="记忆A", category="cat1"),
                MemoryData(content="记忆B", category="cat2"),
                MemoryData(content="记忆C", category="cat1"),
            ]
            for mem in memories:
                await store.add(mem)

            # 搜索指定类别
            results = await store.search(field="id", limit=10, category="cat1")

            assert len(results) == 2
            assert all(m.category == "cat1" for m in results)

    async def test_search_memory_with_limit(self) -> None:
        """测试搜索限制数量"""
        async with aiosqlite.connect(":memory:") as conn:
            await conn.execute("""
                CREATE TABLE test_memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'test'
                )
            """)
            await conn.commit()

            store = SqliteDatabase[MemoryData](
                connection=conn,
                table_name="test_memories",
                memory_cls=MemoryData,
            )

            # 添加5条记忆
            for i in range(5):
                await store.add(MemoryData(content=f"记忆{i}"))

            # 限制返回2条
            results = await store.search(field="id", limit=2)

            assert len(results) == 2

    async def test_search_memory_empty_result(self) -> None:
        """测试空结果搜索"""
        async with aiosqlite.connect(":memory:") as conn:
            await conn.execute("""
                CREATE TABLE test_memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'test'
                )
            """)
            await conn.commit()

            store = SqliteDatabase[MemoryData](
                connection=conn,
                table_name="test_memories",
                memory_cls=MemoryData,
            )

            results = await store.search(
                field="id", limit=10, category="不存在的类别"
            )

            assert len(results) == 0


@pytest.mark.asyncio
class TestSqliteMemoryUpdate:
    """测试更新记忆功能"""

    async def test_update_memory(self) -> None:
        """测试更新记忆"""
        async with aiosqlite.connect(":memory:") as conn:
            await conn.execute("""
                CREATE TABLE test_memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'test'
                )
            """)
            await conn.commit()

            store = SqliteDatabase[MemoryData](
                connection=conn,
                table_name="test_memories",
                memory_cls=MemoryData,
            )

            # 添加记忆
            memory = MemoryData(content="原始内容", category="original")
            await store.add(memory)

            # 更新记忆
            updated_memory = MemoryData(
                id=memory.id, content="更新后内容", category="updated"
            )
            await store.update(updated_memory)

            # 验证更新
            async with conn.execute(
                "SELECT * FROM test_memories WHERE id = ?", (memory.id,)
            ) as cursor:
                row = await cursor.fetchone()

            assert row is not None
            assert row[1] == "更新后内容"
            assert row[2] == "updated"


@pytest.mark.asyncio
class TestSqliteMemoryDelete:
    """测试删除记忆功能"""

    async def test_delete_memory(self) -> None:
        """测试删除记忆"""
        async with aiosqlite.connect(":memory:") as conn:
            await conn.execute("""
                CREATE TABLE test_memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'test'
                )
            """)
            await conn.commit()

            store = SqliteDatabase[MemoryData](
                connection=conn,
                table_name="test_memories",
                memory_cls=MemoryData,
            )

            # 添加记忆
            memory = MemoryData(content="待删除内容")
            await store.add(memory)

            # 验证添加成功
            async with conn.execute(
                "SELECT COUNT(*) FROM test_memories WHERE id = ?", (memory.id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == 1

            # 删除记忆
            await store.delete(memory.id)

            # 验证删除成功
            async with conn.execute(
                "SELECT COUNT(*) FROM test_memories WHERE id = ?", (memory.id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == 0

    async def test_delete_nonexistent_memory(self) -> None:
        """测试删除不存在的记忆（应该不报错）"""
        async with aiosqlite.connect(":memory:") as conn:
            await conn.execute("""
                CREATE TABLE test_memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'test'
                )
            """)
            await conn.commit()

            store = SqliteDatabase[MemoryData](
                connection=conn,
                table_name="test_memories",
                memory_cls=MemoryData,
            )

            # 删除不存在的记忆应该不报错
            await store.delete("nonexistent-id")


@pytest.mark.asyncio
class TestSqliteMemoryClose:
    """测试关闭连接功能"""

    async def test_close_connection(self) -> None:
        """测试关闭连接"""
        conn = await aiosqlite.connect(":memory:")
        await conn.execute("""
            CREATE TABLE test_memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'test'
            )
        """)
        await conn.commit()

        store = SqliteDatabase[MemoryData](
            connection=conn,
            table_name="test_memories",
            memory_cls=MemoryData,
        )

        # 关闭连接
        await store.close()

        # 验证连接已关闭（尝试执行操作应该失败）
        with pytest.raises(Exception):
            await conn.execute("SELECT 1")


@pytest.mark.asyncio
class TestSqliteMemoryIntegration:
    """集成测试 - 完整工作流"""

    async def test_full_lifecycle(self) -> None:
        """测试完整生命周期：添加 -> 搜索 -> 更新 -> 搜索 -> 删除 -> 搜索"""
        async with aiosqlite.connect(":memory:") as conn:
            await conn.execute("""
                CREATE TABLE test_memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'test'
                )
            """)
            await conn.commit()

            store = SqliteDatabase[MemoryData](
                connection=conn,
                table_name="test_memories",
                memory_cls=MemoryData,
            )

            # 1. 添加记忆
            memory = MemoryData(content="生命周期测试", category="lifecycle")
            await store.add(memory)

            # 2. 搜索验证
            results = await store.search(
                field="id", limit=10, category="lifecycle"
            )
            assert len(results) == 1
            assert results[0].content == "生命周期测试"

            # 3. 更新记忆
            updated = MemoryData(
                id=memory.id, content="更新后的内容", category="lifecycle"
            )
            await store.update(updated)

            # 4. 再次搜索验证
            results = await store.search(
                field="id", limit=10, category="lifecycle"
            )
            assert len(results) == 1
            assert results[0].content == "更新后的内容"

            # 5. 删除记忆
            await store.delete(memory.id)

            # 6. 最终验证
            results = await store.search(
                field="id", limit=10, category="lifecycle"
            )
            assert len(results) == 0

    async def test_batch_operations(self) -> None:
        """测试批量操作"""
        async with aiosqlite.connect(":memory:") as conn:
            await conn.execute("""
                CREATE TABLE test_memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'test'
                )
            """)
            await conn.commit()

            store = SqliteDatabase[MemoryData](
                connection=conn,
                table_name="test_memories",
                memory_cls=MemoryData,
            )

            # 批量添加
            memories = [
                MemoryData(content=f"批量记忆{i}", category=f"batch{i % 3}")
                for i in range(10)
            ]
            for mem in memories:
                await store.add(mem)

            # 验证总数
            results = await store.search(field="id", limit=100)
            assert len(results) == 10

            # 按类别搜索
            results = await store.search(
                field="id", limit=100, category="batch0"
            )
            assert len(results) == 4  # 0, 3, 6, 9

            # 批量删除
            for mem in memories[:5]:
                await store.delete(mem.id)

            # 验证剩余
            results = await store.search(field="id", limit=100)
            assert len(results) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
