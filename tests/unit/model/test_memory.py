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
        """测试 MemoryProtocol 是抽象基类"""
        from abc import ABC

        self.assertTrue(issubclass(MemoryProtocol, ABC))
        self.assertTrue(hasattr(MemoryProtocol, '__abstractmethods__'))

        # 验证必需的抽象方法
        abstract_methods = MemoryProtocol.__abstractmethods__
        expected_methods = {'to_dict', 'from_dict'}
        self.assertEqual(abstract_methods, expected_methods)

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

    def __init__(self, id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        self.id = id
        self.content = content
        self.metadata = metadata or {}

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
        memory = ConcreteMemory("test_id", "test_content", {"key": "value"})

        self.assertEqual(memory.id, "test_id")
        self.assertEqual(memory.content, "test_content")
        self.assertEqual(memory.metadata, {"key": "value"})

    def test_to_dict_conversion(self) -> None:
        """测试转换为字典"""
        memory = ConcreteMemory("test_id", "test_content", {"key": "value"})
        result = memory.to_dict()

        expected = {
            "id": "test_id",
            "content": "test_content",
            "metadata": {"key": "value"}
        }
        self.assertEqual(result, expected)

    def test_from_dict_creation(self) -> None:
        """测试从字典创建"""
        data = {
            "id": "test_id",
            "content": "test_content",
            "metadata": {"key": "value"}
        }
        memory = ConcreteMemory.from_dict(data)

        self.assertEqual(memory.id, "test_id")
        self.assertEqual(memory.content, "test_content")
        self.assertEqual(memory.metadata, {"key": "value"})

    def test_round_trip_conversion(self) -> None:
        """测试往返转换"""
        original = ConcreteMemory("test_id", "test_content", {"key": "value"})
        dict_data = original.to_dict()
        restored = ConcreteMemory.from_dict(dict_data)

        self.assertEqual(original.id, restored.id)
        self.assertEqual(original.content, restored.content)
        self.assertEqual(original.metadata, restored.metadata)


class TestEpisodeMemory(unittest.TestCase):
    """情节记忆测试"""

    def test_episode_memory_creation(self) -> None:
        """测试情节记忆创建"""
        episode_id = str(uuid4())
        memory = EpisodeMemory(
            id=episode_id,
            title="测试情节",
            description="这是一个测试情节",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-01T01:00:00Z"
        )

        self.assertEqual(memory.id, episode_id)
        self.assertEqual(memory.title, "测试情节")
        self.assertEqual(memory.description, "这是一个测试情节")
        self.assertEqual(memory.start_time, "2024-01-01T00:00:00Z")
        self.assertEqual(memory.end_time, "2024-01-01T01:00:00Z")

    def test_episode_memory_to_dict(self) -> None:
        """测试情节记忆转换为字典"""
        episode_id = str(uuid4())
        memory = EpisodeMemory(
            id=episode_id,
            title="测试情节",
            description="测试描述",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-01T01:00:00Z",
            participants=["Alice", "Bob"],
            location="测试地点"
        )
        result = memory.to_dict()

        expected = {
            "id": episode_id,
            "title": "测试情节",
            "description": "测试描述",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T01:00:00Z",
            "participants": ["Alice", "Bob"],
            "location": "测试地点",
            "metadata": {}
        }
        self.assertEqual(result, expected)

    def test_episode_memory_from_dict(self) -> None:
        """测试从字典创建情节记忆"""
        episode_id = str(uuid4())
        data = {
            "id": episode_id,
            "title": "测试情节",
            "description": "测试描述",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T01:00:00Z",
            "participants": ["Alice", "Bob"],
            "location": "测试地点",
            "metadata": {"importance": "high"}
        }
        memory = EpisodeMemory.from_dict(data)

        self.assertEqual(memory.id, episode_id)
        self.assertEqual(memory.title, "测试情节")
        self.assertEqual(memory.description, "测试描述")
        self.assertEqual(memory.start_time, "2024-01-01T00:00:00Z")
        self.assertEqual(memory.end_time, "2024-01-01T01:00:00Z")
        self.assertEqual(memory.participants, ["Alice", "Bob"])
        self.assertEqual(memory.location, "测试地点")
        self.assertEqual(memory.metadata, {"importance": "high"})

    def test_episode_memory_defaults(self) -> None:
        """测试情节记忆默认值"""
        memory = EpisodeMemory(
            id="test_id",
            title="测试情节"
        )

        self.assertIsNone(memory.description)
        self.assertIsNone(memory.start_time)
        self.assertIsNone(memory.end_time)
        self.assertEqual(memory.participants, [])
        self.assertIsNone(memory.location)
        self.assertEqual(memory.metadata, {})


class TestProcedureMemory(unittest.TestCase):
    """程序记忆测试"""

    def test_procedure_memory_creation(self) -> None:
        """测试程序记忆创建"""
        memory = ProcedureMemory(
            id="test_id",
            name="测试程序",
            description="这是一个测试程序",
            steps=["步骤1", "步骤2", "步骤3"],
            prerequisites=["前提1", "前提2"]
        )

        self.assertEqual(memory.id, "test_id")
        self.assertEqual(memory.name, "测试程序")
        self.assertEqual(memory.description, "这是一个测试程序")
        self.assertEqual(memory.steps, ["步骤1", "步骤2", "步骤3"])
        self.assertEqual(memory.prerequisites, ["前提1", "前提2"])

    def test_procedure_memory_to_dict(self) -> None:
        """测试程序记忆转换为字典"""
        memory = ProcedureMemory(
            id="test_id",
            name="测试程序",
            description="测试描述",
            steps=["步骤1", "步骤2"],
            prerequisites=["前提1"],
            category="测试类别"
        )
        result = memory.to_dict()

        expected = {
            "id": "test_id",
            "name": "测试程序",
            "description": "测试描述",
            "steps": ["步骤1", "步骤2"],
            "prerequisites": ["前提1"],
            "category": "测试类别",
            "metadata": {}
        }
        self.assertEqual(result, expected)

    def test_procedure_memory_from_dict(self) -> None:
        """测试从字典创建程序记忆"""
        data = {
            "id": "test_id",
            "name": "测试程序",
            "description": "测试描述",
            "steps": ["步骤1", "步骤2"],
            "prerequisites": ["前提1"],
            "category": "测试类别",
            "metadata": {"difficulty": "medium"}
        }
        memory = ProcedureMemory.from_dict(data)

        self.assertEqual(memory.id, "test_id")
        self.assertEqual(memory.name, "测试程序")
        self.assertEqual(memory.description, "测试描述")
        self.assertEqual(memory.steps, ["步骤1", "步骤2"])
        self.assertEqual(memory.prerequisites, ["前提1"])
        self.assertEqual(memory.category, "测试类别")
        self.assertEqual(memory.metadata, {"difficulty": "medium"})

    def test_procedure_memory_defaults(self) -> None:
        """测试程序记忆默认值"""
        memory = ProcedureMemory(
            id="test_id",
            name="测试程序"
        )

        self.assertIsNone(memory.description)
        self.assertEqual(memory.steps, [])
        self.assertEqual(memory.prerequisites, [])
        self.assertIsNone(memory.category)
        self.assertEqual(memory.metadata, {})


class TestSemanticMemory(unittest.TestCase):
    """语义记忆测试"""

    def test_semantic_memory_creation(self) -> None:
        """测试语义记忆创建"""
        memory = SemanticMemory(
            id="test_id",
            concept="测试概念",
            definition="这是测试概念的定义",
            examples=["例子1", "例子2"],
            related_concepts=["相关概念1", "相关概念2"]
        )

        self.assertEqual(memory.id, "test_id")
        self.assertEqual(memory.concept, "测试概念")
        self.assertEqual(memory.definition, "这是测试概念的定义")
        self.assertEqual(memory.examples, ["例子1", "例子2"])
        self.assertEqual(memory.related_concepts, ["相关概念1", "相关概念2"])

    def test_semantic_memory_to_dict(self) -> None:
        """测试语义记忆转换为字典"""
        memory = SemanticMemory(
            id="test_id",
            concept="测试概念",
            definition="测试定义",
            examples=["例子1"],
            related_concepts=["相关概念"],
            domain="测试域"
        )
        result = memory.to_dict()

        expected = {
            "id": "test_id",
            "concept": "测试概念",
            "definition": "测试定义",
            "examples": ["例子1"],
            "related_concepts": ["相关概念"],
            "domain": "测试域",
            "metadata": {}
        }
        self.assertEqual(result, expected)

    def test_semantic_memory_from_dict(self) -> None:
        """测试从字典创建语义记忆"""
        data = {
            "id": "test_id",
            "concept": "测试概念",
            "definition": "测试定义",
            "examples": ["例子1"],
            "related_concepts": ["相关概念"],
            "domain": "测试域",
            "metadata": {"confidence": 0.9}
        }
        memory = SemanticMemory.from_dict(data)

        self.assertEqual(memory.id, "test_id")
        self.assertEqual(memory.concept, "测试概念")
        self.assertEqual(memory.definition, "测试定义")
        self.assertEqual(memory.examples, ["例子1"])
        self.assertEqual(memory.related_concepts, ["相关概念"])
        self.assertEqual(memory.domain, "测试域")
        self.assertEqual(memory.metadata, {"confidence": 0.9})

    def test_semantic_memory_defaults(self) -> None:
        """测试语义记忆默认值"""
        memory = SemanticMemory(
            id="test_id",
            concept="测试概念"
        )

        self.assertIsNone(memory.definition)
        self.assertEqual(memory.examples, [])
        self.assertEqual(memory.related_concepts, [])
        self.assertIsNone(memory.domain)
        self.assertEqual(memory.metadata, {})


class TestStateMemory(unittest.TestCase):
    """状态记忆测试"""

    def test_state_memory_creation(self) -> None:
        """测试状态记忆创建"""
        memory = StateMemory(
            id="test_id",
            state_name="测试状态",
            state_value="active",
            state_type="process_state",
            context={"process_id": "12345", "step": 1}
        )

        self.assertEqual(memory.id, "test_id")
        self.assertEqual(memory.state_name, "测试状态")
        self.assertEqual(memory.state_value, "active")
        self.assertEqual(memory.state_type, "process_state")
        self.assertEqual(memory.context, {"process_id": "12345", "step": 1})

    def test_state_memory_to_dict(self) -> None:
        """测试状态记忆转换为字典"""
        memory = StateMemory(
            id="test_id",
            state_name="测试状态",
            state_value="active",
            state_type="process_state",
            context={"process_id": "12345"},
            timestamp="2024-01-01T00:00:00Z"
        )
        result = memory.to_dict()

        expected = {
            "id": "test_id",
            "state_name": "测试状态",
            "state_value": "active",
            "state_type": "process_state",
            "context": {"process_id": "12345"},
            "timestamp": "2024-01-01T00:00:00Z",
            "metadata": {}
        }
        self.assertEqual(result, expected)

    def test_state_memory_from_dict(self) -> None:
        """测试从字典创建状态记忆"""
        data = {
            "id": "test_id",
            "state_name": "测试状态",
            "state_value": "active",
            "state_type": "process_state",
            "context": {"process_id": "12345"},
            "timestamp": "2024-01-01T00:00:00Z",
            "metadata": {"persistent": True}
        }
        memory = StateMemory.from_dict(data)

        self.assertEqual(memory.id, "test_id")
        self.assertEqual(memory.state_name, "测试状态")
        self.assertEqual(memory.state_value, "active")
        self.assertEqual(memory.state_type, "process_state")
        self.assertEqual(memory.context, {"process_id": "12345"})
        self.assertEqual(memory.timestamp, "2024-01-01T00:00:00Z")
        self.assertEqual(memory.metadata, {"persistent": True})

    def test_state_memory_defaults(self) -> None:
        """测试状态记忆默认值"""
        memory = StateMemory(
            id="test_id",
            state_name="测试状态"
        )

        self.assertIsNone(memory.state_value)
        self.assertIsNone(memory.state_type)
        self.assertEqual(memory.context, {})
        self.assertIsNone(memory.timestamp)
        self.assertEqual(memory.metadata, {})


class TestMemoryTypeVariable(unittest.TestCase):
    """记忆类型变量测试"""

    def test_memory_type_variable(self) -> None:
        """测试 MemoryT 类型变量"""
        from typing import TypeVar

        # 验证 MemoryT 是类型变量
        self.assertTrue(isinstance(MemoryT, TypeVar))
        self.assertEqual(MemoryT.__name__, 'MemoryT')

    def test_memory_type_constraints(self) -> None:
        """测试 MemoryT 类型约束"""
        # MemoryT 应该被限制为 MemoryProtocol 的子类型
        # 这个测试确保类型系统正确使用 MemoryT

        def process_memory(memory: MemoryT) -> dict[str, Any]:
            return memory.to_dict()

        # 测试不同的记忆类型
        episode = EpisodeMemory(id="test", title="test")
        procedure = ProcedureMemory(id="test", name="test")
        semantic = SemanticMemory(id="test", concept="test")
        state = StateMemory(id="test", state_name="test")

        # 所有类型都应该能够使用 process_memory 函数
        episode_dict = process_memory(episode)
        procedure_dict = process_memory(procedure)
        semantic_dict = process_memory(semantic)
        state_dict = process_memory(state)

        self.assertIsInstance(episode_dict, dict)
        self.assertIsInstance(procedure_dict, dict)
        self.assertIsInstance(semantic_dict, dict)
        self.assertIsInstance(state_dict, dict)


if __name__ == "__main__":
    unittest.main()