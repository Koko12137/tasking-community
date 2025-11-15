#!/bin/bash
#
# Scheduler Module Test Runner (Shell Version)
#
# This script provides comprehensive testing for the scheduler module
# with Linux command line entry point as required by CLAUDE.md
#
# Usage: ./run_tests.sh [COMMAND] [OPTIONS]
#

set -e  # Exit on error

# Colors and symbols
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

CHECKMARK="✓"
CROSS="✗"
ROCKET="🚀"
GEAR="⚙"
CHART="📊"
WARNING="⚠"
INFO="ℹ"
PURPLE_SYM="🟣"

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCHEDULER_TEST_DIR="$SCRIPT_DIR"
COVERAGE_DIR="$PROJECT_ROOT/coverage"

# Python command detection
PYTHON_CMD=""
PIP_CMD=""

print_status() {
    local color=$1
    local symbol=$2
    local message=$3
    echo -e "${color}${symbol} ${message}${NC}"
}

print_header() {
    echo
    print_status "$BLUE" "$INFO" "$1"
    echo "================================================================================"
}

print_success() {
    print_status "$GREEN" "$CHECKMARK" "$1"
}

print_error() {
    print_status "$RED" "$CROSS" "$1"
}

print_warning() {
    print_status "$YELLOW" "$WARNING" "$1"
}

print_info() {
    print_status "$CYAN" "$INFO" "$1"
}

detect_python_env() {
    print_header "Detecting Python Environment"

    # Check for uv first (preferred)
    if command -v uv &> /dev/null; then
        if [[ -d "$PROJECT_ROOT/.venv" ]]; then
            PYTHON_CMD="uv run python"
            PIP_CMD="uv pip"
            print_success "Using uv environment (preferred)"
            return 0
        else
            print_warning "uv found but no .venv directory - creating environment..."
            if (cd "$PROJECT_ROOT" && uv venv) &> /dev/null; then
                PYTHON_CMD="uv run python"
                PIP_CMD="uv pip"
                print_success "Created and using uv environment"
                return 0
            else
                print_warning "Failed to create uv environment"
            fi
        fi
    fi

    # Fallback to standard python3
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        PIP_CMD="pip3"
        print_info "Using system python3"
        return 0
    fi

    # Fallback to python
    if command -v python &> /dev/null; then
        PYTHON_CMD="python"
        PIP_CMD="pip"
        print_warning "Using system python (python3 not found)"
        return 0
    fi

    print_error "No Python interpreter found!"
    print_warning "Using python3 as fallback"
    PYTHON_CMD="python3"
    PIP_CMD="pip3"
    return 0
}

verify_prerequisites() {
    print_header "Verifying Prerequisites"

    # Setup environment first
    if ! setup_environment; then
        print_error "Failed to setup environment"
        return 1
    fi

    # Check if we're in the right directory
    if [[ ! -f "$PROJECT_ROOT/pyproject.toml" ]] && [[ ! -f "$PROJECT_ROOT/setup.py" ]]; then
        print_error "Not in a valid Python project directory"
        print_info "Make sure you're in the project root directory"
        return 1
    fi

    print_success "Project structure verified"

    # Check if scheduler tests exist
    if [[ ! -d "$SCHEDULER_TEST_DIR" ]]; then
        print_error "Scheduler test directory not found: $SCHEDULER_TEST_DIR"
        return 1
    fi

    # Check for test files
    local test_files=("test_scheduler_basic.py" "test_scheduler_builder.py" "test_scheduler_integration.py" "test_scheduler_corner_cases.py")

    for file_name in "${test_files[@]}"; do
        local file_path="$SCHEDULER_TEST_DIR/$file_name"
        if [[ -f "$file_path" ]]; then
            print_success "Found test file: $file_name"
        else
            print_warning "Test file not found: $file_name"
        fi
    done

    print_success "Prerequisites verified"
    return 0
}

