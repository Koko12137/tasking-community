"""
核心记忆中间件模块测试套件

测试 tasking.core.middleware.memory 模块中的记忆中间件功能
"""

import unittest
import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime, timezone

from tasking.core.middleware.memory import (
    IMemoryHooks,
    StateMemoryHooks,
    EpisodeMemoryHooks,
    register_memory_fold_hooks
)
from tasking.model.memory import MemoryProtocol, MemoryT, EpisodeMemory, StateMemory
from tasking.model.message import Message, Role, TextBlock, MultimodalContent, ImageBlock, VideoBlock
from tasking.model.queue import IAsyncQueue
from tasking.core.state_machine.task.interface import ITask
from tasking.core.context import IContext
from tasking.database.interface import IVectorDatabase, IKVDatabase
from typing import TypeVar, Protocol

class StateProtocol(Protocol):
    """Mock state protocol for testing"""
    name: str

class EventProtocol(Protocol):
    """Mock event protocol for testing"""
    name: str

StateT = TypeVar('StateT', bound=StateProtocol)
EventT = TypeVar('EventT', bound=EventProtocol)


class MockState:
    """Mock state implementing StateProtocol"""
    def __init__(self, name: str = "mock_state") -> None:
        self.name = name


class MockEvent:
    """Mock event implementing EventProtocol"""
    def __init__(self, name: str = "mock_event") -> None:
        self.name = name


class MockMemory(MemoryProtocol):
    """模拟记忆对象"""

    def __init__(self, memory_id: str, content: list[MultimodalContent]) -> None:
        object.__setattr__(self, 'id', memory_id)
        object.__setattr__(self, 'content', content)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "content": [block.model_dump() for block in self.content]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MockMemory":
        content: list[MultimodalContent] = []
        for item in data["content"]:
            if item['type'] == 'text':
                content.append(TextBlock.model_validate(item))
            elif item['type'] == 'image_url':
                content.append(ImageBlock.model_validate(item))
            elif item['type'] == 'video_url':
                content.append(VideoBlock.model_validate(item))
        return cls(data["id"], content)


class MockTask(ITask[MockState, MockEvent]):
    """模拟任务对象"""

    def __init__(self, task_id: str = "test_task_id") -> None:
        self._state: MockState | None = MockState()
        self._event: MockEvent | None = MockEvent()
        self._context = MockContext()
        self._id = task_id
        self._input: list[TextBlock | ImageBlock | VideoBlock] = [TextBlock(text="test input")]
        self._compiled = False
        self._valid_states: set[MockState] = {MockState()}
        self._transitions: dict[tuple[MockState, MockEvent], tuple[MockState, Any]] = {}
        self._unique_protocol: list[TextBlock | ImageBlock | VideoBlock] = []

    def get_id(self) -> str:
        return self._id

    def get_context(self) -> Any:
        return self._context

    def append_context(self, data: Message) -> None:
        self._context.append_context_data(data)

    def get_input(self) -> list[TextBlock | ImageBlock | VideoBlock]:
        return self._input

    def set_input(self, input_data: list[TextBlock | ImageBlock | VideoBlock]) -> None:
        self._input = input_data

    # Implement other required methods with minimal implementations
    def get_state_visit_count(self, state: MockState) -> int:
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

    def get_contexts(self) -> dict[MockState, IContext]:
        return {}

    def get_state(self) -> MockState:
        if self._state is None:
            raise ValueError("State not set")
        return self._state

    def set_state(self, state: MockState) -> None:
        self._state = state

    def get_event(self) -> MockEvent:
        if self._event is None:
            raise ValueError("Event not set")
        return self._event

    def set_event(self, event: MockEvent) -> None:
        self._event = event

    def get_stage(self) -> str:
        return "test"

    def set_stage(self, stage: str) -> None:
        pass

    def get_valid_states(self) -> set[MockState]:
        return self._valid_states

    def get_current_state(self) -> MockState:
        if self._state is None:
            raise ValueError("State not set")
        return self._state

    def get_transitions(self) -> dict[tuple[MockState, MockEvent], tuple[MockState, Any]]:
        return self._transitions

    def compile(self) -> None:
        self._compiled = True

    def is_compiled(self) -> bool:
        return self._compiled

    async def handle_event(self, event: MockEvent) -> None:
        pass

    def reset(self) -> None:
        self._state = MockState()
        self._event = MockEvent()


class MockContext:
    """模拟上下文对象"""

    def __init__(self) -> None:
        self._messages: list[Message] = []

    def get_context_data(self) -> list[Message]:
        return self._messages

    def append_context_data(self, message: Message) -> None:
        self._messages.append(message)

    def clear_context_data(self) -> None:
        self._messages.clear()


