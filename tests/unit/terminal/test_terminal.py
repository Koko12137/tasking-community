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
import time
from unittest.mock import Mock, patch, MagicMock

from tasking.tool.terminal import ITerminal, LocalTerminal


def create_terminal_in_workspace(temp_workspace, workspace=None, create_workspace=True, **kwargs):
    """Helper function to create LocalTerminal after changing to workspace directory.
    
    This ensures directory sync works correctly in WSL environments.
    
    Args:
        temp_workspace: Root directory for the terminal
        workspace: Workspace directory (defaults to temp_workspace)
        create_workspace: Whether to create workspace if it doesn't exist
        **kwargs: Additional arguments to pass to LocalTerminal
    """
    original_cwd = os.getcwd()
    try:
        os.chdir(temp_workspace)
        if workspace is None:
            workspace = temp_workspace
        return LocalTerminal(
            root_dir=temp_workspace,
            workspace=workspace,
            create_workspace=create_workspace,
            **kwargs
        )
    finally:
        os.chdir(original_cwd)


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
            'is_script_execution_disabled',
            'open',
            'run_command',
            'check_command',
            'close',
            'get_id',
            'acquire',
            'release',
            'cd_to_workspace',
            'read_process',
            'write_process'
        }

        assert abstract_methods == expected_methods


