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

用法: $0 <命令> [子命令] [选项]

全局命令:
    all              - 运行所有测试和检查
    unit             - 运行所有单元测试
    unit <module>    - 运行指定模块的单元测试
    integration      - 运行所有集成测试
    coverage         - 生成覆盖率报告
    quality          - 运行全局代码质量检查
    quality <module> - 运行指定模块的代码质量检查
    install          - 安装测试依赖
    test <path>      - 运行指定测试路径
    help             - 显示此帮助信息

模块命令 (针对特定功能模块):
    <module> quality  - 运行指定模块的代码质量检查
    <module> unit     - 运行指定模块的单元测试
    <module> all      - 运行指定模块的质量检查 + 单元测试

支持的模块:
    agent            - Agent 智能体模块
    scheduler        - Scheduler 调度器模块
    state_machine    - StateMachine 状态机模块
    filesystem       - Filesystem 文件系统模块 (包含terminal测试)
    middleware       - Middleware 中间件模块
    database         - Database 数据库模块
    llm              - LLM 大语言模型模块
    model            - Model 模型模块

示例:
    $0 all                           # 运行完整测试套件
    $0 unit                          # 运行所有单元测试
    $0 unit filesystem               # 运行 filesystem 模块单元测试（包含terminal）
    $0 quality                        # 运行全局代码质量检查
    $0 quality filesystem            # 运行 filesystem 模块质量检查（包含terminal）
    $0 agent quality                 # 运行 agent 模块质量检查
    $0 agent unit                     # 运行 agent 模块单元测试
    $0 agent all                      # 运行 agent 模块所有检查
    $0 test tests/unit/agent/         # 运行指定测试路径

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
    local module_path=${1:-"tasking/"}
    local module_name=${2:-"全局"}
    
    print_header "🔍 运行 ${module_name} 代码质量检查"
    local success=0

    # Pyright 检查
    print_step "运行 Pyright 类型检查: $module_path"
    local pyright_cmd=""
    if [ "$(detect_environment)" = "uv" ]; then
        pyright_cmd="uv run pyright"
    elif command -v pyright >/dev/null 2>&1; then
        pyright_cmd="pyright"
    else
        print_warning "Pyright 未安装，跳过类型检查"
        pyright_cmd=""
    fi
    
    if [ -n "$pyright_cmd" ]; then
        if eval "$pyright_cmd $module_path" 2>&1; then
            print_success "Pyright 检查通过"
        else
            local pyright_exit=$?
            if [ $pyright_exit -eq 0 ]; then
                print_success "Pyright 检查通过"
            else
                print_error "Pyright 检查失败（退出码: $pyright_exit）"
                success=1
            fi
        fi
    fi

    # Pylint 检查
    print_step "运行 Pylint 代码质量检查: $module_path"
    local pylint_cmd=""
    if [ "$(detect_environment)" = "uv" ]; then
        pylint_cmd="uv run pylint"
    elif command -v pylint >/dev/null 2>&1; then
        pylint_cmd="pylint"
    else
        print_warning "Pylint 未安装，跳过代码质量检查"
        pylint_cmd=""
    fi
    
    if [ -n "$pylint_cmd" ]; then
        local pylint_output=$(eval "$pylint_cmd $module_path --score=yes" 2>&1 || true)
        if echo "$pylint_output" | grep -q "Your code has been rated at"; then
            # 提取评分
            local score=$(echo "$pylint_output" | grep "Your code has been rated at" | sed 's/.*rated at \([0-9.]*\)\/.*/\1/')
            print_message "$CYAN" "📈 代码质量评分: ${score}/10"
            
            # 检查评分是否 >= 8.0
            local score_int=$(echo "$score" | cut -d'.' -f1)
            if [ "$score_int" -ge 8 ] 2>/dev/null || [ "$(echo "$score >= 8.0" | bc 2>/dev/null)" = "1" ]; then
                print_success "Pylint 检查通过（评分 >= 8.0）"
            else
                print_warning "Pylint 检查通过但评分低于 8.0（当前: ${score}/10），建议改进"
                success=1
            fi
        else
            print_error "Pylint 检查失败"
            echo "$pylint_output"
            success=1
        fi
    fi

    return $success
}

# 运行模块单元测试
run_module_unit_tests() {
    local module_name=$1
    local test_path=$2
    
    print_header "🧪 运行 ${module_name} 模块单元测试"
    
    if [ ! -d "$test_path" ]; then
        print_error "测试路径不存在: $test_path"
        return 1
    fi

    local cmd_prefix=$(get_command_prefix)
    local test_cmd="$cmd_prefix -m pytest $test_path -v --tb=short"

    if eval "$test_cmd"; then
        print_success "${module_name} 模块单元测试通过"
        return 0
    else
        print_error "${module_name} 模块单元测试失败"
        return 1
    fi
}

# 运行模块完整测试（质量检查 + 单元测试）
run_module_all() {
    local module_name=$1
    local module_path=$2
    local test_path=$3
    
    print_header "🚀 运行 ${module_name} 模块完整测试"
    local success=0

    # 1. 质量检查
    if ! run_quality_check "$module_path" "$module_name"; then
        success=1
    fi

    # 2. 单元测试
    if ! run_module_unit_tests "$module_name" "$test_path"; then
        success=1
    fi

    if [ $success -eq 0 ]; then
        print_success "🎉 ${module_name} 模块所有检查都通过了！"
    else
        print_error "❌ ${module_name} 模块部分检查失败"
    fi

    return $success
}

