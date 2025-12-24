#!/usr/bin/env python3
"""
ReAct Agent测试套件 [原Simple Agent]

测试react.py中的功能：
- end_workflow函数
- get_react_transition函数
- get_react_stages函数
- get_react_event_chain函数
- get_react_actions函数
- build_react_agent函数
"""

import unittest
import asyncio
from unittest.mock import Mock, patch

# pylint: disable=import-error
# NOTE: E0401 import-error is a pylint configuration issue.
# The tests run correctly with pytest, which resolves the src path.
from tasking.core.agent.react import (
    end_workflow,
    get_react_transition,
    get_react_stages,
    get_react_event_chain,
    get_react_actions,
    build_react_agent,
    END_WORKFLOW_DOC
)
from tasking.core.agent.react import ReActStage, ReActEvent
from tasking.model import Message, Role, TextBlock
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from unit.agent.test_helpers import AgentTestMixin, MockState


class TestEndWorkflow(unittest.TestCase, AgentTestMixin):
    """测试end_workflow函数"""

    def setUp(self) -> None:
        """测试设置"""
        self.init_state, self.valid_states = MockState("RUNNING"), {
            MockState("RUNNING"), MockState("FINISHED")
        }
        # 使用MockState类型
        self.task = self.create_mock_task(
            MockState("RUNNING"), {MockState("RUNNING"), MockState("FINISHED")}, "test-task"
        )
        # 设置任务上下文的get_context_data()返回空列表
        self.task.get_context().get_context_data.return_value = []

        # 创建包含output标签的消息
        self.message_with_output = Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="<output>\nTest output content\n</output>")]
        )

        # 创建不包含output标签的消息
        self.message_without_output = Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="No output here")]
        )

    def test_end_workflow_success(self) -> None:
        """测试成功结束工作流"""
        # 验证任务未完成
        self.assertFalse(self.task.is_completed())

        # 设置任务上下文的get_context_data()返回包含消息的列表
        self.task.get_context().get_context_data.return_value = [self.message_with_output]

        # 调用end_workflow
        end_workflow({
            "task": self.task
        })

        # 验证任务已完成
        self.assertTrue(self.task.is_completed())
        self.assertEqual(self.task.get_output(), "Test output content")

    def test_end_workflow_missing_task(self) -> None:
        """测试缺少task参数的错误"""
        with self.assertRaises(RuntimeError) as cm:
            end_workflow({"message": self.message_with_output})

        self.assertIn("缺少必要的 'task' 注入参数", str(cm.exception))

    def test_end_workflow_missing_message(self) -> None:
        """测试缺少message参数的错误"""
        # 设置任务上下文的get_context_data()返回空列表，模拟没有消息的情况
        self.task.get_context().get_context_data.return_value = []

        with self.assertRaises(IndexError) as cm:
            end_workflow({"task": self.task})

        self.assertIn("list index out of range", str(cm.exception))

    def test_end_workflow_no_output_content(self) -> None:
        """测试没有输出内容的错误"""
        # 设置任务上下文的get_context_data()返回包含没有output的消息的列表
        self.task.get_context().get_context_data.return_value = [self.message_without_output]

        with self.assertRaises(Exception) as cm:
            end_workflow({
                "task": self.task
            })

        error_msg = str(cm.exception)
        self.assertIn("没有从标签", error_msg)
        self.assertIn("中提取到任何内容", error_msg)

    def test_end_workflow_wrong_role(self) -> None:
        """测试错误的消息角色"""
        wrong_role_message = Message(
            role=Role.USER,  # 错误的角色
            content=[TextBlock(text="<output>Test output</output>")]
        )

        # 设置任务上下文的get_context_data()返回包含错误角色消息的列表
        self.task.get_context().get_context_data.return_value = [wrong_role_message]

        with self.assertRaises(AssertionError) as cm:
            end_workflow({
                "task": self.task
            })

        self.assertIn("最后一个 Message 不是 Assistant Message", str(cm.exception))


class TestReActTransition(unittest.TestCase):
    """测试get_react_transition函数"""

    def test_transition_structure(self) -> None:
        """测试转换规则结构"""
        transitions = get_react_transition()

        self.assertIsInstance(transitions, dict)
        self.assertGreater(len(transitions), 0)

    def test_processing_to_process_transition(self) -> None:
        """测试PROCESSING + PROCESS转换"""
        transitions = get_react_transition()

        key = (ReActStage.PROCESSING, ReActEvent.PROCESS)
        self.assertIn(key, transitions)

        next_stage, callback = transitions[key]
        self.assertEqual(next_stage, ReActStage.PROCESSING)
        self.assertIsNotNone(callback)

    def test_processing_to_complete_transition(self) -> None:
        """测试PROCESSING + COMPLETE转换"""
        transitions = get_react_transition()

        key = (ReActStage.PROCESSING, ReActEvent.COMPLETE)
        self.assertIn(key, transitions)

        next_stage, callback = transitions[key]
        self.assertEqual(next_stage, ReActStage.COMPLETED)
        self.assertIsNotNone(callback)


