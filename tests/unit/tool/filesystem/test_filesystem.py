"""
LocalFileSystem tool tests.

This module contains tests for the LocalFileSystem implementation,
focusing on file system operations like file creation, reading, search, and path resolution.
"""

import os
import tempfile
import shutil
import pytest
import pytest_asyncio
from unittest.mock import Mock, patch, MagicMock

from tasking.tool.terminal import LocalTerminal
from tasking.tool.filesystem import LocalFileSystem
from tasking.model.filesystem import EditOperation


class TestLocalFileSystem:
    """Test cases for LocalFileSystem implementation."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="test_fs_workspace_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def file_path(self, temp_workspace):
        """Create a test file path."""
        asset_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "ai_intro_v1.txt")
        )
        target_path = os.path.join(temp_workspace, "test_file.txt")
        with open(asset_path, "r", encoding="utf-8") as src, open(target_path, "w", encoding="utf-8") as dst:
            dst.write(src.read())
        return target_path

    @pytest.fixture
    def new_file_path(self, temp_workspace):
        """Return a fresh file path that does not yet exist."""
        return os.path.join(temp_workspace, "new_test_file.txt")

    @pytest.fixture
    def terminal(self, temp_workspace):
        """Create a LocalTerminal instance for testing."""
        return LocalTerminal(root_dir=temp_workspace, workspace=temp_workspace)

    @pytest.fixture
    def filesystem(self, terminal):
        """Create a LocalFileSystem instance for testing."""
        return LocalFileSystem(terminal_instance=terminal)

    @pytest.mark.asyncio
    async def test_initialization(self, terminal):
        """Test LocalFileSystem initialization."""
        fs = LocalFileSystem(terminal_instance=terminal)
        assert fs._terminal == terminal
        assert fs._workspace == terminal.get_workspace()
        assert isinstance(fs._allow_commands, list)

    def test_initialization_fails_without_workspace(self):
        """Test LocalFileSystem initialization fails without workspace."""
        mock_terminal = Mock()
        mock_terminal.get_workspace.return_value = None

        with pytest.raises(RuntimeError, match="终端工作空间未初始化"):
            LocalFileSystem(terminal_instance=mock_terminal)

    def test_resolve_file_path_absolute(self, filesystem, temp_workspace):
        """Test resolving absolute file paths."""
        file_path = os.path.join(temp_workspace, "test.txt")
        abs_path, rel_path = filesystem._terminal.check_path(file_path)

        assert abs_path == file_path
        assert rel_path == "test.txt"

    def test_resolve_file_path_relative(self, filesystem, temp_workspace):
        """Test resolving relative file paths."""
        # Mock current directory
        with patch.object(filesystem._terminal, 'get_current_dir', return_value=temp_workspace):
            abs_path, rel_path = filesystem._terminal.check_path("test.txt")

            assert abs_path == os.path.join(temp_workspace, "test.txt")
            assert rel_path == "test.txt"

    def test_resolve_file_path_outside_workspace(self, filesystem):
        """Test resolving paths outside workspace raises error."""
        outside_path = "/etc/passwd"

        with pytest.raises(RuntimeError, match="文件路径超出 workspace 范围"):
            filesystem._terminal.check_path(outside_path)

    def test_file_exists_true(self, filesystem, file_path):
        """Test file_exists returns True for existing files."""
        # Create a test file
        with open(file_path, 'w') as f:
            f.write("test content")

        assert filesystem.file_exists(file_path) is True

    def test_file_exists_false(self, filesystem, new_file_path):
        """Test file_exists returns False for non-existing files."""
        assert filesystem.file_exists(new_file_path) is False

    def test_get_terminal(self, filesystem, terminal):
        """Test get_terminal returns the terminal instance."""
        assert filesystem.get_terminal() == terminal

    @pytest.mark.asyncio
    async def test_open_file_text(self, filesystem, file_path):
        """Test opening and reading a text file."""
        # Create a test file
        test_content = "Hello, World!\nThis is a test file."
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(test_content)

        # Test reading with utf-8 encoding
        result = await filesystem.open_file(file_path, "text", "utf-8")
        assert result == test_content

    @pytest.mark.asyncio
    async def test_open_file_base64(self, filesystem, file_path):
        """Test opening and reading a file as base64."""
        # Create a test file
        test_content = "Hello, World!"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(test_content)

        # Test reading with base64 encoding
        result = await filesystem.open_file(file_path, "text", "base64")
        import base64
        assert result == base64.b64encode(test_content.encode('utf-8')).decode('utf-8')

    @pytest.mark.asyncio
    async def test_open_file_stream(self, filesystem, file_path):
        """Test streaming read returns bytes chunks in order."""
        content = "Streaming content line 1\nline2" * 10
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        chunks = []
        async for chunk in filesystem.open_file_stream(file_path, chunk_size=16):
            chunks.append(chunk)

        assert b"".join(chunks) == content.encode("utf-8")

    @pytest.mark.asyncio
    async def test_open_file_nonexistent(self, filesystem, new_file_path):
        """Test opening a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await filesystem.open_file(new_file_path, "text", "utf-8")

    @pytest.mark.asyncio
    async def test_new_file_text(self, filesystem, new_file_path):
        """Test creating a new text file."""
        content = "This is a new file content."

        result = await filesystem.new_file(new_file_path, "text", content, "utf-8")

        assert "文件创建成功" in result
        assert os.path.exists(new_file_path)

        # Verify content
        with open(new_file_path, 'r', encoding='utf-8') as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_new_file_base64(self, filesystem, new_file_path):
        """Test creating a new file with base64 content."""
        content = "Hello, Base64!"
        import base64
        base64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

        result = await filesystem.new_file(new_file_path, "text", base64_content, "base64")

        assert "文件创建成功" in result
        assert os.path.exists(new_file_path)

        # Verify content
        with open(new_file_path, 'r', encoding='utf-8') as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_new_file_already_exists(self, filesystem, file_path):
        """Test creating a file that already exists raises FileExistsError."""
        # Create the file first
        with open(file_path, 'w') as f:
            f.write("existing content")

        with pytest.raises(FileExistsError):
            await filesystem.new_file(file_path, "text", "new content", "utf-8")

    @pytest.mark.asyncio
    async def test_new_file_creates_parent_directory(self, filesystem, temp_workspace):
        """Test new_file creates parent directories if they don't exist."""
        nested_path = os.path.join(temp_workspace, "subdir", "nested", "test.txt")
        content = "Nested file content."

        result = await filesystem.new_file(nested_path, "text", content, "utf-8")

        assert "文件创建成功" in result
        assert os.path.exists(nested_path)

        # Verify content
        with open(nested_path, 'r', encoding='utf-8') as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_new_file_utf8_validation(self, filesystem, new_file_path):
        """Test new_file validates UTF-8 content."""
        # Valid UTF-8 content should work
        valid_content = "Hello 世界 🌍"
        result = await filesystem.new_file(new_file_path, "text", valid_content, "utf-8")
        assert "文件创建成功" in result

    @pytest.mark.asyncio
    async def test_search_functionality(self, filesystem, temp_workspace):
        """Test basic search functionality."""
        # Create test files
        test_file1 = os.path.join(temp_workspace, "file1.py")
        test_file2 = os.path.join(temp_workspace, "file2.txt")

        with open(test_file1, 'w', encoding='utf-8') as f:
            f.write("def hello():\n    print('Hello, World!')")

        with open(test_file2, 'w', encoding='utf-8') as f:
            f.write("This is a text file\nwith multiple lines")

        # Test search for simple text
        from tasking.model.filesystem import SearchPattern, SearchParams

        search_params = SearchParams(
            content_pattern=SearchPattern(pattern="hello", case_sensitive=False),
            search_paths=[temp_workspace]
        )

        result = await filesystem.search(search_params)

        # Search should find the content in file1.py
        assert result.total_matches >= 1

    @pytest.mark.asyncio
    async def test_search_text_format(self, filesystem, temp_workspace):
        """Test search text format output."""
        # Create a test file
        test_file = os.path.join(temp_workspace, "test.py")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("def test_function():\n    pass\n")

        # Test search
        from tasking.model.filesystem import SearchPattern, SearchParams, FileFilter

        search_params = SearchParams(
            content_pattern=SearchPattern(pattern="def", case_sensitive=False),
            search_paths=[temp_workspace]
        )

        result = await filesystem.search_text(search_params)

        assert "def" in result
        assert "test.py" in result

    @pytest.mark.asyncio
    async def test_run_command(self, filesystem, temp_workspace):
        """Test running commands through the filesystem."""
        # Create a test file
        test_file = os.path.join(temp_workspace, "test.txt")
        with open(test_file, 'w') as f:
            f.write("Hello")

        # Run a command to list files
        result = await filesystem.get_terminal().run_command("ls")

        assert result is not None
        assert len(result) > 0

    def test_terminal_security_in_filesystem_context(self, filesystem):
        """Test that filesystem context maintains terminal security."""
        # This test ensures LocalFileSystem properly delegates to terminal
        assert hasattr(filesystem, 'get_terminal')
        terminal = filesystem.get_terminal()
        assert hasattr(terminal, 'run_command')

    def test_filesystem_cannot_bypass_security(self, filesystem, temp_workspace):
        """Test that filesystem operations respect workspace boundaries."""
        # Attempt to access file outside workspace
        outside_path = "/etc/passwd"

        with pytest.raises(RuntimeError, match="文件路径超出 workspace 范围"):
            filesystem._terminal.check_path(outside_path)

    def test_path_traversal_protection(self, filesystem, temp_workspace):
        """Test protection against path traversal attacks."""
        # Test various path traversal attempts
        malicious_paths = [
            f"{temp_workspace}/../etc/passwd",
            f"{temp_workspace}/subdir/../../etc/passwd",
            f"{temp_workspace}/./../etc/passwd",
            "/etc/passwd",
            "/tmp/../etc/passwd",
        ]
        
        for path in malicious_paths:
            with pytest.raises(RuntimeError, match="文件路径超出 workspace 范围"):
                filesystem._terminal.check_path(path)

    def test_path_normalization_in_workspace(self, filesystem, temp_workspace):
        """Test that path normalization works correctly within workspace."""
        # These paths should be valid (normalized to workspace)
        valid_paths = [
            f"{temp_workspace}/./file.txt",
            f"{temp_workspace}/subdir/../file.txt",
            f"{temp_workspace}/subdir/./file.txt",
        ]
        
        for path in valid_paths:
            file_abs, file_rel = filesystem._terminal.check_path(path)
            assert file_abs.startswith(temp_workspace)
            assert ".." not in file_rel.split(os.sep)

    @pytest.mark.asyncio
    async def test_file_operations_with_path_traversal(self, filesystem, temp_workspace):
        """Test that file operations reject path traversal attempts."""
        malicious_path = f"{temp_workspace}/../etc/passwd"
        
        # file_exists should return False for paths outside workspace
        assert not filesystem.file_exists(malicious_path)
        
        # open_file should raise RuntimeError
        with pytest.raises(RuntimeError, match="文件路径超出 workspace 范围"):
            await filesystem.open_file(malicious_path, "text", "utf-8")
        
        # new_file should raise RuntimeError
        with pytest.raises(RuntimeError, match="文件路径超出 workspace 范围"):
            await filesystem.new_file(malicious_path, "text", "content", "utf-8")

    @pytest.mark.asyncio
    async def test_terminal_show_prompt_default(self, filesystem, temp_workspace):
        """Test terminal show_prompt setting affects filesystem operations."""
        # This test verifies that LocalFileSystem inherits terminal's show_prompt setting
        # The actual behavior is delegated to the terminal
        result = await filesystem.get_terminal().run_command("pwd")
        assert result is not None
        assert temp_workspace in result or any(temp_workspace.split('/')[-1] in line for line in result.split('\n') if line.strip())

    @pytest.mark.asyncio
    async def test_terminal_show_prompt_true(self, temp_workspace):
        """Test filesystem with show_prompt=True."""
        terminal = LocalTerminal(root_dir=temp_workspace, workspace=temp_workspace, allowed_commands=["pwd", "ls"])
        fs = LocalFileSystem(terminal_instance=terminal)

        result = await fs.get_terminal().run_command("pwd", show_prompt=True)
        assert result is not None

    @pytest.mark.asyncio
    async def test_terminal_show_prompt_false(self, temp_workspace):
        """Test filesystem with show_prompt=False."""
        terminal = LocalTerminal(root_dir=temp_workspace, workspace=temp_workspace, allowed_commands=["pwd", "ls"])
        fs = LocalFileSystem(terminal_instance=terminal)

        result = await fs.get_terminal().run_command("pwd", show_prompt=False)
        assert result is not None

    @pytest.mark.asyncio
    async def test_terminal_show_prompt_no_output_command(self, filesystem):
        """Test filesystem with commands that produce no output."""
        # Commands that don't produce output should still return something
        result = await filesystem.get_terminal().run_command("echo -n")  # Echo without newline
        assert result is not None

    @pytest.mark.asyncio
    async def test_terminal_show_prompt_multiline_output(self, filesystem, temp_workspace):
        """Test filesystem with commands that produce multiple lines of output."""
        # Create multiple files to generate multiline output
        for i in range(3):
            with open(os.path.join(temp_workspace, f"file_{i}.txt"), 'w') as f:
                f.write(f"Content {i}")

        result = await filesystem.get_terminal().run_command("ls -la")
        lines = result.strip().split('\n')
        assert len(lines) >= 3  # Should have multiple lines

    @pytest.mark.asyncio
    async def test_terminal_show_prompt_path_changes(self, temp_workspace):
        """Test filesystem maintains path consistency across operations."""
        terminal = LocalTerminal(root_dir=temp_workspace, workspace=temp_workspace, allowed_commands=["pwd", "cd", "ls"])
        fs = LocalFileSystem(terminal_instance=terminal)

        # Get initial directory
        initial_result = await fs.get_terminal().run_command("pwd", show_prompt=False)
        initial_path = initial_result.strip()

        # Terminal should maintain working directory
        current_dir = terminal.get_current_dir()
        assert current_dir == temp_workspace

    @pytest.mark.asyncio
    async def test_terminal_show_prompt_with_whitespace_command(self, filesystem, temp_workspace):
        """Test filesystem handles commands with whitespace correctly."""
        # Command with trailing whitespace
        result = await filesystem.get_terminal().run_command("pwd ")
        assert result is not None
        assert temp_workspace in result

    @pytest.mark.asyncio
    async def test_terminal_show_prompt_error_handling(self, filesystem):
        """Test filesystem properly handles command errors."""
        # Invalid command should produce error output
        result = await filesystem.get_terminal().run_command("nonexistent_command_12345")
        assert result is not None
        # Error message may vary but should be present


