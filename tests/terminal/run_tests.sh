#!/bin/bash

# Terminal and Document Editor Test Runner
# This script provides comprehensive testing for terminal and document editing tools
# following the project's testing standards and patterns

set -e  # Exit on any error

# Color definitions for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEST_DIR="$SCRIPT_DIR"
RESULTS_DIR="$TEST_DIR/test_results"
COVERAGE_FILE="$RESULTS_DIR/.coverage"

# Ensure results directory exists
mkdir -p "$RESULTS_DIR"

# Help function
show_help() {
    cat << EOF
${BOLD}${BLUE}Terminal and Document Editor Test Runner${NC}

${YELLOW}USAGE:${NC}
    $0 [COMMAND] [OPTIONS]

${YELLOW}COMMANDS:${NC}
    all                     Run all tests (terminal + document editor + quality checks)
    terminal                Run terminal-specific tests only
    docedit                 Run document editor tests only
    basic                   Run basic functionality tests
    security                Run security-focused tests
    coverage                Generate test coverage report
    quality                 Run code quality checks (pyright + pylint)
    install                 Install test dependencies
    single [test_name]      Run a specific test file
    help                    Show this help message

${YELLOW}OPTIONS:${NC}
    -v, --verbose           Enable verbose output
    -q, --quiet             Suppress non-error output
    --no-cleanup            Don't clean up temporary files after tests
    --keep-coverage         Keep coverage data files after tests
    -j, --jobs N            Run tests with N parallel jobs

${YELLOW}EXAMPLES:${NC}
    $0 all                  # Run all tests with quality checks
    $0 terminal -v          # Run terminal tests with verbose output
    $0 coverage             # Generate coverage report only
    $0 single test_terminal # Run specific test file
    $0 quality              # Run only quality checks

${YELLOW}ENVIRONMENT:${NC}
    PYTHON                  Python executable to use (default: uv run python)
    PYTEST_OPTIONS          Additional pytest options
    SKIP_QUALITY            Skip quality checks if set

EOF
}

