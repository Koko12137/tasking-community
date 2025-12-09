# Scheduler Module Tests

This directory contains comprehensive tests for the scheduler module.

## 📁 Test Structure

```
tests/scheduler/
├── 📄 README.md                    # 本文档
├── 📄 run_scheduler_tests.py       # Python 测试运行器
├── 📄 run_scheduler_tests.sh       # Shell 测试运行器
├── 📄 __init__.py                  # 测试模块初始化
├── 📄 test_scheduler_basic.py      # 基础调度器功能测试
├── 📄 test_scheduler_builder.py    # 调度器构建器测试
├── 📄 test_scheduler_corner_cases.py # 边界情况测试
├── 📄 test_scheduler_integration.py # 集成测试
└── 📄 test_helpers.py              # 测试辅助工具
```

### 🧪 Core Test Files

#### 1. test_scheduler_basic.py - Core functionality tests
- **BaseScheduler 初始化和配置测试**
  - 测试默认参数和自定义参数初始化
  - 测试无效参数的错误处理
  - 测试结束状态配置
- **编译逻辑和验证测试**
  - 测试状态机编译规则
  - 测试循环检测和限制
  - 测试状态转换规则验证
- **Builder 函数测试**
  - 测试 `create_simple_scheduler` 函数
  - 测试 `create_tree_scheduler` 函数
  - 测试 Builder 参数传递
- **基础工作流执行测试**
  - 测试简单的状态转换流程
  - 测试事件处理机制
  - 测试回调函数执行
- **边界情况错误处理测试**
  - 测试无效状态转换
  - 测试未配置的状态处理
  - 测试异常情况下的错误恢复

## Test Script

The `run_scheduler_tests.py` script provides a convenient way to run tests:

```bash
# Run all tests
./run_scheduler_tests.py all

# Run basic tests
./run_scheduler_tests.py basic

# Run code quality checks
./run_scheduler_tests.py quality

# Run coverage analysis
./run_scheduler_tests.py coverage

# Run comprehensive test suite
./run_scheduler_tests.py comprehensive
```

## Test Coverage

The tests cover:

- ✅ BaseScheduler initialization
- ✅ Compilation and validation logic
- ✅ State transition handling
- ✅ Callback execution
- ✅ Error handling and retry logic
- ✅ Builder functions (create_simple_scheduler, create_tree_scheduler)
- ✅ Integration with agents and tasks
- ✅ Queue and context handling
- ✅ Async and sync state functions

## Known Issues

Some tests may fail due to:

1. **Compilation Requirements**: BaseScheduler requires all end states to participate in transitions
2. **Mock Requirements**: Tests need proper mock setup for agents and tasks
3. **Type Import Paths**: TaskEvent and TaskState are imported from `src.state_machine.task.const`

## Running Tests Manually

You can also run tests directly with pytest:

```bash
# Run all scheduler tests
uv run pytest tests/scheduler/ -v

# Run specific test file
uv run pytest tests/scheduler/test_scheduler.py -v

# Run with coverage
uv run pytest tests/scheduler/ --cov=src.scheduler --cov-report=term-missing
```

## Code Quality

The test suite includes code quality checks:

- **Pyright**: Type checking
- **Pylint**: Code quality and style analysis

Run quality checks with:

```bash
./run_scheduler_tests.py quality
```

## Test Architecture

The tests follow a modular architecture:

- **MockTask**: Implements ITask interface for testing
- **AsyncMock**: Used for async function mocking
- **IsolatedAsyncioTestCase**: Used for async test methods
- **Fixtures**: Each test class has setUp methods for common test data

## Future Enhancements

Potential improvements:

1. Add performance tests for large state machines
2. Add concurrent execution tests
3. Add integration tests with real agent implementations
4. Add property-based testing for edge cases
5. Add visualization of state transitions for debugging