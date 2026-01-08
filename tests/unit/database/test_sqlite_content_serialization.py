"""
SQLite Content Serialization Tests

确保序列化/反序列化职责由数据模型自身完成，而不是数据库实现。
"""
import json
import unittest
from unittest.mock import AsyncMock
from typing import Any

from tasking.database.sqlite import SqliteDatabase
from tasking.model import TextBlock, MultimodalContent


class MockMemory:
    """Mock memory object that serializes itself to string values."""

    def __init__(self, id: str, content: list[MultimodalContent], **extra_fields: Any) -> None:
        self.id = id
        self.content = content
        self.extra_fields = extra_fields

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "content": json.dumps([block.model_dump() for block in self.content], ensure_ascii=False),
            **{k: str(v) for k, v in self.extra_fields.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MockMemory":
        raw_content = data.get("content", "[]")
        if isinstance(raw_content, str):
            try:
                parsed = json.loads(raw_content)
            except json.JSONDecodeError:
                parsed = [raw_content]
        else:
            parsed = raw_content

        content: list[MultimodalContent] = []
        for item in parsed:
            if isinstance(item, dict):
                content.append(TextBlock.model_validate(item))
            elif isinstance(item, TextBlock):
                content.append(item)
            else:
                content.append(TextBlock(text=str(item)))

        extras = {k: v for k, v in data.items() if k not in ["id", "content"]}
        return cls(id=data["id"], content=content, **extras)


class MockSqlDBManager:
    """Mock SQL database manager for testing"""

    async def get_sql_database(self, context: dict[str, Any]) -> AsyncMock:
        """Get mock database client"""
        return AsyncMock()


class TestSQLiteContentSerialization(unittest.TestCase):
    """Test SQLite content serialization handled by memory models"""

    def setUp(self) -> None:
        """Set up test environment"""
        self.mock_manager = MockSqlDBManager()
        self.sqlite_db = SqliteDatabase(
            manager=self.mock_manager,
            table_name="test_table",
            memory_cls=MockMemory
        )

    def test_to_dict_serializes_content_to_string(self) -> None:
        memory = MockMemory(
            id="test_id",
            content=[TextBlock(text="测试文本内容")],
            user_id="u1",
        )

        memory_dict = memory.to_dict()

        self.assertIsInstance(memory_dict["content"], str)
        parsed = json.loads(memory_dict["content"])
        self.assertEqual(parsed[0]["text"], "测试文本内容")
        self.assertEqual(memory_dict["user_id"], "u1")

    def test_from_dict_deserializes_content(self) -> None:
        json_content = json.dumps([
            {"type": "text", "text": "反序列化内容"}
        ])
        restored = MockMemory.from_dict({"id": "a", "content": json_content})

        self.assertEqual(len(restored.content), 1)
        self.assertIsInstance(restored.content[0], TextBlock)
        self.assertEqual(restored.content[0].text, "反序列化内容")

    def test_process_row_uses_memory_deserialization(self) -> None:
        content_json = json.dumps([
            {"type": "text", "text": "行级内容"}
        ])
        row_dict = {"id": "row", "content": content_json}

        result = self.sqlite_db._process_row(row_dict)

        self.assertEqual(result.id, "row")
        self.assertEqual(result.content[0].text, "行级内容")

    def test_roundtrip_to_dict_from_dict(self) -> None:
        texts = ["第一块", "第二块", "第三块"]
        memory = MockMemory(id="round", content=[TextBlock(text=t) for t in texts])

        serialized = memory.to_dict()
        restored = MockMemory.from_dict(serialized)

        self.assertEqual([b.text for b in restored.content], texts)


if __name__ == "__main__":
    unittest.main()