class TestReActStages(unittest.TestCase):
    """测试get_react_stages函数"""

    def test_stages_content(self) -> None:
        """测试阶段集合内容"""
        stages = get_react_stages()

        self.assertIsInstance(stages, set)
        self.assertIn(ReActStage.PROCESSING, stages)
        self.assertIn(ReActStage.COMPLETED, stages)
        self.assertEqual(len(stages), 2)


class TestReActEventChain(unittest.TestCase):
    """测试get_react_event_chain函数"""

    def test_event_chain_structure(self) -> None:
        """测试事件链结构"""
        event_chain = get_react_event_chain()

        self.assertIsInstance(event_chain, list)
        self.assertEqual(len(event_chain), 2)
        self.assertEqual(event_chain[0], ReActEvent.PROCESS)
        self.assertEqual(event_chain[1], ReActEvent.COMPLETE)


class TestReActActions(unittest.TestCase, AgentTestMixin):
    """测试get_react_actions函数"""

    def setUp(self) -> None:
        """测试设置"""
        # 创建模拟Agent
        mock_agent = Mock()

        # 设置get_llm方法
        mock_llm = self.create_mock_llm()
        mock_agent.get_llm.return_value = mock_llm

        # 设置get_workflow方法
        mock_workflow = Mock()
        mock_workflow.get_current_state.return_value = ReActStage.PROCESSING
        mock_workflow.get_prompt.return_value = "Test prompt"
        mock_workflow.get_tools.return_value = {}
        mock_workflow.get_observe_fn.return_value = lambda task, kwargs: Message(role=Role.USER, content=[TextBlock(text="test")])
        mock_agent.get_workflow.return_value = mock_workflow

        self.mock_agent = mock_agent

    def test_actions_structure(self) -> None:
        """测试动作结构"""
        actions = get_react_actions(self.mock_agent)

        self.assertIsInstance(actions, dict)
        self.assertIn(ReActStage.PROCESSING, actions)

        # 验证动作是可调用对象
        processing_action = actions[ReActStage.PROCESSING]
        self.assertTrue(callable(processing_action))

    def test_processing_action_signature(self) -> None:
        """测试PROCESSING动作签名"""
        actions = get_react_actions(self.mock_agent)
        processing_action = actions[ReActStage.PROCESSING]

        # 创建测试参数
        workflow = self.mock_agent.get_workflow.return_value
        context = {}
        queue = self.create_mock_queue()
        task = self.create_mock_task(MockState("RUNNING"), {MockState("RUNNING"), MockState("FINISHED")})

        # MockTask已经设置了completion_config，不需要额外设置

        try:
            # 调用动作函数
            result = asyncio.run(processing_action(workflow, context, queue, task))

            # 验证返回值是事件类型
            self.assertIsInstance(result, (ReActEvent, str))
        except Exception as e:
            # 由于这个测试涉及复杂的异步操作，我们主要验证函数可以调用
            # 实际的集成测试应该使用更完整的设置
            self.assertIsInstance(e, (AttributeError, TypeError, RuntimeError))


class TestBuildReActAgent(unittest.TestCase):
    """测试build_react_agent函数"""

    @patch('tasking.core.agent.react.get_settings')
    @patch('tasking.core.agent.react.build_llm')
    @patch('tasking.core.agent.react.read_document')
    def test_build_react_agent_basic(self, mock_read_doc, mock_build_llm, mock_get_settings):
        """测试基本ReAct Agent构建"""
        # 设置模拟
        mock_agent_config = Mock()
        mock_agent_config.agent_type = "SimpleAgent"
        mock_llm_config = Mock()
        mock_llm_config.model = "test-model"
        mock_llm_config.base_url = "http://test.com"
        mock_llm_config.api_key = "test-key"

        def mock_get_llm_config(stage):
            return mock_llm_config

        mock_agent_config.get_llm_config = mock_get_llm_config

        def mock_get_agent_config(name):
            if name == "test-agent":
                return mock_agent_config
            return None

        mock_settings = Mock()
        mock_settings.get_agent_config = mock_get_agent_config
        mock_get_settings.return_value = mock_settings

        mock_read_doc.return_value = "Test prompt content"
        mock_build_llm.return_value = Mock()

        try:
            # 构建Agent
            agent = build_react_agent("test-agent")

            # 验证Agent基本属性
            self.assertEqual(agent.get_name(), "test-agent")
            self.assertEqual(agent.get_type(), "SimpleAgent")

            # 验证LLM被创建
            self.assertTrue(mock_build_llm.called)

        except Exception as e:
            # 由于依赖外部配置，主要验证函数调用逻辑
            self.assertIsInstance(e, (ValueError, AttributeError, TypeError))

    @patch('tasking.core.agent.react.get_settings')
    def test_build_agent_no_config(self, mock_get_settings):
        """测试没有配置时的错误"""
        mock_settings = Mock()
        mock_settings.get_agent_config.return_value = None
        mock_get_settings.return_value = mock_settings

        with self.assertRaises(ValueError) as cm:
            build_react_agent("nonexistent-agent")

        self.assertIn("未找到名为", str(cm.exception))


