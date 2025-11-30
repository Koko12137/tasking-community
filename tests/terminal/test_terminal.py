"""
Terminal tool tests.

This module contains comprehensive tests for the terminal tool implementation,
including security checks, command execution, and workspace constraints.
"""

import os
import tempfile
import shutil
import subprocess
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.tool.terminal import ITerminal, SingleThreadTerminal


class TestITerminal:
    """Test cases for ITerminal interface."""

    def test_interface_methods(self):
        """Test that ITerminal defines all required abstract methods."""
        # Check all abstract methods are defined
        abstract_methods = ITerminal.__abstractmethods__
        expected_methods = {
            'get_workspace',
            'get_current_dir',
            'get_allowed_commands',
            'get_prohibited_commands',
            'is_script_execution_disabled',
            'open',
            'run_command',
            'check_command',
            'close'
        }

        assert abstract_methods == expected_methods


class TestSingleThreadTerminal:
    """Test cases for SingleThreadTerminal implementation."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="terminal_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def terminal(self, temp_workspace):
        """Create a terminal instance with a temporary workspace."""
        term = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True,
            allowed_commands=[],  # Allow all commands except prohibited
            prohibited_commands=["sudo ", "rm -rf /"],
            disable_script_execution=True
        )
        yield term
        term.close()

    def test_initialization(self, temp_workspace):
        """Test terminal initialization."""
        term = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True
        )

        try:
            assert term.get_workspace() == os.path.abspath(temp_workspace)
            assert term.get_current_dir() == os.path.abspath(temp_workspace)
            assert isinstance(term.get_allowed_commands(), list)
            assert isinstance(term.get_prohibited_commands(), list)
            assert isinstance(term.is_script_execution_disabled(), bool)
        finally:
            term.close()

    def test_initialization_with_existing_workspace(self, temp_workspace):
        """Test terminal initialization with existing workspace."""
        term = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=False
        )

        try:
            assert term.get_workspace() == os.path.abspath(temp_workspace)
        finally:
            term.close()

    def test_initialization_fails_with_nonexistent_workspace(self):
        """Test terminal initialization fails with nonexistent workspace."""
        nonexistent_path = "/nonexistent/path/that/should/not/exist"

        with pytest.raises(FileNotFoundError):
            SingleThreadTerminal(
                workspace=nonexistent_path,
                create_workspace=False
            )

    def test_initialization_fails_with_file_path(self, temp_workspace):
        """Test terminal initialization fails with file instead of directory."""
        file_path = os.path.join(temp_workspace, "test_file.txt")
        with open(file_path, 'w') as f:
            f.write("test")

        with pytest.raises(NotADirectoryError):
            SingleThreadTerminal(workspace=file_path)

    def test_allowed_commands_configuration(self, temp_workspace):
        """Test terminal with custom allowed commands."""
        allowed = ["ls", "cd", "pwd"]
        term = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True,
            allowed_commands=allowed
        )

        try:
            assert term.get_allowed_commands() == allowed
            assert term.is_script_execution_disabled() is True  # Default value
        finally:
            term.close()

    def test_prohibited_commands_configuration(self, temp_workspace):
        """Test terminal with custom prohibited commands."""
        prohibited = ["rm -rf", "shutdown", "sudo "]
        term = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True,
            prohibited_commands=prohibited
        )

        try:
            assert term.get_prohibited_commands() == prohibited
        finally:
            term.close()

    def test_script_execution_configuration(self, temp_workspace):
        """Test terminal script execution configuration."""
        # Test with script execution disabled (default)
        term1 = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True
        )
        try:
            assert term1.is_script_execution_disabled() is True
        finally:
            term1.close()

        # Test with script execution enabled
        term2 = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True,
            disable_script_execution=False
        )
        try:
            assert term2.is_script_execution_disabled() is False
        finally:
            term2.close()

    def test_check_command_empty(self, terminal):
        """Test command validation with empty command."""
        assert terminal.check_command("") is False
        assert terminal.check_command("   ") is False

    def test_check_command_allowed_list(self, temp_workspace):
        """Test command validation with allowed commands list."""
        term = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True,
            allowed_commands=["ls", "cd"]
        )

        try:
            # Allowed commands should pass
            assert term.check_command("ls") is True
            assert term.check_command("ls -l") is True
            assert term.check_command("cd /tmp") is True

            # Non-allowed commands should fail
            assert term.check_command("pwd") is False
            assert term.check_command("echo hello") is False
        finally:
            term.close()

    def test_check_command_prohibited_list(self, terminal):
        """Test command validation with prohibited commands."""
        # Commands containing prohibited substrings should fail
        assert terminal.check_command("sudo ls") is False
        assert terminal.check_command("rm -rf /") is False
        assert terminal.check_command("shutdown now") is False

    def test_check_command_escaped_prohibited(self, terminal):
        """Test command validation with escaped prohibited commands."""
        # Commands with prohibited commands in quotes should fail
        assert terminal.check_command("bash -c 'sudo ls'") is False
        assert terminal.check_command('python -c "rm -rf /tmp"') is False
        assert terminal.check_command("echo 'sudo reboot'") is False

    def test_check_command_script_disabled(self, terminal):
        """Test command validation with script execution disabled."""
        # Script commands should fail when disabled
        assert terminal.check_command("python script.py") is False
        assert terminal.check_command("bash script.sh") is False
        assert terminal.check_command("node app.js") is False
        assert terminal.check_command("./script.sh") is False
        assert terminal.check_command("go run main.go") is False

    def test_check_command_script_enabled(self, temp_workspace):
        """Test command validation with script execution enabled."""
        term = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True,
            disable_script_execution=False
        )

        try:
            # Script commands should pass when enabled
            assert term.check_command("python script.py") is True
            assert term.check_command("bash script.sh") is True
            assert term.check_command("./script.sh") is True
        finally:
            term.close()

    def test_check_command_path_validation(self, terminal):
        """Test command validation with path constraints."""
        # Commands with paths outside workspace should fail
        outside_path = "/etc/passwd"
        assert terminal.check_command(f"cat {outside_path}") is False
        assert terminal.check_command(f"cd {outside_path}") is False

        # Commands with relative paths that resolve outside workspace should fail
        assert terminal.check_command("cd ../../../etc") is False

    def test_check_command_cd_within_workspace(self, terminal):
        """Test cd command validation within workspace."""
        # cd commands within workspace should pass
        assert terminal.check_command("cd") is True  # cd to home
        assert terminal.check_command("cd .") is True
        assert terminal.check_command("cd ..") is True
        assert terminal.check_command("cd subdir") is True

    def test_run_command_simple(self, terminal):
        """Test running simple commands."""
        # Test pwd command
        output = terminal.run_command("pwd")
        assert terminal.get_workspace() in output

        # Test echo command
        output = terminal.run_command("echo hello world")
        assert "hello world" in output

    def test_run_command_with_options(self, terminal):
        """Test running commands with options."""
        # Create a test file
        terminal.run_command("touch test_file.txt")

        # List with options
        output = terminal.run_command("ls -la")
        assert "test_file.txt" in output

    def test_run_cd_command(self, terminal):
        """Test running cd command and checking directory sync."""
        # Create a subdirectory
        terminal.run_command("mkdir test_subdir")

        # Change to subdirectory
        terminal.run_command("cd test_subdir")

        # Check that current directory was updated
        current_dir = terminal.get_current_dir()
        assert current_dir.endswith("test_subdir")

    def test_run_command_forbidden(self, terminal):
        """Test running forbidden commands raises PermissionError."""
        with pytest.raises(PermissionError):
            terminal.run_command("sudo ls")

        with pytest.raises(PermissionError):
            terminal.run_command("rm -rf /")

    def test_run_script_when_disabled(self, terminal):
        """Test running script commands when disabled."""
        with pytest.raises(PermissionError):
            terminal.run_command("python -c 'print(1)'")

    def test_create_file_and_write_content(self, terminal):
        """Test creating files and writing content."""
        # Create a file with echo
        terminal.run_command("echo 'test content' > test.txt")

        # Read and verify content
        output = terminal.run_command("cat test.txt")
        assert "test content" in output

    def test_directory_operations(self, terminal):
        """Test directory creation and navigation."""
        # Create nested directories
        terminal.run_command("mkdir -p level1/level2/level3")

        # Navigate to nested directory
        terminal.run_command("cd level1/level2/level3")

        # Verify current directory
        current_dir = terminal.get_current_dir()
        assert current_dir.endswith("level3")

        # Go back to parent
        terminal.run_command("cd ..")
        current_dir = terminal.get_current_dir()
        assert current_dir.endswith("level2")

    def test_file_operations(self, terminal):
        """Test various file operations."""
        # Create multiple files
        terminal.run_command("touch file1.txt file2.txt file3.txt")

        # List files
        output = terminal.run_command("ls")
        assert "file1.txt" in output
        assert "file2.txt" in output
        assert "file3.txt" in output

        # Remove a file
        terminal.run_command("rm file1.txt")
        output = terminal.run_command("ls")
        assert "file1.txt" not in output
        assert "file2.txt" in output
        assert "file3.txt" in output

    def test_command_chaining(self, terminal):
        """Test command chaining with &&."""
        # Chain multiple commands
        terminal.run_command("mkdir chained_test && cd chained_test && echo 'success' > result.txt")

        # Verify all commands executed
        current_dir = terminal.get_current_dir()
        assert current_dir.endswith("chained_test")

        output = terminal.run_command("cat result.txt")
        assert "success" in output

    def test_command_with_quotes(self, terminal):
        """Test commands with quoted arguments."""
        # Test single quotes
        terminal.run_command("echo 'hello world with spaces' > quoted.txt")
        output = terminal.run_command("cat quoted.txt")
        assert "hello world with spaces" in output

        # Test double quotes
        terminal.run_command('echo "another quoted string" > double_quoted.txt')
        output = terminal.run_command("cat double_quoted.txt")
        assert "another quoted string" in output

    def test_error_handling_invalid_command(self, terminal):
        """Test error handling for invalid commands."""
        # Non-existent command should raise SubprocessError
        with pytest.raises(subprocess.SubprocessError):
            terminal.run_command("nonexistent_command_12345")

    def test_close_terminates_process(self, temp_workspace):
        """Test that close properly terminates the terminal process."""
        term = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True
        )

        # Run a command to ensure process is started
        term.run_command("echo test")

        # Close terminal
        term.close()

        # Verify process is terminated
        assert term._process is None or term._process.poll() is not None

    def test_double_close(self, terminal):
        """Test closing terminal twice doesn't raise errors."""
        # First close
        terminal.close()

        # Second close should not raise an error
        terminal.close()  # Should not raise

    def test_terminal_after_close(self, terminal):
        """Test that operations after close raise appropriate errors."""
        terminal.close()

        # Operations after close should raise RuntimeError
        with pytest.raises(RuntimeError):
            terminal.run_command("echo test")

        with pytest.raises(RuntimeError):
            terminal.check_command("echo test")


