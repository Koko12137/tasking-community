"""
SQLite 查询构建单元测试

测试 _build_search_query 方法和 SQL 查询构建逻辑
"""

import unittest
from unittest.mock import AsyncMock, create_autospec
from typing import Any

from tasking.database.sqlite import SqliteDatabase, SearchParams
from tasking.model import MemoryProtocol


class MockSqliteManager:
    """Mock SQLite 管理器用于测试"""
    pass


class MockMemory(MemoryProtocol):
    """Mock 内存对象用于测试"""

    def __init__(self, id: str, content: Any, **extra_fields: Any) -> None:
        self.id = id
        self.content = content
        self.extra_fields = extra_fields

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            **self.extra_fields
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MockMemory":
        return cls(
            id=data["id"],
            content=data["content"],
            **{k: v for k, v in data.items() if k not in ["id", "content"]}
        )


class TestSQLiteQueryBuilding(unittest.TestCase):
    """SQLite 查询构建测试"""

    def setUp(self) -> None:
        """设置测试环境"""
        # 创建 Mock 管理器
        self.mock_manager = create_autospec(MockSqliteManager)

        # 创建 SqliteDatabase 实例用于测试查询构建方法
        self.sqlite_db = SqliteDatabase(
            manager=self.mock_manager,
            table_name="test_memories",
            memory_cls=MockMemory
        )

    def test_basic_query_no_conditions(self) -> None:
        """测试基础查询（无条件）"""
        params = SearchParams()

        # 构建查询
        query, values = self.sqlite_db._build_search_query(params)

        # 验证查询语句
        expected_query = "SELECT * FROM test_memories"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_with_fields(self) -> None:
        """测试指定字段的查询"""
        params = SearchParams(fields=["id", "content", "created_at"])

        query, values = self.sqlite_db._build_search_query(params)

        expected_query = "SELECT id, content, created_at FROM test_memories"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_with_single_where_condition(self) -> None:
        """测试单个 WHERE 条件"""
        params = SearchParams(where=["status = 'active'"])

        query, values = self.sqlite_db._build_search_query(params)

        expected_query = "SELECT * FROM test_memories WHERE status = 'active'"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_with_multiple_where_conditions(self) -> None:
        """测试多个 WHERE 条件"""
        params = SearchParams(where=[
            "status = 'active'",
            "created_at > '2024-01-01'",
            "priority IN ('high', 'medium')"
        ])

        query, values = self.sqlite_db._build_search_query(params)

        expected_query = (
            "SELECT * FROM test_memories "
            "WHERE status = 'active' AND created_at > '2024-01-01' AND priority IN ('high', 'medium')"
        )
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_with_order_by(self) -> None:
        """测试 ORDER BY 子句"""
        params = SearchParams(order_by="created_at DESC")

        query, values = self.sqlite_db._build_search_query(params)

        expected_query = "SELECT * FROM test_memories ORDER BY created_at DESC"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_with_limit(self) -> None:
        """测试 LIMIT 子句"""
        params = SearchParams(limit=10)

        query, values = self.sqlite_db._build_search_query(params)

        expected_query = "SELECT * FROM test_memories LIMIT 10"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_with_offset(self) -> None:
        """测试 LIMIT 和 OFFSET 子句（通过 kwargs）"""
        params = SearchParams()

        query, values = self.sqlite_db._build_search_query(params, offset=5)

        expected_query = "SELECT * FROM test_memories LIMIT 5"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_with_limit_and_offset(self) -> None:
        """测试 LIMIT 和 OFFSET 组合"""
        params = SearchParams(limit=10)

        query, values = self.sqlite_db._build_search_query(params, offset=20)

        expected_query = "SELECT * FROM test_memories LIMIT 10, 20"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_with_group_by(self) -> None:
        """测试 GROUP BY 子句"""
        params = SearchParams()

        query, values = self.sqlite_db._build_search_query(params, group_by="category")

        expected_query = "SELECT * FROM test_memories GROUP BY category"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_with_having(self) -> None:
        """测试 HAVING 子句"""
        params = SearchParams()

        query, values = self.sqlite_db._build_search_query(params, having="COUNT(*) > 5")

        expected_query = "SELECT * FROM test_memories HAVING COUNT(*) > 5"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_complex_query_all_components(self) -> None:
        """测试包含所有组件的复杂查询"""
        params = SearchParams(
            fields=["id", "content", "category"],
            where=["status = 'active'", "created_at > '2024-01-01'"],
            order_by="created_at DESC",
            limit=10
        )

        query, values = self.sqlite_db._build_search_query(
            params,
            group_by="category",
            having="COUNT(*) >= 2",
            offset=50
        )

        expected_query = (
            "SELECT id, content, category FROM test_memories "
            "WHERE status = 'active' AND created_at > '2024-01-01' "
            "GROUP BY category "
            "HAVING COUNT(*) >= 2 "
            "ORDER BY created_at DESC "
            "LIMIT 10, 50"
        )
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_with_empty_lists(self) -> None:
        """测试空列表的处理"""
        params = SearchParams(
            fields=[],
            where=[],
            order_by="created_at",
            limit=5
        )

        query, values = self.sqlite_db._build_search_query(params)

        # 空字段列表应该回退到 *
        # 空条件列表不产生 WHERE 子句
        expected_query = "SELECT * FROM test_memories ORDER BY created_at LIMIT 5"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_with_none_values(self) -> None:
        """测试 None 值的处理"""
        params = SearchParams(
            fields=None,
            where=None,
            order_by=None,
            limit=None
        )

        query, values = self.sqlite_db._build_search_query(params)

        # 所有 None 值应该被忽略
        expected_query = "SELECT * FROM test_memories"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_only_with_where_and_order_by(self) -> None:
        """测试只有 WHERE 和 ORDER BY 的查询"""
        params = SearchParams(
            where=["priority = 'high'"],
            order_by="updated_at ASC"
        )

        query, values = self.sqlite_db._build_search_query(params)

        expected_query = "SELECT * FROM test_memories WHERE priority = 'high' ORDER BY updated_at ASC"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_only_with_group_by_and_having(self) -> None:
        """测试只有 GROUP BY 和 HAVING 的查询"""
        params = SearchParams()

        query, values = self.sqlite_db._build_search_query(
            params,
            group_by="status",
            having="AVG(priority_value) > 3"
        )

        expected_query = "SELECT * FROM test_memories GROUP BY status HAVING AVG(priority_value) > 3"
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_complex_where_conditions(self) -> None:
        """测试复杂 WHERE 条件"""
        complex_where = [
            "(status = 'active' OR status = 'pending')",
            "created_at BETWEEN '2024-01-01' AND '2024-12-31'",
            "JSON_EXTRACT(metadata, '$.tags') LIKE '%urgent%'",
            "(priority IN ('high', 'critical') AND assigned_to IS NOT NULL)"
        ]

        params = SearchParams(where=complex_where)

        query, values = self.sqlite_db._build_search_query(params)

        expected_query = (
            "SELECT * FROM test_memories "
            "WHERE (status = 'active' OR status = 'pending') "
            "AND created_at BETWEEN '2024-01-01' AND '2024-12-31' "
            "AND JSON_EXTRACT(metadata, '$.tags') LIKE '%urgent%' "
            "AND (priority IN ('high', 'critical') AND assigned_to IS NOT NULL)"
        )
        self.assertEqual(query, expected_query)
        self.assertEqual(values, [])

    def test_query_order_by_variations(self) -> None:
        """测试各种 ORDER BY 变体"""
        test_cases = [
            ("id", "ORDER BY id"),
            ("created_at DESC", "ORDER BY created_at DESC"),
            ("priority ASC, created_at DESC", "ORDER BY priority ASC, created_at DESC"),
            ("RANDOM()", "ORDER BY RANDOM()")
        ]

        for order_by_input, expected_order_by in test_cases:
            with self.subTest(order_by=order_by_input):
                params = SearchParams(order_by=order_by_input)
                query, values = self.sqlite_db._build_search_query(params)
                expected_query = f"SELECT * FROM test_memories {expected_order_by}"
                self.assertEqual(query, expected_query)

    def test_query_special_characters_in_conditions(self) -> None:
        """测试条件中的特殊字符"""
        params = SearchParams(where=["title LIKE 'Test %_quotes\\' escape'"])

        query, values = self.sqlite_db._build_search_query(params)

        # 特殊字符应该被保留在条件中
        expected_query = "SELECT * FROM test_memories WHERE title LIKE 'Test %_quotes\\' escape'"
        self.assertEqual(query, expected_query)

    def test_query_builder_parameter_safety(self) -> None:
        """测试查询构建器的参数安全性"""
        # 确保没有 SQL 注入风险（参数都是字面量，不是参数化查询）
        params = SearchParams(
            where=["id = 'malicious'; DROP TABLE test_memories; --'"]
        )

        query, values = self.sqlite_db._build_search_query(params)

        # 恶意代码会被包含在字符串字面量中，不会被执行
        self.assertIn("malicious", query)
        self.assertNotIn("DROP TABLE", query.split("'")[1])  # 不在字符串字面量外

    def test_query_consistency_with_table_name(self) -> None:
        """测试查询构建与表名的一致性"""
        # 使用不同的表名创建数据库实例
        custom_table_db = SqliteDatabase(
            manager=self.mock_manager,
            table_name="custom_table_name",
            memory_cls=MockMemory
        )

        params = SearchParams(limit=5)
        query, values = custom_table_db._build_search_query(params)

        # 查询应该使用正确的表名
        self.assertIn("custom_table_name", query)
        expected_query = "SELECT * FROM custom_table_name LIMIT 5"
        self.assertEqual(query, expected_query)

    def test_query_building_edge_cases(self) -> None:
        """测试查询构建的边界情况"""
        # 测试大数字 limit
        params = SearchParams(limit=999999999)
        query, values = self.sqlite_db._build_search_query(params)
        self.assertEqual(query, "SELECT * FROM test_memories LIMIT 999999999")

        # 测试零 limit
        params = SearchParams(limit=0)
        query, values = self.sqlite_db._build_search_query(params)
        self.assertEqual(query, "SELECT * FROM test_memories LIMIT 0")

        # 测试负数 offset（虽然在实际使用中可能不合理）
        params = SearchParams(limit=10)
        query, values = self.sqlite_db._build_search_query(params, offset=-5)
        self.assertEqual(query, "SELECT * FROM test_memories LIMIT 10, -5")

    def test_query_building_result_validation(self) -> None:
        """测试查询构建结果的有效性"""
        params = SearchParams(
            fields=["id", "content"],
            where=["status = 'active'"],
            order_by="created_at DESC",
            limit=10
        )

        query, values = self.sqlite_db._build_search_query(params)

        # 验证返回值类型
        self.assertIsInstance(query, str)
        self.assertIsInstance(values, list)

        # 验证查询不为空
        self.assertNotEqual(query.strip(), "")

        # 验证值列表为空（因为我们使用字面量条件）
        self.assertEqual(values, [])

        # 验证查询包含所有预期组件
        self.assertIn("SELECT id, content", query)
        self.assertIn("FROM test_memories", query)
        self.assertIn("WHERE status = 'active'", query)
        self.assertIn("ORDER BY created_at DESC", query)
        self.assertIn("LIMIT 10", query)


if __name__ == "__main__":
    unittest.main()