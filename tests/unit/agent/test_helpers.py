"""
测试辅助函数和基类

提供共享的测试工具函数和基类，减少测试代码重复。
"""

from typing import Any, Dict, Optional, Callable, Awaitable, Generic
from unittest import TestCase
from unittest.mock import Mock, AsyncMock
import asyncio

from tasking.core.agent.interface import IAgent
from tasking.core.state_machine.const import StateProtocol, EventProtocol
from tasking.core.state_machine.task.interface import ITask
from tasking.core.state_machine.workflow.interface import IWorkflow
from tasking.core.agent.react import ReActStage, ReActEvent
from tasking.llm.interface import ILLM
from tasking.model import CompletionConfig, Message, Role, ToolCallRequest, IQueue
from tasking.llm.const import Provider


class TestState(str):
    """测试状态实现，符合StateProtocol"""

    def __new__(cls, value: str):
        return super().__new__(cls, value)

    @property
    def name(self) -> str:
        return str(self)


class TestEvent(str):
    """测试事件实现，符合EventProtocol"""

    def __new__(cls, value: str):
        return super().__new__(cls, value)

    @property
    def name(self) -> str:
        return str(self)


class MockLLM(ILLM):
    """模拟语言模型实现"""

    def __init__(
        self,
        model_name: str = "test-model",
        response_content: str = "Test response",
        should_fail: bool = False,
        provider: Provider = Provider.OPENAI,
        base_url: str = "https://api.test.com"
    ) -> None:
        self.model_name = model_name
        self.response_content = response_content
        self.should_fail = should_fail
        self._provider = provider
        self._base_url = base_url
        self.completion_history: list[tuple[list[Message], CompletionConfig, dict[str, Any]]] = []

    def get_provider(self) -> Provider:
        """获取语言模型的提供商"""
        return self._provider

    def get_base_url(self) -> str:
        """获取语言模型的基础URL"""
        return self._base_url

    def get_model(self) -> str:
        """获取语言模型的模型"""
        return self.model_name

    async def completion(
        self,
        messages: list[Message],
        completion_config: CompletionConfig,
        **kwargs: Any
    ) -> Message:
        """模拟完成请求"""
        # 记录调用历史
        self.completion_history.append((messages, completion_config, kwargs))

        if self.should_fail:
            raise RuntimeError(f"Mock LLM error for model {self.model_name}")

        return Message(
            role=Role.ASSISTANT,
            content=self.response_content,
            stop_reason=completion_config.stop_words[0] if completion_config.stop_words else None
        )


class MockTask(ITask):
    """模拟任务实现"""

    def __init__(
        self,
        initial_state: TestState,
        valid_states: set[TestState],
        task_id: str = "test-task"
    ) -> None:
        self._id = task_id
        self._current_state = initial_state
        self._valid_states = valid_states
        self._completion_config = CompletionConfig()
        self._context = Mock()
        self._input_data = "test input"
        self._output_data = None
        self._error_message = None
        self._tags = set(["test"])
        self._max_revisit_limit = 3
        self._title = "Test Task"
        self._task_type = "test_type"
        self._protocol = "test_protocol"
        self._is_compiled = True
        self._state_visit_count = {state: 1 for state in valid_states}
        self._contexts = []

    # IStateMachine interface implementation
    def get_id(self) -> str:
        return self._id

    def get_current_state(self) -> TestState:
        return self._current_state

    def get_valid_states(self) -> set[TestState]:
        return self._valid_states.copy()

    def get_transitions(self) -> dict[tuple[TestState, TestEvent], tuple[TestState, Callable[["IStateMachine"], Awaitable[None] | None] | None]]:
        return {}

    def compile(self) -> None:
        self._is_compiled = True

    def is_compiled(self) -> bool:
        return self._is_compiled

    async def handle_event(self, event: TestEvent) -> None:
        # Simple mock implementation
        pass

    def reset(self) -> None:
        # Simple mock implementation
        pass

    # ITask interface implementation
    def get_state_visit_count(self, state: TestState) -> int:
        return self._state_visit_count.get(state, 0)

    def set_max_revisit_count(self, count: int) -> None:
        self._max_revisit_limit = count

    def get_max_revisit_limit(self) -> int:
        return self._max_revisit_limit

    def get_tags(self) -> set[str]:
        return self._tags.copy()

    def get_task_type(self) -> str:
        return self._task_type

    def get_title(self) -> str:
        return self._title

    def set_title(self, title: str) -> None:
        self._title = title

    def get_protocol(self) -> str | dict[str, Any]:
        return self._protocol

    def get_input(self) -> str | dict[str, Any]:
        return self._input_data

    def set_input(self, input_data: str | dict[str, Any]) -> None:
        self._input_data = input_data

    def get_output(self) -> str | dict[str, Any]:
        return self._output_data

    def get_completion_config(self) -> CompletionConfig:
        return self._completion_config

    def get_context(self):
        return self._context

    def get_contexts(self):
        return self._contexts

    def append_context(self, context_data: Any) -> None:
        self._contexts.append(context_data)

    def get_error_info(self):
        return self._error_message

    def clean_error_info(self) -> None:
        self._error_message = None

    def set_completed(self, output: Any = None) -> None:
        self._output_data = output
        self._current_state = list(self._valid_states)[-1]  # Assume last state is completed

    def set_error(self, error_message: str) -> None:
        self._error_message = error_message

    def is_completed(self) -> bool:
        return self._output_data is not None

    def is_error(self) -> bool:
        return self._error_message is not None


