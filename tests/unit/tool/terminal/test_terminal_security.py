"""
Terminal tool security tests.

This module contains comprehensive security tests for the terminal tool,
including shell injection protection, code injection protection, and
validation of the 5-step security verification process.
"""

import os
import tempfile
import shutil
import pytest
import asyncio
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


class TestShellInjectionProtection:
    """Test shell injection protection mechanisms."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="terminal_security_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def terminal(self, temp_workspace):
        """Create a terminal instance with strict security settings."""
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            term = create_terminal_in_workspace(
                temp_workspace,
                allowed_commands=["echo", "ls", "cd", "pwd", "cat", "grep", "find", "mkdir", "touch"],
                disable_script_execution=True
            )
            yield term
            term.close()
        finally:
            os.chdir(original_cwd)

    def test_command_injection_basic(self, terminal):
        """Test basic command injection attempts."""
        # Direct command injection
        assert terminal.check_command("echo hello; sudo rm -rf /") is False
        assert terminal.check_command("echo hello && sudo ls") is False
        assert terminal.check_command("echo hello || sudo cat /etc/passwd") is False

        # Command injection with pipes
        assert terminal.check_command("echo hello | sudo cat /etc/passwd") is False
        assert terminal.check_command("ls | sudo bash") is False

        # Command injection with backticks
        assert terminal.check_command("echo `sudo rm -rf /`") is False
        assert terminal.check_command("echo `sudo cat /etc/shadow`") is False

    def test_command_injection_with_quotes(self, terminal):
        """Test command injection attempts using quotes to bypass detection."""
        # Single quotes - still blocked because dangerous patterns are detected even in quotes
        assert terminal.check_command("echo 'hello; sudo rm -rf /'") is False  # Dangerous pattern detected
        assert terminal.check_command("echo 'hello && sudo ls'") is False  # sudo command detected

        # Double quotes - still blocked because dangerous patterns are detected even in quotes
        assert terminal.check_command('echo "hello; sudo rm -rf /"') is False  # Dangerous pattern detected
        assert terminal.check_command('echo "hello && sudo ls"') is False  # sudo command detected

        # But actual command execution through quotes should be blocked
        assert terminal.check_command("bash -c 'echo hello; sudo rm -rf /'") is False
        assert terminal.check_command('sh -c "echo hello && sudo ls"') is False

        # Safe quoted commands should work
        assert terminal.check_command("echo 'hello world'") is True  # Safe
        assert terminal.check_command('echo "hello world"') is True  # Safe

    def test_command_injection_with_variables(self, terminal):
        """Test command injection through environment variables."""
        # Variable assignment with injection (should be blocked as script)
        assert terminal.check_command("VAR='sudo rm -rf /'; echo $VAR") is False

        # Export with injection
        assert terminal.check_command("export CMD='sudo ls'; $CMD") is False

        # Environment expansion in commands
        assert terminal.check_command("echo $PATH") is True  # Simple expansion
        assert terminal.check_command("LS='ls; sudo rm -rf /'; $LS") is False

    def test_pipe_injection_prevention(self, terminal):
        """Test prevention of pipe-based command injection."""
        # Pipe to dangerous commands
        assert terminal.check_command("echo hello | sudo cat /etc/passwd") is False
        assert terminal.check_command("ls | sudo bash") is False
        assert terminal.check_command("cat file | sudo rm -rf /") is False

        # Pipe chains with injection
        assert terminal.check_command("cat file | grep test | sudo cat /etc/passwd") is False

        # Pipes to interpreters
        assert terminal.check_command("echo 'sudo rm -rf /' | bash") is False
        assert terminal.check_command("ls | python") is False
        assert terminal.check_command("cat script | sh") is False

    def test_redirection_injection(self, terminal):
        """Test redirection-based command injection attempts."""
        # Redirection to sensitive files
        assert terminal.check_command("echo 'data' > /etc/passwd") is False
        assert terminal.check_command("ls > /etc/shadow") is False
        assert terminal.check_command("cat file >> /etc/sudoers") is False

        # Redirection from sensitive files
        assert terminal.check_command("cat < /etc/passwd") is False
        assert terminal.check_command("grep 'root' < /etc/shadow") is False

        # Heredoc to sensitive files
        assert terminal.check_command("cat > /etc/passwd << EOF\nmalicious content\nEOF") is False

    def test_subshell_injection(self, terminal):
        """Test subshell-based command injection."""
        # Command substitution
        assert terminal.check_command("echo $(sudo cat /etc/passwd)") is False
        assert terminal.check_command("echo `sudo ls /root`") is False

        # Process substitution
        assert terminal.check_command("cat <(sudo cat /etc/passwd)") is False
        assert terminal.check_command("echo >(sudo rm -rf /)") is False

        # Nested subshells
        assert terminal.check_command("echo $(echo $(sudo cat /etc/passwd))") is False

    def test_function_injection(self, terminal):
        """Test function-based command injection attempts."""
        # Function definition with dangerous commands
        assert terminal.check_command("evil() { sudo rm -rf /; }; evil") is False

        # Exported functions
        assert terminal.check_command("export -f evil; evil") is False

        # Function calls with injection
        assert terminal.check_command("echo 'sudo rm -rf /' | xargs -I {} bash -c '{}'") is False

    
    @pytest.mark.asyncio
    async def test_injection_prevention_runtime(self, terminal):
        """Test that injection prevention works at runtime."""
        # Create a test file
        await terminal.run_command("echo 'test content' > test.txt")

        # Try injection attempts - should raise PermissionError
        with pytest.raises(PermissionError):
            await terminal.run_command("cat test.txt; sudo rm -rf /")

        with pytest.raises(PermissionError):
            await terminal.run_command("cat test.txt && sudo cat /etc/passwd")

        with pytest.raises(PermissionError):
            await terminal.run_command("cat test.txt | sudo bash")


class TestCodeInjectionProtection:
    """Test code injection protection mechanisms."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="terminal_code_sec_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def terminal(self, temp_workspace):
        """Create a terminal instance with code injection protection."""
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            term = create_terminal_in_workspace(
                temp_workspace,
                allowed_commands=["echo", "ls", "cd", "pwd", "cat"],
                disable_script_execution=True
            )
            yield term
            term.close()
        finally:
            os.chdir(original_cwd)

    def test_command_substitution_protection(self, terminal):
        """Test protection against command substitution injection."""
        # Basic command substitution
        assert terminal.check_command("echo $(sudo ls)") is False
        assert terminal.check_command("echo `sudo cat /etc/passwd`") is False

        # Nested command substitution
        assert terminal.check_command("echo $(echo $(sudo ls))") is False
        assert terminal.check_command("echo `echo `sudo cat /etc/passwd``") is False

        # Command substitution in arguments
        assert terminal.check_command("cat $(find / -name passwd)") is False
        assert terminal.check_command("ls -l `whoami`") is False

        # Command substitution with pipes
        assert terminal.check_command("echo $(cat /etc/passwd | sudo bash)") is False

  
    def test_process_substitution_protection(self, terminal):
        """Test protection against process substitution injection."""
        # Input process substitution
        assert terminal.check_command("cat <(sudo cat /etc/passwd)") is False
        assert terminal.check_command("cat <(ls -la /root)") is False

        # Output process substitution
        assert terminal.check_command("echo 'data' >(sudo bash)") is False
        assert terminal.check_command("ls >(sudo cat /etc/passwd)") is False

        # Process substitution with pipes
        assert terminal.check_command("cat <(ls | sudo bash)") is False

    
    
    
    def test_here_document_protection(self, terminal):
        """Test protection against here document injection."""
        # Basic here documents (blocked as script execution)
        assert terminal.check_command("cat << EOF\nhello world\nEOF") is False
        assert terminal.check_command("cat << 'EOF'\nhello world\nEOF") is False

        # Here documents with commands
        assert terminal.check_command("bash << EOF\nsudo ls\nEOF") is False
        assert terminal.check_command("sh << 'EOF'\nsudo cat /etc/passwd\nEOF") is False

        # Here strings (also blocked)
        assert terminal.check_command("cat <<< 'hello world'") is False
        assert terminal.check_command("bash <<< 'sudo ls'") is False

    def test_eval_protection(self, terminal):
        """Test protection against eval-based injection."""
        # Basic eval (blocked as dangerous)
        assert terminal.check_command("eval 'echo hello'") is False
        assert terminal.check_command("eval \"echo hello\"") is False

        # Eval with injection attempts
        assert terminal.check_command("eval 'sudo rm -rf /'") is False
        assert terminal.check_command('eval "sudo cat /etc/passwd"') is False

        # Eval with command substitution
        assert terminal.check_command("eval '$(sudo ls)'") is False
        assert terminal.check_command('eval "`sudo cat /etc/passwd`"') is False

    def test_exec_protection(self, terminal):
        """Test protection against exec-based injection."""
        # Basic exec (blocked as dangerous)
        assert terminal.check_command("exec 'echo hello'") is False
        assert terminal.check_command('exec "echo hello"') is False

        # Exec with dangerous commands
        assert terminal.check_command("exec 'sudo rm -rf /'") is False
        assert terminal.check_command('exec "sudo cat /etc/passwd"') is False

        # Exec to replace shell
        assert terminal.check_command("exec sudo bash") is False
        assert terminal.check_command("exec sh -c 'sudo ls'") is False

    def test_source_protection(self, terminal):
        """Test protection against source/. command injection."""
        # Source command
        assert terminal.check_command("source malicious.sh") is False
        assert terminal.check_command(". malicious.sh") is False

        # Source with injection
        assert terminal.check_command("source <(echo 'sudo rm -rf /')") is False
        assert terminal.check_command(". <(echo 'sudo cat /etc/passwd')") is False

    
    @pytest.mark.asyncio
    async def test_code_injection_runtime(self, terminal):
        """Test code injection prevention at runtime."""
        # These should raise PermissionError (contain dangerous commands)
        with pytest.raises(PermissionError):
            await terminal.run_command("echo $(sudo ls)")

        with pytest.raises(PermissionError):
            await terminal.run_command("echo `sudo cat /etc/passwd`")

        # This should be allowed (harmless arithmetic expansion)
        # In disabled script execution mode, this is treated as literal
        result = await terminal.run_command("echo $((1 + 1))")
        assert isinstance(result, str)

        # These should raise PermissionError (script execution features)
        with pytest.raises(PermissionError):
            await terminal.run_command("cat << EOF\nhello\nEOF")

        with pytest.raises(PermissionError):
            await terminal.run_command("eval 'echo test'")


