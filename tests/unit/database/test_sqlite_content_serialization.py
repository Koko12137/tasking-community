"""
SQLite Content Serialization Tests

Tests for TextBlock only serialization/deserialization in SQLite
"""
import json
import unittest
from unittest.mock import AsyncMock
from typing import Any

from tasking.database.sqlite import SqliteDatabase, SearchParams
from tasking.model import TextBlock, MultimodalContent


class MockMemory:
    """Mock memory object for testing"""

    def __init__(self, id: str, content: list[MultimodalContent], **extra_fields: Any) -> None:
        self.id = id
        self.content = content
        self.extra_fields = extra_fields

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            **self.extra_fields
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MockMemory":
        return cls(
            id=data["id"],
            content=data["content"],
            **{k: v for k, v in data.items() if k not in ["id", "content"]}
        )


class MockSqlDBManager:
    """Mock SQL database manager for testing"""

    async def get_sql_database(self, context: dict[str, Any]) -> AsyncMock:
        """Get mock database client"""
        return AsyncMock()


class TestSQLiteContentSerialization(unittest.TestCase):
    """Test SQLite content serialization"""

    def setUp(self) -> None:
        """Set up test environment"""
        self.mock_manager = MockSqlDBManager()
        self.sqlite_db = SqliteDatabase(
            manager=self.mock_manager,
            table_name="test_table",
            memory_cls=MockMemory
        )

    def test_serialize_text_content(self) -> None:
        """Test text content serialization"""
        # Create memory with text content
        memory = MockMemory(
            id="test_id",
            content=[TextBlock(text="测试文本内容")]
        )

        # Serialize
        memory_dict = memory.to_dict()
        serialized = self.sqlite_db._serialize_content(memory_dict)

        # Verify
        self.assertIn("content", serialized)
        self.assertIsInstance(serialized["content"], str)

        # Verify JSON format
        parsed = json.loads(serialized["content"])
        self.assertEqual(parsed[0]["type"], "text")
        self.assertEqual(parsed[0]["text"], "测试文本内容")

    def test_deserialize_text_content(self) -> None:
        """Test text content deserialization"""
        # Create JSON content
        json_content = json.dumps([
            {"type": "text", "text": "测试文本内容"}
        ])

        # Deserialize
        result = self.sqlite_db._deserialize_content(json_content)

        # Verify
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], TextBlock)
        self.assertEqual(result[0].text, "测试文本内容")

    def test_serialize_multiple_text_blocks(self) -> None:
        """Test serialization of multiple text blocks"""
        # Create memory with multiple text blocks
        memory = MockMemory(
            id="test_id",
            content=[
                TextBlock(text="第一行文本"),
                TextBlock(text="第二行文本"),
                TextBlock(text="第三行文本")
            ]
        )

        # Serialize
        memory_dict = memory.to_dict()
        serialized = self.sqlite_db._serialize_content(memory_dict)

        # Verify
        parsed = json.loads(serialized["content"])
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["text"], "第一行文本")
        self.assertEqual(parsed[1]["text"], "第二行文本")
        self.assertEqual(parsed[2]["text"], "第三行文本")

    def test_deserialize_multiple_text_blocks(self) -> None:
        """Test deserialization of multiple text blocks"""
        # Create JSON content
        json_content = json.dumps([
            {"type": "text", "text": "第一行文本"},
            {"type": "text", "text": "第二行文本"},
            {"type": "text", "text": "第三行文本"}
        ])

        # Deserialize
        result = self.sqlite_db._deserialize_content(json_content)

        # Verify
        self.assertEqual(len(result), 3)
        expected_texts = ["第一行文本", "第二行文本", "第三行文本"]
        for i, block in enumerate(result):
            self.assertEqual(block.text, expected_texts[i])

    def test_serialize_empty_text_content(self) -> None:
        """Test serialization of empty text content"""
        # Create memory with empty text block
        memory = MockMemory(
            id="test_id",
            content=[TextBlock(text="")]
        )

        # Serialize
        memory_dict = memory.to_dict()
        serialized = self.sqlite_db._serialize_content(memory_dict)

        # Verify
        parsed = json.loads(serialized["content"])
        self.assertEqual(parsed[0]["text"], "")

    def test_deserialize_empty_json(self) -> None:
        """Test deserialization of empty JSON array"""
        json_content = "[]"

        # Deserialize
        result = self.sqlite_db._deserialize_content(json_content)

        # Verify
        self.assertEqual(len(result), 0)

    def test_serialize_special_characters(self) -> None:
        """Test serialization of special characters"""
        special_text = "文本包含特殊字符: 中文测试 🚀 Emoji Test\n换行符测试\n多行吗？"
        memory = MockMemory(
            id="test_id",
            content=[TextBlock(text=special_text)]
        )

        # Serialize
        memory_dict = memory.to_dict()
        serialized = self.sqlite_db._serialize_content(memory_dict)

        # Deserialize and verify roundtrip
        result = self.sqlite_db._deserialize_content(serialized["content"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, special_text)

    def test_roundtrip_serialization(self) -> None:
        """Test serialization roundtrip"""
        original_texts = ["第一块文本", "第二块文本", "第三块文本", "包含特殊字符的文本: 😀"]

        # Create memory
        memory = MockMemory(
            id="test_id",
            content=[TextBlock(text=text) for text in original_texts]
        )

        # Roundtrip
        memory_dict = memory.to_dict()
        serialized = self.sqlite_db._serialize_content(memory_dict)

        # Create row dict and deserialize
        row_dict = {"id": "test_id", "content": serialized["content"]}
        restored = self.sqlite_db._process_row(row_dict)

        # Verify
        self.assertEqual(len(restored.content), len(original_texts))
        for i, text in enumerate(original_texts):
            self.assertEqual(restored.content[i].text, text)


if __name__ == "__main__":
    unittest.main()
