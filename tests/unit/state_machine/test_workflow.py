#!/usr/bin/env python3
"""
工作流测试套件

测试工作流（Workflow）相关的功能：
- BaseWorkflow: 基础工作流实现
- ReActStage 和 ReActEvent: ReAct 模式的状态和事件
- 工作流状态转换和生命周期管理
"""

import unittest
from typing import Dict, Callable, Any, Awaitable
from unittest.mock import Mock
from queue import Queue

from fastmcp.tools import Tool as FastMcpTool

from tasking.core.state_machine.workflow.base import BaseWorkflow
from tasking.core.agent.reflect import ReflectStage, ReflectEvent
from tasking.core.agent.react import ReActStage, ReActEvent
from tasking.core.state_machine.workflow.interface import IWorkflow
from tasking.core.state_machine.task.interface import ITask
from tasking.core.state_machine.task.const import TaskState, TaskEvent
from tasking.model import Message, Role, CompletionConfig

# Type aliases for complex types
ReActTransition = tuple[
    ReflectStage,
    Callable[
        [IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent]],
        Awaitable[None] | None
    ] | None
]
ReActTransitionMap = dict[tuple[ReflectStage, ReflectEvent], ReActTransition]


class TestBaseWorkflow(unittest.IsolatedAsyncioTestCase):
    """测试 BaseWorkflow 核心功能"""

    def setUp(self) -> None:
        """测试设置"""
        # 创建模拟的end_workflow工具
        self.end_workflow_tool = Mock(spec=FastMcpTool)
        self.end_workflow_tool.name = "end_workflow"

        # 创建状态转换
        self.transitions: ReActTransitionMap = {
            (ReflectStage.REASONING, ReflectEvent.REASON): (ReflectStage.REASONING, None),
            (ReflectStage.REASONING, ReflectEvent.REFLECT): (ReflectStage.REFLECTING, None),
            (ReflectStage.REFLECTING, ReflectEvent.FINISH): (ReflectStage.REASONING, None),
        }

        # 创建完成配置
        completion_config = CompletionConfig(
            temperature=0.7,
            max_tokens=1000
        )

        # 创建工作流
        self.workflow = BaseWorkflow[
            ReflectStage,  # WorkflowStageT
            ReflectEvent,  # WorkflowEventT
            TaskState,   # StateT
            TaskEvent    # EventT
        ](
            valid_states={ReflectStage.REASONING, ReflectStage.REFLECTING},
            init_state=ReflectStage.REASONING,
            transitions=self.transitions,
            name="test_workflow",
            completion_configs={
                ReflectStage.REASONING: completion_config,
                ReflectStage.REFLECTING: completion_config,
            },
            actions={
                ReflectStage.REASONING: self._mock_action,
                ReflectStage.REFLECTING: self._mock_action,
            },
            prompts={
                ReflectStage.REASONING: "Reason about the task",
                ReflectStage.REFLECTING: "Reflect on the result",
            },
            observe_funcs={
                ReflectStage.REASONING: self._mock_observe,
                ReflectStage.REFLECTING: self._mock_observe,
            },
            event_chain=[ReflectEvent.REASON, ReflectEvent.REFLECT, ReflectEvent.FINISH],
            tools=None
        )

    async def _mock_action(
        self,
        _workflow: IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
        _context: Dict[str, Any],
        _queue: Queue[Message],
        _task: ITask[TaskState, TaskEvent]
    ) -> ReflectEvent:
        """模拟工作流动作"""
        return ReflectEvent.FINISH

    def _mock_observe(
        self,
        _task: ITask[TaskState, TaskEvent],
        _context: Dict[str, Any]
    ) -> Message:
        """模拟观察函数"""
        return Message(role=Role.ASSISTANT, content="Observation")

    async def test_workflow_initialization(self) -> None:
        """测试工作流初始化"""
        # 检查基本属性
        self.assertIsNotNone(self.workflow)
        self.assertEqual(self.workflow.get_name(), "test_workflow")

    async def test_workflow_stage_properties(self) -> None:
        """测试工作流阶段属性"""
        # 测试 ReActStage 的属性
        self.assertTrue(hasattr(ReflectStage, 'REASONING'))
        self.assertTrue(hasattr(ReflectStage, 'REFLECTING'))
        self.assertTrue(hasattr(ReflectStage, 'FINISHED'))

        # 测试 ReActEvent 的属性
        self.assertTrue(hasattr(ReflectEvent, 'REASON'))
        self.assertTrue(hasattr(ReflectEvent, 'REFLECT'))
        self.assertTrue(hasattr(ReflectEvent, 'FINISH'))

    async def test_workflow_methods(self) -> None:
        """测试工作流方法"""
        # 测试基本方法是否存在
        self.assertTrue(hasattr(self.workflow, 'get_name'))
        self.assertTrue(hasattr(self.workflow, 'get_actions'))
        self.assertTrue(hasattr(self.workflow, 'get_prompts'))
        self.assertTrue(hasattr(self.workflow, 'get_observe_funcs'))
        self.assertTrue(hasattr(self.workflow, 'get_event_chain'))


class TestWorkflowIntegration(unittest.IsolatedAsyncioTestCase):
    """工作流集成测试"""

    async def _mock_simple_action(
        self,
        _workflow: IWorkflow[ReActStage, ReActEvent, TaskState, TaskEvent],
        _context: Dict[str, Any],
        _queue: Queue[Message],
        _task: ITask[TaskState, TaskEvent]
    ) -> ReActEvent:
        """模拟简单工作流动作"""
        return ReActEvent.COMPLETE

    def _mock_simple_observe(
        self,
        _task: ITask[TaskState, TaskEvent],
        _context: Dict[str, Any]
    ) -> Message:
        """模拟观察函数"""
        return Message(role=Role.ASSISTANT, content="Simple observation")

    async def test_workflow_creation(self) -> None:
        """测试工作流创建"""
        # 创建完成配置
        completion_config = CompletionConfig(
            temperature=0.7,
            max_tokens=1000
        )

        workflow = BaseWorkflow[
            ReActStage,   # WorkflowStageT
            ReActEvent,   # WorkflowEventT
            TaskState,     # StateT
            TaskEvent      # EventT
        ](
            valid_states={ReActStage.PROCESSING, ReActStage.COMPLETED},
            init_state=ReActStage.PROCESSING,
            transitions={
                (ReActStage.PROCESSING, ReActEvent.COMPLETE): (ReActStage.COMPLETED, None),
            },
            name="simple_workflow",
            completion_configs={
                ReActStage.PROCESSING: completion_config,
                ReActStage.COMPLETED: completion_config,
            },
            actions={
                ReActStage.PROCESSING: self._mock_simple_action,
                ReActStage.COMPLETED: self._mock_simple_action,
            },
            prompts={
                ReActStage.PROCESSING: "Process",
                ReActStage.COMPLETED: "Complete",
            },
            observe_funcs={
                ReActStage.PROCESSING: self._mock_simple_observe,
                ReActStage.COMPLETED: self._mock_simple_observe,
            },
            event_chain=[ReActEvent.COMPLETE],
            tools=None
        )

        self.assertIsNotNone(workflow)
        self.assertEqual(workflow.get_name(), "simple_workflow")


if __name__ == "__main__":
    unittest.main()
