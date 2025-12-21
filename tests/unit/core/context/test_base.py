"""
核心上下文基础实现模块测试套件

测试 tasking.core.context.base 模块中的上下文基础实现
"""

import unittest
from typing import Any

from tasking.core.context import BaseContext, IContext
from tasking.model import Message, Role, TextBlock


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

        # 验证初始状态为空列表
        self.assertEqual(len(self.context.get_context_data()), 0)

    def test_get_context_data(self) -> None:
        """测试获取上下文数据"""
        # 初始状态应该返回空列表
        self.assertEqual(self.context.get_context_data(), [])

        # 添加消息后应该返回包含消息的列表
        message = Message(role=Role.USER, content=[TextBlock(text="Hello")])
        self.context.append_context_data(message)

        context_data = self.context.get_context_data()
        self.assertEqual(len(context_data), 1)
        self.assertEqual(context_data[0].role, Role.USER)
        self.assertEqual(context_data[0].content[0].text, "Hello")

    def test_append_context_data_user_message(self) -> None:
        """测试添加用户消息"""
        message = Message(role=Role.USER, content=[TextBlock(text="User message")])

        self.context.append_context_data(message)
        context_data = self.context.get_context_data()

        self.assertEqual(len(context_data), 1)
        self.assertEqual(context_data[0], message)

    def test_append_context_data_system_message(self) -> None:
        """测试添加系统消息"""
        message = Message(role=Role.SYSTEM, content=[TextBlock(text="System message")])

        self.context.append_context_data(message)
        context_data = self.context.get_context_data()

        self.assertEqual(len(context_data), 1)
        self.assertEqual(context_data[0], message)

    def test_append_context_data_assistant_message(self) -> None:
        """测试添加助手消息"""
        # 先添加用户消息
        user_message = Message(role=Role.USER, content=[TextBlock(text="User message")])
        self.context.append_context_data(user_message)

        # 然后添加助手消息
        assistant_message = Message(role=Role.ASSISTANT, content=[TextBlock(text="Assistant response")])
        self.context.append_context_data(assistant_message)

        context_data = self.context.get_context_data()
        self.assertEqual(len(context_data), 2)
        self.assertEqual(context_data[1], assistant_message)

    def test_append_context_data_tool_message(self) -> None:
        """测试添加工具消息"""
        # 添加用户消息
        user_message = Message(role=Role.USER, content=[TextBlock(text="User message")])
        self.context.append_context_data(user_message)

        # 添加助手消息
        assistant_message = Message(role=Role.ASSISTANT, content=[TextBlock(text="Assistant response")])
        self.context.append_context_data(assistant_message)

        # 添加工具消息
        tool_message = Message(role=Role.TOOL, content=[TextBlock(text="Tool result")])
        self.context.append_context_data(tool_message)

        context_data = self.context.get_context_data()
        self.assertEqual(len(context_data), 3)
        self.assertEqual(context_data[2], tool_message)

    def test_message_order_validation_system_after_user(self) -> None:
        """测试消息顺序验证：系统消息不能接在用户消息后面"""
        # 添加用户消息
        user_message = Message(role=Role.USER, content=[TextBlock(text="User message")])
        self.context.append_context_data(user_message)

        # 尝试添加系统消息应该失败
        system_message = Message(role=Role.SYSTEM, content=[TextBlock(text="System message")])
        with self.assertRaises(ValueError, msg="系统消息不能接在用户/助手/工具消息后面"):
            self.context.append_context_data(system_message)

    def test_message_order_validation_assistant_without_user(self) -> None:
        """测试消息顺序验证：助手消息在空上下文中应该被允许（当前实现）"""
        # 当前实现允许助手消息作为第一条消息
        assistant_message = Message(role=Role.ASSISTANT, content=[TextBlock(text="Assistant response")])
        self.context.append_context_data(assistant_message)

        # 验证消息被添加
        context_data = self.context.get_context_data()
        self.assertEqual(len(context_data), 1)
        self.assertEqual(context_data[0], assistant_message)

    def test_message_order_validation_tool_without_assistant(self) -> None:
        """测试消息顺序验证：工具消息必须接在助手消息后面"""
        # 添加用户消息
        user_message = Message(role=Role.USER, content=[TextBlock(text="User message")])
        self.context.append_context_data(user_message)

        # 尝试直接添加工具消息应该失败
        tool_message = Message(role=Role.TOOL, content=[TextBlock(text="Tool result")])
        with self.assertRaises(ValueError, msg="工具消息只能接在助手消息后面"):
            self.context.append_context_data(tool_message)

    def test_clear_context_data(self) -> None:
        """测试清空上下文数据"""
        # 添加一些消息
        message1 = Message(role=Role.USER, content=[TextBlock(text="First message")])
        message2 = Message(role=Role.ASSISTANT, content=[TextBlock(text="Second message")])

        self.context.append_context_data(message1)
        self.context.append_context_data(message2)

        # 验证消息存在
        self.assertEqual(len(self.context.get_context_data()), 2)

        # 清空上下文
        self.context.clear_context_data()

        # 验证上下文已清空
        self.assertEqual(len(self.context.get_context_data()), 0)

    def test_context_isolation(self) -> None:
        """测试上下文实例隔离"""
        context1 = BaseContext()
        context2 = BaseContext()

        # 在 context1 中添加消息
        message1 = Message(role=Role.USER, content=[TextBlock(text="Context 1 message")])
        context1.append_context_data(message1)

        # 在 context2 中添加不同的消息
        message2 = Message(role=Role.USER, content=[TextBlock(text="Context 2 message")])
        context2.append_context_data(message2)

        # 验证两个上下文互不影响
        self.assertEqual(len(context1.get_context_data()), 1)
        self.assertEqual(len(context2.get_context_data()), 1)
        self.assertEqual(context1.get_context_data()[0].content[0].text, "Context 1 message")
        self.assertEqual(context2.get_context_data()[0].content[0].text, "Context 2 message")

    def test_large_context_handling(self) -> None:
        """测试大量上下文数据处理"""
        # 添加大量消息
        for i in range(100):
            if i % 2 == 0:
                # 偶数索引：用户消息
                message = Message(role=Role.USER, content=[TextBlock(text=f"User message {i}")])
            else:
                # 奇数索引：助手消息
                message = Message(role=Role.ASSISTANT, content=[TextBlock(text=f"Assistant message {i}")])

            self.context.append_context_data(message)

        # 验证所有消息都正确存储
        self.assertEqual(len(self.context.get_context_data()), 100)

        # 验证特定索引的消息
        context_data = self.context.get_context_data()
        self.assertEqual(context_data[0].content[0].text, "User message 0")
        self.assertEqual(context_data[1].content[0].text, "Assistant message 1")
        self.assertEqual(context_data[98].content[0].text, "User message 98")
        self.assertEqual(context_data[99].content[0].text, "Assistant message 99")


if __name__ == "__main__":
    unittest.main()