class MockQueue(IAsyncQueue[Message]):
    """模拟消息队列"""

    def __init__(self) -> None:
        self.messages: list[Message] = []
        self._is_closed: bool = False

    async def put(self, item: Message, block: bool = True, timeout: float | None = None) -> None:
        self.messages.append(item)

    async def put_nowait(self, item: Message) -> None:
        self.messages.append(item)

    async def get(self, block: bool = True, timeout: float | None = None) -> Message:
        if self.messages:
            return self.messages.pop(0)
        raise ValueError("Empty queue")

    async def get_nowait(self) -> Message:
        if self.messages:
            return self.messages.pop(0)
        raise ValueError("Empty queue")

    def is_empty(self) -> bool:
        return len(self.messages) == 0

    def is_full(self) -> bool:
        return False

    def qsize(self) -> int:
        return len(self.messages)

    def is_closed(self) -> bool:
        return self._is_closed

    async def close(self) -> None:
        self._is_closed = True

    def size(self) -> int:
        return len(self.messages)

    def clear(self) -> None:
        self.messages.clear()


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


class TestStateMemoryHooks(unittest.IsolatedAsyncioTestCase):
    """状态记忆钩子测试"""

    def setUp(self) -> None:
        """设置测试环境"""
        self.mock_kv_db = MagicMock(spec=IKVDatabase[StateMemory])
        self.mock_state_extractor = AsyncMock()
        self.hooks = StateMemoryHooks(
            db=self.mock_kv_db,
            state_extractor=self.mock_state_extractor
        )
        self.context = {
            "user_id": "user123",
            "project_id": "project456",
            "trace_id": "trace789"
        }
        self.queue = MockQueue()
        self.task = MockTask(task_id="task001")

    @pytest.mark.asyncio
    async def test_pre_run_once_hook_with_memory(self) -> None:
        """测试 pre_run_once_hook 在有状态记忆时"""
        # 创建模拟状态记忆
        state_memory = StateMemory(
            id="user123:project456:trace789:task001",
            user_id="user123",
            project_id="project456",
            trace_id="trace789",
            task_id="task001",
            raw_data=[],
            content=[TextBlock(text="Previous state memory")],
            timestamp=datetime.now(timezone.utc).isoformat()
        )

        # 设置数据库返回状态记忆
        self.mock_kv_db.search = AsyncMock(return_value=state_memory)

        # 执行钩子
        await self.hooks.pre_run_once_hook(self.context, self.queue, self.task)

        # 验证数据库搜索调用
        self.mock_kv_db.search.assert_called_once_with(
            context=self.context,
            key="user123:project456:trace789:task001"
        )

        # 验证状态记忆被添加到任务上下文
        context_data = self.task.get_context().get_context_data()
        self.assertEqual(len(context_data), 1)
        self.assertEqual(context_data[0].role, Role.SYSTEM)
        self.assertEqual(len(context_data[0].content), 1)
        self.assertEqual(context_data[0].content[0].text, "Previous state memory")

    @pytest.mark.asyncio
    async def test_pre_run_once_hook_without_memory(self) -> None:
        """测试 pre_run_once_hook 在没有状态记忆时"""
        # 设置数据库返回 None
        self.mock_kv_db.search = AsyncMock(return_value=None)

        # 执行钩子
        await self.hooks.pre_run_once_hook(self.context, self.queue, self.task)

        # 验证数据库搜索调用
        self.mock_kv_db.search.assert_called_once()

        # 验证没有添加任何内容到任务上下文
        context_data = self.task.get_context().get_context_data()
        self.assertEqual(len(context_data), 0)

    @pytest.mark.asyncio
    async def test_pre_run_once_hook_missing_context(self) -> None:
        """测试 pre_run_once_hook 缺少必需的上下文信息"""
        # 缺少 user_id
        with self.assertRaises(AssertionError):
            await self.hooks.pre_run_once_hook({}, self.queue, self.task)

        # 缺少 project_id
        with self.assertRaises(AssertionError):
            await self.hooks.pre_run_once_hook({"user_id": "123"}, self.queue, self.task)

        # 缺少 trace_id
        with self.assertRaises(AssertionError):
            await self.hooks.pre_run_once_hook(
                {"user_id": "123", "project_id": "456"},
                self.queue,
                self.task
            )

    @pytest.mark.asyncio
    @patch('tasking.core.middleware.memory.read_markdown')
    async def test_post_run_once_hook(self, mock_read_markdown: Mock) -> None:
        """测试 post_run_once_hook"""
        # 设置模拟数据
        mock_read_markdown.return_value = "# State compress prompt"
        
        # 添加一些消息到任务上下文
        self.task.get_context().append_context_data(Message(
            role=Role.USER,
            content=[TextBlock(text="Test message")]
        ))

        # 设置状态提取器返回
        extracted_message = Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="Extracted state")]
        )
        self.mock_state_extractor.return_value = extracted_message

        # 执行钩子
        await self.hooks.post_run_once_hook(self.context, self.queue, self.task)

        # 验证状态提取器被调用
        self.mock_state_extractor.assert_called_once()
        
        # 验证提取的消息格式正确
        call_args = self.mock_state_extractor.call_args[0][0]
        self.assertIsInstance(call_args, list)
        self.assertTrue(len(call_args) > 0)

        # 验证数据库添加调用
        self.mock_kv_db.add.assert_called_once()
        call_kwargs = self.mock_kv_db.add.call_args[1]
        self.assertEqual(call_kwargs['key'], "user123:project456:trace789:task001")
        self.assertIsInstance(call_kwargs['value'], StateMemory)

    @pytest.mark.asyncio
    @patch('tasking.core.middleware.memory.read_markdown')
    async def test_post_run_once_hook_invalid_extracted_content(self, mock_read_markdown: Mock) -> None:
        """测试 post_run_once_hook 当提取的内容格式不正确时"""
        mock_read_markdown.return_value = "# State compress prompt"
        
        # 设置状态提取器返回无效格式（多个元素）
        extracted_message = Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="Extracted state"), TextBlock(text="Another block")]
        )
        self.mock_state_extractor.return_value = extracted_message

        # 应该抛出 ValueError
        with self.assertRaises(ValueError, msg="Extracted content must contain exactly one TextBlock"):
            await self.hooks.post_run_once_hook(self.context, self.queue, self.task)


