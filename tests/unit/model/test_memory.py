"""
模型记忆模块测试套件

测试 src.model.memory 模块中的记忆相关类和协议
"""

import unittest
from typing import Any
from uuid import uuid4

from tasking.model.memory import (
    MemoryProtocol,
    MemoryT,
    EpisodeMemory,
    ProcedureMemory,
    SemanticMemory,
    StateMemory
)


class TestMemoryProtocol(unittest.TestCase):
    """记忆协议测试"""

    def test_memory_protocol_is_abstract(self) -> None:
        """测试 MemoryProtocol 是协议类型"""
        from typing import Protocol

        self.assertTrue(issubclass(MemoryProtocol, Protocol))

        # 验证必需的协议方法
        required_methods = ['to_dict', 'from_dict']
        for method in required_methods:
            self.assertTrue(hasattr(MemoryProtocol, method), f"MemoryProtocol missing {method}")

        # 验证必需的协议属性
        required_properties = ['id', 'content']
        for prop in required_properties:
            self.assertTrue(hasattr(MemoryProtocol, prop), f"MemoryProtocol missing {prop}")

    def test_memory_protocol_interface(self) -> None:
        """测试 MemoryProtocol 接口定义"""
        # 验证方法存在
        self.assertTrue(hasattr(MemoryProtocol, 'to_dict'))
        self.assertTrue(hasattr(MemoryProtocol, 'from_dict'))

        # 验证方法是抽象的
        self.assertTrue(callable(MemoryProtocol.to_dict))
        self.assertTrue(callable(MemoryProtocol.from_dict))


class ConcreteMemory(MemoryProtocol):
    """具体的记忆实现，用于测试"""

    def __init__(self, id: str, content: list, metadata: dict[str, Any] | None = None) -> None:
        self._id = id
        self._content = content
        self.metadata = metadata or {}

    @property
    def id(self) -> str:
        return self._id

    @property
    def content(self) -> list:
        return self._content

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConcreteMemory":
        return cls(
            id=data["id"],
            content=data["content"],
            metadata=data.get("metadata", {})
        )


class TestMemoryProtocolImplementation(unittest.TestCase):
    """记忆协议实现测试"""

    def test_concrete_memory_creation(self) -> None:
        """测试具体记忆对象创建"""
        content = [{"type": "text", "text": "test_content"}]
        memory = ConcreteMemory("test_id", content, {"key": "value"})

        self.assertEqual(memory.id, "test_id")
        self.assertEqual(memory.content, content)
        self.assertEqual(memory.metadata, {"key": "value"})

    def test_to_dict_conversion(self) -> None:
        """测试转换为字典"""
        content = [{"type": "text", "text": "test_content"}]
        memory = ConcreteMemory("test_id", content, {"key": "value"})
        result = memory.to_dict()

        expected = {
            "id": "test_id",
            "content": content,
            "metadata": {"key": "value"}
        }
        self.assertEqual(result, expected)

    def test_from_dict_creation(self) -> None:
        """测试从字典创建"""
        content = [{"type": "text", "text": "test_content"}]
        data = {
            "id": "test_id",
            "content": content,
            "metadata": {"key": "value"}
        }
        memory = ConcreteMemory.from_dict(data)

        self.assertEqual(memory.id, "test_id")
        self.assertEqual(memory.content, content)
        self.assertEqual(memory.metadata, {"key": "value"})

    def test_round_trip_conversion(self) -> None:
        """测试往返转换"""
        content = [{"type": "text", "text": "test_content"}]
        original = ConcreteMemory("test_id", content, {"key": "value"})
        dict_data = original.to_dict()
        restored = ConcreteMemory.from_dict(dict_data)

        self.assertEqual(original.id, restored.id)
        self.assertEqual(original.content, restored.content)
        self.assertEqual(original.metadata, restored.metadata)


