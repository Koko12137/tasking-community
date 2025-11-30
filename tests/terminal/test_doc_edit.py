"""
Document editor tool tests.

This module contains comprehensive tests for the document editor implementation,
including line-based editing operations, file creation, and security constraints.
"""

import os
import tempfile
import shutil
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.tool.terminal import SingleThreadTerminal
from src.tool.doc_edit import DocumentEditor


class TestDocumentEditor:
    """Test cases for DocumentEditor implementation."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="doc_edit_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def terminal(self, temp_workspace):
        """Create a terminal instance with a temporary workspace."""
        term = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True,
            allowed_commands=["ls", "cd", "pwd", "cat", "sed", "touch", "mkdir"],
            disable_script_execution=True
        )
        yield term
        term.close()

    @pytest.fixture
    def doc_editor(self, terminal):
        """Create a document editor instance."""
        return DocumentEditor(terminal=terminal)

    @pytest.fixture
    def test_file_path(self, temp_workspace):
        """Create a test file path."""
        return os.path.join(temp_workspace, "test_file.txt")

    def test_initialization(self, terminal):
        """Test document editor initialization."""
        editor = DocumentEditor(terminal=terminal)
        assert editor._terminal == terminal
        assert editor._workspace == terminal.get_workspace()
        assert isinstance(editor._sed_inplace_arg, list)

    def test_initialization_fails_without_workspace(self):
        """Test document editor initialization fails without workspace."""
        mock_terminal = Mock()
        mock_terminal.get_workspace.return_value = ""

        with pytest.raises(RuntimeError):
            DocumentEditor(terminal=mock_terminal)

    def test_resolve_file_path_absolute(self, doc_editor, temp_workspace):
        """Test resolving absolute file paths."""
        absolute_path = os.path.join(temp_workspace, "test.txt")
        file_abs, file_rel = doc_editor._resolve_file_path(absolute_path)

        assert file_abs == absolute_path
        assert file_rel == "test.txt"

    def test_resolve_file_path_relative(self, doc_editor, temp_workspace):
        """Test resolving relative file paths."""
        relative_path = "subdir/test.txt"
        file_abs, file_rel = doc_editor._resolve_file_path(relative_path)

        expected_abs = os.path.join(temp_workspace, relative_path)
        assert file_abs == expected_abs
        assert file_rel == relative_path

    def test_resolve_file_path_outside_workspace(self, doc_editor):
        """Test resolving paths outside workspace raises error."""
        outside_path = "/etc/passwd"

        with pytest.raises(RuntimeError):
            doc_editor._resolve_file_path(outside_path)

    def test_get_file_line_count_empty_file(self, doc_editor, temp_workspace):
        """Test getting line count of empty file."""
        file_path = os.path.join(temp_workspace, "empty.txt")
        with open(file_path, 'w') as f:
            pass  # Create empty file

        line_count = doc_editor._get_file_line_count("empty.txt")
        assert line_count == 0

    def test_get_file_line_count_nonexistent_file(self, doc_editor):
        """Test getting line count of nonexistent file."""
        line_count = doc_editor._get_file_line_count("nonexistent.txt")
        assert line_count == 0

    def test_get_file_line_count_multiple_lines(self, doc_editor, temp_workspace):
        """Test getting line count of file with multiple lines."""
        file_path = os.path.join(temp_workspace, "lines.txt")
        with open(file_path, 'w') as f:
            f.write("line 1\nline 2\nline 3\n")

        line_count = doc_editor._get_file_line_count("lines.txt")
        assert line_count == 3

    def test_ensure_parent_dir_exists(self, doc_editor, temp_workspace):
        """Test ensuring parent directory exists."""
        nested_path = os.path.join(temp_workspace, "level1", "level2", "test.txt")
        doc_editor._ensure_parent_dir(nested_path)

        assert os.path.exists(os.path.join(temp_workspace, "level1", "level2"))

    def test_escape_sed_content(self, doc_editor):
        """Test escaping special characters for sed."""
        # Test basic escaping
        assert doc_editor._escape_sed_content("path/to/file") == "path\\/to\\/file"
        assert doc_editor._escape_sed_content("replace & insert") == "replace \\& insert"
        assert doc_editor._escape_sed_content(r"c:\path") == r"c:\\path"

        # Test multiline content
        multiline = "line 1\nline 2"
        escaped = doc_editor._escape_sed_content(multiline)
        assert "line 1" in escaped
        assert "line 2" in escaped

    def test_edit_parameter_validation(self, doc_editor):
        """Test edit method parameter validation."""
        file_path = "test.txt"

        # Mismatched list lengths should raise ValueError
        with pytest.raises(ValueError):
            doc_editor.edit(
                file_path=file_path,
                lines=[1, 2],
                ops=["modify"],
                contents=["content"]
            )

        # Invalid operation type should raise ValueError
        with pytest.raises(ValueError):
            doc_editor.edit(
                file_path=file_path,
                lines=[1],
                ops=["invalid_op"],
                contents=["content"]
            )

        # Invalid line number type should raise ValueError
        with pytest.raises(ValueError):
            doc_editor.edit(
                file_path=file_path,
                lines=["not_a_number"],
                ops=["modify"],
                contents=["content"]
            )

        # Negative line number for non-insert operations should raise ValueError
        with pytest.raises(ValueError):
            doc_editor.edit(
                file_path=file_path,
                lines=[-1],
                ops=["modify"],
                contents=["content"]
            )

    def test_edit_new_file_with_create(self, doc_editor, temp_workspace):
        """Test creating a new file with allow_create=True."""
        file_path = "new_file.txt"

        # Create file with initial content
        doc_editor.edit(
            file_path=file_path,
            lines=[0],
            ops=["insert"],
            contents=["First line"],
            allow_create=True
        )

        # Verify file was created and contains content
        file_abs = os.path.join(temp_workspace, file_path)
        assert os.path.exists(file_abs)

        with open(file_abs, 'r') as f:
            content = f.read()
        assert "First line" in content

    def test_edit_new_file_without_create(self, doc_editor):
        """Test editing nonexistent file with allow_create=False."""
        file_path = "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            doc_editor.edit(
                file_path=file_path,
                lines=[0],
                ops=["insert"],
                contents=["content"],
                allow_create=False
            )

    def test_edit_modify_existing_file(self, doc_editor, test_file_path):
        """Test modifying lines in existing file."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nLine 2\nLine 3\n")

        # Modify line 2
        doc_editor.edit(
            file_path=test_file_path,
            lines=[2],
            ops=["modify"],
            contents=["Modified line 2"],
            allow_create=False
        )

        # Verify modification
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert "Line 1" in content
        assert "Modified line 2" in content
        assert "Line 3" in content

    def test_edit_delete_lines(self, doc_editor, test_file_path):
        """Test deleting lines from file."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nLine 2\nLine 3\nLine 4\n")

        # Delete lines 2 and 3
        doc_editor.edit(
            file_path=test_file_path,
            lines=[3, 2],  # Delete in reverse order to avoid line number shifts
            ops=["delete", "delete"],
            contents=["", ""],
            allow_create=False
        )

        # Verify deletion
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert "Line 1" in content
        assert "Line 2" not in content
        assert "Line 3" not in content
        assert "Line 4" in content

    def test_edit_insert_lines(self, doc_editor, test_file_path):
        """Test inserting lines into file."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nLine 3\n")

        # Insert line at position 2
        doc_editor.edit(
            file_path=test_file_path,
            lines=[2],
            ops=["insert"],
            contents=["Line 2"],
            allow_create=False
        )

        # Verify insertion
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert "Line 1\nLine 2\nLine 3" in content

    def test_edit_insert_at_beginning(self, doc_editor, test_file_path):
        """Test inserting line at beginning of file."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 2\nLine 3\n")

        # Insert at beginning (line 0)
        doc_editor.edit(
            file_path=test_file_path,
            lines=[0],
            ops=["insert"],
            contents=["Line 1"],
            allow_create=False
        )

        # Verify insertion
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert content.startswith("Line 1\n")

    def test_edit_insert_at_end(self, doc_editor, test_file_path):
        """Test inserting line at end of file."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nLine 2\n")

        # Insert at end (line -1)
        doc_editor.edit(
            file_path=test_file_path,
            lines=[-1],
            ops=["insert"],
            contents=["Line 3"],
            allow_create=False
        )

        # Verify insertion
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert content.endswith("Line 3\n")

    def test_edit_multiple_operations(self, doc_editor, test_file_path):
        """Test performing multiple operations in one call."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nOld line 2\nLine 3\nLine 4\n")

        # Perform multiple operations
        doc_editor.edit(
            file_path=test_file_path,
            lines=[4, 2, 0, -1],  # Delete line 4, modify line 2, insert at start, insert at end
            ops=["delete", "modify", "insert", "insert"],
            contents=["", "New line 2", "Prologue", "Epilogue"],
            allow_create=False
        )

        # Verify all operations
        with open(test_file_path, 'r') as f:
            content = f.read()
        lines = content.strip().split('\n')
        assert lines[0] == "Prologue"
        assert lines[1] == "Line 1"
        assert lines[2] == "New line 2"
        assert lines[3] == "Line 3"
        assert lines[4] == "Epilogue"

    def test_edit_with_special_characters(self, doc_editor, test_file_path):
        """Test editing with special characters in content."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\n")

        # Insert line with special characters
        special_content = "Path: /usr/bin, Text: &symbols, Backslashes: \\"
        doc_editor.edit(
            file_path=test_file_path,
            lines=[-1],
            ops=["insert"],
            contents=[special_content],
            allow_create=False
        )

        # Verify special characters preserved
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert special_content in content

    def test_edit_multiline_content(self, doc_editor, test_file_path):
        """Test editing with multiline content."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Start\n")

        # Insert multiline content
        multiline = "Line A\nLine B\nLine C"
        doc_editor.edit(
            file_path=test_file_path,
            lines=[-1],
            ops=["insert"],
            contents=[multiline],
            allow_create=False
        )

        # Verify multiline content preserved
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert "Line A" in content
        assert "Line B" in content
        assert "Line C" in content

    def test_edit_subdirectory_file(self, doc_editor, temp_workspace):
        """Test editing file in subdirectory."""
        subdir_file = "subdir/nested_file.txt"

        # Create file in subdirectory
        doc_editor.edit(
            file_path=subdir_file,
            lines=[0, -1],
            ops=["insert", "insert"],
            contents=["First line", "Last line"],
            allow_create=True
        )

        # Verify file created in correct location
        file_abs = os.path.join(temp_workspace, subdir_file)
        assert os.path.exists(file_abs)

        with open(file_abs, 'r') as f:
            content = f.read()
        assert "First line" in content
        assert "Last line" in content

    def test_edit_modify_nonexistent_file(self, doc_editor):
        """Test modifying nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            doc_editor.edit(
                file_path="nonexistent.txt",
                lines=[1],
                ops=["modify"],
                contents=["content"],
                allow_create=True  # Even with create=True, modify should fail
            )

    def test_edit_delete_nonexistent_file(self, doc_editor):
        """Test deleting from nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            doc_editor.edit(
                file_path="nonexistent.txt",
                lines=[1],
                ops=["delete"],
                contents=[""],
                allow_create=True  # Even with create=True, delete should fail
            )

    def test_edit_line_out_of_bounds(self, doc_editor, test_file_path):
        """Test editing line beyond file bounds."""
        # Create file with 3 lines
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nLine 2\nLine 3\n")

        # Try to modify line 10 should raise RuntimeError
        with pytest.raises(RuntimeError):
            doc_editor.edit(
                file_path=test_file_path,
                lines=[10],
                ops=["modify"],
                contents=["content"],
                allow_create=False
            )

        # Try to delete line 10 should raise RuntimeError
        with pytest.raises(RuntimeError):
            doc_editor.edit(
                file_path=test_file_path,
                lines=[10],
                ops=["delete"],
                contents=[""],
                allow_create=False
            )

    def test_edit_with_nested_directory(self, doc_editor, temp_workspace):
        """Test editing file in deeply nested directory."""
        nested_file = "level1/level2/level3/deep_file.txt"

        # Create file with nested directories
        doc_editor.edit(
            file_path=nested_file,
            lines=[0],
            ops=["insert"],
            contents=["Deep content"],
            allow_create=True
        )

        # Verify nested directories were created
        for level in ["level1", "level1/level2", "level1/level2/level3"]:
            assert os.path.exists(os.path.join(temp_workspace, level))

        # Verify file was created
        file_abs = os.path.join(temp_workspace, nested_file)
        assert os.path.exists(file_abs)

    def test_edit_preserves_file_permissions(self, doc_editor, test_file_path):
        """Test that editing preserves file permissions."""
        # Create file
        with open(test_file_path, 'w') as f:
            f.write("Original\n")

        # Set specific permissions
        os.chmod(test_file_path, 0o644)

        # Edit file
        doc_editor.edit(
            file_path=test_file_path,
            lines=[2],
            ops=["insert"],
            contents=["New line"],
            allow_create=False
        )

        # Check permissions are preserved
        stat = os.stat(test_file_path)
        assert oct(stat.st_mode)[-3:] == "644"

    def test_edit_unicode_content(self, doc_editor, test_file_path):
        """Test editing with unicode content."""
        # Create file
        with open(test_file_path, 'w', encoding='utf-8') as f:
            f.write("English\n")

        # Add unicode content
        unicode_content = "中文\nFrançais\nEspañol\n🎉 Emoji"
        doc_editor.edit(
            file_path=test_file_path,
            lines=[-1],
            ops=["insert"],
            contents=[unicode_content],
            allow_create=False
        )

        # Verify unicode content is preserved
        with open(test_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "中文" in content
        assert "Français" in content
        assert "Español" in content
        assert "🎉 Emoji" in content

    def test_edit_empty_line_content(self, doc_editor, test_file_path):
        """Test editing with empty lines."""
        # Create file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\n")

        # Insert empty line
        doc_editor.edit(
            file_path=test_file_path,
            lines=[2],
            ops=["insert"],
            contents=[""],  # Empty content
            allow_create=False
        )

        # Verify empty line is preserved
        with open(test_file_path, 'r') as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert lines[1] == "\n"  # Empty line

    def test_edit_large_content(self, doc_editor, test_file_path):
        """Test editing with large content."""
        # Create large content (10KB)
        large_content = "A" * 10240

        # Edit with large content
        doc_editor.edit(
            file_path=test_file_path,
            lines=[0],
            ops=["insert"],
            contents=[large_content],
            allow_create=True
        )

        # Verify large content is preserved
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert len(content) >= 10240
        assert large_content in content