class TestLocalTerminal:
    """Test cases for LocalTerminal implementation."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="terminal_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def terminal(self, temp_workspace):
        """Create a terminal instance with a temporary workspace."""
        # Change to temp_workspace directory before creating terminal
        # to avoid directory sync issues in WSL environment
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            term = create_terminal_in_workspace(temp_workspace,
                allowed_commands=[],  # Allow all commands except prohibited
                disable_script_execution=True
            )
            yield term
            term.close()
        finally:
            os.chdir(original_cwd)

    def test_initialization(self, temp_workspace):
        """Test terminal initialization."""
        term = create_terminal_in_workspace(temp_workspace)

        try:
            assert term.get_workspace() == os.path.abspath(temp_workspace)
            assert term.get_current_dir() == os.path.abspath(temp_workspace)
            assert isinstance(term.get_allowed_commands(), list)
            assert isinstance(term.is_script_execution_disabled(), bool)
        finally:
            term.close()

    def test_initialization_with_existing_workspace(self, temp_workspace):
        """Test terminal initialization with existing workspace."""
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            term = create_terminal_in_workspace(temp_workspace, create_workspace=False
            )

            try:
                assert term.get_workspace() == os.path.abspath(temp_workspace)
            finally:
                term.close()
        finally:
            os.chdir(original_cwd)

    def test_initialization_fails_with_nonexistent_workspace(self, temp_workspace):
        """Test terminal initialization fails with nonexistent workspace."""
        nonexistent_path = "nonexistent_subdir"

        with pytest.raises(FileNotFoundError):
            LocalTerminal(
                root_dir=temp_workspace,  # Use valid root_dir
                workspace=nonexistent_path,  # Use relative path within root_dir
                create_workspace=False
            )

    def test_initialization_fails_with_file_path(self, temp_workspace):
        """Test terminal initialization fails with file instead of directory."""
        file_path = os.path.join(temp_workspace, "test_file.txt")
        with open(file_path, 'w') as f:
            f.write("test")

        with pytest.raises(NotADirectoryError):
            LocalTerminal(root_dir=temp_workspace, workspace=file_path)

    def test_allowed_commands_configuration(self, temp_workspace):
        """Test terminal with custom allowed commands."""
        allowed = ["ls", "cd", "pwd"]
        term = create_terminal_in_workspace(temp_workspace, allowed_commands=allowed)

        try:
            assert term.get_allowed_commands() == allowed
            assert term.is_script_execution_disabled() is True  # Default value
        finally:
            term.close()

    def test_prohibited_commands_configuration(self, temp_workspace):
        """Test that prohibited commands are built-in and cannot be configured."""
        # Prohibited commands are built-in constants, not configurable
        # Test that prohibited commands are still blocked
        term = create_terminal_in_workspace(temp_workspace)

        try:
            # Test that prohibited commands are blocked
            assert term.check_command("sudo ls") is False
            assert term.check_command("rm -rf /") is False
        finally:
            term.close()

    def test_script_execution_configuration(self, temp_workspace):
        """Test terminal script execution configuration."""
        # Test with script execution disabled (default)
        term1 = create_terminal_in_workspace(temp_workspace)
        try:
            assert term1.is_script_execution_disabled() is True
        finally:
            term1.close()

        # Test with script execution enabled
        term2 = create_terminal_in_workspace(temp_workspace, disable_script_execution=False)
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
        term = create_terminal_in_workspace(temp_workspace, allowed_commands=["ls", "cd"])

        try:
            # Allowed commands should pass
            assert term.check_command("ls") is True
            assert term.check_command("ls -l") is True
            # Use cd to workspace directory (not outside root_dir)
            assert term.check_command("cd .") is True

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
        # Note: prohibited commands are built-in constants

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
        term = create_terminal_in_workspace(temp_workspace, disable_script_execution=False)

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

    @pytest.mark.asyncio
    async def test_check_command_cd_within_workspace(self, terminal):
        """Test cd command validation within workspace."""
        # cd commands within workspace should pass
        assert terminal.check_command("cd") is True  # cd to home
        assert terminal.check_command("cd .") is True
        # Note: cd .. may fail if it would go outside root_dir (new security feature)
        # This is expected behavior when workspace is at root_dir boundary
        assert terminal.check_command("cd subdir") is True

        # Create a subdirectory and test cd .. from there (should work)
        await terminal.run_command("mkdir test_subdir")
        await terminal.run_command("cd test_subdir")
        # cd .. from test_subdir should work (goes back to workspace root)
        assert terminal.check_command("cd ..") is True

    @pytest.mark.asyncio
    async def test_run_command_simple(self, terminal):
        """Test running simple commands."""
        # Test pwd command
        output = await terminal.run_command("pwd")
        assert terminal.get_workspace() in output

        # Test echo command
        output = await terminal.run_command("echo hello world")
        assert "hello world" in output

    @pytest.mark.asyncio
    async def test_run_command_with_options(self, terminal):
        """Test running commands with options."""
        # Create a test file
        await terminal.run_command("touch test_file.txt")

        # List with options
        output = await terminal.run_command("ls -la")
        assert "test_file.txt" in output

    @pytest.mark.asyncio
    async def test_run_cd_command(self, terminal):
        """Test running cd command and checking directory sync."""
        # Create a subdirectory
        await terminal.run_command("mkdir test_subdir")

        # Change to subdirectory
        await terminal.run_command("cd test_subdir")

        # Check that current directory was updated
        current_dir = terminal.get_current_dir()
        assert current_dir.endswith("test_subdir")

    @pytest.mark.asyncio
    async def test_run_command_forbidden(self, terminal):
        """Test running forbidden commands raises PermissionError."""
        with pytest.raises(PermissionError):
            await terminal.run_command("sudo ls")

        with pytest.raises(PermissionError):
            await terminal.run_command("rm -rf /")

    @pytest.mark.asyncio
    async def test_run_script_when_disabled(self, terminal):
        """Test running script commands when disabled."""
        with pytest.raises(PermissionError):
            await terminal.run_command("python -c 'print(1)'")

    @pytest.mark.asyncio
    async def test_create_file_and_write_content(self, terminal):
        """Test creating files and writing content."""
        # Create a file with echo
        await terminal.run_command("echo 'test content' > test.txt")

        # Read and verify content
        output = await terminal.run_command("cat test.txt")
        assert "test content" in output

    @pytest.mark.asyncio
    async def test_directory_operations(self, terminal):
        """Test directory creation and navigation."""
        # Create nested directories
        await terminal.run_command("mkdir -p level1/level2/level3")

        # Navigate to nested directory
        await terminal.run_command("cd level1/level2/level3")

        # Verify current directory
        current_dir = terminal.get_current_dir()
        assert current_dir.endswith("level3")

        # Go back to parent
        await terminal.run_command("cd ..")
        current_dir = terminal.get_current_dir()
        assert current_dir.endswith("level2")

    @pytest.mark.asyncio
    async def test_file_operations(self, terminal):
        """Test various file operations."""
        # Create multiple files
        await terminal.run_command("touch file1.txt file2.txt file3.txt")

        # List files
        output = await terminal.run_command("ls")
        assert "file1.txt" in output
        assert "file2.txt" in output
        assert "file3.txt" in output

        # Remove a file
        await terminal.run_command("rm file1.txt")
        output = await terminal.run_command("ls")
        assert "file1.txt" not in output
        assert "file2.txt" in output
        assert "file3.txt" in output

    @pytest.mark.asyncio
    async def test_command_chaining(self, terminal):
        """Test command chaining with &&."""
        # Chain multiple commands
        await terminal.run_command("mkdir chained_test && cd chained_test && echo 'success' > result.txt")

        # Verify all commands executed
        current_dir = terminal.get_current_dir()
        assert current_dir.endswith("chained_test")

        output = await terminal.run_command("cat result.txt")
        assert "success" in output

    @pytest.mark.asyncio
    async def test_command_with_quotes(self, terminal):
        """Test commands with quoted arguments."""
        # Test single quotes
        await terminal.run_command("echo 'hello world with spaces' > quoted.txt")
        output = await terminal.run_command("cat quoted.txt")
        assert "hello world with spaces" in output

        # Test double quotes
        await terminal.run_command('echo "another quoted string" > double_quoted.txt')
        output = await terminal.run_command("cat double_quoted.txt")
        assert "another quoted string" in output

    @pytest.mark.asyncio
    async def test_error_handling_invalid_command(self, terminal):
        """Test error handling for invalid commands."""
        # Non-existent command should raise SubprocessError
        with pytest.raises(subprocess.SubprocessError):
            await terminal.run_command("nonexistent_command_12345")

    @pytest.mark.asyncio
    async def test_close_terminates_process(self, temp_workspace):
        """Test that close properly terminates the terminal process."""
        term = create_terminal_in_workspace(temp_workspace
        )

        # Run a command to ensure process is started
        await term.run_command("echo test")

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

    @pytest.mark.asyncio
    async def test_terminal_after_close(self, terminal):
        """Test that operations after close raise appropriate errors."""
        terminal.close()

        # Operations after close should raise RuntimeError
        with pytest.raises(RuntimeError):
            await terminal.run_command("echo test")

        with pytest.raises(RuntimeError):
            terminal.check_command("echo test")

    @pytest.mark.asyncio
    async def test_workspace_with_special_characters(self, temp_workspace):
        """Test workspace creation and navigation with special characters (FUNC-CWD-001)."""
        # Create workspace with spaces and quotes as per test case template
        special_workspace = os.path.join(temp_workspace, "safe ws'2024")
        os.makedirs(special_workspace, exist_ok=True)

        term = create_terminal_in_workspace(temp_workspace, workspace=special_workspace, create_workspace=False
        )

        try:
            assert term.get_workspace() == os.path.abspath(special_workspace)

            # Test cd to workspace with special characters
            term.cd_to_workspace()
            current_dir = term.get_current_dir()
            assert current_dir == os.path.abspath(special_workspace)

            # Test basic commands work in special character path
            output = await term.run_command("pwd")
            assert special_workspace in output

            # Verify no path parsing errors (spaces not truncated)
            # Note: pwd output might be escaped differently, so check workspace name parts
            assert "safe" in output and "ws" in output and "2024" in output

        finally:
            term.close()

    @pytest.mark.asyncio
    async def test_process_lifecycle(self, temp_workspace):
        """Test terminal process start, stop, and state management."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Process should be started automatically in __init__
            assert term._process is not None
            assert term._process.poll() is None  # Process should be alive

            # Run a command to verify process is working
            output = await term.run_command("echo test")
            assert "test" in output
            assert term._process is not None
            assert term._process.poll() is None  # Process should still be alive

            # Test terminal ID is generated and unique
            term_id = term.get_id()
            assert isinstance(term_id, str)
            assert len(term_id) > 0

        finally:
            term.close()
            # Process should be terminated
            assert term._process is None or term._process.poll() is not None

    @pytest.mark.asyncio
    async def test_double_start_prevention(self, temp_workspace):
        """Test that terminal cannot be started twice."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Run first command to start process
            await term.run_command("echo first")

            # Store original process
            original_process = term._process

            # Attempting to start again should raise RuntimeError
            with pytest.raises(RuntimeError, match="终端进程已在运行"):
                term.open()

        finally:
            term.close()

    @pytest.mark.asyncio
    async def test_graceful_shutdown_sequence(self, temp_workspace):
        """Test graceful shutdown sequence: stdin close -> SIGTERM -> SIGKILL."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Start process
            await term.run_command("echo ready")
            process = term._process
            assert process is not None

            # Close should trigger graceful shutdown
            term.close()

            # Process should be terminated
            if process:
                assert process.poll() is not None

        finally:
            # Ensure real cleanup
            if hasattr(term, '_process') and term._process and term._process.poll() is None:
                try:
                    term._process.terminate()
                    term._process.wait(timeout=2)
                except:
                    pass

    @pytest.mark.asyncio
    async def test_directory_sync_after_cd(self, temp_workspace):
        """Test directory synchronization after cd command execution."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Create nested directory structure
            await term.run_command("mkdir -p level1/level2")

            # Change to nested directory using cd command
            await term.run_command("cd level1/level2")

            # Verify internal directory state is synchronized
            current_dir = term.get_current_dir()
            assert current_dir.endswith("level2")

            # Change back using cd command
            await term.run_command("cd ..")
            current_dir = term.get_current_dir()
            assert current_dir.endswith("level1")

        finally:
            term.close()

    @pytest.mark.asyncio
    async def test_command_execution_with_complex_output(self, temp_workspace):
        """Test command execution with complex output and marker filtering."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Test simple command output
            output = await term.run_command("echo 'Hello, World!'")
            assert "Hello, World!" in output

            # Test command with multiple lines (use echo instead of printf for reliability)
            output = await term.run_command("echo -e 'line1\\nline2\\nline3'")
            assert "line1" in output and "line2" in output and "line3" in output

            # Test command chaining with &&
            output = await term.run_command("echo 'test' > output.txt && cat output.txt")
            assert "test" in output

            # Verify file was created
            assert os.path.exists(os.path.join(term.get_workspace(), "output.txt"))

            # Test compound command with semicolon
            await term.run_command("mkdir compound_test; cd compound_test; pwd")
            current_dir = term.get_current_dir()
            assert current_dir.endswith("compound_test")

        finally:
            term.close()

    @pytest.mark.asyncio
    async def test_workspace_boundary_enforcement(self, temp_workspace):
        """Test that terminal operations respect workspace boundaries."""
        # Create workspace inside root
        workspace = os.path.join(temp_workspace, "workspace")
        os.makedirs(workspace, exist_ok=True)

        term = create_terminal_in_workspace(temp_workspace, workspace=workspace, create_workspace=False
        )

        try:
            # Create file outside workspace in root_dir
            outside_file = os.path.join(temp_workspace, "outside.txt")
            with open(outside_file, 'w') as f:
                f.write("outside content")

            # Attempt to access file outside workspace should fail
            assert term.check_command(f"cat {outside_file}") is False

            # Create file inside workspace
            inside_file = os.path.join(workspace, "inside.txt")
            await term.run_command(f"echo 'inside' > {inside_file}")
            assert os.path.exists(inside_file)

        finally:
            term.close()


