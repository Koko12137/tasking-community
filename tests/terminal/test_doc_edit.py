"""
Text editor tool tests.

This module contains comprehensive tests for the text editor implementation,
including line-based editing operations, file creation, and security constraints.
"""

import os
import tempfile
import shutil
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.tool.terminal import SingleThreadTerminal
from src.tool.text_edit import TextEditor, EditOperation


class TestTextEditor:
    """Test cases for TextEditor implementation."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="doc_edit_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def terminal(self, temp_workspace):
        """Create a terminal instance with a temporary workspace."""
        # Change to temp workspace before creating terminal
        old_cwd = os.getcwd()
        os.chdir(temp_workspace)

        term = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True,
            allowed_commands=["ls", "cd", "pwd", "cat", "sed", "touch", "mkdir", "wc", "rm", "echo"],
            disable_script_execution=True
        )

        # Restore original directory
        os.chdir(old_cwd)

        yield term
        term.close()

    @pytest.fixture
    def text_editor(self, terminal):
        """Create a text editor instance."""
        return TextEditor(terminal=terminal)

    @pytest.fixture
    def test_file_path(self, temp_workspace):
        """Create a test file path."""
        return os.path.join(temp_workspace, "test_file.txt")

    def test_initialization(self, terminal):
        """Test text editor initialization."""
        editor = TextEditor(terminal=terminal)
        assert editor._terminal == terminal
        assert editor._workspace == terminal.get_workspace()
        assert isinstance(editor._sed_inplace_arg, list)

    def test_initialization_fails_without_workspace(self):
        """Test text editor initialization fails without workspace."""
        mock_terminal = Mock()
        mock_terminal.get_workspace.return_value = ""
        mock_terminal.get_allowed_commands.return_value = []
        mock_terminal.is_script_execution_disabled.return_value = True

        with pytest.raises(RuntimeError):
            TextEditor(terminal=mock_terminal)

    def test_resolve_file_path_absolute(self, text_editor, temp_workspace):
        """Test resolving absolute file paths."""
        absolute_path = os.path.join(temp_workspace, "test.txt")
        file_abs, file_rel = text_editor._resolve_file_path(absolute_path)

        assert file_abs == absolute_path
        assert file_rel == "test.txt"

    def test_resolve_file_path_relative(self, text_editor, temp_workspace):
        """Test resolving relative file paths."""
        relative_path = "subdir/test.txt"
        file_abs, file_rel = text_editor._resolve_file_path(relative_path)

        expected_abs = os.path.join(temp_workspace, relative_path)
        assert file_abs == expected_abs
        assert file_rel == relative_path

    def test_resolve_file_path_outside_workspace(self, text_editor):
        """Test resolving paths outside workspace raises error."""
        outside_path = "/etc/passwd"

        with pytest.raises(RuntimeError):
            text_editor._resolve_file_path(outside_path)

    def test_get_file_line_count_empty_file(self, text_editor, temp_workspace):
        """Test getting line count of empty file."""
        file_path = os.path.join(temp_workspace, "empty.txt")
        with open(file_path, 'w') as f:
            pass  # Create empty file

        line_count = text_editor._get_file_line_count("empty.txt")
        assert line_count == 0

    def test_get_file_line_count_nonexistent_file(self, text_editor):
        """Test getting line count of nonexistent file."""
        line_count = text_editor._get_file_line_count("nonexistent.txt")
        assert line_count == 0

    def test_get_file_line_count_multiple_lines(self, text_editor, temp_workspace):
        """Test getting line count of file with multiple lines."""
        file_path = os.path.join(temp_workspace, "lines.txt")
        with open(file_path, 'w') as f:
            f.write("line 1\nline 2\nline 3\n")

        line_count = text_editor._get_file_line_count("lines.txt")
        assert line_count == 3

    def test_ensure_parent_dir_exists(self, text_editor, temp_workspace):
        """Test ensuring parent directory exists."""
        nested_path = os.path.join(temp_workspace, "level1", "level2", "test.txt")
        text_editor._ensure_parent_dir(nested_path)

        assert os.path.exists(os.path.join(temp_workspace, "level1", "level2"))

    def test_escape_sed_content(self, text_editor):
        """Test escaping special characters for sed."""
        # Test basic escaping
        assert text_editor._escape_sed_content("path/to/file") == "path\\/to\\/file"
        assert text_editor._escape_sed_content("replace & insert") == "replace \\& insert"
        assert text_editor._escape_sed_content(r"c:\path") == r"c:\\path"

        # Test multiline content
        multiline = "line 1\nline 2"
        escaped = text_editor._escape_sed_content(multiline)
        assert "line 1" in escaped
        assert "line 2" in escaped

    def test_edit_parameter_validation(self, text_editor):
        """Test edit method parameter validation."""
        file_path = "test.txt"

        # Empty operations list should raise ValueError
        with pytest.raises(ValueError):
            text_editor.edit(
                file_path=file_path,
                operations=[]
            )

        # Test that invalid operations are caught at runtime (type checking happens at development time)
        from unittest.mock import Mock

        with pytest.raises(Exception):  # Could be ValueError or other validation error
            # Create a mock operation that simulates invalid data
            mock_op = Mock()
            mock_op.line = 1
            mock_op.op = "invalid_op"  # This would be caught by type checker in real code
            mock_op.content = "content"
            text_editor.edit(
                file_path=file_path,
                operations=[mock_op]
            )

        # Test that non-integer line numbers are rejected
        with pytest.raises(Exception):  # Could be TypeError or other validation error
            mock_op2 = Mock()
            mock_op2.line = "not_a_number"  # Invalid type for line number
            mock_op2.op = "modify"
            mock_op2.content = "content"
            text_editor.edit(
                file_path=file_path,
                operations=[mock_op2]
            )

        # Negative line number for non-insert operations should raise ValueError
        with pytest.raises(ValueError):
            text_editor.edit(
                file_path=file_path,
                operations=[EditOperation(line=-1, op="modify", content="content")]
            )

    def test_edit_new_file(self, text_editor, temp_workspace):
        """Test creating a new file (default behavior - allowed)."""
        file_path = "new_file.txt"

        # Create file with initial content
        text_editor.edit(
            file_path=file_path,
            operations=[EditOperation(line=0, op="insert", content="First line")]
        )

        # Verify file was created and contains content
        file_abs = os.path.join(temp_workspace, file_path)
        assert os.path.exists(file_abs)

        with open(file_abs, 'r') as f:
            content = f.read()
        assert "First line" in content

    def test_edit_modify_existing_file(self, text_editor, test_file_path):
        """Test modifying lines in existing file."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nLine 2\nLine 3\n")

        # Modify line 2
        text_editor.edit(
            file_path=test_file_path,
            operations=[EditOperation(line=2, op="modify", content="Modified line 2")]
        )

        # Verify modification
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert "Line 1" in content
        assert "Modified line 2" in content
        assert "Line 3" in content

    def test_edit_delete_lines(self, text_editor, test_file_path):
        """Test deleting lines from file."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nLine 2\nLine 3\nLine 4\n")

        # Delete lines 2 and 3
        text_editor.edit(
            file_path=test_file_path,
            operations=[
                EditOperation(line=3, op="delete", content=""),
                EditOperation(line=2, op="delete", content="")
            ]
        )

        # Verify deletion
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert "Line 1" in content
        assert "Line 2" not in content
        assert "Line 3" not in content
        assert "Line 4" in content

    def test_edit_insert_lines(self, text_editor, test_file_path):
        """Test inserting lines into file."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nLine 3\n")

        # Insert line at position 2
        text_editor.edit(
            file_path=test_file_path,
            operations=[EditOperation(line=2, op="insert", content="Line 2")]
        )

        # Verify insertion
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert "Line 1\nLine 2\nLine 3" in content

    def test_edit_insert_at_beginning(self, text_editor, test_file_path):
        """Test inserting line at beginning of file."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 2\nLine 3\n")

        # Insert at beginning (line 0)
        text_editor.edit(
            file_path=test_file_path,
            operations=[EditOperation(line=0, op="insert", content="Line 1")]
        )

        # Verify insertion
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert content.startswith("Line 1\n")

    def test_edit_insert_at_end(self, text_editor, test_file_path):
        """Test inserting line at end of file."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nLine 2\n")

        # Insert at end (line -1)
        text_editor.edit(
            file_path=test_file_path,
            operations=[EditOperation(line=-1, op="insert", content="Line 3")]
        )

        # Verify insertion
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert content.endswith("Line 3\n")

    def test_edit_multiple_operations(self, text_editor, test_file_path):
        """Test performing multiple operations in one call."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nOld line 2\nLine 3\nLine 4\n")

        # Perform multiple operations
        text_editor.edit(
            file_path=test_file_path,
            operations=[
                EditOperation(line=4, op="delete", content=""),
                EditOperation(line=2, op="modify", content="New line 2"),
                EditOperation(line=0, op="insert", content="Prologue"),
                EditOperation(line=-1, op="insert", content="Epilogue")
            ]
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

    def test_edit_with_special_characters(self, text_editor, test_file_path):
        """Test editing with special characters in content."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\n")

        # Insert line with special characters
        special_content = "Path: /usr/bin, Text: &symbols, Backslashes: \\"
        text_editor.edit(
            file_path=test_file_path,
            operations=[EditOperation(line=-1, op="insert", content=special_content)]
        )

        # Verify special characters preserved
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert special_content in content

    def test_edit_multiline_content(self, text_editor, test_file_path):
        """Test editing with multiline content."""
        # Create initial file
        with open(test_file_path, 'w') as f:
            f.write("Start\n")

        # Insert multiline content
        multiline = "Line A\nLine B\nLine C"
        text_editor.edit(
            file_path=test_file_path,
            operations=[EditOperation(line=-1, op="insert", content=multiline)]
        )

        # Verify multiline content preserved
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert "Line A" in content
        assert "Line B" in content
        assert "Line C" in content

    def test_edit_subdirectory_file(self, text_editor, temp_workspace):
        """Test editing file in subdirectory."""
        subdir_file = "subdir/nested_file.txt"

        # Create file in subdirectory
        text_editor.edit(
            file_path=subdir_file,
            operations=[
                EditOperation(line=0, op="insert", content="First line"),
                EditOperation(line=-1, op="insert", content="Last line")
            ]
        )

        # Verify file created in correct location
        file_abs = os.path.join(temp_workspace, subdir_file)
        assert os.path.exists(file_abs)

        with open(file_abs, 'r') as f:
            content = f.read()
        assert "First line" in content
        assert "Last line" in content

    def test_edit_modify_nonexistent_file(self, text_editor):
        """Test modifying nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            text_editor.edit(
                file_path="nonexistent.txt",
                operations=[EditOperation(line=1, op="modify", content="content")]
            )

    def test_edit_delete_nonexistent_file(self, text_editor):
        """Test deleting from nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            text_editor.edit(
                file_path="nonexistent.txt",
                operations=[EditOperation(line=1, op="delete", content="")]
            )

    def test_edit_line_out_of_bounds(self, text_editor, test_file_path):
        """Test editing line beyond file bounds."""
        # Create file with 3 lines
        with open(test_file_path, 'w') as f:
            f.write("Line 1\nLine 2\nLine 3\n")

        # Try to modify line 10 should raise RuntimeError
        with pytest.raises(RuntimeError):
            text_editor.edit(
                file_path=test_file_path,
                operations=[EditOperation(line=10, op="modify", content="content")]
            )

        # Try to delete line 10 should raise RuntimeError
        with pytest.raises(RuntimeError):
            text_editor.edit(
                file_path=test_file_path,
                operations=[EditOperation(line=10, op="delete", content="")]
            )

    def test_edit_with_nested_directory(self, text_editor, temp_workspace):
        """Test editing file in deeply nested directory."""
        nested_file = "level1/level2/level3/deep_file.txt"

        # Create file with nested directories
        text_editor.edit(
            file_path=nested_file,
            operations=[EditOperation(line=0, op="insert", content="Deep content")]
        )

        # Verify nested directories were created
        for level in ["level1", "level1/level2", "level1/level2/level3"]:
            assert os.path.exists(os.path.join(temp_workspace, level))

        # Verify file was created
        file_abs = os.path.join(temp_workspace, nested_file)
        assert os.path.exists(file_abs)

    def test_edit_preserves_file_permissions(self, text_editor, test_file_path):
        """Test that editing preserves file permissions."""
        # Create file
        with open(test_file_path, 'w') as f:
            f.write("Original\n")

        # Set specific permissions (using os.chmod is safe in tests)
        os.chmod(test_file_path, 0o644)

        # Edit file
        text_editor.edit(
            file_path=test_file_path,
            operations=[EditOperation(line=2, op="insert", content="New line")]
        )

        # Check permissions are preserved
        stat = os.stat(test_file_path)
        assert oct(stat.st_mode)[-3:] == "644"

    def test_terminal_security_in_text_editor_context(self, text_editor, terminal):
        """Test that terminal security constraints are enforced in text editor context."""
        # The text editor should only be able to use allowed commands
        allowed_commands = terminal.get_allowed_commands()

        # Verify that dangerous commands are not in allowed list
        dangerous_commands = ["chmod", "sudo ", "apt ", "yum ", "rm -rf /"]
        for cmd in dangerous_commands:
            assert cmd not in allowed_commands, f"Dangerous command should not be allowed: {cmd}"

        # Verify script execution is disabled
        assert terminal.is_script_execution_disabled() is True

    def test_text_editor_cannot_bypass_security(self, text_editor):
        """Test that text editor operations cannot bypass terminal security."""
        # Even with malformed file paths, security should be maintained
        with pytest.raises(RuntimeError):
            # Try to access file outside workspace
            text_editor.edit(
                file_path="/etc/passwd",
                operations=[EditOperation(line=1, op="modify", content="hacked")]
            )

        with pytest.raises(RuntimeError):
            # Try path traversal
            text_editor.edit(
                file_path="../../../etc/passwd",
                operations=[EditOperation(line=1, op="modify", content="hacked")]
            )

    def test_edit_unicode_content(self, text_editor, test_file_path):
        """Test editing with unicode content."""
        # Create file
        with open(test_file_path, 'w', encoding='utf-8') as f:
            f.write("English\n")

        # Add unicode content
        unicode_content = "中文\nFrançais\nEspañol\n🎉 Emoji"
        text_editor.edit(
            file_path=test_file_path,
            operations=[EditOperation(line=-1, op="insert", content=unicode_content)]
        )

        # Verify unicode content is preserved
        with open(test_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "中文" in content
        assert "Français" in content
        assert "Español" in content
        assert "🎉 Emoji" in content

    def test_edit_empty_line_content(self, text_editor, test_file_path):
        """Test editing with empty lines."""
        # Create file
        with open(test_file_path, 'w') as f:
            f.write("Line 1\n")

        # Insert empty line
        text_editor.edit(
            file_path=test_file_path,
            operations=[EditOperation(line=2, op="insert", content="")]
        )

        # Verify empty line is preserved
        with open(test_file_path, 'r') as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert lines[1] == "\n"  # Empty line

    def test_edit_large_content(self, text_editor, test_file_path):
        """Test editing with large content."""
        # Create large content (10KB)
        large_content = "A" * 10240

        # Edit with large content
        text_editor.edit(
            file_path=test_file_path,
            operations=[EditOperation(line=0, op="insert", content=large_content)]
        )

        # Verify large content is preserved
        with open(test_file_path, 'r') as f:
            content = f.read()
        assert len(content) >= 10240
        assert large_content in content