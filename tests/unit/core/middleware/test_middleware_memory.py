"""
核心记忆中间件模块测试套件

测试 src.core.middleware.memory 模块中的记忆中间件功能
"""

import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from tasking.core.middleware.memory import IMemoryHooks
from tasking.model.memory import MemoryProtocol, MemoryT
from tasking.model.message import Message, Role
from tasking.model.queue import IQueue
from tasking.core.state_machine.task.interface import ITask
from typing import TypeVar

StateT = TypeVar('StateT')
EventT = TypeVar('EventT')


class MockMemory(MemoryProtocol):
    """模拟记忆对象"""

    def __init__(self, id: str, content: str) -> None:
        self.id = id
        self.content = content

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "content": self.content}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MockMemory":
        return cls(data["id"], data["content"])


class MockTask(ITask[StateT, EventT]):
    """模拟任务对象"""

    def __init__(self) -> None:
        self.state = None
        self.event = None

    async def run(self, context: dict[str, Any]) -> EventT:
        return self.event


class MockQueue(IQueue[Message]):
    """模拟消息队列"""

    def __init__(self) -> None:
        self.messages = []

    async def put(self, item: Message) -> None:
        self.messages.append(item)

    async def get(self) -> Message:
        if self.messages:
            return self.messages.pop(0)
        raise ValueError("Empty queue")

    async def empty(self) -> bool:
        return len(self.messages) == 0

    async def size(self) -> int:
        return len(self.messages)


class TestMemoryHooksInterface(unittest.TestCase):
    """记忆钩子接口测试"""

    def test_imemory_hooks_interface(self) -> None:
        """测试 IMemoryHooks 接口定义"""
        from abc import ABC

        # 验证是抽象基类
        self.assertTrue(issubclass(IMemoryHooks, ABC))
        self.assertTrue(hasattr(IMemoryHooks, '__abstractmethods__'))

        # 验证抽象方法
        abstract_methods = IMemoryHooks.__abstractmethods__
        expected_methods = {'pre_run_once_hook', 'post_run_once_hook'}
        self.assertEqual(abstract_methods, expected_methods)

    def test_imemory_hooks_method_signatures(self) -> None:
        """测试 IMemoryHooks 方法签名"""
        import inspect

        # 检查 pre_run_once_hook 方法签名
        pre_sig = inspect.signature(IMemoryHooks.pre_run_once_hook)
        params = list(pre_sig.parameters.keys())
        expected_params = ['self', 'context', 'queue', 'task']
        self.assertEqual(params, expected_params)

        # 检查 post_run_once_hook 方法签名
        post_sig = inspect.signature(IMemoryHooks.post_run_once_hook)
        params = list(post_sig.parameters.keys())
        expected_params = ['self', 'context', 'queue', 'task']
        self.assertEqual(params, expected_params)