# 获取模块路径和测试路径
get_module_paths() {
    local module=$1
    case "$module" in
        "agent")
            echo "tasking/core/agent/ tests/unit/agent/"
            ;;
        "scheduler")
            echo "tasking/core/scheduler/ tests/unit/scheduler/"
            ;;
        "state_machine"|"statemachine")
            echo "tasking/core/state_machine/ tests/unit/state_machine/"
            ;;
        "filesystem")
            echo "tasking/tool/filesystem.py tasking/tool/terminal.py tests/unit/terminal/"
            ;;
        "middleware")
            echo "tasking/core/middleware/ tests/unit/core/middleware/"
            ;;
        "database")
            echo "tasking/database/ tests/unit/database/"
            ;;
        "llm")
            echo "tasking/llm/ tests/unit/llm/"
            ;;
        "model")
            echo "tasking/model/ tests/unit/model/"
            ;;
        *)
            echo ""
            ;;
    esac
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
    if ! run_quality_check "tasking/" "全局"; then
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

    local command="${1:-help}"
    local subcommand="${2:-}"

    # 特殊处理：terminal命令重定向到filesystem
    if [ "$command" = "terminal" ]; then
        print_message "$YELLOW" "⚠️  terminal 测试已合并到 filesystem 模块中"
        print_message "$CYAN" "💡 请使用: $0 filesystem ${subcommand:-unit}"
        echo
        # 执行filesystem命令
        command="filesystem"
    fi

    # 处理模块命令
    case "$command" in
        "agent"|"scheduler"|"state_machine"|"statemachine"|"filesystem"|"middleware"|"database"|"llm"|"model")
            local module_name="$command"
            # 统一 state_machine 名称
            if [ "$module_name" = "statemachine" ]; then
                module_name="state_machine"
            fi
            
            local paths=$(get_module_paths "$module_name")
            if [ -z "$paths" ]; then
                print_error "未知模块: $command"
                show_help
                exit 1
            fi
            
            # 提取所有文件路径和测试路径
            local module_files=""
            local test_path=""

            # 获取所有参数
            local all_paths="$paths"
            # 最后一个参数是测试路径（目录）
            test_path=$(echo "$all_paths" | awk '{print $NF}')
            # 前面的所有参数是模块文件
            module_files=$(echo "$all_paths" | sed "s| $test_path$||")
            
            case "$subcommand" in
                "quality")
                    run_quality_check "$module_files" "$module_name"
                    ;;
                "unit")
                    run_module_unit_tests "$module_name" "$test_path"
                    ;;
                "all"|"")
                    # 如果没有子命令或子命令为 all，运行完整测试
                    run_module_all "$module_name" "$module_files" "$test_path"
                    ;;
                *)
                    print_error "未知子命令: $subcommand"
                    echo "支持的子命令: quality, unit, all"
                    exit 1
                    ;;
            esac
            ;;
        "all")
            run_all_tests
            ;;
        "unit")
            # 如果指定了模块名（如 unit terminal），运行该模块的单元测试
            if [ -n "$subcommand" ]; then
                local module_name="$subcommand"
                # 统一 state_machine 名称
                if [ "$module_name" = "statemachine" ]; then
                    module_name="state_machine"
                fi
                
                local paths=$(get_module_paths "$module_name")
                if [ -z "$paths" ]; then
                    print_error "未知模块: $subcommand"
                    echo "支持的模块: agent, scheduler, state_machine, filesystem, middleware, database, llm, model"
                    exit 1
                fi
                
                # 最后一个参数是测试路径（目录）
                local test_path=$(echo "$paths" | awk '{print $NF}')
                run_module_unit_tests "$module_name" "$test_path"
            else
                # 没有指定模块，运行所有单元测试
                run_unit_tests
            fi
            ;;
        "integration")
            run_integration_tests
            ;;
        "coverage")
            run_coverage_report
            ;;
        "quality")
            # 如果指定了模块名（如 quality terminal），运行该模块的质量检查
            if [ -n "$subcommand" ]; then
                local module_name="$subcommand"
                # 统一 state_machine 名称
                if [ "$module_name" = "statemachine" ]; then
                    module_name="state_machine"
                fi
                
                local paths=$(get_module_paths "$module_name")
                if [ -z "$paths" ]; then
                    print_error "未知模块: $subcommand"
                    echo "支持的模块: agent, scheduler, state_machine, filesystem, middleware, database, llm, model"
                    exit 1
                fi
                
                # 获取所有模块文件路径（除了最后一个测试路径）
                local all_paths="$paths"
                local test_path=$(echo "$all_paths" | awk '{print $NF}')
                local module_files=$(echo "$all_paths" | sed "s| $test_path$||")
                run_quality_check "$module_files" "$module_name"
            else
                # 没有指定模块，运行全局质量检查
                run_quality_check "tasking/" "全局"
            fi
            ;;
        "install")
            install_dependencies
            ;;
        "test")
            if [ -z "$subcommand" ]; then
                print_error "使用 'test' 命令时必须指定测试路径"
                echo "示例: $0 test tests/unit/agent/"
                exit 1
            fi
            run_specific_test "$subcommand"
            ;;
        "help"|"-h"|"--help")
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

# 错误处理
trap 'print_error "脚本执行被中断"; exit 1' INT TERM

# 执行主函数
main "$@"