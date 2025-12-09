#!/bin/bash

# 统一测试运行脚本 (Shell版本)
# 提供完整的测试套件执行，包括单元测试、集成测试、覆盖率报告和代码质量检查

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 项目路径
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEST_DIR="$PROJECT_ROOT/tests"
SRC_DIR="$PROJECT_ROOT/src"

# 打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

print_header() {
    echo
    echo "================================================================================"
    print_message "$CYAN" "$1"
    echo "================================================================================"
}

print_step() {
    print_message "$BLUE" "  • $1"
}

print_success() {
    print_message "$GREEN" "✅ $1"
}

print_error() {
    print_message "$RED" "❌ $1"
}

print_warning() {
    print_message "$YELLOW" "⚠️  $1"
}

# 检测环境
detect_environment() {
    if command -v uv >/dev/null 2>&1; then
        echo "uv"
    elif command -v python3 >/dev/null 2>&1; then
        echo "python3"
    elif command -v python >/dev/null 2>&1; then
        echo "python"
    else
        print_error "未找到可用的Python环境"
        exit 1
    fi
}

# 获取命令前缀
get_command_prefix() {
    local env=$(detect_environment)
    if [ "$env" = "uv" ]; then
        echo "uv run python"
    else
        echo "$env"
    fi
}

# 执行命令
run_command() {
    local cmd_prefix=$(get_command_prefix)
    local cmd="$cmd_prefix $1"
    print_message "$PURPLE" "执行命令: $cmd"

    if [ "$2" = "capture" ]; then
        $cmd 2>&1
    else
        $cmd
    fi
}

# 显示帮助信息
show_help() {
    cat << EOF
统一测试运行脚本

用法: $0 <命令> [选项]

命令:
    all         - 运行所有测试和检查
    unit        - 运行单元测试
    integration - 运行集成测试
    coverage    - 生成覆盖率报告
    quality     - 运行代码质量检查
    install     - 安装测试依赖
    test <path> - 运行指定测试
    help        - 显示此帮助信息

示例:
    $0 all                    # 运行完整测试套件
    $0 unit                   # 只运行单元测试
    $0 test tests/unit/agent/ # 运行agent模块测试
    $0 quality                # 只进行代码质量检查

EOF
}

# 安装测试依赖
install_dependencies() {
    print_header "📦 安装测试依赖"

    local cmd_prefix=$(get_command_prefix)
    local install_cmd="$cmd_prefix -m pip install pytest pytest-cov pytest-asyncio"

    if eval "$install_cmd" >/dev/null 2>&1; then
        print_success "依赖安装成功"
        return 0
    else
        print_error "依赖安装失败"
        return 1
    fi
}

# 运行单元测试
run_unit_tests() {
    print_header "🧪 运行单元测试"

    local cmd_prefix=$(get_command_prefix)
    local test_cmd="$cmd_prefix -m pytest tests/unit/ -v --tb=short"

    if eval "$test_cmd"; then
        print_success "单元测试通过"
        return 0
    else
        print_error "单元测试失败"
        return 1
    fi
}

# 运行集成测试
run_integration_tests() {
    print_header "🔗 运行集成测试"

    local cmd_prefix=$(get_command_prefix)
    local test_cmd="$cmd_prefix -m pytest tests/integration/ -v --tb=short"

    if eval "$test_cmd"; then
        print_success "集成测试通过"
        return 0
    else
        print_error "集成测试失败"
        return 1
    fi
}

# 生成覆盖率报告
run_coverage_report() {
    print_header "📊 生成覆盖率报告"

    local cmd_prefix=$(get_command_prefix)
    local coverage_cmd="$cmd_prefix -m pytest tests/ --cov=tasking --cov-report=term-missing --cov-report=html:htmlcov --cov-fail-under=80"

    if eval "$coverage_cmd"; then
        print_success "覆盖率报告生成成功"
        print_message "$CYAN" "HTML覆盖率报告已生成到: htmlcov/index.html"
        return 0
    else
        print_error "覆盖率不足或生成失败"
        return 1
    fi
}

# 运行代码质量检查
run_quality_check() {
    print_header "🔍 运行代码质量检查"
    local success=0

    # Pyright 检查
    print_step "运行 Pyright 类型检查"
    local cmd_prefix=$(get_command_prefix)
    if eval "$cmd_prefix -m pyright tasking/" >/dev/null 2>&1; then
        print_success "Pyright 检查通过"
    else
        print_error "Pyright 检查失败"
        success=1
    fi

    # Pylint 检查
    print_step "运行 Pylint 代码质量检查"
    local pylint_output=$(eval "$cmd_prefix -m pylint tasking/ --score=yes" 2>&1 || true)
    if echo "$pylint_output" | grep -q "Your code has been rated at"; then
        print_success "Pylint 检查通过"
        # 提取评分
        local score=$(echo "$pylint_output" | grep "Your code has been rated at" | sed 's/.*rated at \([0-9.]*\)\/.*/\1/')
        print_message "$CYAN" "📈 代码质量评分: ${score}/10"
    else
        print_error "Pylint 检查失败"
        echo "$pylint_output"
        success=1
    fi

    return $success
}

# 运行指定测试
run_specific_test() {
    local test_path=$1
    print_header "🧪 运行指定测试: $test_path"

    if [ ! -f "$test_path" ] && [ ! -d "$test_path" ]; then
        print_error "测试路径不存在: $test_path"
        return 1
    fi

    local cmd_prefix=$(get_command_prefix)
    local test_cmd="$cmd_prefix -m pytest $test_path -v --tb=short"

    if eval "$test_cmd"; then
        print_success "测试通过"
        return 0
    else
        print_error "测试失败"
        return 1
    fi
}

# 运行所有测试
run_all_tests() {
    print_header "🚀 开始运行完整测试套件"
    local success=0

    # 1. 单元测试
    if ! run_unit_tests; then
        success=1
    fi

    # 2. 集成测试
    if ! run_integration_tests; then
        success=1
    fi

    # 3. 覆盖率报告
    if ! run_coverage_report; then
        success=1
    fi

    # 4. 代码质量检查
    if ! run_quality_check; then
        success=1
    fi

    print_header "测试完成"
    if [ $success -eq 0 ]; then
        print_message "$GREEN" "🎉 所有测试和检查都通过了！"
    else
        print_message "$RED" "❌ 部分测试或检查失败，请查看上面的详细信息"
    fi

    return $success
}

# 主函数
main() {
    cd "$PROJECT_ROOT"

    case "${1:-help}" in
        "all")
            run_all_tests
            ;;
        "unit")
            run_unit_tests
            ;;
        "integration")
            run_integration_tests
            ;;
        "coverage")
            run_coverage_report
            ;;
        "quality")
            run_quality_check
            ;;
        "install")
            install_dependencies
            ;;
        "test")
            if [ -z "${2:-}" ]; then
                print_error "使用 'test' 命令时必须指定测试路径"
                echo "示例: $0 test tests/unit/agent/"
                exit 1
            fi
            run_specific_test "$2"
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            echo
            show_help
            exit 1
            ;;
    esac
}

# 错误处理
trap 'print_error "脚本执行被中断"; exit 1' INT TERM

# 执行主函数
main "$@"