class MockMemoryHooks(IMemoryHooks[MockMemory]):
    """模拟记忆钩子实现"""

    def __init__(self) -> None:
        self.pre_hook_called = False
        self.post_hook_called = False
        self.pre_hook_context = None
        self.post_hook_context = None
        self.pre_hook_queue = None
        self.post_hook_queue = None
        self.pre_hook_task = None
        self.post_hook_task = None

    async def pre_run_once_hook(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        """运行前钩子"""
        self.pre_hook_called = True
        self.pre_hook_context = context
        self.pre_hook_queue = queue
        self.pre_hook_task = task

    async def post_run_once_hook(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        """运行后钩子"""
        self.post_hook_called = True
        self.post_hook_context = context
        self.post_hook_queue = queue
        self.post_hook_task = task


class TestMemoryHooksImplementation(unittest.TestCase):
    """记忆钩子实现测试"""

    def setUp(self) -> None:
        """设置测试环境"""
        self.hooks = MockMemoryHooks()
        self.context = {"test_key": "test_value"}
        self.queue = MockQueue()
        self.task = MockTask()

    def test_hook_initialization(self) -> None:
        """测试钩子初始化"""
        self.assertIsInstance(self.hooks, IMemoryHooks)
        self.assertFalse(self.hooks.pre_hook_called)
        self.assertFalse(self.hooks.post_hook_called)

    async def test_pre_hook_execution(self) -> None:
        """测试前钩子执行"""
        await self.hooks.pre_run_once_hook(self.context, self.queue, self.task)

        # 验证钩子被调用
        self.assertTrue(self.hooks.pre_hook_called)
        self.assertFalse(self.hooks.post_hook_called)

        # 验证参数传递
        self.assertEqual(self.hooks.pre_hook_context, self.context)
        self.assertEqual(self.hooks.pre_hook_queue, self.queue)
        self.assertEqual(self.hooks.pre_hook_task, self.task)

    async def test_post_hook_execution(self) -> None:
        """测试后钩子执行"""
        await self.hooks.post_run_once_hook(self.context, self.queue, self.task)

        # 验证钩子被调用
        self.assertFalse(self.hooks.pre_hook_called)
        self.assertTrue(self.hooks.post_hook_called)

        # 验证参数传递
        self.assertEqual(self.hooks.post_hook_context, self.context)
        self.assertEqual(self.hooks.post_hook_queue, self.queue)
        self.assertEqual(self.hooks.post_hook_task, self.task)

    async def test_both_hooks_execution(self) -> None:
        """测试两个钩子都执行"""
        # 执行前钩子
        await self.hooks.pre_run_once_hook(self.context, self.queue, self.task)

        # 执行后钩子
        await self.hooks.post_run_once_hook(self.context, self.queue, self.task)

        # 验证两个钩子都被调用
        self.assertTrue(self.hooks.pre_hook_called)
        self.assertTrue(self.hooks.post_hook_called)

        # 验证参数一致
        self.assertEqual(self.hooks.pre_hook_context, self.hooks.post_hook_context)
        self.assertEqual(self.hooks.pre_hook_queue, self.hooks.post_hook_queue)
        self.assertEqual(self.hooks.pre_hook_task, self.hooks.post_hook_task)

    async def test_hook_with_different_contexts(self) -> None:
        """测试不同上下文下的钩子执行"""
        contexts = [
            {"key1": "value1"},
            {"key2": "value2", "nested": {"data": "test"}},
            {},
            {"list": [1, 2, 3]}
        ]

        for i, context in enumerate(contexts):
            await self.hooks.pre_run_once_hook(context, self.queue, self.task)

            # 验证上下文正确传递
            self.assertEqual(self.hooks.pre_hook_context, context)

            # 重置状态
            self.hooks.pre_hook_called = False
            self.hooks.pre_hook_context = None

    async def test_hook_error_handling(self) -> None:
        """测试钩子错误处理"""
        class ErrorMemoryHooks(IMemoryHooks[MockMemory]):
            def __init__(self, should_error: bool = False):
                self.should_error = should_error
                self.call_count = 0

            async def pre_run_once_hook(
                self,
                context: dict[str, Any],
                queue: IQueue[Message],
                task: ITask[StateT, EventT],
            ) -> None:
                self.call_count += 1
                if self.should_error:
                    raise RuntimeError("模拟钩子错误")

            async def post_run_once_hook(
                self,
                context: dict[str, Any],
                queue: IQueue[Message],
                task: ITask[StateT, EventT],
            ) -> None:
                self.call_count += 1
                if self.should_error:
                    raise RuntimeError("模拟钩子错误")

        # 测试正常执行
        normal_hooks = ErrorMemoryHooks(should_error=False)
        await normal_hooks.pre_run_once_hook(self.context, self.queue, self.task)
        self.assertEqual(normal_hooks.call_count, 1)

        # 测试错误抛出
        error_hooks = ErrorMemoryHooks(should_error=True)
        with self.assertRaises(RuntimeError):
            await error_hooks.pre_run_once_hook(self.context, self.queue, self.task)
        self.assertEqual(error_hooks.call_count, 1)

    async def test_hook_state_isolation(self) -> None:
        """测试钩子状态隔离"""
        hooks1 = MockMemoryHooks()
        hooks2 = MockMemoryHooks()

        # 在第一个钩子实例上执行
        await hooks1.pre_run_once_hook(self.context, self.queue, self.task)

        # 验证状态隔离
        self.assertTrue(hooks1.pre_hook_called)
        self.assertFalse(hooks2.pre_hook_called)

        # 在第二个钩子实例上执行
        await hooks2.pre_run_once_hook(self.context, self.queue, self.task)

        # 验证两个实例都有正确的状态
        self.assertTrue(hooks1.pre_hook_called)
        self.assertTrue(hooks2.pre_hook_called)
        self.assertEqual(hooks1.pre_hook_context, hooks2.pre_hook_context)


if __name__ == "__main__":
    unittest.main()