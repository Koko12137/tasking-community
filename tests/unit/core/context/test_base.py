"""
核心上下文基础实现模块测试套件

测试 src.core.context.base 模块中的基础实现
"""

import unittest
from typing import Any

from tasking.core.context.base import BaseContext
from tasking.core.context.interface import IContext


class TestBaseContext(unittest.TestCase):
    """BaseContext 基础实现测试"""

    def setUp(self) -> None:
        """设置测试环境"""
        self.context = BaseContext()

    def test_basecontext_initialization(self) -> None:
        """测试 BaseContext 初始化"""
        # 验证继承关系
        self.assertIsInstance(self.context, IContext)
        self.assertIsInstance(self.context, BaseContext)

        # 验证初始状态
        self.assertEqual(len(list(self.context.keys())), 0)
        self.assertEqual(len(list(self.context.values())), 0)
        self.assertEqual(len(list(self.context.items())), 0)

    def test_set_and_get(self) -> None:
        """测试设置和获取值"""
        # 测试基本设置和获取
        self.context.set("key1", "value1")
        self.assertEqual(self.context.get("key1"), "value1")

        # 测试默认值
        self.assertEqual(self.context.get("nonexistent", "default"), "default")
        self.assertIsNone(self.context.get("nonexistent"))

        # 测试覆盖设置
        self.context.set("key1", "value2")
        self.assertEqual(self.context.get("key1"), "value2")

        # 测试不同类型的值
        self.context.set("number", 42)
        self.context.set("boolean", True)
        self.context.set("list", [1, 2, 3])
        self.context.set("dict", {"nested": "value"})

        self.assertEqual(self.context.get("number"), 42)
        self.assertEqual(self.context.get("boolean"), True)
        self.assertEqual(self.context.get("list"), [1, 2, 3])
        self.assertEqual(self.context.get("dict"), {"nested": "value"})

    def test_has(self) -> None:
        """测试键存在性检查"""
        # 测试空上下文
        self.assertFalse(self.context.has("any_key"))

        # 测试添加后的检查
        self.context.set("existing_key", "value")
        self.assertTrue(self.context.has("existing_key"))
        self.assertFalse(self.context.has("nonexistent_key"))

    def test_delete(self) -> None:
        """测试删除键值对"""
        # 测试删除存在的键
        self.context.set("key1", "value1")
        self.context.set("key2", "value2")

        self.assertTrue(self.context.has("key1"))
        self.context.delete("key1")
        self.assertFalse(self.context.has("key1"))
        self.assertTrue(self.context.has("key2"))

        # 测试删除不存在的键（不应该抛出错误）
        self.context.delete("nonexistent")  # 应该静默处理

    def test_clear(self) -> None:
        """测试清空上下文"""
        # 添加一些数据
        self.context.set("key1", "value1")
        self.context.set("key2", "value2")
        self.context.set("key3", "value3")

        self.assertEqual(len(list(self.context.keys())), 3)

        # 清空
        self.context.clear()
        self.assertEqual(len(list(self.context.keys())), 0)
        self.assertIsNone(self.context.get("key1"))

    def test_keys_values_items(self) -> None:
        """测试键、值、键值对迭代器"""
        # 添加测试数据
        test_data = {
            "key1": "value1",
            "key2": "value2",
            "key3": "value3"
        }

        for key, value in test_data.items():
            self.context.set(key, value)

        # 测试 keys
        keys = list(self.context.keys())
        self.assertEqual(len(keys), 3)
        for key in test_data:
            self.assertIn(key, keys)

        # 测试 values
        values = list(self.context.values())
        self.assertEqual(len(values), 3)
        for value in test_data.values():
            self.assertIn(value, values)

        # 测试 items
        items = list(self.context.items())
        self.assertEqual(len(items), 3)
        for key, value in test_data.items():
            self.assertIn((key, value), items)

        # 验证键值对的对应关系
        item_dict = dict(items)
        self.assertEqual(item_dict, test_data)

    def test_complex_keys(self) -> None:
        """测试复杂键类型"""
        # 测试字符串键
        self.context.set("string_key", "value")
        self.assertEqual(self.context.get("string_key"), "value")

        # 测试数字键
        self.context.set(42, "number_key_value")
        self.assertEqual(self.context.get(42), "number_key_value")

        # 测试元组键
        tuple_key = ("nested", "key")
        self.context.set(tuple_key, "tuple_key_value")
        self.assertEqual(self.context.get(tuple_key), "tuple_key_value")

    def test_none_values(self) -> None:
        """测试 None 值处理"""
        # 设置 None 值
        self.context.set("none_key", None)

        # has 应该返回 True（键存在）
        self.assertTrue(self.context.has("none_key"))

        # get 应该返回 None
        self.assertIsNone(self.context.get("none_key"))

        # 使用默认值测试
        self.assertEqual(self.context.get("none_key", "default"), None)
        self.assertEqual(self.context.get("nonexistent", "default"), "default")

    def test_context_isolation(self) -> None:
        """测试上下文实例隔离"""
        context1 = BaseContext()
        context2 = BaseContext()

        # 在 context1 中设置值
        context1.set("shared_key", "value1")
        context1.set("unique_key1", "unique1")

        # 在 context2 中设置值
        context2.set("shared_key", "value2")
        context2.set("unique_key2", "unique2")

        # 验证隔离性
        self.assertEqual(context1.get("shared_key"), "value1")
        self.assertEqual(context2.get("shared_key"), "value2")
        self.assertEqual(context1.get("unique_key1"), "unique1")
        self.assertEqual(context2.get("unique_key2"), "unique2")

        self.assertFalse(context1.has("unique_key2"))
        self.assertFalse(context2.has("unique_key1"))

    def test_large_data_handling(self) -> None:
        """测试大数据处理"""
        # 测试大量数据
        large_data = {f"key_{i}": f"value_{i}" for i in range(1000)}

        for key, value in large_data.items():
            self.context.set(key, value)

        # 验证数据完整性
        for key, expected_value in large_data.items():
            self.assertEqual(self.context.get(key), expected_value)

        # 验证计数
        self.assertEqual(len(list(self.context.keys())), 1000)

    def test_thread_safety_simulation(self) -> None:
        """模拟线程安全测试（单线程环境）"""
        # 快速连续操作，模拟并发访问
        operations = []
        for i in range(100):
            self.context.set(f"temp_key_{i}", f"temp_value_{i}")
            operations.append(("set", f"temp_key_{i}", f"temp_value_{i}"))

        # 验证所有操作都成功
        for i in range(100):
            expected_value = f"temp_value_{i}"
            actual_value = self.context.get(f"temp_key_{i}")
            self.assertEqual(actual_value, expected_value)


if __name__ == "__main__":
    unittest.main()