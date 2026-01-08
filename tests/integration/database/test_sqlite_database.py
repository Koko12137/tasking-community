"""
SQLite 数据库模块测试套件

测试 src.database.sqlite 模块的功能和错误处理
"""

import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import aiosqlite
from pydantic import BaseModel, Field

from tasking.database.interface import ISqlDBManager
from tasking.database.sqlite import SqliteDatabase, SearchParams
from tasking.model import MemoryT, MultimodalContent, TextBlock


class TestMemory(BaseModel):
    """测试用记忆数据类"""
    content: Any  # 接受任意类型，因为会被序列化/反序列化为多模态内容
    category: str = "test"
    priority: int = 1
    id: str = Field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """将记忆对象转为字典形式"""
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestMemory":
        """从字典形式创建记忆对象"""
        return cls(
            id=data["id"],
            content=data["content"],
            category=data.get("category", "test"),
            priority=data.get("priority", 1),
        )


class MockSqlDBManager(ISqlDBManager[aiosqlite.Connection]):
    """模拟 SQL 数据库管理器"""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self.connection = connection

    async def get_sql_database(self, context: dict[str, Any]) -> aiosqlite.Connection:
        """获取 SQL 数据库连接"""
        return self.connection

    async def close(self, context: dict[str, Any]) -> None:
        """关闭数据库连接"""
        await self.connection.close()


class TestSearchParams(unittest.TestCase):
    """测试 SearchParams 数据类"""

    def test_search_params_creation(self) -> None:
        """测试 SearchParams 创建"""
        params = SearchParams(
            fields=["id", "content"],
            where=["category = 'test'"],
            order_by="id DESC",
            limit=10,
            filters={"priority": 1}
        )

        assert params.fields == ["id", "content"]
        assert params.where == ["category = 'test'"]
        assert params.order_by == "id DESC"
        assert params.limit == 10
        assert params.filters == {"priority": 1}

    def test_search_params_defaults(self) -> None:
        """测试 SearchParams 默认值"""
        params = SearchParams()

        assert params.fields is None
        assert params.where is None
        assert params.order_by is None
        assert params.limit is None
        assert params.filters is None


