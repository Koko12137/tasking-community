#!/bin/bash

# 状态机测试运行器 - Shell版本
#
# 提供状态机模块的测试运行功能

set -e  # 遇到错误立即退出

# ===== 终端颜色定义 - 用户体验设计 =====
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# ===== 全局变量定义 - 配置管理 =====
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"  # tests/state_machine -> project_root
BASIC_TEST_FILE="$SCRIPT_DIR/test_state_machine.py"
CORNER_TEST_FILE="$SCRIPT_DIR/test_corner_cases.py"
TASK_TEST_FILE="$SCRIPT_DIR/test_task.py"
TREE_TASK_TEST_FILE="$SCRIPT_DIR/test_tree_task.py"
WORKFLOW_TEST_FILE="$SCRIPT_DIR/test_workflow.py"
HELPERS_TEST_FILE="$SCRIPT_DIR/test_helpers.py"
ALL_TEST_FILES="$BASIC_TEST_FILE $CORNER_TEST_FILE $TASK_TEST_FILE $TREE_TASK_TEST_FILE $WORKFLOW_TEST_FILE"
PYTHON_CMD=""
PIP_CMD=""

# ===== 工具函数设计 - 通用功能封装 =====

# 打印带颜色的状态信息
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${WHITE}=== $1 ===${NC}"
}

# 检测命令是否可用
command_exists() {
    command -v "$1" &> /dev/null
}

# 智能检测Python环境 - 环境适配设计
detect_python_environment() {
    print_status "检测Python环境..."

    if command_exists uv; then
        PYTHON_CMD="uv run python"
        PIP_CMD="uv pip"
        print_success "检测到uv环境: $PYTHON_CMD"
    elif command_exists python3; then
        PYTHON_CMD="python3"
        PIP_CMD="pip3"
        print_success "使用系统Python3: $PYTHON_CMD"
    elif command_exists python; then
        PYTHON_CMD="python"
        PIP_CMD="pip"
        print_warning "使用系统Python: $PYTHON_CMD"
    else
        print_error "未找到Python环境，请安装Python或uv"
        exit 1
    fi
}

# 验证运行环境 - 环境检查
validate_environment() {
    print_status "验证运行环境..."

    # 检查测试文件是否存在
    for test_file in $ALL_TEST_FILES; do
        if [ ! -f "$test_file" ]; then
            print_error "测试文件不存在: $test_file"
            exit 1
        fi
    done

    # 检查Python命令是否可用
    if ! $PYTHON_CMD --version &> /dev/null; then
        print_error "Python命令不可用: $PYTHON_CMD"
        exit 1
    fi

    print_success "环境验证通过"
}

# 执行测试命令的通用函数 - 命令执行封装
run_test_command() {
    local cmd="$1"
    local description="$2"

    print_status "执行: $cmd"

    cd "$PROJECT_ROOT"

    if eval "$cmd"; then
        print_success "$description"
        return 0
    else
        print_error "$description"
        return 1
    fi
}

# ===== 测试功能函数 - 模块化设计 =====

# 运行所有测试
run_all_tests() {
    print_header "运行所有测试"

    local cmd="$PYTHON_CMD -m pytest $ALL_TEST_FILES -v --tb=short"
    run_test_command "$cmd" "所有测试完成"
}

# 运行基础功能测试
run_basic_tests() {
    print_header "运行基础功能测试"
    local cmd="$PYTHON_CMD -m pytest $BASIC_TEST_FILE -v --tb=short"
    run_test_command "$cmd" "基础功能测试完成"
}

# 运行Corner Cases测试
run_corner_tests() {
    print_header "运行Corner Cases测试"
    local cmd="$PYTHON_CMD -m pytest $CORNER_TEST_FILE -v --tb=short"
    run_test_command "$cmd" "Corner Cases测试完成"
}

# 运行特定测试文件
run_task_tests() {
    print_header "运行Task测试"
    run_test_command "$PYTHON_CMD -m pytest $TASK_TEST_FILE -v --tb=short" "Task测试完成"
}