setup_environment() {
    # Detect Python environment if not already set
    if [[ -z "$PYTHON_CMD" ]]; then
        detect_python_env
    fi

    # Check if scheduler module is available
    if [[ ! -d "$PROJECT_ROOT/src/core/scheduler" ]]; then
        print_error "Scheduler module not found in src/core/scheduler"
        return 1
    fi

    return 0
}

run_command() {
    local cmd="$1"
    local description="$2"

    print_info "Executing: $cmd"
    if eval "$cmd" 2>&1; then
        print_success "$description completed successfully"
        return 0
    else
        local exit_code=$?
        print_error "$description failed with exit code $exit_code"
        return $exit_code
    fi
}

run_basic_tests() {
    print_header "$GEAR Running Basic Scheduler Tests"

    setup_environment || return 1

    local test_file="$SCHEDULER_TEST_DIR/test_scheduler_basic.py"
    if [[ -f "$test_file" ]]; then
        run_command "$PYTHON_CMD -m pytest $test_file -v --tb=short" "Basic tests"
    else
        print_warning "Basic test file not found: $test_file"
        return 0
    fi
}

run_builder_tests() {
    print_header "$GEAR Running Scheduler Builder Tests"

    setup_environment || return 1

    local test_file="$SCHEDULER_TEST_DIR/test_scheduler_builder.py"
    if [[ -f "$test_file" ]]; then
        run_command "$PYTHON_CMD -m pytest $test_file -v --tb=short" "Builder tests"
    else
        print_warning "Builder test file not found: $test_file"
        return 0
    fi
}

run_integration_tests() {
    print_header "$GEAR Running Scheduler Integration Tests"

    setup_environment || return 1

    local test_file="$SCHEDULER_TEST_DIR/test_scheduler_integration.py"
    if [[ -f "$test_file" ]]; then
        run_command "$PYTHON_CMD -m pytest $test_file -v --tb=short" "Integration tests"
    else
        print_warning "Integration test file not found: $test_file"
        return 0
    fi
}

run_corner_case_tests() {
    print_header "$GEAR Running Corner Case Tests"

    setup_environment || return 1

    local test_file="$SCHEDULER_TEST_DIR/test_scheduler_corner_cases.py"
    if [[ -f "$test_file" ]]; then
        run_command "$PYTHON_CMD -m pytest $test_file -v --tb=short" "Corner case tests"
    else
        print_warning "Corner case test file not found: $test_file"
        return 0
    fi
}

run_coverage_tests() {
    print_header "$CHART Running Coverage Analysis"

    setup_environment || return 1

    # Create coverage directory
    mkdir -p "$COVERAGE_DIR"

    local cmd="$PYTHON_CMD -m pytest $SCHEDULER_TEST_DIR --cov=scheduler --cov-report=term-missing --cov-report=html:$COVERAGE_DIR/html --cov-report=xml:$COVERAGE_DIR/coverage.xml --cov-fail-under=80"

    if run_command "$cmd" "Coverage analysis"; then
        print_success "Coverage requirements met (≥80% overall, ≥75% branch)"
        print_info "HTML report generated: $COVERAGE_DIR/html/index.html"
        return 0
    else
        print_error "Coverage requirements not met"
        print_warning "Check the coverage report for details"
        return 1
    fi
}

run_single_test() {
    local test_name="$1"

    if [[ -z "$test_name" ]]; then
        print_error "Test name required for single test execution"
        show_help
        return 1
    fi

    print_header "$ROCKET Running Single Test: $test_name"

    setup_environment || return 1

    # Try to find the test file
    local test_file=""
    for file_path in "$SCHEDULER_TEST_DIR"/test_*.py; do
        if [[ -f "$file_path" ]] && [[ "$(basename "$file_path")" == *"$test_name"* ]]; then
            test_file="$file_path"
            break
        fi
    done

    if [[ -n "$test_file" ]]; then
        print_info "Running test file: $(basename "$test_file")"
        run_command "$PYTHON_CMD -m pytest $test_file -v --tb=short" "Test file $(basename "$test_file")"
    else
        # Try as a function name
        print_info "Running test function: $test_name"
        run_command "$PYTHON_CMD -m pytest $SCHEDULER_TEST_DIR -v -k $test_name --tb=short" "Test function $test_name"
    fi
}