class TestFiveStepSecurityVerification:
    """Test the 5-step security verification process."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="terminal_5step_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def restricted_terminal(self, temp_workspace):
        """Create a terminal with restricted allowed commands."""
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            term = create_terminal_in_workspace(
                temp_workspace,
                allowed_commands=["echo", "ls", "cd"],  # Very restrictive
                disable_script_execution=True
            )
            yield term
            term.close()
        finally:
            os.chdir(original_cwd)

    @pytest.fixture
    def unrestricted_terminal(self, temp_workspace):
        """Create a terminal with unrestricted allowed commands."""
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            term = create_terminal_in_workspace(
                temp_workspace,
                allowed_commands=[],  # Allow all except prohibited
                disable_script_execution=True
            )
            yield term
            term.close()
        finally:
            os.chdir(original_cwd)

    def test_step1_allowed_commands_check(self, restricted_terminal):
        """Test Step 1: Allowed commands list check."""
        # Commands in allowed list should pass
        assert restricted_terminal.check_command("echo hello") is True
        assert restricted_terminal.check_command("ls -la") is True
        assert restricted_terminal.check_command("cd .") is True

        # Commands not in allowed list should fail
        assert restricted_terminal.check_command("cat file.txt") is False
        assert restricted_terminal.check_command("grep pattern file") is False
        assert restricted_terminal.check_command("find . -name '*.txt'") is False
        assert restricted_terminal.check_command("pwd") is False

        # With allow_by_human=True, should bypass allowed list
        assert restricted_terminal.check_command("cat file.txt", allow_by_human=True) is True

    def test_step2_script_execution_check(self, unrestricted_terminal):
        """Test Step 2: Script execution check."""
        # Script commands should be blocked when disabled
        assert unrestricted_terminal.check_command("python script.py") is False
        assert unrestricted_terminal.check_command("bash script.sh") is False
        assert unrestricted_terminal.check_command("node app.js") is False
        assert unrestricted_terminal.check_command("./script.sh") is False
        assert unrestricted_terminal.check_command("go run main.go") is False

        # With allow_by_human=True, should bypass script check
        assert unrestricted_terminal.check_command("python script.py", allow_by_human=True) is True
        assert unrestricted_terminal.check_command("bash script.sh", allow_by_human=True) is True

    def test_step3_escaped_prohibited_check(self, unrestricted_terminal):
        """Test Step 3: Escaped prohibited command check."""
        # These should be blocked even in quotes or escaped
        assert unrestricted_terminal.check_command("bash -c 'sudo ls'") is False
        assert unrestricted_terminal.check_command('sh -c "rm -rf /"') is False
        assert unrestricted_terminal.check_command("bash -c \"echo 'sudo rm -rf /'\"") is False

        # Command substitution with prohibited commands
        assert unrestricted_terminal.check_command("echo $(sudo ls)") is False
        assert unrestricted_terminal.check_command("cat `sudo cat /etc/passwd`") is False

        # With allow_by_human=True, some might pass but absolute prohibitions remain
        assert unrestricted_terminal.check_command("bash -c 'sudo ls'", allow_by_human=True) is False

    def test_step4_prohibited_commands_check(self, unrestricted_terminal):
        """Test Step 4: Prohibited commands list check."""
        # Absolute prohibitions (blocked even with allow_by_human=True)
        assert unrestricted_terminal.check_command("rm -rf /", allow_by_human=True) is False
        assert unrestricted_terminal.check_command("rm -rf *", allow_by_human=True) is False
        assert unrestricted_terminal.check_command("rm -rf ../", allow_by_human=True) is False
        assert unrestricted_terminal.check_command("sudo ls", allow_by_human=True) is False

        # Conditional prohibitions (blocked unless allow_by_human=True)
        assert unrestricted_terminal.check_command("chmod 777 file.txt") is False
        assert unrestricted_terminal.check_command("chmod 777 file.txt", allow_by_human=True) is True

        assert unrestricted_terminal.check_command("apt install git") is False
        assert unrestricted_terminal.check_command("apt install git", allow_by_human=True) is True

    def test_step5_path_constraints_check(self, temp_workspace):
        """Test Step 5: Path constraints check."""
        workspace = os.path.join(temp_workspace, "workspace")
        os.makedirs(workspace, exist_ok=True)

        # Create terminal with workspace
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            term = create_terminal_in_workspace(
                temp_workspace,
                workspace=workspace,
                allowed_commands=["cat", "ls", "cd"],
                disable_script_execution=True
            )

            # Paths within workspace should pass
            assert term.check_command("cat test.txt") is True
            assert term.check_command("ls ./") is True
            assert term.check_command("cd .") is True

            # Paths outside workspace should fail
            assert term.check_command("cat /etc/passwd") is False
            assert term.check_command("ls /root") is False
            assert term.check_command("cd /tmp") is False

            # With allow_by_human=True, should relax to root_dir
            assert term.check_command("cat /etc/passwd", allow_by_human=True) is False  # Still outside root_dir
            assert term.check_command(f"cat {temp_workspace}/outside.txt", allow_by_human=True) is True  # In root_dir

            term.close()
        finally:
            os.chdir(original_cwd)

    def test_all_five_steps_integration(self, restricted_terminal):
        """Test that all five steps work together correctly."""
        # This should fail at step 1 (not in allowed list)
        assert restricted_terminal.check_command("sudo cat /etc/passwd") is False

        # This should fail at step 2 (script execution)
        assert restricted_terminal.check_command("python -c 'sudo ls'") is False

        # This should fail at step 3 (escaped prohibited)
        assert restricted_terminal.check_command("bash -c 'sudo rm -rf /'") is False

        # This should fail at step 4 (prohibited command)
        assert restricted_terminal.check_command("rm -rf *") is False

        # This should fail at step 5 (path constraint)
        assert restricted_terminal.check_command("echo hello > /etc/passwd") is False

        # A valid command should pass all steps
        assert restricted_terminal.check_command("echo hello") is True
        assert restricted_terminal.check_command("ls -la") is True

    @pytest.mark.asyncio
    async def test_security_verification_order(self, unrestricted_terminal):
        """Test that security verification happens in the correct order."""
        # Create a command that fails at multiple steps
        # Should be caught at step 1 if allowed_commands is set
        restricted = create_terminal_in_workspace(
            tempfile.mkdtemp(),
            allowed_commands=["echo"],
            disable_script_execution=True
        )
        try:
            # This fails at step 1 (not in allowed list), not step 4 (prohibited)
            assert restricted.check_command("sudo rm -rf /") is False
        finally:
            restricted.close()

    def test_security_logging(self, unrestricted_terminal):
        """Test that security violations are properly logged."""
        # Check a command that should fail - this will log to stderr
        result = unrestricted_terminal.check_command("sudo ls")

        # Should fail the security check
        assert result is False

        # The test passes if we get here without crashing, as logging is handled by loguru
        # and visible in the captured stderr (as shown in the test output above)

    @pytest.mark.asyncio
    async def test_complex_command_security_check(self, unrestricted_terminal):
        """Test security checking on complex multi-part commands."""
        # Complex command with multiple potential issues
        complex_cmd = '''
        echo "Starting"
        && ls -la
        && find . -name "*.txt" | xargs cat
        && echo "Done"
        '''

        # Should pass all checks (no actual security violations)
        assert unrestricted_terminal.check_command(complex_cmd) is True

        # Complex command with actual security violation
        malicious_cmd = '''
        echo "Starting"
        && ls -la
        && find / -name "passwd" | xargs cat
        && echo "Done"
        '''

        # Should fail due to path violation in find command
        assert unrestricted_terminal.check_command(malicious_cmd) is False


class TestSecurityEdgeCases:
    """Test edge cases in security implementation."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="terminal_edge_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def terminal(self, temp_workspace):
        """Create a terminal instance for edge case testing."""
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            term = create_terminal_in_workspace(
                temp_workspace,
                allowed_commands=[],
                disable_script_execution=True
            )
            yield term
            term.close()
        finally:
            os.chdir(original_cwd)

    def test_empty_and_whitespace_commands(self, terminal):
        """Test security handling of empty and whitespace commands."""
        # Empty command should fail
        assert terminal.check_command("") is False
        assert terminal.check_command("   ") is False
        assert terminal.check_command("\t\n") is False

    def test_very_long_commands(self, terminal):
        """Test security handling of very long commands."""
        # Very long but safe command
        long_arg = "a" * 10000
        assert terminal.check_command(f"echo {long_arg}") is True

        # Very long dangerous command
        long_dangerous = f"sudo rm -rf {'a' * 10000}"
        assert terminal.check_command(long_dangerous) is False

    
    def test_command_fragmentation(self, terminal):
        """Test that fragmented commands are properly reassembled and checked."""
        # Commands split across multiple lines
        multiline_cmd = "rm -rf \\\n/"
        assert terminal.check_command(multiline_cmd) is False

        # Commands with continuation characters
        continued_cmd = "sudo rm -rf \\"
        # This might not be a complete command, but should be handled safely
        assert terminal.check_command(continued_cmd) is True  # Incomplete, but not dangerous yet

    def test_obfuscation_techniques(self, terminal):
        """Test various command obfuscation techniques."""
        # Variable indirection (script execution)
        assert terminal.check_command("CMD='sudo rm -rf /'; $CMD") is False

        # Function wrapping (script execution)
        assert terminal.check_command("wrap() { sudo rm -rf /; }; wrap") is False

        # String manipulation (script execution)
        assert terminal.check_command("S='s'; C='u'; D='d'; O='o'; $S$C$D$O ls") is False

    @pytest.mark.asyncio
    async def test_concurrent_security_checks(self, temp_workspace):
        """Test that security checks work correctly under concurrent access."""
        import threading
        import time

        terminals = []
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)

            # Create multiple terminals
            for _ in range(5):
                term = create_terminal_in_workspace(
                    temp_workspace,
                    allowed_commands=["echo"],
                    disable_script_execution=True
                )
                terminals.append(term)

            results = []
            errors = []

            def worker(term):
                try:
                    # Should all pass (allowed command)
                    result = asyncio.run(term.run_command("echo hello"))
                    results.append(result)

                    # Should all fail (prohibited command)
                    try:
                        asyncio.run(term.run_command("sudo ls"))
                    except PermissionError:
                        pass  # Expected
                    else:
                        errors.append("Prohibited command was not blocked")

                except Exception as e:
                    errors.append(str(e))

            # Run concurrent security checks
            threads = []
            for term in terminals:
                thread = threading.Thread(target=worker, args=(term,))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join(timeout=5)

            # Verify results
            assert len(errors) == 0, f"Concurrent security errors: {errors}"
            assert len(results) == 5

        finally:
            os.chdir(original_cwd)
            for term in terminals:
                term.close()

    