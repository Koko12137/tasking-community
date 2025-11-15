# Scheduler Module Tests

This directory contains comprehensive tests for the scheduler module.

## Test Files

### Core Test Files

1. **test_scheduler_basic.py** - Core functionality tests
   - Tests BaseScheduler initialization and configuration
   - Tests compilation logic and validation
   - Tests Builder functions (create_simple_scheduler, create_tree_scheduler)
   - Tests basic workflow execution
   - Tests error handling for edge cases

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