class TestLocalFileSystemEdgeCases:
    """Test edge cases and error handling for LocalFileSystem."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="test_fs_edge_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def terminal(self, temp_workspace):
        """Create a LocalTerminal instance for testing."""
        return LocalTerminal(root_dir=temp_workspace, workspace=temp_workspace)

    @pytest.fixture
    def filesystem(self, terminal):
        """Create a LocalFileSystem instance for testing."""
        return LocalFileSystem(terminal_instance=terminal)

    @pytest.mark.asyncio
    async def test_new_file_utf8_edge_case(self, filesystem, temp_workspace):
        """Test new_file with UTF-8 edge cases."""
        file_path = os.path.join(temp_workspace, "utf8_edge_case.txt")

        # Test with valid UTF-8 but with special characters
        edge_case_content = "UTF-8 edge: \u0000 control character"
        result = await filesystem.new_file(file_path, "text", edge_case_content, "utf-8")
        assert "文件创建成功" in result

        # Verify content was written correctly
        with open(file_path, 'r', encoding='utf-8') as f:
            assert f.read() == edge_case_content

    @pytest.mark.asyncio
    async def test_search_empty_directory(self, filesystem, temp_workspace):
        """Test search in empty directory."""
        from tasking.model.filesystem import SearchPattern, SearchParams, FileFilter

        search_params = SearchParams(
            content_pattern=SearchPattern(pattern="anything"),
            search_paths=[temp_workspace]
        )

        result = await filesystem.search(search_params)
        assert result.total_matches == 0
        assert len(result.file_results) == 0

    @pytest.mark.asyncio
    async def test_search_invalid_path(self, filesystem):
        """Test search with non-existent path."""
        from tasking.model.filesystem import SearchPattern, SearchParams

        search_params = SearchParams(
            content_pattern=SearchPattern(pattern="test"),
            search_paths=["/nonexistent/path"]
        )

        result = await filesystem.search(search_params)
        assert len(result.errors) > 0

    def test_file_exists_with_symlink_outside_workspace(self, filesystem, temp_workspace):
        """Test file_exists with symlinks pointing outside workspace."""
        outside_file = os.path.join(temp_workspace, "..", "outside_file.txt")
        symlink_path = os.path.join(temp_workspace, "symlink.txt")

        # Create a file outside workspace and a symlink to it
        try:
            with open(outside_file, 'w') as f:
                f.write("outside content")

            os.symlink(outside_file, symlink_path)

            # This should still work because the symlink itself is in the workspace
            assert filesystem.file_exists(symlink_path) is True

        finally:
            # Cleanup
            if os.path.exists(symlink_path):
                os.unlink(symlink_path)
            if os.path.exists(outside_file):
                os.unlink(outside_file)

    @pytest.mark.asyncio
    async def test_open_file_binary(self, filesystem, temp_workspace):
        """Test opening binary files."""
        binary_file = os.path.join(temp_workspace, "binary.dat")

        # Create a binary file
        with open(binary_file, 'wb') as f:
            f.write(b'\x00\x01\x02\x03\x04\x05')

        # Should return base64 encoding
        result = await filesystem.open_file(binary_file, "binary", "base64")
        assert isinstance(result, str)

        import base64
        decoded = base64.b64decode(result)
        assert decoded == b'\x00\x01\x02\x03\x04\x05'