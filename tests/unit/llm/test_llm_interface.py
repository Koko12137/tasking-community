"""
LLM接口模块测试套件

测试 src.llm.interface 模块中的LLM接口定义
"""

import unittest
from abc import ABC
from typing import Any

from tasking.llm.interface import ILLM, IEmbedModel


class TestILLMInterface(unittest.TestCase):
    """ILLM 接口定义测试"""

    def test_illm_interface(self) -> None:
        """测试 ILLM 接口定义"""
        # 验证 ILLM 是抽象基类
        self.assertTrue(issubclass(ILLM, ABC))
        self.assertTrue(hasattr(ILLM, '__abstractmethods__'))

        # 验证必需的抽象方法
        abstract_methods = ILLM.__abstractmethods__
        expected_methods = {'chat', 'get_model_name', 'get_config'}
        self.assertEqual(abstract_methods, expected_methods)

    def test_illm_method_names(self) -> None:
        """测试 ILLM 方法名称"""
        expected_methods = [
            'chat', 'get_model_name', 'get_config'
        ]

        for method_name in expected_methods:
            self.assertTrue(hasattr(ILLM, method_name))
            self.assertTrue(callable(getattr(ILLM, method_name)))

    def test_illm_interface_documentation(self) -> None:
        """测试接口文档完整性"""
        # 验证接口有文档字符串
        self.assertIsNotNone(ILLM.__doc__)
        self.assertIsInstance(ILLM.__doc__, str)
        self.assertTrue(len(ILLM.__doc__.strip()) > 0)


class TestIEmbedModelInterface(unittest.TestCase):
    """IEmbedModel 接口定义测试"""

    def test_iembed_model_interface(self) -> None:
        """测试 IEmbedModel 接口定义"""
        # 验证 IEmbedModel 是抽象基类
        self.assertTrue(issubclass(IEmbedModel, ABC))
        self.assertTrue(hasattr(IEmbedModel, '__abstractmethods__'))

        # 验证必需的抽象方法
        abstract_methods = IEmbedModel.__abstractmethods__
        expected_methods = {'embed', 'get_model_name', 'get_config', 'get_dimension'}
        self.assertEqual(abstract_methods, expected_methods)

    def test_iembed_model_method_names(self) -> None:
        """测试 IEmbedModel 方法名称"""
        expected_methods = [
            'embed', 'get_model_name', 'get_config', 'get_dimension'
        ]

        for method_name in expected_methods:
            self.assertTrue(hasattr(IEmbedModel, method_name))
            self.assertTrue(callable(getattr(IEmbedModel, method_name)))

    def test_iembed_model_interface_documentation(self) -> None:
        """测试接口文档完整性"""
        # 验证接口有文档字符串
        self.assertIsNotNone(IEmbedModel.__doc__)
        self.assertIsInstance(IEmbedModel.__doc__, str)
        self.assertTrue(len(IEmbedModel.__doc__.strip()) > 0)


if __name__ == "__main__":
    unittest.main()