class TestTerminalSecurity:
    """Test cases for terminal security features."""

    @pytest.fixture
    def restricted_terminal(self, temp_workspace):
        """Create a terminal with strict security settings."""
        term = SingleThreadTerminal(
            workspace=temp_workspace,
            create_workspace=True,
            allowed_commands=["ls", "cd", "pwd", "echo", "cat"],
            prohibited_commands=["sudo", "rm", "shutdown", "reboot"],
            disable_script_execution=True
        )
        yield term
        term.close()

    def test_security_escaped_commands(self, restricted_terminal):
        """Test security against escaped prohibited commands."""
        # Various escape attempts should be blocked
        prohibited_attempts = [
            "bash -c 'sudo ls'",
            "python -c \"import os; os.system('sudo ls')\"",
            "echo 'sudo rm -rf /' | sh",
            "bash <<< 'sudo ls'",
            "$(sudo ls)",
            "`sudo ls`",
        ]

        for cmd in prohibited_attempts:
            assert restricted_terminal.check_command(cmd) is False, f"Command should be blocked: {cmd}"

    def test_security_path_escalation(self, restricted_terminal):
        """Test security against path escalation attempts."""
        # Path escalation attempts should be blocked
        escalation_attempts = [
            "cd /etc",
            "cd ../../../root",
            "cat /etc/passwd",
            "ls -la /root",
            "cd / && ls",
        ]

        for cmd in escalation_attempts:
            assert restricted_terminal.check_command(cmd) is False, f"Command should be blocked: {cmd}"

    def test_security_script_injection(self, restricted_terminal):
        """Test security against script injection attempts."""
        # Script injection attempts should be blocked
        script_attempts = [
            "python -c 'import os; os.system(\"rm -rf /\")'",
            "perl -e 'system(\"sudo ls\")'",
            "ruby -e 'system(\"shutdown now\")'",
            "node -e 'require(\"child_process\").exec(\"sudo ls\")'",
            "php -r 'system(\"sudo ls\");'",
        ]

        for cmd in script_attempts:
            assert restricted_terminal.check_command(cmd) is False, f"Command should be blocked: {cmd}"

    def test_security_command_substitution(self, restricted_terminal):
        """Test security against command substitution."""
        # Command substitution should be blocked if it contains prohibited commands
        substitution_attempts = [
            "echo $(sudo ls)",
            "echo `sudo ls`",
            "cat $(find / -name passwd)",
        ]

        for cmd in substitution_attempts:
            assert restricted_terminal.check_command(cmd) is False, f"Command should be blocked: {cmd}"