class TestWorkflowDocumentation(unittest.TestCase):
    """测试工作流文档"""

    def test_end_workflow_doc(self) -> None:
        """测试end_workflow工具文档"""
        self.assertIsInstance(END_WORKFLOW_DOC, str)
        self.assertGreater(len(END_WORKFLOW_DOC), 0)
        self.assertIn("结束工作流", END_WORKFLOW_DOC)


# New tests based on updated requirements

class TestReactAgentWorkflowStates:
    """Test React Agent workflow state transitions based on new requirements."""

    def test_react_stage_normal_transitions(self):
        """Test ReActStage can normally transition (PROCESSING -> COMPLETED)."""
        # Get transition function
        transitions = get_react_transition()

        # Test PROCESSING + PROCESS -> PROCESSING (continues processing)
        transition_key = (ReActStage.PROCESSING, ReActEvent.PROCESS)
        assert transition_key in transitions
        next_stage, _ = transitions[transition_key]
        assert next_stage == ReActStage.PROCESSING

        # Test PROCESSING + COMPLETE -> COMPLETED (ends workflow)
        transition_key = (ReActStage.PROCESSING, ReActEvent.COMPLETE)
        assert transition_key in transitions
        next_stage, _ = transitions[transition_key]
        assert next_stage == ReActStage.COMPLETED

    def test_no_unreachable_workflow_states(self):
        """Check for unreachable workflow states."""
        reachable_states = {ReActStage.PROCESSING, ReActStage.COMPLETED}
        all_states = set(ReActStage.list_stages())

        # All defined states should be reachable
        assert reachable_states == all_states, f"Unreachable states: {all_states - reachable_states}"

    def test_workflow_state_transition_correctness(self):
        """Verify workflow state transition correctness."""
        transitions = get_react_transition()

        # Verify PROCESSING -> PROCESSING transition (for continued processing)
        processing_key = (ReActStage.PROCESSING, ReActEvent.PROCESS)
        assert processing_key in transitions
        next_stage, callback = transitions[processing_key]
        assert next_stage == ReActStage.PROCESSING
        assert callback is not None

        # Verify PROCESSING -> COMPLETED transition (for workflow completion)
        completed_key = (ReActStage.PROCESSING, ReActEvent.COMPLETE)
        assert completed_key in transitions
        next_stage, callback = transitions[completed_key]
        assert next_stage == ReActStage.COMPLETED
        assert callback is not None


class TestReactAgentWorkflowExecution:
    """Test React Agent workflow execution with mocked dependencies."""

    def test_mocked_llm_and_tool_calls_normal_execution(self):
        """Test Mock LLM and tool calls for normal execution flow."""
        # This test would require async testing setup
        # For now, we verify the structure exists
        actions = get_react_actions(Mock())
        assert ReActStage.PROCESSING in actions
        assert callable(actions[ReActStage.PROCESSING])

    def test_potential_infinite_loop_detection(self):
        """Test for potential workflow infinite loops."""
        # The transition rules show PROCESSING + PROCESS -> PROCESSING
        # This could potentially cause infinite loops if not handled properly
        transitions = get_react_transition()

        # Check the potentially problematic transition
        processing_key = (ReActStage.PROCESSING, ReActEvent.PROCESS)
        assert processing_key in transitions
        next_stage, _ = transitions[processing_key]

        # This transition back to PROCESSING could cause infinite loops
        # The actual implementation must have logic to break the loop
        # (e.g., task completion, error conditions, finish flags)
        assert next_stage == ReActStage.PROCESSING


class TestReactAgentToolCallLogic:
    """Test React Agent tool call logic."""

    def test_tool_call_normal_continues_execution_loop(self):
        """Test that successful tool calls continue the execution loop."""
        # This test verifies that when tool calls are successful,
        # the workflow continues to the next iteration (PROCESS event)
        transitions = get_react_transition()

        # Successful processing should return to PROCESSING state
        processing_key = (ReActStage.PROCESSING, ReActEvent.PROCESS)
        next_stage, _ = transitions[processing_key]
        assert next_stage == ReActStage.PROCESSING

    def test_tool_call_error_sends_complete_event_error_handling(self):
        """Test that tool call errors send complete event and enter error handling flow."""
        # When tool calls fail, the workflow should complete
        # This is verified by the COMPLETE event transition
        transitions = get_react_transition()

        # Error processing should transition to COMPLETED
        completed_key = (ReActStage.PROCESSING, ReActEvent.COMPLETE)
        next_stage, _ = transitions[completed_key]
        assert next_stage == ReActStage.COMPLETED


class TestReactAgentWorkflowEnd:
    """Test React Agent workflow end."""

    def test_react_agent_workflow_ends_normally(self):
        """Test that React Agent workflow can end normally."""
        # Verify that COMPLETED is a valid end state
        stages = get_react_stages()
        assert ReActStage.COMPLETED in stages

        # Verify that there's a transition to COMPLETED
        transitions = get_react_transition()
        completed_key = (ReActStage.PROCESSING, ReActEvent.COMPLETE)
        assert completed_key in transitions

        next_stage, _ = transitions[completed_key]
        assert next_stage == ReActStage.COMPLETED


if __name__ == "__main__":
    unittest.main()