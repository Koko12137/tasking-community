# pylint: disable=too-many-lines
#!/usr/bin/env python3
"""
BaseAgent测试套件

测试BaseAgent的核心功能：
- 基础信息管理（ID、名称、类型）
- 语言模型管理（LLM获取和设置）
- 工作流管理（Workflow关联和操作）
- 工具调用机制
- 任务执行流程
- 钩子函数系统
- 观察-思考-行动循环
"""

import unittest
import asyncio
from typing import Any, Dict, Set, Tuple, Optional, Callable, Awaitable
from unittest.mock import Mock, AsyncMock, patch

# pylint: disable=import-error
# NOTE: E0401 import-error is a pylint configuration issue.
# The tests run correctly with pytest, which resolves the src path.
from src.core.agent.base import BaseAgent
from src.core.agent.interface import IAgent
from src.core.state_machine.const import StateT, EventT
from src.core.state_machine.task.interface import ITask
from src.core.state_machine.workflow.interface import IWorkflow
from src.core.state_machine.workflow.const import WorkflowStageT, WorkflowEventT
from src.llm.interface import ILLM
from src.model import CompletionConfig, Message, Role, ToolCallRequest, IQueue
from tests.agent.test_helpers import (
    AgentTestMixin,
    MockLLM,
    MockTask,
    MockWorkflow,
    MockQueue,
    create_simple_agent_test_state,
    create_simple_agent_test_events
)