run_tree_task_tests() {
    print_header "运行Tree Task测试"
    run_test_command "$PYTHON_CMD -m pytest $TREE_TASK_TEST_FILE -v --tb=short" "Tree Task测试完成"
}

run_workflow_tests() {
    print_header "运行Workflow测试"
    run_test_command "$PYTHON_CMD -m pytest $WORKFLOW_TEST_FILE -v --tb=short" "Workflow测试完成"
}

run_helpers_tests() {
    print_header "运行Helpers测试"
    run_test_command "$PYTHON_CMD -m pytest $HELPERS_TEST_FILE -v --tb=short" "Helpers测试完成"
}

# 运行覆盖率测试
run_coverage_tests() {
    print_header "生成覆盖率报告"

    local cmd="$PYTHON_CMD -m pytest $ALL_TEST_FILES --cov=src.state_machine --cov-report=html --cov-report=term -v"

    if run_test_command "$cmd" "覆盖率测试完成"; then
        print_status "覆盖率报告已生成: htmlcov/index.html"
    fi
}

# 运行代码质量检查
run_quality_check() {
    print_header "运行代码质量检查"

    # 运行 pyright
    print_status "运行 pyright 检查..."
    if $PYTHON_CMD -m pyright src/core/state_machine; then
        print_success "pyright 检查通过"
        pyright_success=0
    else
        print_error "pyright 检查失败"
        pyright_success=1
    fi

    # 运行 pylint
    print_status "运行 pylint 检查..."
    if $PYTHON_CMD -m pylint src/core/state_machine; then
        print_success "pylint 检查通过"
        pylint_success=0
    else
        print_error "pylint 检查失败"
        pylint_success=1
    fi

    if [ $pyright_success -eq 0 ] && [ $pylint_success -eq 0 ]; then
        print_success "所有质量检查通过"
        return 0
    else
        print_error "质量检查失败"
        return 1
    fi
}

# 显示帮助信息
show_help() {
    cat << EOF
${WHITE}状态机测试运行器 - Shell版本${NC}

${CYAN}基本使用:${NC}
  $0 all                    运行所有测试
  $0 basic                  运行基础功能测试
  $0 corner/corners         运行Corner Cases测试
  $0 coverage               生成覆盖率报告
  $0 quality                运行代码质量检查 (pyright & pylint)
  $0 help                   显示此帮助信息

${CYAN}精确控制:${NC}
  $0 task                   运行Task测试
  $0 tree                   运行Tree Task测试
  $0 workflow               运行Workflow测试
  $0 helpers                运行Helpers测试

${CYAN}其他选项:${NC}
  verbose      - 详细模式运行测试
  clean        - 清理测试文件

${YELLOW}示例:${NC}
  $0 all
  $0 basic
  $0 coverage
  $0 quality

EOF
}

# ===== 主程序逻辑 - 命令分发 =====

main() {
    # 显示脚本标题
    echo -e "${PURPLE}状态机测试运行器 (Shell版本)${NC}"
    echo -e "${CYAN}项目根目录: $PROJECT_ROOT${NC}"
    echo -e "${CYAN}测试文件: $ALL_TEST_FILES${NC}"
    echo

    # 检测环境
    detect_python_environment

    # 验证环境
    if ! validate_environment; then
        exit 1
    fi

    # 解析命令
    local command="${1:-help}"

    # 根据命令执行相应操作
    case "$command" in
        "all")
            run_all_tests
            ;;
        "coverage")
            run_coverage_tests
            ;;
        "quality")
            run_quality_check
            ;;
        "help")
            show_help
            ;;
        "basic")
            run_basic_tests
            ;;
        "corner"|"corners")
            run_corner_tests
            ;;
        "task")
            run_task_tests
            ;;
        "tree")
            run_tree_task_tests
            ;;
        "workflow")
            run_workflow_tests
            ;;
        "helpers")
            run_helpers_tests
            ;;
        *)
            print_error "未知命令: $command"
            echo
            show_help
            exit 1
            ;;
    esac
}

# 执行主程序
main "$@"