run_quality_checks() {
    print_header "$GEAR Running Code Quality Checks"

    setup_environment || return 1

    local overall_result=0

    # Run pyright
    print_info "Running pyright type checking..."
    if eval "$PYTHON_CMD -m pyright src/core/scheduler/" 2>&1; then
        print_success "Pyright type checking passed"
    else
        print_error "Pyright type checking failed"
        overall_result=1
    fi

    echo

    # Run pylint
    print_info "Running pylint code quality checking..."
    local pylint_output
    pylint_output=$(eval "$PYTHON_CMD -m pylint src/core/scheduler/ --score=yes" 2>&1) || overall_result=$?

    if [[ $overall_result -eq 0 ]]; then
        print_success "Pylint code quality checking passed"
        # Extract score from output
        local score=$(echo "$pylint_output" | grep "rated at" | sed -n 's/.*rated at \([^/]*\)\/.*/\1/p')
        if [[ -n "$score" ]]; then
            print_info "Pylint score: $score"
        fi
    else
        print_error "Pylint code quality checking failed"
        echo "$pylint_output"
    fi

    return $overall_result
}

run_all_tests() {
    print_header "$ROCKET Running All Scheduler Tests"

    local overall_result=0

    # Run all test categories
    if ! run_basic_tests; then
        overall_result=1
    fi

    echo
    if ! run_builder_tests; then
        overall_result=1
    fi

    echo
    if ! run_integration_tests; then
        overall_result=1
    fi

    echo
    if ! run_corner_case_tests; then
        overall_result=1
    fi

    echo
    if [[ $overall_result -eq 0 ]]; then
        print_success "All scheduler tests completed successfully!"
    else
        print_error "Some scheduler tests failed!"
    fi

    return $overall_result
}

run_comprehensive_tests() {
    print_header "$PURPLE_SYM Running Comprehensive Test Suite"

    local overall_result=0

    # Run all tests
    if ! run_all_tests; then
        overall_result=1
    fi

    echo
    # Run coverage analysis
    if ! run_coverage_tests; then
        overall_result=1
    fi

    echo
    if [[ $overall_result -eq 0 ]]; then
        print_success "Comprehensive test suite completed successfully!"
        print_info "All tests passed and coverage requirements met"
    else
        print_error "Comprehensive test suite failed!"
    fi

    return $overall_result
}

install_dependencies() {
    print_header "Installing Test Dependencies"

    detect_python_env || return 1

    print_info "Installing test dependencies..."

    # Install the project in development mode
    if ! (cd "$PROJECT_ROOT" && eval "$PIP_CMD install -e .") &> /dev/null; then
        print_error "Failed to install project"
        return 1
    fi

    # Install test dependencies
    if ! (cd "$PROJECT_ROOT" && eval "$PIP_CMD install pytest pytest-asyncio pytest-cov") &> /dev/null; then
        print_error "Failed to install test dependencies"
        return 1
    fi

    print_success "Dependencies installed successfully"
    return 0
}

