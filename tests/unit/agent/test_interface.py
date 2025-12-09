#!/usr/bin/env python3
"""
Agent接口测试套件

测试IAgent接口的定义和契约：
- 接口方法签名验证
- 抽象方法验证
- 泛型类型约束验证
- 接口实现验证
"""

import unittest
from typing import Any, Dict, Set, Tuple, Optional, Callable, Awaitable
from abc import ABC, abstractmethod

# pylint: disable=import-error
# NOTE: E0401 import-error is a pylint configuration issue.
# The tests run correctly with pytest, which resolves the src path.
from tasking.core.agent.interface import IAgent
from tasking.core.state_machine.task.interface import ITask
from tasking.core.state_machine.workflow.interface import IWorkflow
from tasking.core.agent.react import ReActStage, ReActEvent
from tasking.llm.interface import ILLM
from tasking.model import CompletionConfig, Message, Role, ToolCallRequest, IQueue
from tests.unit.agent.test_helpers import AgentTestMixin, TestState, TestEvent


class TestIAgentInterface(unittest.TestCase, AgentTestMixin):
    """测试IAgent接口定义"""

    def test_interface_is_abstract(self) -> None:
        """验证IAgent是抽象基类"""
        self.assertTrue(issubclass(IAgent, ABC))

        # 验证不能直接实例化接口
        with self.assertRaises(TypeError) as cm:
            IAgent()  # type: ignore

        self.assertIn("abstract", str(cm.exception))

    def test_interface_method_signatures(self) -> None:
        """验证接口方法签名的存在性"""
        # 获取接口所有抽象方法
        abstract_methods = IAgent.__abstractmethods__

        # 验证必需的抽象方法存在
        required_methods = {
            'get_id', 'get_name', 'get_type',
            'get_llm', 'get_llms',
            'get_workflow', 'set_workflow',
            'get_tool_service',
            'call_tool',
            'run_task_stream',
            'add_pre_run_once_hook', 'add_post_run_once_hook',
            'observe',
            'add_pre_observe_hook', 'add_post_observe_hook',
            'think',
            'add_pre_think_hook', 'add_post_think_hook',
            'act',
            'add_pre_act_hook', 'add_post_act_hook'
        }

        self.assertEqual(abstract_methods, required_methods)

    def test_generic_type_parameters(self) -> None:
        """验证泛型类型参数"""
        # 检查IAgent是否正确使用泛型
        from typing import Generic

        self.assertTrue(hasattr(IAgent, '__orig_bases__'))

        # 验证类型参数（这个检查可能在Python中比较复杂，我们主要验证接口可以正确使用）
        # 这里我们主要验证接口可以正确使用不同的类型参数

    def test_interface_contract_compliance(self) -> None:
        """验证接口契约符合性"""
        # 创建一个最小的实现类来测试接口契约
        class MinimalAgent(IAgent[ReActStage, ReActEvent, TestState, TestEvent, Any]):
            def __init__(self):
                pass

            # 基础信息
            def get_id(self) -> str:
                return "test-id"

            def get_name(self) -> str:
                return "TestAgent"

            def get_type(self) -> str:
                return "TestType"

            # 语言模型信息
            def get_llm(self) -> ILLM:
                raise NotImplementedError

            def get_llms(self) -> dict[ReActStage, ILLM]:
                return {}

            # 工作流管理
            def get_workflow(self) -> IWorkflow[ReActStage, ReActEvent, TestState, TestEvent]:
                raise NotImplementedError

            def set_workflow(self, workflow: IWorkflow[ReActStage, ReActEvent, TestState, TestEvent]) -> None:
                pass

            def get_tool_service(self):
                raise NotImplementedError

            async def call_tool(self, name: str, task: ITask[TestState, TestEvent], inject: dict[str, Any], kwargs: dict[str, Any]) -> Message:
                raise NotImplementedError

            # 任务执行
            async def run_task_stream(self, context: dict[str, Any], queue: IQueue[Message], task: ITask[TestState, TestEvent]) -> ITask[TestState, TestEvent]:
                return task

            def add_pre_run_once_hook(self, hook: Callable[[dict[str, Any], IQueue[Message], ITask[TestState, TestEvent]], Awaitable[None] | None]) -> None:
                pass

            def add_post_run_once_hook(self, hook: Callable[[dict[str, Any], IQueue[Message], ITask[TestState, TestEvent]], Awaitable[None] | None]) -> None:
                pass

            # 运行时能力
            async def observe(self, context: dict[str, Any], queue: IQueue[Message], task: ITask[TestState, TestEvent], observe_fn: Callable[[ITask[TestState, TestEvent], dict[str, Any]], Message], **kwargs: Any) -> list[Message]:
                return []

            def add_pre_observe_hook(self, hook: Callable[[dict[str, Any], IQueue[Message], ITask[TestState, TestEvent]], Awaitable[None] | None]) -> None:
                pass

            def add_post_observe_hook(self, hook: Callable[[dict[str, Any], IQueue[Message], ITask[TestState, TestEvent], list[Message]], Awaitable[None] | None]) -> None:
                pass

            async def think(self, context: dict[str, Any], queue: IQueue[Message], llm_name: str, observe: list[Message], completion_config: CompletionConfig, **kwargs: Any) -> Message:
                return Message(role=Role.ASSISTANT, content="test")

            def add_pre_think_hook(self, hook: Callable[[dict[str, Any], IQueue[Message], list[Message]], Awaitable[None] | None]) -> None:
                pass

            def add_post_think_hook(self, hook: Callable[[dict[str, Any], IQueue[Message], list[Message], Message], Awaitable[None] | None]) -> None:
                pass

            async def act(self, context: dict[str, Any], queue: IQueue[Message], tool_call: ToolCallRequest, task: ITask[TestState, TestEvent], **kwargs: Any) -> Message:
                return Message(role=Role.TOOL, content="test result")

            def add_pre_act_hook(self, hook: Callable[[dict[str, Any], IQueue[Message], ITask[TestState, TestEvent]], Awaitable[None] | None]) -> None:
                pass

            def add_post_act_hook(self, hook: Callable[[dict[str, Any], IQueue[Message], ITask[TestState, TestEvent], Message], Awaitable[None] | None]) -> None:
                pass

        # 验证可以实例化最小实现
        agent = MinimalAgent()
        self.assertIsInstance(agent, IAgent)

    def test_interface_method_return_types(self) -> None:
        """验证接口方法的返回类型注解"""
        import inspect

        # 检查基础信息方法的返回类型
        get_id_sig = inspect.signature(IAgent.get_id)
        self.assertEqual(get_id_sig.return_annotation, str)

        get_name_sig = inspect.signature(IAgent.get_name)
        self.assertEqual(get_name_sig.return_annotation, str)

        get_type_sig = inspect.signature(IAgent.get_type)
        self.assertEqual(get_type_sig.return_annotation, str)

    def test_interface_method_parameter_types(self) -> None:
        """验证接口方法的参数类型注解"""
        import inspect

        # 检查钩子方法的参数类型
        pre_run_hook_sig = inspect.signature(IAgent.add_pre_run_once_hook)
        hook_param = pre_run_hook_sig.parameters['hook']
        # 这里我们主要验证参数存在，具体类型注解的检查比较复杂