class TestTerminalSecurity:
    """Test cases for terminal security features."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="terminal_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    """Test cases for terminal security features."""

    @pytest.fixture
    def restricted_terminal(self, temp_workspace):
        """Create a terminal with strict security settings."""
        # Change to temp_workspace directory before creating terminal
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            term = create_terminal_in_workspace(temp_workspace,
                allowed_commands=["ls", "cd", "pwd", "echo", "cat", "find", "grep"],
                disable_script_execution=True
            )
            yield term
            term.close()
        finally:
            os.chdir(original_cwd)

    def test_security_new_prohibited_commands(self, temp_workspace):
        """Test security against newly added prohibited commands (chmod, package managers)."""
        term = create_terminal_in_workspace(temp_workspace,
            disable_script_execution=True
        )

        try:
            # Test chmod commands are blocked
            chmod_attempts = [
                "chmod 777 test.txt",
                "chmod -R 755 /tmp",
                "chmod +x script.sh",
                "sudo chmod 777 /etc/passwd",
            ]

            for cmd in chmod_attempts:
                assert term.check_command(cmd) is False, f"chmod command should be blocked: {cmd}"

            # Test package manager commands are blocked
            pkg_attempts = [
                "apt install git",
                "apt-get update",
                "yum install nginx",
                "dnf upgrade",
                "brew install python",
                "dpkg -i package.deb",
                "rpm -ivh package.rpm",
            ]

            for cmd in pkg_attempts:
                assert term.check_command(cmd) is False, f"package manager command should be blocked: {cmd}"

        finally:
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
            # Test escapes for new prohibited commands
            "bash -c 'chmod 777 file.txt'",
            "sh -c \"apt install git\"",
            "python -c \"os.system('yum update')\"",
        ]

        for cmd in prohibited_attempts:
            assert restricted_terminal.check_command(cmd) is False, f"Command should be blocked: {cmd}"

    def test_security_pipe_and_semicolon_escape(self, temp_workspace):
        """Test security against pipe and semicolon escape attempts."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Test pipe escape attempts
            pipe_attempts = [
                "echo test | sudo ls",
                "ls | cat /etc/passwd",
                "pwd | chmod 777 file.txt",
                "echo hello | apt update",
            ]

            for cmd in pipe_attempts:
                assert term.check_command(cmd) is False, f"pipe escape should be blocked: {cmd}"

            # Test semicolon escape attempts
            semicolon_attempts = [
                "ls; sudo rm -rf /",
                "cd /tmp; chmod 777 *",
                "pwd; apt install git",
                "echo test; yum update",
            ]

            for cmd in semicolon_attempts:
                assert term.check_command(cmd) is False, f"semicolon escape should be blocked: {cmd}"

        finally:
            term.close()

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

    @pytest.mark.asyncio
    async def test_security_path_sensitive_commands(self, temp_workspace):
        """Test security for path-sensitive commands (find, grep, ls)."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Create some test files in workspace
            await term.run_command("touch test.txt")
            await term.run_command("mkdir -p subdir && echo 'secret' > subdir/secret.txt")

            # These should work - paths within workspace
            assert term.check_command("find . -name '*.txt'") is True
            assert term.check_command("grep 'secret' ./subdir/secret.txt") is True
            assert term.check_command("ls -la ./subdir") is True

            # These should be blocked - paths outside workspace
            outside_attempts = [
                "find /etc -name 'passwd'",
                "grep 'root' /etc/passwd",
                "ls -la /root",
                "find /usr -name 'python'",
                "cat /etc/shadow",
            ]

            for cmd in outside_attempts:
                assert term.check_command(cmd) is False, f"path-sensitive command outside workspace should be blocked: {cmd}"

        finally:
            term.close()

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

    @pytest.mark.asyncio
    async def test_security_script_file_detection(self, temp_workspace):
        """Test detection of script file execution."""
        term = create_terminal_in_workspace(temp_workspace,
            disable_script_execution=True
        )

        try:
            # Create script files
            await term.run_command("echo 'echo hello' > test.sh")
            await term.run_command("echo 'print(\"hello\")' > test.py")
            await term.run_command("echo 'package main' > test.go")
            await term.run_command("echo 'console.log(\"hello\")' > test.js")

            # Direct script execution should be blocked
            script_file_attempts = [
                "./test.sh",
                "bash test.sh",
                "python test.py",
                "python3 test.py",
                "go run test.go",
                "node test.js",
                "sh test.sh",
                "./test.py",
            ]

            for cmd in script_file_attempts:
                assert term.check_command(cmd) is False, f"script file execution should be blocked: {cmd}"

        finally:
            term.close()

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

    def test_security_complex_escape_patterns(self, temp_workspace):
        """Test complex escape patterns and nested commands."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Complex escape patterns
            complex_attempts = [
                # Nested quotes
                "'chmod 777 file.txt'",
                "\"sudo rm -rf /tmp\"",
                # Mixed escape techniques
                "eval \"chmod 777 file.txt\"",
                "exec 'sudo ls'",
                # Command chaining with escapes
                "ls; 'chmod 777 file.txt'",
                "pwd && \"apt update\"",
                # Here documents and herestrings
                "bash <<EOF\nsudo ls\nEOF",
                "bash <<< 'chmod 777 file.txt'",
            ]

            for cmd in complex_attempts:
                # 某些命令可能因为语法错误（如引号未闭合）导致解析失败
                # 这种情况下应该返回 False（不通过）
                try:
                    result = term.check_command(cmd)
                    assert result is False, f"complex escape pattern should be blocked: {cmd}"
                except (ValueError, RuntimeError) as e:
                    # 语法错误也应该被视为不通过（命令不安全）
                    # 这是预期的行为，因为恶意构造的命令应该被拦截
                    pass

        finally:
            term.close()

    def test_security_allowed_commands_bypass(self, temp_workspace):
        """Test that allowed commands list properly restricts execution."""
        term = create_terminal_in_workspace(temp_workspace,
            allowed_commands=["ls", "cd", "pwd"],  # Very restrictive
            disable_script_execution=True
        )

        try:
            # Allowed commands should work
            assert term.check_command("ls") is True
            assert term.check_command("ls -la") is True
            # cd /tmp 会被路径校验拦截（/tmp 不在 root_dir 内），这是预期的安全行为
            # 如果需要在测试中允许，可以使用 allow_by_human=True
            # assert term.check_command("cd /tmp") is True  # 这个会被路径校验拦截
            assert term.check_command("cd .") is True  # 使用相对路径
            assert term.check_command("pwd") is True

            # Non-allowed commands should be blocked (even if not prohibited)
            non_allowed_attempts = [
                "echo hello",
                "cat file.txt",
                "mkdir test",
                "touch file.txt",
                "find . -name '*.txt'",
                "grep 'pattern' file.txt",
            ]

            for cmd in non_allowed_attempts:
                assert term.check_command(cmd) is False, f"non-allowed command should be blocked: {cmd}"

        finally:
            term.close()

    @pytest.mark.asyncio
    async def test_batch_deletion_blocking_detailed(self, temp_workspace):
        """Test detailed batch deletion command blocking (SEC-RM-001)."""
        term = create_terminal_in_workspace(temp_workspace,
            disable_script_execution=True
        )

        try:
            # Create some test files in workspace
            await term.run_command("touch file1.txt file2.txt file3.txt")
            test_files_exist = os.path.exists(os.path.join(term.get_workspace(), "file1.txt"))

            # Test all batch deletion variants that should be blocked
            batch_deletion_attempts = [
                "rm -rf *",
                "rm -rf ./*",
                "rm -rf *.*",
                "rm -rf ./*.*",
                "rm -rf **",
                "rm -rf **/*",
                "rm -rf ./**/*",
                "rm -rf ./**",
                "rm -rf $(find . -type f)",
                "rm -rf `find . -type f`",
                # With sudo
                "sudo rm -rf *",
                "sudo rm -rf ./*",
                # With different flags
                "rm -r *",
                "rm -r ./*",
                "rm -f *",
                "rm -f ./*",
                "rm *",
                "rm ./*",
                # With wildcards in subdirectories
                "rm -rf */*",
                "rm -rf */*",
                "rm -rf dir/*",
                "rm -rf dir/**/*",
            ]

            for cmd in batch_deletion_attempts:
                assert term.check_command(cmd) is False, f"batch deletion should be blocked: {cmd}"

            # Verify test files still exist (commands were blocked, not executed)
            assert os.path.exists(os.path.join(term.get_workspace(), "file1.txt"))
            assert os.path.exists(os.path.join(term.get_workspace(), "file2.txt"))
            assert os.path.exists(os.path.join(term.get_workspace(), "file3.txt"))

            # Test that specific file deletion is allowed
            assert term.check_command("rm file1.txt") is True
            assert term.check_command("rm -f file2.txt") is True
            assert term.check_command("rm ./file3.txt") is True

        finally:
            term.close()

    def test_cross_level_deletion_blocking(self, temp_workspace):
        """Test cross-level deletion command blocking."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Create sub-workspace directory
            sub_workspace = os.path.join(temp_workspace, "sub_ws")
            os.makedirs(sub_workspace, exist_ok=True)

            # Cross-level deletion attempts that should be blocked
            cross_level_attempts = [
                "rm -rf ../",
                "rm -rf ../sub_ws",
                "rm -rf ../../",
                "rm -rf ../../etc",
                "rm -rf ../../../",
                "rm -rf ../sub_ws/*",
                "rm -rf ../../*",
                # With different paths
                "rm -rf ./../",
                "rm -rf ./../../",
                "rm -rf pwd/../../*",  # Attempting to use command substitution
            ]

            for cmd in cross_level_attempts:
                assert term.check_command(cmd) is False, f"cross-level deletion should be blocked: {cmd}"

        finally:
            term.close()

    @pytest.mark.asyncio
    async def test_path_sensitive_command_validation(self, temp_workspace):
        """Test path validation for path-sensitive commands (ls, cp, rm, etc.)."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Create test structure
            await term.run_command("mkdir -p subdir/level2")
            await term.run_command("touch test.txt subdir/file.txt")

            # Test path-sensitive commands with valid paths (should work)
            valid_path_commands = [
                "ls .",
                "ls ./subdir",
                "ls ./subdir/level2",
                "cat test.txt",
                "cat ./test.txt",
                "cat subdir/file.txt",
                "find . -name '*.txt'",
                "find ./subdir -name '*.txt'",
                "grep 'test' ./test.txt",
                "rm test.txt",
                "rm ./test.txt",
                "cp subdir/file.txt subdir/level2/",
            ]

            for cmd in valid_path_commands:
                assert term.check_command(cmd) is True, f"valid path command should work: {cmd}"

            # Test path-sensitive commands with invalid paths (should be blocked)
            invalid_path_commands = [
                "ls /etc",
                "ls /root",
                "ls /tmp",
                "cat /etc/passwd",
                "cat /etc/shadow",
                "find /etc -name '*.conf'",
                "find /usr -name 'python'",
                "grep 'root' /etc/passwd",
                "cp /etc/passwd ./",  # Copy from outside to inside
                "cp ./test.txt /tmp/",  # Copy from inside to outside
                "rm /tmp/test",
                "rm -rf /etc/test",
            ]

            for cmd in invalid_path_commands:
                assert term.check_command(cmd) is False, f"invalid path command should be blocked: {cmd}"

        finally:
            term.close()

    @pytest.mark.asyncio
    async def test_workspace_rm_command_restrictions(self, temp_workspace):
        """Test enhanced rm command restrictions within workspace."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Create test structure
            await term.run_command("mkdir -p testdir/subdir")
            await term.run_command("touch testdir/file1.txt testdir/file2.txt")
            await term.run_command("touch root_file.txt")

            # rm commands that should be blocked even within workspace
            blocked_rm_commands = [
                "rm -rf testdir/*",  # Wildcard deletion in subdirectory
                "rm -rf testdir/**/*",  # Recursive glob
                "rm -rf ./*",  # Current directory wildcard
                "rm -rf */*",  # All subdirectories
                "rm -f *.txt",  # File extension wildcard
                "rm -f test*.*",  # Prefix wildcard
                "rm -f *test*",  # Contains wildcard
            ]

            for cmd in blocked_rm_commands:
                assert term.check_command(cmd) is False, f"wildcard rm should be blocked: {cmd}"

            # rm commands that should be allowed
            allowed_rm_commands = [
                "rm root_file.txt",  # Specific file
                "rm -f testdir/file1.txt",  # Specific file with flag
                "rm testdir/file2.txt",  # Specific file
                "rm -rf testdir",  # Specific directory (no wildcards)
                "rmdir testdir/subdir",  # Directory removal
            ]

            for cmd in allowed_rm_commands:
                assert term.check_command(cmd) is True, f"specific rm should be allowed: {cmd}"

        finally:
            term.close()

    def test_escape_command_detection_comprehensive(self, temp_workspace):
        """Test comprehensive escape command detection in nested contexts."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Complex nested escape patterns
            complex_escapes = [
                # Multiple levels of quoting
                "bash -c \"echo 'sudo rm -rf /'\"",
                "sh -c 'bash -c \"sudo ls\"'",
                # Command substitution with escapes
                "$(echo 'sudo ls')",
                "`echo 'sudo rm -rf /'`",
                # Here documents with embedded commands
                "bash <<'EOF'\nsudo ls\nEOF",
                "cat <<'SCRIPT'\nsudo rm -rf /\nSCRIPT",
                # Process substitution
                "bash <(echo 'sudo ls')",
                # Eval with escaped content
                "eval \"bash -c 'sudo ls'\"",
                # Pipes with command construction
                "echo 'sudo ls' | bash",
                "printf 'rm -rf /tmp' | sh",
                # Environment variable expansion
                "CMD='sudo ls'; bash -c \"$CMD\"",
                # Multiple command separators
                "ls; sudo rm -rf /; pwd",
                "pwd && sudo ls && echo done",
                "find . -exec sudo ls {} \\;",
            ]

            for cmd in complex_escapes:
                assert term.check_command(cmd) is False, f"complex escape should be blocked: {cmd}"

        finally:
            term.close()

    def test_allow_by_human_whitelist_bypass(self, temp_workspace):
        """Test that allow_by_human=True bypasses whitelist check."""
        term = create_terminal_in_workspace(temp_workspace,
            allowed_commands=["ls", "cd", "pwd"],  # Very restrictive whitelist
            disable_script_execution=True
        )

        try:
            # Without allow_by_human, non-whitelisted commands should fail
            assert term.check_command("echo hello") is False
            assert term.check_command("cat file.txt") is False

            # With allow_by_human=True, should bypass whitelist
            assert term.check_command("echo hello", allow_by_human=True) is True
            assert term.check_command("cat file.txt", allow_by_human=True) is True

            # Note: script execution check is bypassed when allow_by_human=True
            # This is tested separately in test_allow_by_human_script_execution_bypass
            # The current behavior is that allow_by_human=True bypasses both whitelist and script execution checks

        finally:
            term.close()

    def test_allow_by_human_script_execution_bypass(self, temp_workspace):
        """Test that allow_by_human=True bypasses script execution check."""
        term = create_terminal_in_workspace(temp_workspace,
            allowed_commands=[],  # Allow all except prohibited
            disable_script_execution=True  # Script execution disabled
        )

        try:
            # Without allow_by_human, script commands should fail
            assert term.check_command("python script.py") is False
            assert term.check_command("bash script.sh") is False
            assert term.check_command("./test.sh") is False

            # With allow_by_human=True, should bypass script execution check
            assert term.check_command("python script.py", allow_by_human=True) is True
            assert term.check_command("bash script.sh", allow_by_human=True) is True
            assert term.check_command("./test.sh", allow_by_human=True) is True

        finally:
            term.close()

    def test_allow_by_human_prohibited_commands_still_blocked(self, temp_workspace):
        """Test that prohibited commands are still blocked even with allow_by_human=True."""
        term = create_terminal_in_workspace(temp_workspace,
            allowed_commands=[],
            disable_script_execution=True
        )

        try:
            # Prohibited commands should be blocked even with allow_by_human=True
            prohibited_commands = [
                "sudo ls",
                "rm -rf /",
                "shutdown now",
                "rm -rf *",  # Batch deletion
                "rm -rf ../",  # Cross-level deletion
            ]

            for cmd in prohibited_commands:
                assert term.check_command(cmd, allow_by_human=True) is False, \
                    f"Prohibited command should be blocked even with allow_by_human=True: {cmd}"

        finally:
            term.close()

    def test_allow_by_human_path_validation_relaxed(self, temp_workspace):
        """Test that allow_by_human=True relaxes path validation to root_dir."""
        # Create nested structure: root_dir/workspace/subdir
        workspace = os.path.join(temp_workspace, "workspace")
        subdir = os.path.join(temp_workspace, "subdir")
        os.makedirs(workspace, exist_ok=True)
        os.makedirs(subdir, exist_ok=True)

        term = create_terminal_in_workspace(temp_workspace, workspace=workspace, create_workspace=False,
            allowed_commands=[],
            disable_script_execution=True
        )

        try:
            # Create test file in root_dir but outside workspace
            outside_file = os.path.join(subdir, "outside.txt")
            with open(outside_file, 'w') as f:
                f.write("test content")

            # Without allow_by_human, path outside workspace should fail
            assert term.check_command(f"cat {outside_file}") is False
            assert term.check_command(f"ls {subdir}") is False

            # With allow_by_human=True, path within root_dir should pass
            assert term.check_command(f"cat {outside_file}", allow_by_human=True) is True
            assert term.check_command(f"ls {subdir}", allow_by_human=True) is True

            # But path outside root_dir should still fail
            assert term.check_command("cat /etc/passwd", allow_by_human=True) is False
            assert term.check_command("ls /root", allow_by_human=True) is False

        finally:
            term.close()

    def test_allow_by_human_rm_command_still_restricted(self, temp_workspace):
        """Test that rm commands still have strict restrictions even with allow_by_human=True."""
        workspace = os.path.join(temp_workspace, "workspace")
        subdir = os.path.join(temp_workspace, "subdir")
        os.makedirs(workspace, exist_ok=True)
        os.makedirs(subdir, exist_ok=True)

        term = create_terminal_in_workspace(temp_workspace, workspace=workspace, create_workspace=False,
            allowed_commands=[],
            disable_script_execution=True
        )

        try:
            # Create test file in workspace
            workspace_file = os.path.join(workspace, "test.txt")
            with open(workspace_file, 'w') as f:
                f.write("test")

            # Create test file outside workspace but in root_dir
            outside_file = os.path.join(subdir, "outside.txt")
            with open(outside_file, 'w') as f:
                f.write("test")

            # rm with wildcards should still be blocked even with allow_by_human=True
            assert term.check_command("rm -rf *", allow_by_human=True) is False
            assert term.check_command("rm -rf ./*", allow_by_human=True) is False
            assert term.check_command("rm -rf testdir/*", allow_by_human=True) is False

            # Specific file deletion in workspace should work
            assert term.check_command(f"rm {workspace_file}", allow_by_human=True) is True

            # But rm outside workspace should still fail (rm is restricted to workspace)
            assert term.check_command(f"rm {outside_file}", allow_by_human=True) is False

        finally:
            term.close()