class MockWorkflow(IWorkflow):
    """模拟工作流实现"""

    def __init__(
        self,
        current_state: ReActStage,
        event_chain: list[ReActEvent] = None,
        workflow_id: str = "test-workflow"
    ) -> None:
        self._id = workflow_id
        self._current_state = current_state
        self._event_chain = event_chain or []
        self._valid_states = {current_state}
        self._transitions = {}
        self._is_compiled = True
        self._action = None
        self._prompt = "Test prompt"
        self._observe_fn = lambda task, kwargs: Message(role=Role.USER, content="Mock observation")
        self._actions = {}
        self._prompts = {current_state: self._prompt}
        self._observe_funcs = {current_state: self._observe_fn}
        self._tools = {}
        self._end_workflow_tool = Mock()

    # IStateMachine interface implementation
    def get_id(self) -> str:
        return self._id

    def get_valid_states(self) -> set[ReActStage]:
        return self._valid_states.copy()

    def get_current_state(self) -> ReActStage:
        return self._current_state

    def get_transitions(self) -> dict[
        tuple[ReActStage, ReActEvent],
        tuple[ReActStage, Callable[["IWorkflow[ReActStage, ReActEvent, StateT, EventT]"], Awaitable[None] | None] | None]
    ]:
        return self._transitions.copy()

    def compile(self) -> None:
        self._is_compiled = True

    def is_compiled(self) -> bool:
        return self._is_compiled

    async def handle_event(self, event: ReActEvent) -> None:
        # Simple mock implementation - just update current state
        pass

    def reset(self) -> None:
        # Simple mock implementation
        pass

    # IWorkflow interface implementation
    def get_name(self) -> str:
        return "MockWorkflow"

    def has_stage(self, stage: ReActStage) -> bool:
        return stage in self._valid_states

    def get_end_workflow_tool(self):
        return self._end_workflow_tool

    def get_event_chain(self) -> list[ReActEvent]:
        return self._event_chain.copy()

    def get_actions(self) -> dict[ReActStage, Callable[
        [
            "IWorkflow[ReActStage, ReActEvent, StateT, EventT]",
            dict[str, Any],
            IQueue[Message],
            ITask[TestState, TestEvent],
        ],
        Awaitable[ReActEvent]
    ]]:
        return self._actions.copy()

    def get_action(self):
        return self._action

    def get_prompts(self) -> dict[ReActStage, str]:
        return self._prompts.copy()

    def get_prompt(self) -> str:
        return self._prompts.get(self._current_state, self._prompt)

    def get_observe_funcs(self) -> dict[ReActStage, Callable[[ITask[TestState, TestEvent], dict[str, Any]], Message]]:
        return self._observe_funcs.copy()

    def get_observe_fn(self):
        return self._observe_funcs.get(self._current_state, self._observe_fn)

    def add_tool(self, tool: Callable[..., Any], name: str, tags: set[str], dependencies: list[str]) -> None:
        # Mock implementation
        pass

    def get_tool(self, name: str):
        # Mock tool implementation
        return (Mock(), set()) if name == "test_tool" else None

    def get_tools(self) -> dict[str, tuple[Any, set[str]]]:
        return {"test_tool": (Mock(), set())}

    async def call_tool(self, name: str, task: ITask[TestState, TestEvent], inject: dict[str, Any], kwargs: dict[str, Any]):
        # Mock tool call implementation
        result = Mock()
        result.content = [Mock()]
        result.content[0].model_dump.return_value = {"type": "text", "text": "Tool result"}
        result.isError = False
        result.structuredContent = {}
        return result