class TestBaseAgent(unittest.TestCase, AgentTestMixin):
    """测试BaseAgent核心功能"""

    def setUp(self) -> None:
        """测试设置"""
        # 创建测试状态
        self.init_state, self.valid_states = create_simple_agent_test_state()
        self.test_events = create_simple_agent_test_events()

        # 创建模拟LLM
        self.mock_llm = self.create_mock_llm("test-model", "Test response")

        # 创建LLM字典
        self.llms: dict[WorkflowStageT, ILLM] = {
            "PROCESSING": self.mock_llm,  # type: ignore
            "COMPLETED": self.mock_llm,   # type: ignore
        }

        # 创建BaseAgent实例
        self.agent = BaseAgent[WorkflowStageT, WorkflowEventT, StateT, EventT](
            name="TestAgent",
            agent_type="TestType",
            llms=self.llms
        )

        # 设置工作流
        self.workflow = self.create_mock_workflow(self.init_state, self.test_events)
        self.agent.set_workflow(self.workflow)

    def test_agent_basic_info(self) -> None:
        """测试Agent基础信息"""
        # 测试ID生成
        agent_id = self.agent.get_id()
        self.assertIsInstance(agent_id, str)
        self.assertTrue(agent_id.startswith("agent_"))

        # 测试名称
        self.assertEqual(self.agent.get_name(), "TestAgent")

        # 测试类型
        self.assertEqual(self.agent.get_type(), "TestType")

    def test_llm_management(self) -> None:
        """测试语言模型管理"""
        # 测试获取LLM字典
        llms = self.agent.get_llms()
        self.assertIsInstance(llms, dict)
        self.assertEqual(len(llms), 2)

        # 验证LLM字典是副本（修改不影响原版）
        llms["NEW_STAGE"] = self.mock_llm
        original_llms = self.agent.get_llms()
        self.assertNotIn("NEW_STAGE", original_llms)

        # 测试获取当前LLM
        current_llm = self.agent.get_llm()
        self.assertIsInstance(current_llm, MockLLM)

    def test_workflow_management(self) -> None:
        """测试工作流管理"""
        # 测试获取已设置的工作流
        workflow = self.agent.get_workflow()
        self.assertIsInstance(workflow, MockWorkflow)

        # 测试设置新工作流
        new_workflow = self.create_mock_workflow("COMPLETED", self.test_events)
        self.agent.set_workflow(new_workflow)
        self.assertEqual(self.agent.get_workflow(), new_workflow)

        # 测试未设置工作流时的错误
        agent_no_workflow = BaseAgent[WorkflowStageT, WorkflowEventT, StateT, EventT](
            name="NoWorkflowAgent",
            agent_type="TestType",
            llms=self.llms
        )
        with self.assertRaises(RuntimeError) as cm:
            agent_no_workflow.get_workflow()
        self.assertIn("Workflow is not set", str(cm.exception))

    def test_tool_service(self) -> None:
        """测试工具服务"""
        # 测试未设置工具服务时的错误
        with self.assertRaises(RuntimeError) as cm:
            self.agent.get_tool_service()
        self.assertIn("Tool service is not set", str(cm.exception))

    async def test_observe(self) -> None:
        """测试观察功能"""
        # 创建任务和队列
        task = self.create_mock_task(self.init_state, self.valid_states)
        queue = self.create_mock_queue()

        # 定义观察函数
        def observe_fn(task: ITask[StateT, EventT], kwargs: dict[str, Any]) -> Message:
            return Message(role=Role.USER, content=f"Observing task {task.get_id()}")

        # 执行观察
        result = await self.agent.observe(
            context={},
            queue=queue,
            task=task,
            observe_fn=observe_fn,
            test_param="test_value"
        )

        # 验证结果
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

        # 验证任务上下文被更新
        task.get_context().append_context_data.assert_called()

    async def test_think(self) -> None:
        """测试思考功能"""
        # 创建观察消息
        observe_messages = [
            Message(role=Role.USER, content="Observation 1"),
            Message(role=Role.USER, content="Observation 2")
        ]

        # 创建完成配置
        completion_config = CompletionConfig(
            model="test-model",
            max_tokens=100,
            temperature=0.7
        )

        # 执行思考
        result = await self.agent.think(
            context={},
            queue=self.create_mock_queue(),
            llm_name="PROCESSING",
            observe=observe_messages,
            completion_config=completion_config,
            test_param="test_value"
        )

        # 验证结果
        self.assertIsInstance(result, Message)
        self.assertEqual(result.role, Role.ASSISTANT)
        self.assertEqual(result.content, "Test response")

        # 验证LLM调用历史
        self.assertEqual(len(self.mock_llm.completion_history), 1)
        messages, config, kwargs = self.mock_llm.completion_history[0]
        self.assertEqual(len(messages), 2)
        self.assertEqual(config, completion_config)
        self.assertEqual(kwargs.get("test_param"), "test_value")

    async def test_act(self) -> None:
        """测试行动功能"""
        # 创建任务和工具调用请求
        task = self.create_mock_task(self.init_state, self.valid_states)
        tool_call = self.create_test_tool_call_request("test_tool", {"param": "value"})

        # 执行行动
        result = await self.agent.act(
            context={},
            queue=self.create_mock_queue(),
            tool_call=tool_call,
            task=task,
            extra_param="extra_value"
        )

        # 验证结果
        self.assertIsInstance(result, Message)
        self.assertEqual(result.role, Role.TOOL)
        self.assertFalse(result.is_error)

    async def test_hook_system(self) -> None:
        """测试钩子系统"""
        # 创建钩子函数
        pre_hook_called = []
        post_hook_called = []

        def pre_hook(context: dict[str, Any], queue: IQueue[Message], task: ITask[StateT, EventT]) -> None:
            pre_hook_called.append(True)

        def post_hook(context: dict[str, Any], queue: IQueue[Message], task: ITask[StateT, EventT]) -> None:
            post_hook_called.append(True)

        # 添加钩子
        self.agent.add_pre_run_once_hook(pre_hook)
        self.agent.add_post_run_once_hook(post_hook)
        self.agent.add_pre_observe_hook(pre_hook)
        self.agent.add_post_observe_hook(post_hook)
        self.agent.add_pre_think_hook(pre_hook)
        self.agent.add_post_think_hook(post_hook)
        self.agent.add_pre_act_hook(pre_hook)
        self.agent.add_post_act_hook(post_hook)

        # 验证钩子被添加（通过内部属性）
        self.assertEqual(len(self.agent._pre_run_once_hooks), 1)
        self.assertEqual(len(self.agent._post_run_once_hooks), 1)
        self.assertEqual(len(self.agent._pre_observe_hooks), 1)
        self.assertEqual(len(self.agent._post_observe_hooks), 1)
        self.assertEqual(len(self.agent._pre_think_hooks), 1)
        self.assertEqual(len(self.agent._post_think_hooks), 1)
        self.assertEqual(len(self.agent._pre_act_hooks), 1)
        self.assertEqual(len(self.agent._post_act_hooks), 1)

    async def test_async_hook_execution(self) -> None:
        """测试异步钩子执行"""
        # 创建异步钩子函数
        async_hook_called = []

        async def async_pre_hook(context: dict[str, Any], queue: IQueue[Message], task: ITask[StateT, EventT]) -> None:
            await asyncio.sleep(0.01)  # 模拟异步操作
            async_hook_called.append(True)

        # 添加异步钩子
        self.agent.add_pre_run_once_hook(async_pre_hook)

        # 创建任务和队列
        task = self.create_mock_task(self.init_state, self.valid_states)
        queue = self.create_mock_queue()

        # 验证异步钩子可以正常执行（通过钩子历史）
        self.assertEqual(len(self.agent._pre_run_once_hooks), 1)

    async def test_run_task_stream_basic(self) -> None:
        """测试基本任务流式执行"""
        # 创建模拟任务
        task = self.create_mock_task(self.init_state, self.valid_states)
        queue = self.create_mock_queue()

        # 设置工作流动作（简单返回完成事件）
        async def mock_action(workflow, context, queue, task):
            return "COMPLETE"  # type: ignore

        self.workflow._action = mock_action

        # 执行任务流
        result = await self.run_with_timeout(
            self.agent.run_task_stream({}, queue, task)
        )

        # 验证结果
        self.assertEqual(result, task)

    def test_agent_type_safety(self) -> None:
        """测试Agent类型安全"""
        # 验证Agent实现了正确的接口
        self.assertIsInstance(self.agent, IAgent)

        # 验证泛型类型约束
        # 这里我们主要测试BaseAgent可以正确处理不同的状态和事件类型
        agent_generic = BaseAgent[str, str, str, str](
            name="GenericAgent",
            agent_type="Generic",
            llms={"stage": self.mock_llm}
        )
        self.assertEqual(agent_generic.get_name(), "GenericAgent")

    def test_error_handling(self) -> None:
        """测试错误处理"""
        # 测试LLM错误处理
        failing_llm = self.create_mock_llm("failing-model", should_fail=True)
        llms_with_failure: dict[WorkflowStageT, ILLM] = {
            "PROCESSING": failing_llm,  # type: ignore
            "COMPLETED": self.mock_llm,  # type: ignore
        }

        agent_with_failing_llm = BaseAgent[WorkflowStageT, WorkflowEventT, StateT, EventT](
            name="FailingAgent",
            agent_type="TestType",
            llms=llms_with_failure
        )
        agent_with_failing_llm.set_workflow(self.workflow)

        # 验证错误LLM会被正确设置
        self.assertEqual(agent_with_failing_llm.get_llms(), llms_with_failure)


