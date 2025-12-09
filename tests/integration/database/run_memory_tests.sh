#!/bin/bash

# 记忆模块测试运行器 - Shell版本
#
# 提供记忆模块的测试运行功能

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
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"  # tests/memory -> project_root
SQLITE_TEST_FILE="$SCRIPT_DIR/test_sqlite_memory.py"
MILVUS_TEST_FILE="$SCRIPT_DIR/test_milvus_memory.py"
ALL_TEST_FILES="$SQLITE_TEST_FILE $MILVUS_TEST_FILE"
PYTHON_CMD=""

# ===== 工具函数设计 - 通用功能封装 =====

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

command_exists() {
    command -v "$1" &> /dev/null
}

# 智能检测Python环境
detect_python_environment() {
    print_status "检测Python环境..."

    if command_exists uv; then
        PYTHON_CMD="uv run python"
        print_success "检测到uv环境: $PYTHON_CMD"
    elif command_exists python3; then
        PYTHON_CMD="python3"
        print_success "使用系统Python3: $PYTHON_CMD"
    elif command_exists python; then
        PYTHON_CMD="python"
        print_warning "使用系统Python: $PYTHON_CMD"
    else
        print_error "未找到Python环境，请安装Python或uv"
        exit 1
    fi
}

# 验证运行环境
validate_environment() {
    print_status "验证运行环境..."

    for test_file in $ALL_TEST_FILES; do
        if [ ! -f "$test_file" ]; then
            print_error "测试文件不存在: $test_file"
            exit 1
        fi
    done

    if ! $PYTHON_CMD --version &> /dev/null; then
        print_error "Python命令不可用: $PYTHON_CMD"
        exit 1
    fi

    print_success "环境验证通过"
}

# 执行测试命令
run_test_command() {
    local cmd="$1"
    local description="$2"

    print_status "执行: $cmd"

    cd "$PROJECT_ROOT"
    export PYTHONPATH="$PROJECT_ROOT"

    if eval "$cmd"; then
        print_success "$description"
        return 0
    else
        print_error "$description"
        return 1
    fi
}

# ===== 测试功能函数 =====

run_all_tests() {
    print_header "运行所有记忆测试"
    local cmd="$PYTHON_CMD -m pytest $ALL_TEST_FILES -v --tb=short"
    run_test_command "$cmd" "所有测试完成"
}

run_sqlite_tests() {
    print_header "运行SQLite记忆测试"
    local cmd="$PYTHON_CMD -m pytest $SQLITE_TEST_FILE -v --tb=short"
    run_test_command "$cmd" "SQLite测试完成"
}

run_milvus_tests() {
    print_header "运行Milvus记忆测试"
    local cmd="$PYTHON_CMD -m pytest $MILVUS_TEST_FILE -v --tb=short"
    run_test_command "$cmd" "Milvus测试完成"
}

run_coverage_tests() {
    print_header "生成覆盖率报告"
    local cmd="$PYTHON_CMD -m pytest $ALL_TEST_FILES --cov=src.memory --cov-report=html --cov-report=term -v"

    if run_test_command "$cmd" "覆盖率测试完成"; then
        print_status "覆盖率报告已生成: htmlcov/index.html"
    fi
}

run_quality_check() {
    print_header "运行代码质量检查"

    local pyright_success=0
    local pylint_success=0

    print_status "运行 pyright 检查..."
    if $PYTHON_CMD -m pyright src/memory; then
        print_success "pyright 检查通过"
    else
        print_error "pyright 检查失败"
        pyright_success=1
    fi

    print_status "运行 pylint 检查..."
    if $PYTHON_CMD -m pylint src/memory; then
        print_success "pylint 检查通过"
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

show_help() {
    cat << EOF
${WHITE}记忆模块测试运行器 - Shell版本${NC}

${CYAN}基本使用:${NC}
  $0 all                    运行所有测试
  $0 sqlite                 运行SQLite记忆测试
  $0 milvus                 运行Milvus记忆测试
  $0 coverage               生成覆盖率报告
  $0 quality                运行代码质量检查 (pyright & pylint)
  $0 help                   显示此帮助信息

${YELLOW}示例:${NC}
  $0 all
  $0 sqlite
  $0 milvus
  $0 coverage
  $0 quality

EOF
}

# ===== 主程序逻辑 =====

main() {
    echo -e "${PURPLE}记忆模块测试运行器 (Shell版本)${NC}"
    echo -e "${CYAN}项目根目录: $PROJECT_ROOT${NC}"
    echo

    detect_python_environment

    if ! validate_environment; then
        exit 1
    fi

    local command="${1:-help}"

    case "$command" in
        "all")
            run_all_tests
            ;;
        "sqlite")
            run_sqlite_tests
            ;;
        "milvus")
            run_milvus_tests
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
        *)
            print_error "未知命令: $command"
            echo
            show_help
            exit 1
            ;;
    esac
}

main "$@"