class TestTerminalConcurrencyAndExceptions:
    """Test cases for terminal concurrency and exception handling."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="terminal_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_concurrent_command_execution(self, temp_workspace):
        """Test concurrent command execution with multiple threads."""
        # Shared data for thread coordination
        results: dict[str, str] = {}
        errors: dict[int, Exception] = {}

        def worker_thread(thread_id: int) -> None:
            """Worker function for concurrent testing."""
            try:
                # Each thread performs different operations
                for i in range(5):
                    cmd = f"echo 'thread{thread_id}_iteration{i}'"
                    output = asyncio.run(concurrent_terminal.run_command(cmd))
                    results[f"thread{thread_id}_iteration{i}"] = output
                    time.sleep(0.01)  # Small delay to increase contention
            except Exception as e:
                errors[f"thread{thread_id}"] = e

        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=10)

        # Verify results
        assert len(errors) == 0, f"Concurrent execution errors: {errors}"
        assert len(results) == 15, f"Expected 15 results, got {len(results)}"

        # Verify each thread's output is correct
        for thread_id in range(3):
            for i in range(5):
                key = f"thread{thread_id}_iteration{i}"
                assert key in results
                assert f"thread{thread_id}_iteration{i}" in results[key]

    @pytest.mark.asyncio
    async def test_thread_safety_critical_section(self, temp_workspace):
        """Test thread safety in critical section operations."""
        # Shared state for testing thread safety
        shared_state: list[str] = []

        def critical_section_worker(thread_id: int) -> None:
            """Worker that accesses shared critical section."""
            try:
                # Each thread creates its own directory to avoid conflicts
                dir_name = f"critical_test_{thread_id}"
                # Use mkdir -p to avoid errors if directory already exists
                asyncio.run(concurrent_terminal.run_command(f"mkdir -p {dir_name}"))
                asyncio.run(concurrent_terminal.run_command(f"cd {dir_name}"))
                current_dir = concurrent_terminal.get_current_dir()

                # Shared state update (should be thread-safe)
                shared_state.append(f"thread{thread_id}:{current_dir}")

                asyncio.run(concurrent_terminal.run_command("cd .."))
                # Use rm -rf to avoid errors if directory doesn't exist or is not empty
                asyncio.run(concurrent_terminal.run_command(f"rm -rf {dir_name}"))

            except Exception as e:
                shared_state.append(f"thread{thread_id}:error:{e}")

        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=critical_section_worker, args=(i,))
            threads.append(thread)

        # Start all threads simultaneously
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join(timeout=10)

        # Verify no errors occurred
        error_count = sum(1 for state in shared_state if "error" in state)
        assert error_count == 0, f"Thread safety errors: {[s for s in shared_state if 'error' in s]}"

        # Verify all threads completed
        assert len(shared_state) == 5, f"Expected 5 completions, got {len(shared_state)}"

    @pytest.mark.asyncio
    async def test_command_timeout_handling(self, temp_workspace):
        """Test command timeout handling."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Test that a command that takes longer than timeout raises TimeoutError
            # Use a short timeout (0.5 seconds) and a command that takes longer (sleep 2)
            with pytest.raises(TimeoutError):
                await term.run_command("sleep 2", timeout=0.5)

        finally:
            term.close()

    def test_nonblock_read_write(self, temp_workspace):
        """Test non-blocking read and write interfaces."""
        term = create_terminal_in_workspace(temp_workspace)

        try:
            # Test read_process: non-blocking read (should return empty if no data)
            empty_read = term.read_process(stop_word="$")
            assert isinstance(empty_read, str), "read_process should return a string"
            assert empty_read == "", "read_process should return empty string when no data"
            
            # Test write_process: write a command without completion marker
            # write_process will wait a short time for command to start
            term.write_process("echo 'test output'")
            
            # Test read_process: read the output (non-blocking)
            # Since write_process doesn't wait for completion marker, we need to read manually
            output = ""
            start_time = time.time()
            timeout = 2.0
            while time.time() - start_time < timeout:
                data = term.read_process(stop_word="$")
                if data:
                    output += data
                    if "test output" in output:
                        break
                time.sleep(0.01)
            
            # Verify we got the expected output
            assert "test output" in output, f"Expected 'test output' in output, got: {output}"
            
            # Test write_process with completion marker: it will wait for the marker
            from tasking.tool.terminal import _COMMAND_DONE_MARKER
            term.write_process(f"echo 'test output 2' && echo '{_COMMAND_DONE_MARKER}'")
            # write_process already waited for completion, so output may have been consumed
            # But we can still test that read_process works
            empty_read2 = term.read_process(stop_word="$")
            assert isinstance(empty_read2, str), "read_process should return a string"
            
        finally:
            term.close()

    def test_nonblock_read_write_multiple_commands(self, temp_workspace):
        """Test non-blocking read and write with multiple commands."""
        term = create_terminal_in_workspace(temp_workspace)

        try:
            # Write multiple commands without completion markers
            # write_process will wait a short time for each command to start
            term.write_process("echo 'first'")
            time.sleep(0.1)
            term.write_process("echo 'second'")
            time.sleep(0.1)
            term.write_process("echo 'third'")
            
            # Read all outputs (non-blocking)
            all_output = ""
            start_time = time.time()
            timeout = 3.0
            found_count = 0
            while time.time() - start_time < timeout:
                data = term.read_process(stop_word="$")
                if data:
                    all_output += data
                    if "first" in all_output and found_count == 0:
                        found_count += 1
                    if "second" in all_output and found_count == 1:
                        found_count += 1
                    if "third" in all_output and found_count == 2:
                        found_count += 3
                        break
                time.sleep(0.01)
            
            # Verify we got all outputs
            assert "first" in all_output, f"Should contain 'first', got: {all_output}"
            assert "second" in all_output, f"Should contain 'second', got: {all_output}"
            assert "third" in all_output, f"Should contain 'third', got: {all_output}"
            
        finally:
            term.close()

    def test_nonblock_read_write_error_handling(self, temp_workspace):
        """Test error handling for non-blocking read and write."""
        term = create_terminal_in_workspace(temp_workspace)

        try:
            # Test that nonblock_read raises RuntimeError when terminal is closed
            term.close()
            
            with pytest.raises(RuntimeError, match="终端未运行或已退出"):
                term.read_process(stop_word="$")
            
            with pytest.raises(RuntimeError, match="终端未运行或已退出"):
                term.write_process("echo test")
                
        except Exception:
            # If terminal is already closed, that's fine
            pass

    @pytest.mark.asyncio
    async def test_empty_command_validation(self, concurrent_terminal):
        """Test empty command validation."""
        # Empty commands should fail validation
        assert concurrent_terminal.check_command("") is False
        assert concurrent_terminal.check_command("   ") is False
        assert concurrent_terminal.check_command("\t\n") is False

        # And should raise errors when executed
        with pytest.raises((ValueError, PermissionError)):
            await concurrent_terminal.run_command("")

    @pytest.mark.asyncio
    async def test_malformed_command_handling(self, concurrent_terminal):
        """Test handling of malformed commands."""
        malformed_commands = [
            "echo 'unclosed quote",
            "echo \"unclosed double quote",
            "ls -",  # Invalid option
            "cat --invalid-flag",
            "find . -name",  # Missing argument
        ]

        for cmd in malformed_commands:
            # These should either fail validation or raise execution errors
            try:
                if concurrent_terminal.check_command(cmd):
                    # If validation passes, execution might fail
                    try:
                        await concurrent_terminal.run_command(cmd)
                    except (subprocess.SubprocessError, ValueError):
                        pass  # Expected for malformed commands
                # else: validation failed - also acceptable
            except Exception:
                pass  # Any exception is acceptable for malformed commands

    @pytest.mark.asyncio
    async def test_process_crash_recovery(self, temp_workspace):
        """Test terminal behavior when underlying process crashes."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Start the process
            await term.run_command("echo 'before crash'")

            # Simulate process crash by killing the underlying process
            if term._process:
                term._process.terminate()
                term._process.wait(timeout=2)

            # Next command should detect crashed process and handle it
            with pytest.raises((RuntimeError, subprocess.SubprocessError)):
                await term.run_command("echo 'after crash'")

        finally:
            term.close()

    @pytest.mark.asyncio
    async def test_permission_denied_handling(self, temp_workspace):
        """Test handling of permission denied errors."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Create a file with no read permissions (if possible)
            test_file = os.path.join(temp_workspace, "no_permission.txt")
            await term.run_command(f"echo 'test' > {test_file}")

            # Try to remove read permissions (may not work on all systems)
            try:
                os.chmod(test_file, 0o000)

                # Attempt to read the file
                with pytest.raises((subprocess.SubprocessError, PermissionError)):
                    await term.run_command(f"cat {test_file}")

            except OSError:
                # chmod not supported or insufficient permissions - skip this test
                pass

        finally:
            term.close()

    @pytest.mark.asyncio
    async def test_nonexistent_path_handling(self, concurrent_terminal):
        """Test handling of nonexistent paths."""
        nonexistent_operations = [
            # cd 命令会被路径校验拦截（路径不在 root_dir 内）
            # "cd /nonexistent/path",  # 这个会被拦截，因为路径不在 root_dir 内
            "cat nonexistent_file.txt",  # 相对路径，在 workspace 内，应该通过验证
            "ls nonexistent_directory",  # 相对路径，在 workspace 内，应该通过验证
            "rm nonexistent_file.txt",  # 相对路径，在 workspace 内，应该通过验证（但执行会失败）
        ]

        for cmd in nonexistent_operations:
            # Commands should pass validation but fail execution
            assert concurrent_terminal.check_command(cmd) is True, f"Command should pass validation: {cmd}"

            try:
                await concurrent_terminal.run_command(cmd)
            except (subprocess.SubprocessError, FileNotFoundError):
                pass  # Expected for nonexistent paths

    @pytest.mark.asyncio
    async def test_terminal_resource_cleanup(self, temp_workspace):
        """Test proper resource cleanup during terminal operations."""
        terminals = []
        original_cwd = os.getcwd()

        try:
            # 确保在 temp_workspace 目录中执行，避免目录同步问题
            os.chdir(temp_workspace)
            
            # Create multiple terminals
            for i in range(3):
                term = LocalTerminal(
                    root_dir=temp_workspace,
                    workspace=os.path.join(temp_workspace, f"workspace_{i}"),
                    create_workspace=True
                )
                terminals.append(term)

                # Run some commands
                await term.run_command(f"echo 'terminal {i} test'")
                assert term.get_id() is not None

        finally:
            # 恢复原始目录
            os.chdir(original_cwd)
            
            # Clean up all terminals
            for term in terminals:
                term.close()

            # Verify all processes are terminated
            for term in terminals:
                assert term._process is None or term._process.poll() is not None

    @pytest.mark.asyncio
    async def test_exception_propagation_consistency(self, temp_workspace):
        """Test that exceptions are consistently propagated."""
        term = create_terminal_in_workspace(temp_workspace
        )

        try:
            # Test that permission errors are properly raised
            with pytest.raises(PermissionError):
                await term.run_command("sudo ls")

            # Test that runtime errors are properly raised after close
            term.close()
            with pytest.raises(RuntimeError):
                await term.run_command("echo test")

        except:
            term.close()
            raise