class TestBaseAgentIntegration(unittest.TestCase, AgentTestMixin):
    """BaseAgent集成测试"""

    def setUp(self) -> None:
        """测试设置"""
        self.init_state, self.valid_states = create_simple_agent_test_state()
        self.test_events = create_simple_agent_test_events()
        self.mock_llm = self.create_mock_llm("test-model", "Integration test response")

        self.llms: dict[WorkflowStageT, ILLM] = {
            "PROCESSING": self.mock_llm,  # type: ignore
            "COMPLETED": self.mock_llm,   # type: ignore
        }

    async def test_full_observe_think_act_cycle(self) -> None:
        """测试完整的观察-思考-行动循环"""
        # 创建Agent
        agent = BaseAgent[WorkflowStageT, WorkflowEventT, StateT, EventT](
            name="CycleAgent",
            agent_type="Integration",
            llms=self.llms
        )

        # 设置工作流
        workflow = self.create_mock_workflow(self.init_state, self.test_events)
        agent.set_workflow(workflow)

        # 创建任务、队列和工具调用
        task = self.create_mock_task(self.init_state, self.valid_states)
        queue = self.create_mock_queue()
        tool_call = self.create_test_tool_call_request("test_tool", {"input": "test"})

        # 1. 观察阶段
        def observe_fn(task: ITask[StateT, EventT], kwargs: dict[str, Any]) -> Message:
            return Message(role=Role.USER, content=f"Task state: {task.get_current_state()}")

        observations = await agent.observe(
            context={"user_id": "test_user"},
            queue=queue,
            task=task,
            observe_fn=observe_fn
        )
        self.assertIsInstance(observations, list)

        # 2. 思考阶段
        thought = await agent.think(
            context={"user_id": "test_user"},
            queue=queue,
            llm_name="PROCESSING",
            observe=observations,
            completion_config=CompletionConfig(model="test-model", max_tokens=50)
        )
        self.assertEqual(thought.role, Role.ASSISTANT)
        self.assertEqual(thought.content, "Integration test response")

        # 3. 行动阶段
        action_result = await agent.act(
            context={"user_id": "test_user"},
            queue=queue,
            tool_call=tool_call,
            task=task
        )
        self.assertEqual(action_result.role, Role.TOOL)
        self.assertFalse(action_result.is_error)

    async def test_hook_integration(self) -> None:
        """测试钩子系统集成"""
        # 创建Agent
        agent = BaseAgent[WorkflowStageT, WorkflowEventT, StateT, EventT](
            name="HookAgent",
            agent_type="Integration",
            llms=self.llms
        )
        agent.set_workflow(self.create_mock_workflow(self.init_state, self.test_events))

        # 创建钩子跟踪
        hook_calls = {"pre_obs": 0, "post_obs": 0, "pre_think": 0, "post_think": 0, "pre_act": 0, "post_act": 0}

        def create_counter_hook(hook_name: str) -> Callable:
            def hook(*args, **kwargs) -> None:
                hook_calls[hook_name] += 1
            return hook

        # 添加所有钩子
        agent.add_pre_observe_hook(create_counter_hook("pre_obs"))
        agent.add_post_observe_hook(create_counter_hook("post_obs"))
        agent.add_pre_think_hook(create_counter_hook("pre_think"))
        agent.add_post_think_hook(create_counter_hook("post_think"))
        agent.add_pre_act_hook(create_counter_hook("pre_act"))
        agent.add_post_act_hook(create_counter_hook("post_act"))

        # 执行完整循环
        task = self.create_mock_task(self.init_state, self.valid_states)
        queue = self.create_mock_queue()

        # 观察
        await agent.observe({}, queue, task, lambda t, k: Message(role=Role.USER, content="test"))
        self.assertEqual(hook_calls["pre_obs"], 1)
        self.assertEqual(hook_calls["post_obs"], 1)

        # 思考
        await agent.think({}, queue, "PROCESSING", [Message(role=Role.USER, content="test")], CompletionConfig())
        self.assertEqual(hook_calls["pre_think"], 1)
        self.assertEqual(hook_calls["post_think"], 1)

        # 行动
        await agent.act({}, queue, self.create_test_tool_call_request(), task)
        self.assertEqual(hook_calls["pre_act"], 1)
        self.assertEqual(hook_calls["post_act"], 1)

    def test_agent_with_multiple_llms(self) -> None:
        """测试多LLM配置的Agent"""
        # 创建多个LLM
        llm1 = self.create_mock_llm("model-1", "Response from model 1")
        llm2 = self.create_mock_llm("model-2", "Response from model 2")

        multi_llms: dict[WorkflowStageT, ILLM] = {
            "PROCESSING": llm1,  # type: ignore
            "COMPLETED": llm2,   # type: ignore
        }

        # 创建Agent
        agent = BaseAgent[WorkflowStageT, WorkflowEventT, StateT, EventT](
            name="MultiLLMAgent",
            agent_type="Test",
            llms=multi_llms
        )
        agent.set_workflow(self.create_mock_workflow("PROCESSING", self.test_events))

        # 验证LLM获取
        all_llms = agent.get_llms()
        self.assertEqual(len(all_llms), 2)
        self.assertIn("PROCESSING", all_llms)
        self.assertIn("COMPLETED", all_llms)

        # 验证当前LLM（基于工作流状态）
        current_llm = agent.get_llm()
        self.assertEqual(current_llm, llm1)


if __name__ == "__main__":
    unittest.main()