class TestEpisodeMemory(unittest.TestCase):
    """情节记忆测试"""

    def test_episode_memory_creation(self) -> None:
        """测试情节记忆创建"""
        from tasking.model.message import Message, Role, TextBlock

        messages = [Message(role=Role.USER, content=[TextBlock(text="Hello")])]
        content = [TextBlock(text="Hello")]

        memory = EpisodeMemory(
            user_id="user123",
            project_id="project456",
            trace_id="trace789",
            task_id="task001",
            episode_id="episode001",
            raw_data=messages,
            content=content,
            timestamp="2024-01-01T00:00:00Z"
        )

        self.assertEqual(memory.user_id, "user123")
        self.assertEqual(memory.project_id, "project456")
        self.assertEqual(memory.trace_id, "trace789")
        self.assertEqual(memory.task_id, "task001")
        self.assertEqual(memory.episode_id, "episode001")
        self.assertEqual(memory.content, content)
        self.assertEqual(memory.timestamp, "2024-01-01T00:00:00Z")

    def test_episode_memory_to_dict(self) -> None:
        """测试情节记忆转换为字典"""
        from tasking.model.message import Message, Role, TextBlock

        messages = [Message(role=Role.USER, content=[TextBlock(text="Hello")])]
        content = [TextBlock(text="Hello")]

        memory = EpisodeMemory(
            user_id="user123",
            project_id="project456",
            trace_id="trace789",
            task_id="task001",
            episode_id="episode001",
            raw_data=messages,
            content=content,
            timestamp="2024-01-01T00:00:00Z"
        )
        result = memory.to_dict()

        # Check key fields exist
        self.assertIn("user_id", result)
        self.assertIn("project_id", result)
        self.assertIn("trace_id", result)
        self.assertIn("task_id", result)
        self.assertIn("episode_id", result)
        self.assertIn("raw_data", result)
        self.assertIn("content", result)
        self.assertIn("timestamp", result)

        self.assertEqual(result["user_id"], "user123")
        self.assertEqual(result["project_id"], "project456")
        self.assertEqual(result["task_id"], "task001")
        self.assertEqual(result["episode_id"], "episode001")
        self.assertEqual(result["timestamp"], "2024-01-01T00:00:00Z")

    def test_episode_memory_from_dict(self) -> None:
        """测试从字典创建情节记忆"""
        data = {
            "id": "test_id",
            "user_id": "user123",
            "project_id": "project456",
            "trace_id": "trace789",
            "task_id": "task001",
            "episode_id": "episode001",
            "raw_data": [{"role": "user", "content": [{"type": "text", "text": "Hello"}]}],
            "content": [{"type": "text", "text": "Hello"}],
            "timestamp": "2024-01-01T00:00:00Z"
        }
        memory = EpisodeMemory.from_dict(data)

        self.assertEqual(memory.user_id, "user123")
        self.assertEqual(memory.project_id, "project456")
        self.assertEqual(memory.trace_id, "trace789")
        self.assertEqual(memory.task_id, "task001")
        self.assertEqual(memory.episode_id, "episode001")
        self.assertEqual(memory.timestamp, "2024-01-01T00:00:00Z")
        self.assertEqual(len(memory.content), 1)
        self.assertEqual(memory.content[0].text, "Hello")


class TestMemoryTypeVariable(unittest.TestCase):
    """记忆类型变量测试"""

    def test_memory_type_variable(self) -> None:
        """测试 MemoryT 类型变量"""
        from typing import TypeVar

        # 验证 MemoryT 是类型变量
        self.assertTrue(isinstance(MemoryT, TypeVar))
        self.assertEqual(MemoryT.__name__, 'MemoryT')

    def test_memory_type_constraints(self) -> None:
        """测试 MemoryT 类型约束 - 只测试类型变量不测试具体实现"""
        # MemoryT 应该被限制为 MemoryProtocol 的子类型
        # 这个测试确保类型系统正确使用 MemoryT
        from tasking.model.message import TextBlock

        def process_memory(memory: MemoryT) -> dict[str, Any]:
            return memory.to_dict()

        # 只测试 ConcreteMemory 而不是具体的实现类
        content = [{"type": "text", "text": "test"}]
        concrete = ConcreteMemory("test", content)

        result = process_memory(concrete)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["id"], "test")


if __name__ == "__main__":
    unittest.main()