class TestInterfaceTypeSafety(unittest.TestCase):
    """测试接口类型安全性"""

    def test_interface_with_different_type_parameters(self) -> None:
        """验证接口可以处理不同的类型参数"""
        # 这里我们验证接口可以正确使用不同的具体类型
        # 实际的类型检查在运行时可能不太容易验证，我们主要验证接口的泛型结构

        # 创建使用不同类型参数的接口类型别名
        SimpleAgent = IAgent[ReActStage, ReActEvent, TestState, TestEvent, Any]

        # 验证类型别名是有效的
        self.assertTrue(callable(SimpleAgent))

    def test_interface_inheritance_structure(self) -> None:
        """验证接口继承结构"""
        # 验证IAgent继承了ABC
        from abc import ABC
        self.assertTrue(issubclass(IAgent, ABC))

    def test_interface_method_count(self) -> None:
        """验证接口方法数量完整性"""
        abstract_methods = IAgent.__abstractmethods__

        # 验证方法数量符合预期
        expected_method_count = 21  # 根据接口定义，应该有21个抽象方法
        actual_method_count = len(abstract_methods)

        self.assertEqual(actual_method_count, expected_method_count,
                        f"Expected {expected_method_count} methods, got {actual_method_count}: {abstract_methods}")


class TestInterfaceDocumentation(unittest.TestCase):
    """测试接口文档完整性"""

    def test_interface_docstring(self) -> None:
        """验证接口文档字符串"""
        # IAgent接口应该有文档字符串
        doc = IAgent.__doc__
        self.assertIsNotNone(doc)
        if doc:  # type: ignore
            self.assertIn("Agent接口定义", doc)

    def test_method_documentation(self) -> None:
        """验证方法文档字符串"""
        # 检查关键方法是否有文档
        methods_to_check = [
            'get_id', 'get_name', 'get_type',
            'get_llm', 'get_llms', 'get_workflow', 'set_workflow',
            'call_tool', 'run_task_stream', 'observe', 'think', 'act'
        ]

        for method_name in methods_to_check:
            method = getattr(IAgent, method_name)
            self.assertIsNotNone(method.__doc__, f"Method {method_name} should have docstring")


if __name__ == "__main__":
    unittest.main()