# Print functions with colors
print_header() {
    echo -e "\n${BOLD}${BLUE}$1${NC}"
    echo -e "${BLUE}$(printf '=%.0s' {1..50})${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

# Check if we're in the right directory
check_environment() {
    if [[ ! -f "$PROJECT_ROOT/pyproject.toml" ]]; then
        print_error "pyproject.toml not found. Please run from project root or ensure project structure is correct."
        exit 1
    fi

    # Check if uv is available
    if ! command -v uv &> /dev/null; then
        print_warning "uv not found, falling back to python3"
        PYTHON_CMD="python3"
    else
        PYTHON_CMD="uv run python"
    fi

    print_info "Using Python command: $PYTHON_CMD"
    print_info "Project root: $PROJECT_ROOT"
}

# Install dependencies
install_deps() {
    print_header "Installing Test Dependencies"

    cd "$PROJECT_ROOT"

    # Install project in development mode
    if command -v uv &> /dev/null; then
        $PYTHON_CMD -m pip install -e .
        print_success "Project installed with uv"
    else
        $PYTHON_CMD -m pip install -e .
        print_success "Project installed with pip"
    fi

    # Install test dependencies
    local test_deps=(
        "pytest>=7.0.0"
        "pytest-cov>=4.0.0"
        "pytest-mock>=3.10.0"
        "pytest-asyncio>=0.21.0"
    )

    for dep in "${test_deps[@]}"; do
        if command -v uv &> /dev/null; then
            uv add --dev "$dep" 2>/dev/null || $PYTHON_CMD -m pip install "$dep"
        else
            $PYTHON_CMD -m pip install "$dep"
        fi
    done

    print_success "Test dependencies installed"
}

# Run tests with pytest
run_pytest() {
    local test_pattern="$1"
    local test_name="$2"
    local extra_args="$3"

    print_header "Running $test_name Tests"

    cd "$PROJECT_ROOT"

    # Build pytest command
    local pytest_cmd="$PYTHON_CMD -m pytest"

    # Add verbosity if requested
    if [[ "$VERBOSE" == "true" ]]; then
        pytest_cmd="$pytest_cmd -v -s"
    fi

    # Add coverage if this is a full test run
    if [[ "$test_name" == "All" ]]; then
        pytest_cmd="$pytest_cmd --cov=src.tool --cov-report=html:$RESULTS_DIR/htmlcov --cov-report=term-missing --cov-report=xml:$RESULTS_DIR/coverage.xml"
    fi

    # Add parallel execution if requested
    if [[ -n "$JOBS" ]]; then
        pytest_cmd="$pytest_cmd -n $JOBS"
    fi

    # Add test pattern
    pytest_cmd="$pytest_cmd $test_pattern"

    # Add any extra arguments
    if [[ -n "$extra_args" ]]; then
        pytest_cmd="$pytest_cmd $extra_args"
    fi

    # Add any user-specified pytest options
    if [[ -n "$PYTEST_OPTIONS" ]]; then
        pytest_cmd="$pytest_cmd $PYTEST_OPTIONS"
    fi

    print_info "Running: $pytest_cmd"

    # Run tests and capture exit code
    if eval "$pytest_cmd"; then
        print_success "$test_name tests passed"
        return 0
    else
        print_error "$test_name tests failed"
        return 1
    fi
}

# Run code quality checks
run_quality_checks() {
    print_header "Running Code Quality Checks"

    cd "$PROJECT_ROOT"

    local quality_failed=0

    # Check if SKIP_QUALITY is set
    if [[ -n "$SKIP_QUALITY" ]]; then
        print_warning "SKIP_QUALITY is set, skipping quality checks"
        return 0
    fi

    # Run pyright
    print_info "Running pyright type checking..."
    if command -v uv &> /dev/null; then
        if uv run pyright src/tool/terminal.py src/tool/text_edit.py; then
            print_success "pyright checks passed"
        else
            print_error "pyright checks failed"
            quality_failed=1
        fi
    else
        print_warning "uv not found, skipping pyright checks"
    fi

    # Run pylint
    print_info "Running pylint linting..."
    if command -v uv &> /dev/null; then
        # Check if pylint is installed
        if uv run pylint --version &> /dev/null; then
            if uv run pylint --score=yes src/tool/terminal.py src/tool/text_edit.py; then
                print_success "pylint checks passed"
            else
                print_error "pylint checks failed"
                quality_failed=1
            fi
        else
            print_warning "pylint not installed, skipping linting checks"
        fi
    else
        print_warning "uv not found, skipping pylint checks"
    fi

    if [[ $quality_failed -eq 0 ]]; then
        print_success "All quality checks passed"
    else
        print_error "Some quality checks failed"
    fi

    return $quality_failed
}

# Run basic functionality tests
run_basic_tests() {
    print_header "Running Basic Functionality Tests"

    # Test terminal initialization
    run_pytest "$TEST_DIR/test_terminal.py::TestSingleThreadTerminal::test_initialization" "Terminal Initialization" ""

    # Test text editor initialization
    run_pytest "$TEST_DIR/test_doc_edit.py::TestTextEditor::test_initialization" "Text Editor Initialization" ""

    # Test basic command execution
    run_pytest "$TEST_DIR/test_terminal.py::TestSingleThreadTerminal::test_run_command_simple" "Basic Command Execution" ""

    # Test basic file editing
    run_pytest "$TEST_DIR/test_doc_edit.py::TestTextEditor::test_edit_new_file" "Basic File Editing" ""
}

# Run security tests
run_security_tests() {
    print_header "Running Security Tests"

    # Test overall security constraints
    run_pytest "$TEST_DIR/test_terminal.py::TestTerminalSecurity" "Terminal Security" ""

    # Test new prohibited commands (chmod, package managers)
    run_pytest "$TEST_DIR/test_terminal.py::TestTerminalSecurity::test_security_new_prohibited_commands" "New Prohibited Commands" ""

    # Test pipe and semicolon escape attempts
    run_pytest "$TEST_DIR/test_terminal.py::TestTerminalSecurity::test_security_pipe_and_semicolon_escape" "Pipe/Semicolon Escape" ""

    # Test path-sensitive command security
    run_pytest "$TEST_DIR/test_terminal.py::TestTerminalSecurity::test_security_path_sensitive_commands" "Path-Sensitive Commands" ""

    # Test script file detection
    run_pytest "$TEST_DIR/test_terminal.py::TestTerminalSecurity::test_security_script_file_detection" "Script File Detection" ""

    # Test complex escape patterns
    run_pytest "$TEST_DIR/test_terminal.py::TestTerminalSecurity::test_security_complex_escape_patterns" "Complex Escape Patterns" ""

    # Test text editor security integration
    run_pytest "$TEST_DIR/test_doc_edit.py::TestTextEditor::test_terminal_security_in_text_editor_context" "Text Editor Security" ""

    # Test prohibited commands
    run_pytest "$TEST_DIR/test_terminal.py::TestSingleThreadTerminal::test_check_command_prohibited_list" "Prohibited Commands" ""

    # Test escaped commands
    run_pytest "$TEST_DIR/test_terminal.py::TestSingleThreadTerminal::test_check_command_escaped_prohibited" "Escaped Commands" ""
}

# Generate coverage report
generate_coverage() {
    print_header "Generating Test Coverage Report"

    cd "$PROJECT_ROOT"

    # Run all tests with coverage
    run_pytest "$TEST_DIR/" "Coverage" "--cov=src.tool --cov-report=html --cov-report=term --cov-report=xml"

    # Show coverage summary
    if [[ -f "$RESULTS_DIR/htmlcov/index.html" ]]; then
        print_success "Coverage report generated: $RESULTS_DIR/htmlcov/index.html"

        # Try to open in browser (optional)
        if command -v xdg-open &> /dev/null; then
            print_info "To view coverage report: xdg-open $RESULTS_DIR/htmlcov/index.html"
        elif command -v open &> /dev/null; then
            print_info "To view coverage report: open $RESULTS_DIR/htmlcov/index.html"
        fi
    fi
}

# Main execution logic
main() {
    local command="${1:-all}"
    local failed=0

    # Parse command line arguments
    VERBOSE="false"
    JOBS=""
    NO_CLEANUP="false"
    KEEP_COVERAGE="false"

    while [[ $# -gt 0 ]]; do
        case $1 in
            -v|--verbose)
                VERBOSE="true"
                shift
                ;;
            -q|--quiet)
                set +x
                shift
                ;;
            -j|--jobs)
                JOBS="$2"
                shift 2
                ;;
            --no-cleanup)
                NO_CLEANUP="true"
                shift
                ;;
            --keep-coverage)
                KEEP_COVERAGE="true"
                shift
                ;;
            all|terminal|docedit|basic|security|coverage|quality|install|single|help)
                command="$1"
                shift
                ;;
            *)
                # Unknown option, might be test name for single command
                if [[ "$command" == "single" ]]; then
                    break
                fi
                print_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Show help if requested
    if [[ "$command" == "help" ]]; then
        show_help
        exit 0
    fi

    # Check environment
    check_environment

    # Execute command
    case $command in
        install)
            install_deps
            ;;
        all)
            print_header "Running All Tests"
            install_deps
            run_pytest "$TEST_DIR/" "All" ""
            if [[ $? -eq 0 ]]; then
                run_quality_checks
                failed=$?
            else
                failed=1
            fi
            ;;
        terminal)
            install_deps
            run_pytest "$TEST_DIR/test_terminal.py" "Terminal" ""
            ;;
        docedit)
            install_deps
            run_pytest "$TEST_DIR/test_doc_edit.py" "Document Editor" ""
            ;;
        basic)
            install_deps
            run_basic_tests
            ;;
        security)
            install_deps
            run_security_tests
            ;;
        coverage)
            install_deps
            generate_coverage
            ;;
        quality)
            run_quality_checks
            failed=$?
            ;;
        single)
            if [[ $# -eq 0 ]]; then
                print_error "Please specify a test name"
                show_help
                exit 1
            fi
            install_deps
            test_name="$1"
            run_pytest "$TEST_DIR/$test_name" "Single Test" ""
            ;;
        *)
            print_error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac

    # Cleanup
    if [[ "$NO_CLEANUP" != "true" ]]; then
        # Clean up coverage files if not keeping them
        if [[ "$KEEP_COVERAGE" != "true" ]]; then
            find "$PROJECT_ROOT" -name ".coverage" -type f -delete 2>/dev/null || true
        fi
    fi

    # Print final status
    print_header "Test Summary"
    if [[ $failed -eq 0 ]]; then
        print_success "All tests completed successfully!"
        exit 0
    else
        print_error "Some tests failed or quality checks failed!"
        exit 1
    fi
}

# Run main function with all arguments
main "$@"