class TestSqliteDatabase(unittest.TestCase):
    """SQLite 数据库实现测试"""

    def setUp(self) -> None:
        """设置测试环境"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self) -> None:
        """清理测试环境"""
        self.loop.close()

    async def asyncSetUp(self) -> None:
        """异步设置测试环境"""
        # 创建内存数据库
        self.connection = await aiosqlite.connect(":memory:")

        # 创建测试表
        await self.connection.execute("""
            CREATE TABLE test_memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'test',
                priority INTEGER DEFAULT 1
            )
        """)
        await self.connection.commit()

        # 创建模拟管理器和数据库实例
        self.manager = MockSqlDBManager(self.connection)
        self.db = SqliteDatabase[TestMemory](
            manager=self.manager,
            table_name="test_memories",
            memory_cls=TestMemory,
        )

    async def asyncTearDown(self) -> None:
        """异步清理测试环境"""
        await self.connection.close()

    def test_database_initialization(self) -> None:
        """测试数据库初始化"""
        async def test_init():
            await self.asyncSetUp()

            assert self.db._manager == self.manager
            assert self.db._table_name == "test_memories"
            assert self.db._memory_cls == TestMemory

            await self.asyncTearDown()

        self.loop.run_until_complete(test_init())

    def test_add_memory(self) -> None:
        """测试添加记忆"""
        async def test_add():
            await self.asyncSetUp()

            # 创建记忆时包裹内容在 TextBlock 中
            memory = TestMemory(content=[TextBlock(text="测试内容")], category="unit_test", priority=2)
            context = {}

            await self.db.add(context, memory)

            # 验证数据已写入
            async with self.connection.execute(
                "SELECT * FROM test_memories WHERE id = ?", (memory.id,)
            ) as cursor:
                row = await cursor.fetchone()

            assert row is not None
            assert row[0] == memory.id
            assert '测试内容' in row[1]  # 数据库中存储的是 JSON 字符串
            assert row[2] == "unit_test"
            assert row[3] == 2

            await self.asyncTearDown()

        self.loop.run_until_complete(test_add())

    def test_delete_memory(self) -> None:
        """测试删除记忆"""
        async def test_delete():
            await self.asyncSetUp()

            # 先添加一条记录
            memory = TestMemory(content="待删除内容", category="delete_test")
            context = {}
            await self.db.add(context, memory)

            # 验证记录存在
            async with self.connection.execute(
                "SELECT COUNT(*) FROM test_memories WHERE id = ?", (memory.id,)
            ) as cursor:
                count = await cursor.fetchone()
            assert count[0] == 1

            # 删除记录
            await self.db.delete(context, memory.id)

            # 验证记录已删除
            async with self.connection.execute(
                "SELECT COUNT(*) FROM test_memories WHERE id = ?", (memory.id,)
            ) as cursor:
                count = await cursor.fetchone()
            assert count[0] == 0

            await self.asyncTearDown()

        self.loop.run_until_complete(test_delete())

    def test_update_memory(self) -> None:
        """测试更新记忆"""
        async def test_update():
            await self.asyncSetUp()

            # 先添加一条记录
            memory = TestMemory(content="原始内容", category="update_test", priority=1)
            context = {}
            await self.db.add(context, memory)

            # 更新记录
            updated_memory = TestMemory(
                id=memory.id,
                content="更新内容",
                category="updated",
                priority=3
            )
            await self.db.update(context, updated_memory)

            # 验证记录已更新
            async with self.connection.execute(
                "SELECT * FROM test_memories WHERE id = ?", (memory.id,)
            ) as cursor:
                row = await cursor.fetchone()

            assert row is not None
            assert row[1] == "更新内容"
            assert row[2] == "updated"
            assert row[3] == 3

            await self.asyncTearDown()

        self.loop.run_until_complete(test_update())

    def test_search_all_memories(self) -> None:
        """测试搜索所有记忆"""
        async def test_search_all():
            await self.asyncSetUp()

            context = {}

            # 添加多条记录
            memories = [
                TestMemory(content="记忆A", category="cat1", priority=1),
                TestMemory(content="记忆B", category="cat2", priority=2),
                TestMemory(content="记忆C", category="cat1", priority=3),
            ]
            for memory in memories:
                await self.db.add(context, memory)

            # 搜索所有记录
            results = await self.db.search(context)

            assert len(results) == 3
            # 提取文本内容进行比较
            contents = {m.content[0].text for m in results}
            assert contents == {"记忆A", "记忆B", "记忆C"}

            await self.asyncTearDown()

        self.loop.run_until_complete(test_search_all())

    def test_search_with_fields(self) -> None:
        """测试指定字段搜索"""
        async def test_search_fields():
            await self.asyncSetUp()

            context = {}

            # 添加记录
            memory = TestMemory(content="字段测试", category="field_test", priority=5)
            await self.db.add(context, memory)

            # 只搜索特定字段
            results = await self.db.search(context, fields=["id", "content"])

            assert len(results) == 1
            result = results[0]
            assert result.content[0].text == "字段测试"  # content 是 list[MultimodalContent]
            assert result.category == "test"  # 默认值
            assert result.priority == 1      # 默认值

            await self.asyncTearDown()

        self.loop.run_until_complete(test_search_fields())

    def test_search_with_where_conditions(self) -> None:
        """测试带 WHERE 条件的搜索"""
        async def test_search_where():
            await self.asyncSetUp()

            context = {}

            # 添加多条记录
            memories = [
                TestMemory(content="记忆A", category="cat1", priority=1),
                TestMemory(content="记忆B", category="cat2", priority=2),
                TestMemory(content="记忆C", category="cat1", priority=3),
            ]
            for memory in memories:
                await self.db.add(context, memory)

            # 搜索特定类别
            results = await self.db.search(context, where=["category = 'cat1'"])

            assert len(results) == 2
            assert all(m.category == "cat1" for m in results)

            await self.asyncTearDown()

        self.loop.run_until_complete(test_search_where())

    def test_search_with_kwargs_filters(self) -> None:
        """测试使用 kwargs 过滤的搜索"""
        async def test_search_kwargs():
            await self.asyncSetUp()

            context = {}

            # 添加多条记录
            memories = [
                TestMemory(content="记忆A", category="cat1", priority=1),
                TestMemory(content="记忆B", category="cat2", priority=2),
                TestMemory(content="记忆C", category="cat1", priority=3),
            ]
            for memory in memories:
                await self.db.add(context, memory)

            # 使用 kwargs 过滤
            results = await self.db.search(context, category="cat1")

            assert len(results) == 2
            assert all(m.category == "cat1" for m in results)

            await self.asyncTearDown()

        self.loop.run_until_complete(test_search_kwargs())

    def test_search_with_order_by(self) -> None:
        """测试带排序的搜索"""
        async def test_search_order():
            await self.asyncSetUp()

            context = {}

            # 添加多条记录
            memories = [
                TestMemory(content="第一", category="test", priority=3),
                TestMemory(content="第二", category="test", priority=1),
                TestMemory(content="第三", category="test", priority=2),
            ]
            for memory in memories:
                await self.db.add(context, memory)

            # 按优先级排序
            results = await self.db.search(context, order_by="priority ASC")

            assert len(results) == 3
            assert results[0].priority == 1
            assert results[1].priority == 2
            assert results[2].priority == 3

            await self.asyncTearDown()

        self.loop.run_until_complete(test_search_order())

    def test_search_with_limit(self) -> None:
        """测试限制数量的搜索"""
        async def test_search_limit():
            await self.asyncSetUp()

            context = {}

            # 添加多条记录
            memories = [
                TestMemory(content=f"记忆{i}", category="test", priority=i)
                for i in range(10)
            ]
            for memory in memories:
                await self.db.add(context, memory)

            # 限制返回数量
            results = await self.db.search(context, limit=5)

            assert len(results) == 5

            await self.asyncTearDown()

        self.loop.run_until_complete(test_search_limit())

    def test_search_complex_query(self) -> None:
        """测试复杂搜索查询"""
        async def test_search_complex():
            await self.asyncSetUp()

            context = {}

            # 添加多条记录
            memories = [
                TestMemory(content="记忆A", category="important", priority=1),
                TestMemory(content="记忆B", category="normal", priority=2),
                TestMemory(content="记忆C", category="important", priority=3),
                TestMemory(content="记忆D", category="normal", priority=1),
            ]
            for memory in memories:
                await self.db.add(context, memory)

            # 复杂查询 - 只查询特定字段，所以 category 会使用默认值
            results = await self.db.search(
                context,
                fields=["id", "content", "priority"],
                where=["category = 'important'"],
                order_by="priority DESC",
                limit=2
            )

            assert len(results) == 2
            assert results[0].priority == 3
            assert results[1].priority == 1
            # 验证内容包含重要记忆的内容
            contents = {m.content[0].text for m in results}
            assert "记忆A" in contents
            assert "记忆C" in contents

            await self.asyncTearDown()

        self.loop.run_until_complete(test_search_complex())

    def test_build_search_query(self) -> None:
        """测试查询构建方法"""
        async def test_build_query():
            await self.asyncSetUp()

            # 基本查询
            params = SearchParams()
            query, values = self.db._build_search_query(params)

            assert query == "SELECT * FROM test_memories"
            assert values == []

            # 带字段的查询
            params = SearchParams(fields=["id", "content"])
            query, values = self.db._build_search_query(params)

            assert query == "SELECT id, content FROM test_memories"
            assert values == []

            # 带过滤条件的查询
            params = SearchParams(
                where=["category = 'test'"],
                filters={"priority": 1}
            )
            query, values = self.db._build_search_query(params)

            assert "WHERE category = 'test' AND priority = ?" in query
            assert values == [1]

            # 完整查询
            params = SearchParams(
                fields=["id", "content"],
                where=["category = 'test'"],
                order_by="priority DESC",
                limit=10,
                filters={"priority": 1}
            )
            query, values = self.db._build_search_query(params)

            assert "SELECT id, content FROM test_memories" in query
            assert "WHERE category = 'test' AND priority = ?" in query
            assert "ORDER BY priority DESC" in query
            assert "LIMIT 10" in query
            assert values == [1]

            await self.asyncTearDown()

        self.loop.run_until_complete(test_build_query())


@pytest.mark.asyncio
class TestSqliteDatabaseErrors:
    """SQLite 数据库错误处理测试"""

    async def test_add_with_invalid_data(self) -> None:
        """测试添加无效数据的错误处理"""
        # 创建模拟管理器
        mock_connection = AsyncMock()
        mock_manager = MockSqlDBManager(mock_connection)

        db = SqliteDatabase[TestMemory](
            manager=mock_manager,
            table_name="test_memories",
            memory_cls=TestMemory,
        )

        memory = TestMemory(content="测试内容")
        context = {}

        # 模拟数据库错误
        mock_connection.execute.side_effect = aiosqlite.Error("数据库错误")

        with pytest.raises(aiosqlite.Error):
            await db.add(context, memory)

    async def test_search_with_invalid_table(self) -> None:
        """测试搜索不存在表的错误处理"""
        # 创建真实的数据库连接但不创建表
        connection = await aiosqlite.connect(":memory:")
        manager = MockSqlDBManager(connection)

        try:
            db = SqliteDatabase[TestMemory](
                manager=manager,
                table_name="nonexistent_table",
                memory_cls=TestMemory,
            )

            context = {}

            # 这应该抛出错误
            with pytest.raises(aiosqlite.Error):
                await db.search(context)

        finally:
            await connection.close()


if __name__ == "__main__":
    unittest.main()