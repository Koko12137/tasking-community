"""
Test helper functions for terminal and document editor tests.

This module provides utility functions and fixtures to support testing
of terminal and document editing functionality.
"""

import os
import sys
import tempfile
import shutil
import subprocess
from typing import Optional

from src.tool.terminal import SingleThreadTerminal


class TestWorkspace:
    """Helper class for managing test workspaces."""

    def __init__(self, name_prefix: str = "terminal_test_"):
        """Initialize test workspace.

        Args:
            name_prefix: Prefix for temporary directory name
        """
        self.temp_dir: Optional[str] = None
        self.name_prefix = name_prefix

    def create(self) -> str:
        """Create a new temporary workspace.

        Returns:
            Path to the created workspace directory
        """
        self.temp_dir = tempfile.mkdtemp(prefix=self.name_prefix)
        return self.temp_dir

    def cleanup(self) -> None:
        """Clean up the temporary workspace."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None

    def get_path(self) -> str:
        """Get the workspace path.

        Returns:
            Path to the workspace directory

        Raises:
            RuntimeError: If workspace hasn't been created
        """
        if not self.temp_dir:
            raise RuntimeError("Workspace not created. Call create() first.")
        return self.temp_dir

    def create_file(self, relative_path: str, content: str = "") -> str:
        """Create a file in the workspace.

        Args:
            relative_path: Relative path from workspace root
            content: Content to write to file

        Returns:
            Absolute path to created file
        """
        if not self.temp_dir:
            raise RuntimeError("Workspace not created. Call create() first.")

        file_path = os.path.join(self.temp_dir, relative_path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, 'w') as f:
            f.write(content)

        return file_path

    def read_file(self, relative_path: str) -> str:
        """Read a file from the workspace.

        Args:
            relative_path: Relative path from workspace root

        Returns:
            File content as string
        """
        if not self.temp_dir:
            raise RuntimeError("Workspace not created. Call create() first.")

        file_path = os.path.join(self.temp_dir, relative_path)
        with open(file_path, 'r') as f:
            return f.read()

    def file_exists(self, relative_path: str) -> bool:
        """Check if file exists in workspace.

        Args:
            relative_path: Relative path from workspace root

        Returns:
            True if file exists, False otherwise
        """
        if not self.temp_dir:
            return False

        file_path = os.path.join(self.temp_dir, relative_path)
        return os.path.exists(file_path)


def create_test_terminal(
    workspace: str,
    allowed_commands: Optional[list] = None,
    prohibited_commands: Optional[list] = None,
    disable_script_execution: bool = True
) -> SingleThreadTerminal:
    """Create a terminal instance for testing.

    Args:
        workspace: Path to workspace directory
        allowed_commands: List of allowed commands (whitelist)
        prohibited_commands: List of prohibited commands (blacklist)
        disable_script_execution: Whether to disable script execution

    Returns:
        Configured SingleThreadTerminal instance
    """
    return SingleThreadTerminal(
        workspace=workspace,
        create_workspace=False,  # Workspace should already exist
        allowed_commands=allowed_commands or [],
        prohibited_commands=prohibited_commands or [
            "sudo ", "su ", "shutdown", "reboot",
            "rm -rf /", "dd if=/", "mv /", "cp /",
            "rm -rf *", "rm -rf .*"
        ],
        disable_script_execution=disable_script_execution
    )


def run_command_in_terminal(terminal: SingleThreadTerminal, command: str) -> tuple[str, int]:
    """Run a command in terminal and return output and exit code.

    Args:
        terminal: Terminal instance
        command: Command to run

    Returns:
        Tuple of (output, exit_code)
    """
    try:
        output = terminal.run_command(f"{command}; echo $?")
        lines = output.strip().split('\n')
        if lines:
            exit_code = int(lines[-1])
            output = '\n'.join(lines[:-1])
        else:
            exit_code = 0

        return output, exit_code
    except Exception as e:
        return str(e), 1


def verify_file_content(
    workspace: TestWorkspace,
    file_path: str,
    expected_content: str,
    exact_match: bool = False
) -> bool:
    """Verify file content matches expectations.

    Args:
        workspace: Test workspace instance
        file_path: Relative path to file
        expected_content: Expected content
        exact_match: Whether to require exact match (True) or just containment (False)

    Returns:
        True if content matches expectations, False otherwise
    """
    try:
        actual_content = workspace.read_file(file_path)

        if exact_match:
            return actual_content == expected_content
        else:
            return expected_content in actual_content
    except Exception:
        return False


def count_lines_in_file(workspace: TestWorkspace, file_path: str) -> int:
    """Count the number of lines in a file.

    Args:
        workspace: Test workspace instance
        file_path: Relative path to file

    Returns:
        Number of lines in file
    """
    try:
        content = workspace.read_file(file_path)
        return len(content.split('\n')) if content else 0
    except Exception:
        return 0


def create_test_file_structure(workspace: TestWorkspace):
    """Create a standard test file structure.

    Args:
        workspace: Test workspace instance
    """
    # Create various test files
    workspace.create_file("empty.txt", "")
    workspace.create_file("single_line.txt", "Single line content")
    workspace.create_file("multi_line.txt", "Line 1\nLine 2\nLine 3\n")

    # Create nested directory structure
    workspace.create_file("dir1/file1.txt", "File in dir1")
    workspace.create_file("dir1/subdir/file2.txt", "File in nested dir")
    workspace.create_file("dir2/file3.txt", "File in dir2")


def assert_terminal_security(
    terminal: SingleThreadTerminal,
    forbidden_commands: list
):
    """Assert that terminal properly blocks forbidden commands.

    Args:
        terminal: Terminal instance to test
        forbidden_commands: List of commands that should be blocked

    Raises:
        AssertionError: If any forbidden command is not properly blocked
    """
    for cmd in forbidden_commands:
        assert not terminal.check_command(cmd), f"Security violation: {cmd} should be blocked"


def assert_terminal_functionality(
    terminal: SingleThreadTerminal,
    allowed_commands: list
):
    """Assert that terminal properly allows allowed commands.

    Args:
        terminal: Terminal instance to test
        allowed_commands: List of commands that should be allowed

    Raises:
        AssertionError: If any allowed command is not properly allowed
    """
    for cmd in allowed_commands:
        assert terminal.check_command(cmd), f"Functionality issue: {cmd} should be allowed"


def get_system_info() -> dict:
    """Get system information for test environment.

    Returns:
        Dictionary containing system information
    """
    return {
        "os": os.name,
        "platform": os.uname() if hasattr(os, 'uname') else "unknown",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "bash_available": bool(shutil.which("bash")),
        "sed_available": bool(shutil.which("sed")),
    }