class MockQueue(IQueue[Message]):
    """模拟消息队列实现"""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def put(self, item: Message) -> None:
        self.messages.append(item)

    async def get(self) -> Message:
        if self.messages:
            return self.messages.pop(0)
        raise asyncio.QueueEmpty()

    def size(self) -> int:
        return len(self.messages)

    def is_empty(self) -> bool:
        return len(self.messages) == 0

    def clear(self) -> None:
        self.messages.clear()

    def get_nowait(self) -> Message:
        """立即获取消息，如果没有消息则抛出异常"""
        if self.messages:
            return self.messages.pop(0)
        raise asyncio.QueueEmpty()

    def put_nowait(self, item: Message) -> None:
        """立即放入消息"""
        self.messages.append(item)

    def is_full(self) -> bool:
        """检查队列是否已满"""
        return False  # Mock队列永不 满


class AgentTestMixin:
    """Agent测试混入类，提供共享的测试工具方法"""

    @staticmethod
    def create_mock_llm(
        model_name: str = "test-model",
        response_content: str = "Test response",
        should_fail: bool = False
    ) -> MockLLM:
        """创建模拟语言模型"""
        return MockLLM(model_name, response_content, should_fail)

    @staticmethod
    def create_mock_task(
        initial_state: TestState,
        valid_states: set[TestState],
        task_id: str = "test-task"
    ) -> MockTask:
        """创建模拟任务"""
        return MockTask(initial_state, valid_states, task_id)

    @staticmethod
    def create_mock_workflow(
        current_state: ReActStage,
        event_chain: list[ReActEvent] = None,
        workflow_id: str = "test-workflow"
    ) -> MockWorkflow:
        """创建模拟工作流"""
        return MockWorkflow(current_state, event_chain, workflow_id)

    @staticmethod
    def create_mock_queue() -> MockQueue:
        """创建模拟消息队列"""
        return MockQueue()

    @staticmethod
    def create_test_tool_call_request(
        name: str = "test_tool",
        args: dict[str, Any] = None
    ) -> ToolCallRequest:
        """创建测试工具调用请求"""
        return ToolCallRequest(
            id=f"call_{name}",
            name=name,
            args=args or {"param1": "value1"}
        )

    @staticmethod
    def create_test_message(
        content: str = "Test message",
        role: Role = Role.USER
    ) -> Message:
        """创建测试消息"""
        return Message(role=role, content=content)

    @staticmethod
    async def run_with_timeout(coro: Awaitable[Any], timeout: float = 5.0) -> Any:
        """运行协程并设置超时"""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise AssertionError(f"Test timed out after {timeout} seconds")


def create_react_agent_test_state() -> tuple[TestState, set[TestState]]:
    """创建ReAct Agent的测试状态"""
    # Using string literals as mock states for testing
    init_state = TestState("PROCESSING")
    valid_states: set[TestState] = {TestState("PROCESSING"), TestState("COMPLETED")}
    return init_state, valid_states


def create_react_agent_test_events() -> list[ReActEvent]:
    """创建ReAct Agent的测试事件"""
    # Using SimpleEvent constants for testing
    return [ReActEvent.PROCESS, ReActEvent.COMPLETE]