class TestEpisodeMemoryHooks(unittest.IsolatedAsyncioTestCase):
    """情节记忆钩子测试"""

    def setUp(self) -> None:
        """设置测试环境"""
        self.mock_vector_db = MagicMock(spec=IVectorDatabase[EpisodeMemory])
        self.mock_memory_compressor = AsyncMock()
        self.hooks = EpisodeMemoryHooks(
            db=self.mock_vector_db,
            memory_compressor=self.mock_memory_compressor
        )
        self.context = {
            "user_id": "user123",
            "project_id": "project456",
            "trace_id": "trace789"
        }
        self.queue = MockQueue()
        self.task = MockTask(task_id="task001")

    @pytest.mark.asyncio
    @patch('tasking.core.middleware.memory.read_markdown')
    async def test_pre_run_once_hook_with_memories(self, mock_read_markdown: Mock) -> None:
        """测试 pre_run_once_hook 在有情节记忆时"""
        mock_read_markdown.return_value = "# Episode retrieval prompt"
        
        # 创建模拟情节记忆
        episode_memory1 = EpisodeMemory(
            user_id="user123",
            project_id="project456",
            trace_id="trace789",
            task_id="task001",
            episode_id="1",
            raw_data=[],
            content=[TextBlock(text="Episode 1 content")],
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        episode_memory2 = EpisodeMemory(
            user_id="user123",
            project_id="project456",
            trace_id="trace789",
            task_id="task001",
            episode_id="2",
            raw_data=[],
            content=[TextBlock(text="Episode 2 content")],
            timestamp=datetime.now(timezone.utc).isoformat()
        )

        # 设置数据库返回情节记忆
        self.mock_vector_db.search = AsyncMock(return_value=[
            (episode_memory1, 0.9),
            (episode_memory2, 0.85)
        ])

        # 执行钩子
        await self.hooks.pre_run_once_hook(self.context, self.queue, self.task)

        # 验证数据库搜索调用
        self.mock_vector_db.search.assert_called_once()
        call_kwargs = self.mock_vector_db.search.call_args[1]
        self.assertEqual(call_kwargs['top_k'], 5)
        self.assertEqual(call_kwargs['threshold'], 0.8)
        self.assertIn("task_id = 'task001'", call_kwargs['filter_expr'])

        # 验证情节记忆被添加到任务上下文
        context_data = self.task.get_context().get_context_data()
        # 应该总共添加了4个消息：2个基础消息（输入+提示词）+ 2个记忆摘要
        self.assertEqual(len(context_data), 4)

        # 验证记忆摘要消息存在
        memory_messages = [msg for msg in context_data if "相关记忆片段" in msg.content[0].text]
        self.assertEqual(len(memory_messages), 2)
        self.assertIn("相关记忆片段 1", memory_messages[0].content[0].text)
        self.assertIn("Episode 1 content", memory_messages[0].content[0].text)

    @pytest.mark.asyncio
    @patch('tasking.core.middleware.memory.read_markdown')
    async def test_pre_run_once_hook_without_memories(self, mock_read_markdown: Mock) -> None:
        """测试 pre_run_once_hook 在没有情节记忆时"""
        mock_read_markdown.return_value = "# Episode retrieval prompt"
        
        # 设置数据库返回空列表
        self.mock_vector_db.search = AsyncMock(return_value=[])

        # 执行钩子
        await self.hooks.pre_run_once_hook(self.context, self.queue, self.task)

        # 验证数据库搜索调用
        self.mock_vector_db.search.assert_called_once()

        # 验证只添加了基础消息（输入+提示词），没有记忆摘要
        context_data = self.task.get_context().get_context_data()
        # 应该添加了2个基础消息：输入消息和提示词消息
        self.assertEqual(len(context_data), 2)

        # 验证没有记忆摘要消息
        memory_messages = [msg for msg in context_data if "相关记忆片段" in msg.content[0].text]
        self.assertEqual(len(memory_messages), 0)

    @pytest.mark.asyncio
    @patch('tasking.core.middleware.memory.read_markdown')
    async def test_post_run_once_hook(self, mock_read_markdown: Mock) -> None:
        """测试 post_run_once_hook"""
        mock_read_markdown.return_value = "# Episode compress prompt"
        
        # 添加一些消息到任务上下文
        self.task.get_context().append_context_data(Message(
            role=Role.USER,
            content=[TextBlock(text="Test message")]
        ))

        # 设置记忆压缩器返回
        compressed_message = Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="Compressed episode")]
        )
        self.mock_memory_compressor.return_value = compressed_message

        # 设置数据库查询返回现有记忆
        self.mock_vector_db.query = AsyncMock(return_value=[
            EpisodeMemory(
                user_id="user123",
                project_id="project456",
                trace_id="trace789",
                task_id="task001",
                episode_id="1",
                raw_data=[],
                content=[TextBlock(text="Existing episode")],
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        ])

        # 执行钩子
        await self.hooks.post_run_once_hook(self.context, self.queue, self.task)

        # 验证记忆压缩器被调用
        self.mock_memory_compressor.assert_called_once()
        
        # 验证数据库查询调用（用于获取现有记忆数量）
        self.mock_vector_db.query.assert_called_once()
        query_kwargs = self.mock_vector_db.query.call_args[1]
        self.assertIn("task_id = 'task001'", query_kwargs['filter_expr'])

        # 验证数据库添加调用
        self.mock_vector_db.add.assert_called_once()
        add_kwargs = self.mock_vector_db.add.call_args[1]
        self.assertIsInstance(add_kwargs['memory'], EpisodeMemory)
        # 验证 episode_id 正确生成（基于现有记忆数量 + 1）
        self.assertEqual(add_kwargs['memory'].episode_id, "2")

    @pytest.mark.asyncio
    @patch('tasking.core.middleware.memory.read_markdown')
    async def test_post_run_once_hook_invalid_compressed_content(self, mock_read_markdown: Mock) -> None:
        """测试 post_run_once_hook 当压缩的内容格式不正确时"""
        mock_read_markdown.return_value = "# Episode compress prompt"
        
        # 设置记忆压缩器返回无效格式
        compressed_message = Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="Compressed episode"), TextBlock(text="Another block")]
        )
        self.mock_memory_compressor.return_value = compressed_message

        # 应该抛出 ValueError
        with self.assertRaises(ValueError, msg="Compressed content must contain exactly one TextBlock"):
            await self.hooks.post_run_once_hook(self.context, self.queue, self.task)

    @pytest.mark.asyncio
    @patch('tasking.core.middleware.memory.read_markdown')
    async def test_post_run_once_hook_missing_context(self, mock_read_markdown: Mock) -> None:
        """测试 post_run_once_hook 缺少必需的上下文信息"""
        mock_read_markdown.return_value = "# Episode compress prompt"
        
        # 缺少 user_id
        with self.assertRaises(AssertionError):
            await self.hooks.post_run_once_hook({}, self.queue, self.task)

        # 缺少 project_id
        with self.assertRaises(AssertionError):
            await self.hooks.post_run_once_hook({"user_id": "123"}, self.queue, self.task)

        # 缺少 trace_id
        with self.assertRaises(AssertionError):
            await self.hooks.post_run_once_hook(
                {"user_id": "123", "project_id": "456"},
                self.queue,
                self.task
            )


if __name__ == "__main__":
    unittest.main()