diagnose_issues() {
    print_header "Diagnosing Common Issues"

    # Check Python version
    if [[ -n "$PYTHON_CMD" ]]; then
        local python_version
        python_version=$(eval "$PYTHON_CMD --version" 2>&1) || python_version="Failed to get version"
        print_info "Python version: $python_version"

        # Check if version is adequate
        if eval "$PYTHON_CMD -c \"import sys; exit(0 if sys.version_info >= (3, 12) else 1)\"" 2>/dev/null; then
            print_success "Python version meets requirements (3.12+)"
        else
            print_warning "Python version may be too old (3.12+ recommended)"
        fi
    else
        print_error "Python interpreter not configured"
    fi

    # Check project structure
    if [[ -f "$PROJECT_ROOT/pyproject.toml" ]]; then
        print_success "Found pyproject.toml"
    else
        print_warning "No pyproject.toml found"
    fi

    # Check for uv
    if command -v uv &> /dev/null; then
        print_success "uv found (preferred)"
        if [[ -d "$PROJECT_ROOT/.venv" ]]; then
            print_success "uv virtual environment found"
        else
            print_warning "No uv virtual environment found"
        fi
    else
        print_warning "uv not found (optional but recommended)"
    fi

    # Check for scheduler module
    if [[ -d "$PROJECT_ROOT/src/core/scheduler" ]]; then
        print_success "Scheduler module found"
    else
        print_error "Scheduler module not found in src/core/scheduler"
    fi

    # Check for test dependencies
    if [[ -n "$PYTHON_CMD" ]]; then
        local dependencies=("pytest:pytest available" "pytest_asyncio:pytest-asyncio available" "pytest_cov:pytest-cov available")

        for dep_info in "${dependencies[@]}"; do
            local module="${dep_info%:*}"
            local desc="${dep_info#*:}"

            if eval "$PYTHON_CMD -c \"import $module\"" 2>/dev/null; then
                print_success "$desc"
            else
                print_warning "$desc - run 'install' command"
            fi
        done
    fi
}

show_help() {
    echo
    print_header "Scheduler Test Runner Help"
    echo
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo
    echo "COMMANDS:"
    echo "  all                    Run all scheduler tests"
    echo "  basic                  Run basic functionality tests"
    echo "  builder                Run scheduler builder function tests"
    echo "  integration            Run integration tests for scheduler workflows"
    echo "  corner                 Run corner case and error handling tests"
    echo "  coverage               Run coverage analysis"
    echo "  comprehensive          Run all tests with coverage analysis"
    echo "  quality                Run code quality checks (pyright & pylint)"
    echo "  single [test_name]     Run a single test file or test function"
    echo "  install                Install test dependencies"
    echo "  diagnose               Diagnose common issues"
    echo "  help                   Show this help message"
    echo
    echo "EXAMPLES:"
    echo "  $0 all"
    echo "  $0 basic"
    echo "  $0 builder"
    echo "  $0 integration"
    echo "  $0 corner"
    echo "  $0 coverage"
    echo "  $0 single test_scheduler"
    echo "  $0 single test_base_scheduler"
    echo "  $0 comprehensive"
    echo
    echo "ENVIRONMENT:"
    echo "  The script automatically detects and uses uv if available."
    echo "  Falls back to system python3/python if uv is not found."
    echo
    echo "COVERAGE REQUIREMENTS:"
    echo "  - Overall coverage: ≥80%"
    echo "  - Branch coverage: ≥75%"
    echo "  - HTML report: coverage/html/index.html"
    echo
    echo "TROUBLESHOOTING:"
    echo "  1. Ensure Python 3.12+ is installed"
    echo "  2. Install uv for preferred environment management"
    echo "  3. Run 'install' command to set up dependencies"
    echo "  4. Check that you're in the project root directory"
    echo "  5. Use 'diagnose' command for detailed analysis"
    echo
}

main() {
    # Change to project root
    cd "$PROJECT_ROOT"

    # Handle KeyboardInterrupt
    trap 'echo; print_warning "Test execution interrupted by user"; exit 130' INT

    local command="${1:-help}"
    local test_name="$2"

    case "$command" in
        "all")
            verify_prerequisites && run_all_tests
            ;;
        "basic")
            verify_prerequisites && run_basic_tests
            ;;
        "builder")
            verify_prerequisites && run_builder_tests
            ;;
        "integration")
            verify_prerequisites && run_integration_tests
            ;;
        "corner")
            verify_prerequisites && run_corner_case_tests
            ;;
        "coverage")
            verify_prerequisites && run_coverage_tests
            ;;
        "comprehensive")
            verify_prerequisites && run_comprehensive_tests
            ;;
        "quality")
            verify_prerequisites && run_quality_checks
            ;;
        "single")
            verify_prerequisites && run_single_test "$test_name"
            ;;
        "install")
            install_dependencies
            ;;
        "diagnose")
            diagnose_issues
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            print_error "Unknown command: $command"
            echo
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"