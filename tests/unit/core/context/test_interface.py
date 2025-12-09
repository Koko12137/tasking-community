"""
核心上下文接口模块测试套件

测试 src.core.context.interface 模块中的接口定义
"""

import unittest
from abc import ABC
from typing import Any

from tasking.core.context.interface import IContext


class TestContextInterface(unittest.TestCase):
    """上下文接口定义测试"""

    def test_icontext_interface(self) -> None:
        """测试 IContext 接口定义"""
        # 验证 IContext 是抽象基类
        self.assertTrue(issubclass(IContext, ABC))
        self.assertTrue(hasattr(IContext, '__abstractmethods__'))

        # 验证必需的抽象方法
        abstract_methods = IContext.__abstractmethods__
        expected_methods = {'get', 'set', 'has', 'delete', 'clear', 'keys', 'values', 'items'}
        self.assertEqual(abstract_methods, expected_methods)

    def test_icontext_method_names(self) -> None:
        """测试 IContext 方法名称"""
        expected_methods = [
            'get', 'set', 'has', 'delete', 'clear',
            'keys', 'values', 'items'
        ]

        for method_name in expected_methods:
            self.assertTrue(hasattr(IContext, method_name))
            self.assertTrue(callable(getattr(IContext, method_name)))

    def test_icontext_interface_documentation(self) -> None:
        """测试接口文档完整性"""
        # 验证接口有文档字符串
        self.assertIsNotNone(IContext.__doc__)
        self.assertIsInstance(IContext.__doc__, str)
        self.assertTrue(len(IContext.__doc__.strip()) > 0)

        # 验证主要方法有文档字符串
        for method_name in IContext.__abstractmethods__:
            method = getattr(IContext, method_name)
            if method.__doc__:
                self.assertTrue(len(method.__doc__.strip()) > 0)


if __name__ == "__main__":
    unittest.main()