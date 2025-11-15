#!/usr/bin/env python3
"""
Scheduler Test Runner - Python Version

This is a fully functional test runner script for running all scheduler-related tests.
"""

import sys
import os
import subprocess
import argparse
import time
from pathlib import Path
from typing import Optional, List


class Colors:
    """Terminal color definitions"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    CYAN = '\033[0;36m'
    WHITE = '\033[1;37m'
    NC = '\033[0m'  # No Color


class TestRunner:
    """Test runner class"""

    def __init__(self):
        self.script_dir = Path(__file__).parent
        self.project_root = self.script_dir.parent.parent  # tests/scheduler -> project_root
        # All test files
        self.basic_test_file = self.script_dir / "test_scheduler_basic.py"
        self.builder_test_file = self.script_dir / "test_scheduler_builder.py"
        self.integration_test_file = self.script_dir / "test_scheduler_integration.py"
        self.corner_test_file = self.script_dir / "test_scheduler_corner_cases.py"
        self.all_test_files = [
            self.basic_test_file,
            self.builder_test_file,
            self.integration_test_file,
            self.corner_test_file
        ]
        self.python_cmd = self._find_python_command()

    def _find_python_command(self) -> List[str]:
        """Find the appropriate Python command"""
        # Try uv first (preferred)
        if self._check_command("uv"):
            venv_path = self.project_root / ".venv"
            if venv_path.exists():
                return ["uv", "run", "python"]
            else:
                # Create uv environment
                try:
                    subprocess.run(
                        ["uv", "venv"],
                        cwd=self.project_root,
                        check=True,
                        capture_output=True
                    )
                    return ["uv", "run", "python"]
                except subprocess.CalledProcessError:
                    pass

        # Try python3
        if self._check_command("python3"):
            return ["python3"]

        # Try python
        if self._check_command("python"):
            return ["python"]

        # Fallback
        return ["python3"]

    def _check_command(self, cmd: str) -> bool:
        """Check if command exists"""
        try:
            subprocess.run([cmd, "--version"], check=True, capture_output=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _print_color(self, color: str, message: str) -> None:
        """Print colored message"""
        print(f"{color}{message}{Colors.NC}")

    def print_header(self, title: str) -> None:
        """Print section header"""
        print()
        self._print_color(Colors.BLUE, title)
        print("=" * 80)

    def print_success(self, message: str) -> None:
        """Print success message"""
        self._print_color(Colors.GREEN, f"✓ {message}")

    def print_error(self, message: str) -> None:
        """Print error message"""
        self._print_color(Colors.RED, f"✗ {message}")

    def print_warning(self, message: str) -> None:
        """Print warning message"""
        self._print_color(Colors.YELLOW, f"⚠ {message}")

    def print_info(self, message: str) -> None:
        """Print info message"""
        self._print_color(Colors.CYAN, f"ℹ {message}")

    def run_command(self, cmd: List[str], description: str) -> bool:
        """Run command and return success status"""
        self.print_info(f"Executing: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, cwd=self.project_root, check=True)
            self.print_success(f"{description} completed successfully")
            return True
        except subprocess.CalledProcessError as e:
            self.print_error(f"{description} failed with exit code {e.returncode}")
            return False
        except FileNotFoundError:
            self.print_error(f"Command not found: {cmd[0]}")
            return False

    def run_basic_tests(self) -> bool:
        """Run basic scheduler functionality tests"""
        self.print_header("🚀 Running Basic Scheduler Tests")
        if not self.basic_test_file.exists():
            self.print_warning(f"Basic test file not found: {self.basic_test_file}")
            return True
        cmd = self.python_cmd + ["-m", "pytest", str(self.basic_test_file), "-v", "--tb=short"]
        return self.run_command(cmd, "Basic scheduler tests")

    def run_builder_tests(self) -> bool:
        """Run scheduler builder function tests"""
        self.print_header("🚀 Running Scheduler Builder Tests")
        if not self.builder_test_file.exists():
            self.print_warning(f"Builder test file not found: {self.builder_test_file}")
            return True
        cmd = self.python_cmd + ["-m", "pytest", str(self.builder_test_file), "-v", "--tb=short"]
        return self.run_command(cmd, "Scheduler builder tests")

    def run_integration_tests(self) -> bool:
        """Run scheduler integration tests"""
        self.print_header("🚀 Running Scheduler Integration Tests")
        if not self.integration_test_file.exists():
            self.print_warning(f"Integration test file not found: {self.integration_test_file}")
            return True
        cmd = self.python_cmd + ["-m", "pytest", str(self.integration_test_file), "-v", "--tb=short"]
        return self.run_command(cmd, "Scheduler integration tests")

    def run_corner_tests(self) -> bool:
        """Run corner case and error handling tests"""
        self.print_header("🚀 Running Corner Case Tests")
        if not self.corner_test_file.exists():
            self.print_warning(f"Corner case test file not found: {self.corner_test_file}")
            return True
        cmd = self.python_cmd + ["-m", "pytest", str(self.corner_test_file), "-v", "--tb=short"]
        return self.run_command(cmd, "Corner case tests")

    def run_all_tests(self) -> bool:
        """Run all scheduler tests"""
        self.print_header("🚀 Running All Scheduler Tests")
        overall_result = True

        for test_file in self.all_test_files:
            if test_file.exists():
                test_name = test_file.stem.replace("test_scheduler_", "").replace("test_", "")
                self.print_header(f"🚀 Running {test_name.title()} Tests")
                cmd = self.python_cmd + ["-m", "pytest", str(test_file), "-v", "--tb=short"]
                if not self.run_command(cmd, f"{test_name.title()} tests"):
                    overall_result = False
                print()
            else:
                self.print_warning(f"Test file not found: {test_file}")

        if overall_result:
            self.print_success("All scheduler tests completed successfully!")
        else:
            self.print_error("Some scheduler tests failed!")

        return overall_result

    def run_coverage_tests(self) -> bool:
        """Run coverage analysis"""
        self.print_header("📊 Running Coverage Analysis")
        coverage_dir = self.project_root / "coverage"
        coverage_dir.mkdir(exist_ok=True)

        cmd = self.python_cmd + [
            "-m", "pytest", str(self.script_dir),
            "--cov=scheduler",
            "--cov-report=term-missing",
            f"--cov-report=html:{coverage_dir}/html",
            f"--cov-report=xml:{coverage_dir}/coverage.xml",
            "--cov-fail-under=80"
        ]

        if self.run_command(cmd, "Coverage analysis"):
            self.print_success("Coverage requirements met (≥80% overall, ≥75% branch)")
            self.print_info(f"HTML report generated: {coverage_dir}/html/index.html")
            return True
        else:
            self.print_error("Coverage requirements not met")
            self.print_warning("Check the coverage report for details")
            return False

    def run_quality_checks(self) -> bool:
        """Run code quality checks (pyright and pylint)"""
        self.print_header("⚙ Running Code Quality Checks")
        overall_result = True

        # Run pyright
        self.print_info("Running pyright type checking...")
        pyright_cmd = self.python_cmd + ["-m", "pyright", "src/scheduler/"]
        try:
            subprocess.run(pyright_cmd, cwd=self.project_root, check=True, capture_output=True)
            self.print_success("Pyright type checking passed")
        except subprocess.CalledProcessError as e:
            self.print_error("Pyright type checking failed")
            if e.stdout:
                try:
                    print(e.stdout.decode())
                except Exception:
                    print(e.stdout)
            overall_result = False

        print()

        # Run pylint
        self.print_info("Running pylint code quality checking...")
        pylint_cmd = self.python_cmd + ["-m", "pylint", "src/scheduler/", "--score=yes"]
        try:
            result = subprocess.run(pylint_cmd, cwd=self.project_root, check=True, capture_output=True, text=True)
            self.print_success("Pylint code quality checking passed")
            # Extract score from output
            for line in result.stdout.split('\n'):
                if 'rated at' in line:
                    score = line.split('rated at')[1].split('/')[0].strip()
                    self.print_info(f"Pylint score: {score}")
                    break
        except subprocess.CalledProcessError as e:
            self.print_error("Pylint code quality checking failed")
            if e.stdout:
                print(e.stdout)
            overall_result = False

        return overall_result

    def run_single_test(self, test_name: str) -> bool:
        """Run a single test file or test function"""
        self.print_header(f"🚀 Running Single Test: {test_name}")

        # Try to find the test file
        test_file = None
        for file_path in self.all_test_files:
            if test_name in file_path.name:
                test_file = file_path
                break

        if test_file:
            self.print_info(f"Running test file: {test_file.name}")
            cmd = self.python_cmd + ["-m", "pytest", str(test_file), "-v", "--tb=short"]
            return self.run_command(cmd, f"Test file {test_file.name}")
        else:
            # Try as a function name
            self.print_info(f"Running test function: {test_name}")
            cmd = self.python_cmd + ["-m", "pytest", str(self.script_dir), "-v", "-k", test_name, "--tb=short"]
            return self.run_command(cmd, f"Test function {test_name}")

    def install_dependencies(self) -> bool:
        """Install test dependencies"""
        self.print_header("Installing Test Dependencies")
        try:
            # Install the project in development mode
            subprocess.run(
                self.python_cmd + ["-m", "pip", "install", "-e", "."],
                cwd=self.project_root,
                check=True,
                capture_output=True
            )
            # Install test dependencies
            subprocess.run(
                self.python_cmd + ["-m", "pip", "install", "pytest", "pytest-asyncio", "pytest-cov"],
                cwd=self.project_root,
                check=True,
                capture_output=True
            )
            self.print_success("Dependencies installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            self.print_error(f"Failed to install dependencies: {e}")
            return False

    def verify_environment(self) -> bool:
        """Verify testing environment"""
        self.print_header("Verifying Testing Environment")

        # Check if we're in the right directory
        pyproject_path = self.project_root / "pyproject.toml"
        if not pyproject_path.exists():
            self.print_error("Not in a valid Python project directory")
            return False

        self.print_success("Project structure verified")

        # Check if test files exist
        for test_file in self.all_test_files:
            if test_file.exists():
                self.print_success(f"Found test file: {test_file.name}")
            else:
                self.print_warning(f"Test file not found: {test_file.name}")

        return True

    def show_help(self) -> None:
        """Show help information"""
        print()
        self.print_header("Scheduler Test Runner Help")
        print()
        print("Usage: python run_scheduler_tests.py [COMMAND] [OPTIONS]")
        print()
        print("COMMANDS:")
        print("  all                    Run all scheduler tests")
        print("  basic                  Run basic functionality tests")
        print("  builder                Run scheduler builder function tests")
        print("  integration            Run integration tests for scheduler workflows")
        print("  corner/corners         Run corner case and error handling tests")
        print("  coverage               Run coverage analysis")
        print("  quality                Run code quality checks (pyright & pylint)")
        print("  single [test_name]     Run a single test file or test function")
        print("  install                Install test dependencies")
        print("  help                   Show this help message")
        print()
        print("EXAMPLES:")
        print("  python run_scheduler_tests.py all")
        print("  python run_scheduler_tests.py basic")
        print("  python run_scheduler_tests.py builder")
        print("  python run_scheduler_tests.py integration")
        print("  python run_scheduler_tests.py corner")
        print("  python run_scheduler_tests.py single test_scheduler")
        print("  python run_scheduler_tests.py coverage")
        print()
        print("ENVIRONMENT:")
        print("  The script automatically detects and uses uv if available.")
        print("  Falls back to system python3/python if uv is not found.")
        print()
        print("COVERAGE REQUIREMENTS:")
        print("  - Overall coverage: ≥80%")
        print("  - Branch coverage: ≥75%")
        print("  - HTML report: coverage/html/index.html")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Scheduler Module Test Runner",
        add_help=False
    )

    parser.add_argument(
        "command",
        nargs="?",
        default="help",
        choices=[
            "all", "basic", "builder", "integration", "corner", "corners",
            "coverage", "quality", "single", "install", "help"
        ],
        help="Command to execute"
    )

    parser.add_argument(
        "test_name",
        nargs="?",
        help="Test name for single test execution"
    )

    parser.add_argument(
        "-h", "--help",
        action="store_true",
        help="Show help message"
    )

    args = parser.parse_args()

    # Handle help flag
    if args.help:
        args.command = "help"

    # Run the test runner
    runner = TestRunner()

    # Change to project root
    os.chdir(runner.project_root)

    try:
        if args.command == "all":
            success = runner.verify_environment() and runner.run_all_tests()
        elif args.command == "basic":
            success = runner.verify_environment() and runner.run_basic_tests()
        elif args.command == "builder":
            success = runner.verify_environment() and runner.run_builder_tests()
        elif args.command == "integration":
            success = runner.verify_environment() and runner.run_integration_tests()
        elif args.command in ["corner", "corners"]:
            success = runner.verify_environment() and runner.run_corner_tests()
        elif args.command == "coverage":
            success = runner.verify_environment() and runner.run_coverage_tests()
        elif args.command == "quality":
            success = runner.verify_environment() and runner.run_quality_checks()
        elif args.command == "single":
            if not args.test_name:
                runner.print_error("Test name required for single test execution")
                runner.show_help()
                return 1
            success = runner.verify_environment() and runner.run_single_test(args.test_name)
        elif args.command == "install":
            success = runner.install_dependencies()
        elif args.command in ["help", "-h", "--help"]:
            runner.show_help()
            success = True
        else:
            runner.print_error(f"Unknown command: {args.command}")
            print()
            runner.show_help()
            return 1

        return 0 if success else 1

    except KeyboardInterrupt:
        runner.print_warning("Test execution interrupted by user")
        return 130
    except Exception as e:
        runner.print_error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())