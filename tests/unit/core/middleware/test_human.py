"""
Unit tests for middleware human components.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Any, cast

from tasking.core.middleware.human import (
    IHumanClient,
    BaseHumanClient,
    IHumanInterfereHooks,
    BaseHumanInterfereHooks,
    HumanInterfere
)
from tasking.model import Message, Role, IAsyncQueue, AsyncQueue, TextBlock, MultimodalContent, ImageBlock, VideoBlock
from tasking.core.state_machine.task import ITask, TaskState, TaskEvent
from tasking.core.context import IContext


class TestHumanInterfere:
    """Test HumanInterfere exception class."""

    def test_human_interfere_initialization(self) -> None:
        """Test HumanInterfere initialization with messages."""
        text_block = TextBlock(text="Test human message")
        messages: list[MultimodalContent] = [text_block]

        exception = HumanInterfere(messages)

        assert exception._messages == messages
        # Extract text from the first content block safely
        if isinstance(messages[0], TextBlock):
            assert exception._message == "Test human message"
        else:
            assert exception._message == ""
        assert str(exception) == "HumanInterfere: Test human message"

    def test_human_interfere_get_messages(self) -> None:
        """Test getting messages from HumanInterfere."""
        text_block1 = TextBlock(text="Message 1")
        text_block2 = TextBlock(text="Message 2")
        messages: list[MultimodalContent] = [text_block1, text_block2]

        exception = HumanInterfere(messages)

        assert exception.get_messages() == messages

    def test_human_interfere_empty_messages(self) -> None:
        """Test HumanInterfere with empty messages."""
        messages: list[MultimodalContent] = []

        exception = HumanInterfere(messages)

        assert exception._messages == []
        assert exception._message == ""
        assert str(exception) == "HumanInterfere: "


class TestIHumanClient:
    """Test IHumanClient interface compliance."""

    def test_ihuman_client_is_abstract(self) -> None:
        """Test that IHumanClient cannot be instantiated directly."""
        with pytest.raises(TypeError):
            IHumanClient()  # type: ignore[arg-type]

    def test_ihuman_client_method_signatures(self) -> None:
        """Test that IHumanClient defines required methods."""
        # Check that abstract methods are defined
        abstract_methods = IHumanClient.__abstractmethods__
        expected_methods = {"is_valid", "ask_human", "handle_human_response"}

        assert abstract_methods == expected_methods


class TestBaseHumanClient:
    """Test BaseHumanClient implementation."""

    def test_base_human_client_initialization(self) -> None:
        """Test BaseHumanClient initialization."""
        client = BaseHumanClient()
        assert client._response_queues == {}

    def test_base_human_client_is_valid(self) -> None:
        """Test BaseHumanClient is_valid method."""
        client = BaseHumanClient()
        
        # Default implementation always returns True
        assert client.is_valid({}) is True
        assert client.is_valid({"user_id": "123"}) is True
        assert client.is_valid({"invalid": "context"}) is True

    @pytest.mark.asyncio
    async def test_base_human_client_ask_human(self) -> None:
        """Test BaseHumanClient ask_human method."""
        client = BaseHumanClient()
        context = {
            "user_id": "user123",
            "trace_id": "trace456"
        }
        queue = AsyncQueue[Message]()
        message = Message(
            role=Role.USER,
            content=[TextBlock(text="Test message")]
        )

        # Use asyncio.gather with timeout to avoid deadlock
        import asyncio
        
        async def ask_human_with_response() -> Message:
            # Start ask_human
            ask_task = asyncio.create_task(
                client.ask_human(context, queue, message)
            )
            
            # Wait a short time for response queue to be created
            await asyncio.sleep(0.001)
            
            # Send human response
            await client.handle_human_response(
                context,
                Message(
                    role=Role.ASSISTANT,
                    content=[TextBlock(text="Human response")]
                )
            )
            
            # Wait for ask_human to complete
            return await ask_task

        # Use timeout to prevent deadlock
        response = await asyncio.wait_for(ask_human_with_response(), timeout=5.0)

        assert response.role == Role.ASSISTANT
        assert len(response.content) == 1
        assert isinstance(response.content[0], TextBlock)
        assert response.content[0].text == "Human response"

    @pytest.mark.asyncio
    async def test_base_human_client_handle_human_response(self) -> None:
        """Test BaseHumanClient handle_human_response method."""
        client = BaseHumanClient()
        context = {
            "user_id": "user123",
            "trace_id": "trace456"
        }
        response_message = Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="Response from human")]
        )

        # First, create a request to set up the response queue
        queue = AsyncQueue[Message]()
        request_message = Message(
            role=Role.USER,
            content=[TextBlock(text="Request")]
        )

        import asyncio
        
        async def ask_human_with_response() -> Message:
            # Start ask_human in background
            ask_task = asyncio.create_task(
                client.ask_human(context, queue, request_message)
            )
            
            # Wait a short time for the response queue to be created
            await asyncio.sleep(0.001)

            # Handle human response
            await client.handle_human_response(context, response_message)

            # Get the response
            return await ask_task

        # Use timeout to prevent deadlock
        response = await asyncio.wait_for(ask_human_with_response(), timeout=5.0)

        assert response.role == Role.ASSISTANT
        assert isinstance(response.content[0], TextBlock)
        assert response.content[0].text == "Response from human"


class TestIHumanInterfereHooks:
    """Test IHumanInterfereHooks interface compliance."""

    def test_ihuman_interfere_hooks_is_abstract(self) -> None:
        """Test that IHumanInterfereHooks cannot be instantiated directly."""
        with pytest.raises(TypeError):
            IHumanInterfereHooks()  # type: ignore[arg-type]

    def test_ihuman_interfere_hooks_method_signatures(self) -> None:
        """Test that IHumanInterfereHooks defines required methods."""
        abstract_methods = IHumanInterfereHooks.__abstractmethods__
        expected_methods = {"on_pre_human_interfere", "on_post_human_interfere"}

        assert abstract_methods == expected_methods


class MockTask(ITask[TaskState, TaskEvent]):
    """Mock task for testing."""

    def __init__(self) -> None:
        self._context = MockContext()
        self._id = "test_task_id"
        self._state = TaskState.CREATED
        self._event = TaskEvent.INIT
        self._compiled = False
        self._valid_states = {TaskState.CREATED, TaskState.RUNNING, TaskState.CANCELED}
        self._transitions: dict[tuple[TaskState, TaskEvent], tuple[TaskState, Any]] = {}
        self._unique_protocol: list[TextBlock | ImageBlock | VideoBlock] = []

    def get_id(self) -> str:
        return self._id

    def get_context(self) -> IContext:
        return self._context

    def append_context(self, data: Message) -> None:
        self._context.append_context_data(data)

    def get_input(self) -> list[TextBlock | ImageBlock | VideoBlock]:
        return [TextBlock(text="test input")]

    def set_input(self, input_data: list[TextBlock | ImageBlock | VideoBlock]) -> None:
        pass

    # Implement other required methods with minimal implementations
    def get_state_visit_count(self, state: TaskState) -> int:
        return 0

    def set_max_revisit_count(self, count: int) -> None:
        pass

    def get_max_revisit_limit(self) -> int:
        return 0

    @classmethod
    def get_tags(cls) -> set[str]:
        return set()

    @classmethod
    def get_task_type(cls) -> str:
        return "test"

    @classmethod
    def get_protocol(cls) -> list[TextBlock | ImageBlock | VideoBlock]:
        return []

    def get_unique_protocol(self) -> list[TextBlock | ImageBlock | VideoBlock]:
        return self._unique_protocol.copy()

    def set_unique_protocol(self, protocol: list[TextBlock | ImageBlock | VideoBlock]) -> None:
        self._unique_protocol = protocol

    def get_title(self) -> str:
        return "test"

    def set_title(self, title: str) -> None:
        pass

    def get_output(self) -> str:
        return ""

    def set_completed(self, output: str) -> None:
        pass

    def is_completed(self) -> bool:
        return False

    def is_error(self) -> bool:
        return False

    def get_error_info(self) -> str:
        return ""

    def set_error(self, error_info: str) -> None:
        pass

    def clean_error_info(self) -> None:
        pass

    def get_contexts(self) -> dict[TaskState, IContext]:
        return {}

    def get_state(self) -> TaskState:
        return self._state

    def set_state(self, state: TaskState) -> None:
        self._state = state

    def get_event(self) -> TaskEvent:
        return self._event

    def set_event(self, event: TaskEvent) -> None:
        self._event = event

    def get_stage(self) -> str:
        return "test"

    def set_stage(self, stage: str) -> None:
        pass

    def get_valid_states(self) -> set[TaskState]:
        return self._valid_states

    def get_current_state(self) -> TaskState:
        return self._state

    def get_transitions(self) -> dict[tuple[TaskState, TaskEvent], tuple[TaskState, Any]]:
        return self._transitions

    def compile(self) -> None:
        self._compiled = True

    def is_compiled(self) -> bool:
        return self._compiled

    async def handle_event(self, event: TaskEvent) -> None:
        pass

    def reset(self) -> None:
        self._state = TaskState.CREATED
        self._event = TaskEvent.INIT


class MockContext(IContext):
    """Mock context for testing."""

    def __init__(self) -> None:
        self._messages: list[Message] = []

    def get_context_data(self) -> list[Message]:
        return self._messages

    def append_context_data(self, data: Message) -> None:
        self._messages.append(data)

    def clear_context_data(self) -> None:
        self._messages.clear()

    def get_state(self) -> Any:
        return None

    def set_state(self, state: Any) -> None:
        pass


class TestBaseHumanInterfereHooks:
    """Test BaseHumanInterfereHooks implementation."""

    def test_base_human_interfere_hooks_initialization(self) -> None:
        """Test BaseHumanInterfereHooks initialization."""
        mock_client = Mock(spec=IHumanClient)
        hooks = BaseHumanInterfereHooks(mock_client)

        assert hooks._human_client == mock_client
        assert hooks._approve_resp == set()

    def test_base_human_interfere_hooks_initialization_with_approve_resp(self) -> None:
        """Test BaseHumanInterfereHooks initialization with approve_resp."""
        mock_client = Mock(spec=IHumanClient)
        approve_resp = {"yes", "ok", "approve"}
        hooks = BaseHumanInterfereHooks(mock_client, approve_resp=approve_resp)

        assert hooks._human_client == mock_client
        assert hooks._approve_resp == approve_resp

    @pytest.mark.asyncio
    @patch('tasking.core.middleware.human.read_markdown')
    async def test_on_pre_human_interfere_valid_context(self, mock_read_markdown: Mock) -> None:
        """Test on_pre_human_interfere with valid context."""
        mock_read_markdown.return_value = "# Human Interfere Template"
        
        mock_client = Mock(spec=IHumanClient)
        mock_client.is_valid = Mock(return_value=True)
        
        hooks = BaseHumanInterfereHooks(mock_client)
        context = {"user_id": "123", "trace_id": "456"}
        queue = Mock(spec=IAsyncQueue)
        task = MockTask()

        await hooks.on_pre_human_interfere(context, queue, task)

        # Verify human client was checked
        mock_client.is_valid.assert_called_once_with(context)
        
        # Verify markdown was read
        mock_read_markdown.assert_called_once_with("tool/human_interfere.md")
        
        # Verify message was added to task context
        context_data = task.get_context().get_context_data()
        assert len(context_data) == 1
        assert context_data[0].role == Role.USER
        assert len(context_data[0].content) == 1
        assert isinstance(context_data[0].content[0], TextBlock)
        assert context_data[0].content[0].text == "# Human Interfere Template"

    @pytest.mark.asyncio
    async def test_on_pre_human_interfere_invalid_context(self) -> None:
        """Test on_pre_human_interfere with invalid context."""
        mock_client = Mock(spec=IHumanClient)
        mock_client.is_valid = Mock(return_value=False)
        
        hooks = BaseHumanInterfereHooks(mock_client)
        context = {"user_id": "123"}
        queue = Mock(spec=IAsyncQueue)
        task = MockTask()

        await hooks.on_pre_human_interfere(context, queue, task)

        # Verify human client was checked
        mock_client.is_valid.assert_called_once_with(context)
        
        # Verify no message was added to task context
        context_data = task.get_context().get_context_data()
        assert len(context_data) == 0

    @pytest.mark.asyncio
    async def test_on_post_human_interfere_no_human_interfere_tag(self) -> None:
        """Test on_post_human_interfere when no human_interfere tag exists."""
        mock_client = Mock(spec=IHumanClient)
        mock_client.is_valid = Mock(return_value=True)
        
        hooks = BaseHumanInterfereHooks(mock_client)
        context = {"user_id": "123", "trace_id": "456"}
        queue = Mock(spec=IAsyncQueue)
        task = MockTask()

        # Add a message without human_interfere tag
        task.get_context().append_context_data(Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="Normal response")]
        ))

        # Should return without raising exception
        await hooks.on_post_human_interfere(context, queue, task)

        # Verify human client was checked
        mock_client.is_valid.assert_called_once_with(context)

    @pytest.mark.asyncio
    async def test_on_post_human_interfere_with_empty_human_interfere_tag(self) -> None:
        """Test on_post_human_interfere with empty human_interfere tag."""
        mock_client = Mock(spec=IHumanClient)
        mock_client.is_valid = Mock(return_value=True)
        mock_client.ask_human = AsyncMock()
        
        hooks = BaseHumanInterfereHooks(mock_client)
        context = {"user_id": "123", "trace_id": "456"}
        queue = Mock(spec=IAsyncQueue)
        task = MockTask()

        # Add a message with empty human_interfere tag
        task.get_context().append_context_data(Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="<human_interfere>\n</human_interfere>")]
        ))

        # Should return without raising exception
        await hooks.on_post_human_interfere(context, queue, task)

        # Verify ask_human was not called
        mock_client.ask_human.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_post_human_interfere_with_content_raises_exception(self) -> None:
        """Test on_post_human_interfere with human_interfere content raises HumanInterfere."""
        mock_client = Mock(spec=IHumanClient)
        mock_client.is_valid = Mock(return_value=True)
        mock_client.ask_human = AsyncMock(return_value=Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="Human response")]
        ))
        
        hooks = BaseHumanInterfereHooks(mock_client)
        context = {"user_id": "123", "trace_id": "456"}
        queue = Mock(spec=IAsyncQueue)
        task = MockTask()

        # Add a message with human_interfere tag
        task.get_context().append_context_data(Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="<human_interfere>\n<content>\nNeed human help\n</content>\n</human_interfere>")]
        ))

        # Should raise HumanInterfere exception
        with pytest.raises(HumanInterfere) as exc_info:
            await hooks.on_post_human_interfere(context, queue, task)

        # Verify ask_human was called
        mock_client.ask_human.assert_called_once()
        
        # Verify exception contains human response
        assert len(exc_info.value.get_messages()) == 1
        response_content = exc_info.value.get_messages()[0]
        assert isinstance(response_content, TextBlock)
        assert response_content.text == "Human response"

    @pytest.mark.asyncio
    async def test_on_post_human_interfere_with_approve_response(self) -> None:
        """Test on_post_human_interfere with approve response does not raise exception."""
        mock_client = Mock(spec=IHumanClient)
        mock_client.is_valid = Mock(return_value=True)
        mock_client.ask_human = AsyncMock(return_value=Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="yes")]
        ))
        
        hooks = BaseHumanInterfereHooks(mock_client, approve_resp={"yes", "ok"})
        context = {"user_id": "123", "trace_id": "456"}
        queue = Mock(spec=IAsyncQueue)
        task = MockTask()

        # Add a message with human_interfere tag
        task.get_context().append_context_data(Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="<human_interfere>\n<content>\nNeed approval\n</content>\n</human_interfere>")]
        ))

        # Should not raise exception when response is in approve_resp
        await hooks.on_post_human_interfere(context, queue, task)

        # Verify ask_human was called
        mock_client.ask_human.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_post_human_interfere_with_empty_response(self) -> None:
        """Test on_post_human_interfere with empty response does not raise exception."""
        mock_client = Mock(spec=IHumanClient)
        mock_client.is_valid = Mock(return_value=True)
        mock_client.ask_human = AsyncMock(return_value=Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="")]
        ))
        
        hooks = BaseHumanInterfereHooks(mock_client)
        context = {"user_id": "123", "trace_id": "456"}
        queue = Mock(spec=IAsyncQueue)
        task = MockTask()

        # Add a message with human_interfere tag
        task.get_context().append_context_data(Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="<human_interfere>\n<content>\nNeed help\n</content>\n</human_interfere>")]
        ))

        # Should not raise exception when response is empty
        await hooks.on_post_human_interfere(context, queue, task)

        # Verify ask_human was called
        mock_client.ask_human.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_post_human_interfere_invalid_last_message_role(self) -> None:
        """Test on_post_human_interfere raises ValueError when last message is not from ASSISTANT."""
        mock_client = Mock(spec=IHumanClient)
        mock_client.is_valid = Mock(return_value=True)
        
        hooks = BaseHumanInterfereHooks(mock_client)
        context = {"user_id": "123", "trace_id": "456"}
        queue = Mock(spec=IAsyncQueue)
        task = MockTask()

        # Add a message with USER role (should be ASSISTANT)
        task.get_context().append_context_data(Message(
            role=Role.USER,
            content=[TextBlock(text="User message")]
        ))

        # Should raise ValueError
        with pytest.raises(ValueError, match="The last message in context must be from ASSISTANT role"):
            await hooks.on_post_human_interfere(context, queue, task)
