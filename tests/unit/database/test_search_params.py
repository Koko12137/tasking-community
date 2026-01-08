"""
SQLite SearchParams 类单元测试

测试 SearchParams 数据类的初始化、默认值处理和参数验证
"""

import unittest
from typing import Any

from tasking.database.sqlite import SearchParams


class TestSearchParams(unittest.TestCase):
    """SearchParams 数据类测试"""

    def test_default_initialization(self) -> None:
        """测试 SearchParams 默认初始化"""
        # 创建无参数的 SearchParams 实例
        params = SearchParams()

        # 验证所有字段默认值为 None
        self.assertIsNone(params.fields)
        self.assertIsNone(params.where)
        self.assertIsNone(params.order_by)
        self.assertIsNone(params.limit)
        self.assertIsNone(params.filters)

    def test_partial_initialization(self) -> None:
        """测试 SearchParams 部分参数初始化"""
        # 只设置部分参数
        params = SearchParams(
            fields=["id", "content"],
            limit=10
        )

        # 验证设置的参数正确
        self.assertEqual(params.fields, ["id", "content"])
        self.assertEqual(params.limit, 10)

        # 验证未设置的参数为 None
        self.assertIsNone(params.where)
        self.assertIsNone(params.order_by)
        self.assertIsNone(params.filters)

    def test_full_initialization(self) -> None:
        """测试 SearchParams 完整参数初始化"""
        fields = ["id", "content", "created_at"]
        where = ["status = 'active'", "created_at > '2024-01-01'"]
        order_by = "created_at DESC"
        limit = 50
        filters = {"category": "work", "priority": "high"}

        params = SearchParams(
            fields=fields,
            where=where,
            order_by=order_by,
            limit=limit,
            filters=filters
        )

        # 验证所有参数正确设置
        self.assertEqual(params.fields, fields)
        self.assertEqual(params.where, where)
        self.assertEqual(params.order_by, order_by)
        self.assertEqual(params.limit, limit)
        self.assertEqual(params.filters, filters)

    def test_empty_list_initialization(self) -> None:
        """测试空列表参数初始化"""
        params = SearchParams(
            fields=[],
            where=[],
            filters={}
        )

        # 验证空列表和空字典被正确存储
        self.assertEqual(params.fields, [])
        self.assertEqual(params.where, [])
        self.assertEqual(params.filters, {})

        # 验证其他参数仍为 None
        self.assertIsNone(params.order_by)
        self.assertIsNone(params.limit)

    def test_immutability(self) -> None:
        """测试 SearchParams 的不可变性"""
        params = SearchParams(
            fields=["id", "content"],
            limit=10
        )

        # 验证 SearchParams 是可变的（因为不是 frozen dataclass）
        # 这允许在测试中修改参数
        params.fields = ["id"]
        params.limit = 20

        self.assertEqual(params.fields, ["id"])
        self.assertEqual(params.limit, 20)

    def test_type_validation(self) -> None:
        """测试参数类型验证（pydantic BaseModel 会进行类型验证）"""
        from pydantic import ValidationError

        # pydantic BaseModel 会进行严格的类型检查，错误类型会抛出 ValidationError
        with self.assertRaises(ValidationError):
            SearchParams(
                fields="not_a_list",  # type: ignore[arg-type] # 故意传入错误类型测试验证
                where=123,            # type: ignore[arg-type] # 故意传入错误类型测试验证
                limit="not_a_number", # type: ignore[arg-type] # 故意传入错误类型测试验证
                filters="not_a_dict"  # type: ignore[arg-type] # 故意传入错误类型测试验证
            )

        # 正确的类型应该可以正常工作
        params = SearchParams(
            fields=["id", "content"],
            where=["status = 'active'"],
            limit=10,
            filters={"key": "value"}
        )
        self.assertEqual(params.fields, ["id", "content"])
        self.assertEqual(params.where, ["status = 'active'"])
        self.assertEqual(params.limit, 10)
        self.assertEqual(params.filters, {"key": "value"})

    def test_equality(self) -> None:
        """测试 SearchParams 对象相等性比较"""
        params1 = SearchParams(
            fields=["id", "content"],
            limit=10
        )

        params2 = SearchParams(
            fields=["id", "content"],
            limit=10
        )

        params3 = SearchParams(
            fields=["id", "content"],
            limit=20  # 不同的 limit
        )

        # 验证相同参数的对象相等
        self.assertEqual(params1, params2)

        # 验证不同参数的对象不相等
        self.assertNotEqual(params1, params3)

        # 验证与不同类型对象不相等
        self.assertNotEqual(params1, "not_a_search_params")

    def test_repr(self) -> None:
        """测试 SearchParams 字符串表示"""
        params = SearchParams(
            fields=["id", "content"],
            limit=10
        )

        repr_str = repr(params)

        # 验证字符串表示包含字段名和值
        self.assertIn("SearchParams", repr_str)
        self.assertIn("fields=", repr_str)
        self.assertIn("limit=10", repr_str)

    def test_complex_data_types(self) -> None:
        """测试复杂数据类型参数"""
        complex_filters = {
            "nested_dict": {"key": "value"},
            "list_value": [1, 2, 3],
            "boolean": True,
            "none_value": None
        }

        complex_where = [
            "status IN ('active', 'pending')",
            "created_at > DATE('2024-01-01')",
            "metadata->>'type' = 'document'"
        ]

        params = SearchParams(
            filters=complex_filters,
            where=complex_where
        )

        # 验证复杂数据类型被正确存储
        self.assertEqual(params.filters, complex_filters)
        self.assertEqual(params.where, complex_where)

    def test_edge_cases(self) -> None:
        """测试边界情况"""
        # 测试零值
        params = SearchParams(limit=0)
        self.assertEqual(params.limit, 0)

        # 测试负数
        params = SearchParams(limit=-1)
        self.assertEqual(params.limit, -1)

        # 测试空字符串
        params = SearchParams(order_by="")
        self.assertEqual(params.order_by, "")

        # 测试布尔值
        params = SearchParams(filters={"active": True, "deleted": False})
        self.assertEqual(params.filters, {"active": True, "deleted": False})


if __name__ == "__main__":
    unittest.main()