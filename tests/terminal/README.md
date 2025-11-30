# Terminal and Document Editor Tests

This directory contains comprehensive tests for the terminal tool (`src/tool/terminal.py`) and document editor tool (`src/tool/doc_edit.py`). The test suite ensures the security, reliability, and functionality of these critical system components.

## 📋 Table of Contents

- [Test Overview](#test-overview)
- [Test Structure](#test-structure)
- [Test Categories](#test-categories)
- [Running Tests](#running-tests)
- [Test Design Principles](#test-design-principles)
- [Environment Setup](#environment-setup)
- [Coverage](#coverage)
- [Troubleshooting](#troubleshooting)

## 🎯 Test Overview

The terminal and document editor test suite validates:

### Terminal Tests (`test_terminal.py`)
- **Initialization**: Terminal workspace setup and configuration
- **Security**: Command filtering, workspace constraints, script execution control
- **Command Execution**: Safe command execution within workspace boundaries
- **Process Management**: Terminal process lifecycle and cleanup
- **Error Handling**: Proper error responses for invalid operations

### Document Editor Tests (`test_doc_edit.py`)
- **File Operations**: Creation, modification, and deletion of files
- **Line-based Editing**: Insert, modify, and delete operations
- **Path Resolution**: Absolute and relative path handling
- **Content Processing**: Special characters, unicode, and multiline content
- **Security**: Workspace constraints and path validation

## 📁 Test Structure

```
tests/terminal/
├── README.md                    # This documentation
├── run_tests.sh                # Test runner script
├── test_terminal.py            # Terminal implementation tests
├── test_doc_edit.py            # Document editor tests
└── test_helpers.py             # Test utility functions
```

### Test Files

- **`test_terminal.py`**: Comprehensive tests for `SingleThreadTerminal` implementation
- **`test_doc_edit.py`**: Tests for `DocumentEditor` class and file editing operations
- **`test_helpers.py`**: Utility functions and test fixtures

## 🧪 Test Categories

### 1. Basic Functionality Tests
验证核心功能的正常工作：
- Terminal initialization and configuration
- Basic command execution (`pwd`, `echo`, `ls`)
- File creation and basic editing operations
- Directory navigation and management

### 2. Security Tests
确保安全约束有效：
- **命令过滤**: 验证禁止命令列表正确阻止危险操作
- **逃逸检测**: 测试嵌套引号、管道、命令替换逃逸尝试
- **路径约束**: 确保所有操作限制在workspace内
- **脚本控制**: 验证脚本执行开关正确工作

### 3. Error Handling Tests
确保错误情况正确处理：
- 无效命令和参数
- 文件不存在或权限错误
- 终端进程异常
- 路径越界尝试

### 4. Edge Cases Tests
处理边界情况：
- 空文件和空行处理
- 大文件和长内容
- 特殊字符和unicode内容
- 嵌套目录结构

## 🚀 Running Tests

### Prerequisites
```bash
# Ensure you're in the project root
cd /path/to/tasking

# Install dependencies (handled automatically by test runner)
./tests/terminal/run_tests.sh install
```

### Quick Start
```bash
# Run all tests with quality checks
./tests/terminal/run_tests.sh all

# Run only terminal tests
./tests/terminal/run_tests.sh terminal

# Run only document editor tests
./tests/terminal/run_tests.sh docedit
```

### Test Categories
```bash
# Run basic functionality tests
./tests/terminal/run_tests.sh basic

# Run security-focused tests
./tests/terminal/run_tests.sh security

# Run code quality checks only
./tests/terminal/run_tests.sh quality
```

### Coverage Report
```bash
# Generate comprehensive coverage report
./tests/terminal/run_tests.sh coverage

# View HTML coverage report (opens in browser)
open tests/terminal/test_results/htmlcov/index.html
```

### Individual Test Files
```bash
# Run specific test file
./tests/terminal/run_tests.sh single test_terminal.py

# Run specific test method
uv run pytest tests/terminal/test_terminal.py::TestSingleThreadTerminal::test_initialization -v
```

### Verbose Output
```bash
# Run with verbose output for debugging
./tests/terminal/run_tests.sh terminal -v

# Run with quiet output
./tests/terminal/run_tests.sh terminal -q
```

### Parallel Execution
```bash
# Run tests with parallel execution
./tests/terminal/run_tests.sh all -j 4
```

## 🎨 Test Design Principles

### 1. 功能验证优先
Tests focus on verifying that the terminal and document editor perform their intended functions correctly, rather than measuring performance or load testing.

### 2. 独立性
Each test method runs independently without depending on the execution order of other tests. Tests create their own temporary workspaces and clean up after themselves.

### 3. 可重复性
Tests use fixed test data and mocking to ensure consistent results across different environments and runs.

### 4. 清晰性
Test names and documentation clearly indicate what functionality is being tested and why.

### 5. 安全第一
Many tests specifically focus on verifying security constraints work correctly to prevent workspace escape and command injection.

## 🌍 Environment Setup

### Test Isolation
Tests use temporary workspaces that are automatically created and cleaned up:

```python
@pytest.fixture
def temp_workspace(self):
    """Create a temporary workspace for testing."""
    temp_dir = tempfile.mkdtemp(prefix="terminal_test_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)
```

### Mock Usage
Tests use mocking to isolate external dependencies and ensure consistent behavior:

```python
@patch('src.tool.terminal.subprocess.Popen')
def test_terminal_initialization(self, mock_popen):
    # Test terminal initialization with mocked subprocess
    pass
```

### Environment Variables
The test runner respects these environment variables:

- `PYTHON`: Python executable to use (default: `uv run python`)
- `PYTEST_OPTIONS`: Additional pytest options
- `SKIP_QUALITY`: Skip quality checks if set

## 📊 Coverage

### Target Coverage
- **Overall Coverage**: ≥ 80%
- **Branch Coverage**: ≥ 75%

### Coverage Reports
Coverage reports are generated in multiple formats:
- **Terminal**: Real-time coverage display
- **HTML**: Interactive report at `tests/terminal/test_results/htmlcov/`
- **XML**: Machine-readable report at `tests/terminal/test_results/coverage.xml`

### Coverage Areas
- All public methods and classes
- Error handling paths
- Security validation logic
- Edge case handling

## 🔧 Troubleshooting

### Common Issues

#### 1. Import Errors
```
ModuleNotFoundError: No module named 'src.tool.terminal'
```
**Solution**: Run from project root or ensure PYTHONPATH is set correctly
```bash
cd /path/to/tasking
PYTHONPATH=. ./tests/terminal/run_tests.sh all
```

#### 2. Permission Errors
```
PermissionError: Command not through security validation
```
**Expected**: This is normal for security tests. The test is verifying that prohibited commands are correctly blocked.

#### 3. Process Already Running
```
RuntimeError: Terminal process already running
```
**Solution**: Ensure proper cleanup in tests. Each test should use a fresh terminal instance.

#### 4. uv Not Found
```
uv: command not found
```
**Solution**: Install uv or let the test runner fall back to system python
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### 5. Quality Check Failures
```
pyright: 8 errors
pylint: 6.50/10
```
**Solution**: Fix type hints and code style issues before submitting

### Debugging Tests

#### Enable Debug Output
```bash
# Run with maximum verbosity
./tests/terminal/run_tests.sh terminal -v -s

# Run with pytest debug options
PYTEST_OPTIONS="--tb=short --no-header" ./tests/terminal/run_tests.sh terminal
```

#### Test Specific Functionality
```bash
# Run specific test categories
uv run pytest tests/terminal/test_terminal.py::TestTerminalSecurity -v

# Run with debugging
uv run pytest tests/terminal/test_terminal.py -k "security" -v -s --pdb
```

#### Inspect Test Workspaces
For debugging, you can temporarily disable cleanup:
```bash
# Modify test to keep temporary directories
# In test file: Comment out shutil.rmtree() in fixture
```

### Getting Help

If you encounter issues not covered here:

1. Check the test output for specific error messages
2. Verify you're running from the correct directory
3. Ensure dependencies are installed
4. Check for Python version compatibility (requires Python 3.12+)

## 📝 Contributing

When adding new tests:

1. **Follow naming conventions**: `test_<functionality>_<scenario>`
2. **Use descriptive docstrings**: Explain what the test validates
3. **Include security tests**: For any new functionality, include security validation
4. **Maintain coverage**: Ensure new code is adequately tested
5. **Update documentation**: Add new test categories to this README

Example test structure:
```python
def test_terminal_feature_scenario(self, terminal):
    """Test that terminal feature handles scenario correctly."""
    # Arrange
    setup_test_conditions()

    # Act
    result = terminal.perform_action()

    # Assert
    assert result == expected_result
    assert security_constraints_maintained()
```

## 🔗 Related Documentation

- [Project README](../../../README.md) - Project overview and setup
- [Developer Guide](../../../src/README.md) - Module architecture and API documentation
- [Terminal Source](../../../src/tool/terminal.py) - Terminal implementation
- [Document Editor Source](../../../src/tool/doc_edit.py) - Document editor implementation