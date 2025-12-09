#!/bin/bash

# Agent Tests Runner Script
# 版本: 1.0
# 描述: Agent模块测试套件的完整运行脚本，包含环境检测、测试执行、代码质量检查

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 脚本信息
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGENT_TEST_DIR="$SCRIPT_DIR"

# 打印带颜色的消息
print_info() {
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
    echo -e "${BOLD}${CYAN}=== $1 ===${NC}"
}

# 显示帮助信息
show_help() {
    cat << EOF
Agent模块测试运行脚本

用法: $0 [COMMAND] [OPTIONS]

命令:
    all             运行所有Agent测试（默认）
    basic           运行基础功能测试
    interface       运行接口测试
    react           运行ReAct Agent测试 [原Simple]
    reflect         运行Reflect Agent测试 [原ReAct]
    coverage        生成测试覆盖率报告
    quality         运行代码质量检查
    install         安装测试依赖
    help            显示此帮助信息

选项:
    -v, --verbose   详细输出模式
    -q, --quiet     静默模式（只显示错误）
    -k, --keep      保留测试输出文件
    --no-coverage   跳过覆盖率生成
    --fast          快速模式（跳过一些耗时测试）

示例:
    $0 all                    # 运行所有测试
    $0 basic -v               # 运行基础测试并显示详细输出
    $0 coverage --keep        # 生成覆盖率报告并保留文件
    $0 quality --no-coverage  # 运行质量检查但不生成覆盖率

环境要求:
    - Python 3.12+
    - uv (推荐) 或 python3/pytest

更多信息请参考: tests/agent/README.md
EOF
}

# 检查命令是否存在
check_command() {
    if command -v "$1" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 检测和验证Python环境
detect_python_env() {
    print_info "检测Python环境..."

    # 首先检查uv
    if check_command uv; then
        PYTHON_CMD="uv run python"
        PYTEST_CMD="uv run pytest"
        PYRIGHT_CMD="uv run pyright"
        PYLINT_CMD="uv run pylint"
        print_success "检测到uv环境"
        return 0
    fi

    # 回退到系统Python
    if check_command python3; then
        PYTHON_CMD="python3"
        PYTEST_CMD="python3 -m pytest"
        if check_command pyright; then
            PYRIGHT_CMD="pyright"
        else
            PYRIGHT_CMD=""
            print_warning "pyright未安装，将跳过类型检查"
        fi
        if check_command pylint; then
            PYLINT_CMD="pylint"
        else
            PYLINT_CMD=""
            print_warning "pylint未安装，将跳过代码风格检查"
        fi
        print_success "使用系统Python3环境"
        return 0
    fi

    # 最后检查python
    if check_command python; then
        PYTHON_CMD="python"
        PYTEST_CMD="python -m pytest"
        print_success "使用系统Python环境"
        return 0
    fi

    print_error "未找到Python环境，请安装Python 3.12+或uv"
    return 1
}

# 验证项目结构
validate_project_structure() {
    print_info "验证项目结构..."

    # 检查关键目录和文件
    local required_dirs=(
        "$PROJECT_ROOT/src"
        "$PROJECT_ROOT/src/core"
        "$PROJECT_ROOT/src/core/agent"
        "$AGENT_TEST_DIR"
    )

    local required_files=(
        "$PROJECT_ROOT/pyproject.toml"
        "$PROJECT_ROOT/src/core/agent/interface.py"
        "$PROJECT_ROOT/src/core/agent/base.py"
        "$AGENT_TEST_DIR/test_base_agent.py"
        "$AGENT_TEST_DIR/test_interface.py"
        "$AGENT_TEST_DIR/test_react.py"
        "$AGENT_TEST_DIR/test_reflect.py"
        "$AGENT_TEST_DIR/test_helpers.py"
    )

    for dir in "${required_dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            print_error "缺少必需目录: $dir"
            return 1
        fi
    done

    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            print_error "缺少必需文件: $file"
            return 1
        fi
    done

    print_success "项目结构验证通过"
    return 0
}

# 安装测试依赖
install_dependencies() {
    print_info "安装测试依赖..."

    cd "$PROJECT_ROOT"

    if [[ "$PYTHON_CMD" == "uv run python" ]]; then
        if $PYTHON_CMD -m pip install pytest pytest-cov pytest-asyncio; then
            print_success "依赖安装完成 (uv)"
        else
            print_error "依赖安装失败 (uv)"
            return 1
        fi
    else
        if $PYTHON_CMD -m pip install pytest pytest-cov pytest-asyncio; then
            print_success "依赖安装完成"
        else
            print_error "依赖安装失败"
            return 1
        fi
    fi

    return 0
}

# 运行基础功能测试
run_basic_tests() {
    print_header "运行基础功能测试"

    local test_files=(
        "test_base_agent.py"
        "test_interface.py"
    )

    local pytest_args=()

    if [[ "$VERBOSE" == "true" ]]; then
        pytest_args+=("-v")
    fi

    pytest_args+=("-x" "--tb=short")

    for test_file in "${test_files[@]}"; do
        if [[ -f "$AGENT_TEST_DIR/$test_file" ]]; then
            print_info "运行测试: $test_file"
            cd "$AGENT_TEST_DIR"

            if $PYTEST_CMD "$test_file" "${pytest_args[@]}"; then
                print_success "测试通过: $test_file"
            else
                print_error "测试失败: $test_file"
                return 1
            fi
        else
            print_warning "测试文件不存在: $test_file"
        fi
    done

    return 0
}

# 运行特定组件测试
run_component_tests() {
    local component="$1"
    print_header "运行$component组件测试"

    local test_file="test_${component,,}.py"

    if [[ ! -f "$AGENT_TEST_DIR/$test_file" ]]; then
        print_error "测试文件不存在: $test_file"
        return 1
    fi

    cd "$AGENT_TEST_DIR"

    local pytest_args=()
    if [[ "$VERBOSE" == "true" ]]; then
        pytest_args+=("-v")
    fi
    pytest_args+=("-x" "--tb=short")

    print_info "运行测试: $test_file"
    if $PYTEST_CMD "$test_file" "${pytest_args[@]}"; then
        print_success "测试通过: $test_file"
        return 0
    else
        print_error "测试失败: $test_file"
        return 1
    fi
}

# 生成覆盖率报告
generate_coverage_report() {
    print_header "生成测试覆盖率报告"

    cd "$AGENT_TEST_DIR"

    local coverage_args=(
        "--cov=src.core.agent"
        "--cov-report=term-missing"
        "--cov-report=html:htmlcov"
        "--cov-report=xml"
    )

    if [[ "$VERBOSE" == "true" ]]; then
        coverage_args+=("-v")
    fi

    print_info "生成覆盖率报告..."
    if $PYTEST_CMD . "${coverage_args[@]}"; then
        print_success "覆盖率报告生成完成"
        if [[ "$KEEP_OUTPUT" == "true" ]]; then
            print_info "HTML覆盖率报告保存在: $AGENT_TEST_DIR/htmlcov/index.html"
        else
            print_info "使用 --keep 参数保留HTML覆盖率报告"
        fi
        return 0
    else
        print_error "覆盖率报告生成失败"
        return 1
    fi
}

# 运行代码质量检查
run_quality_checks() {
    print_header "运行代码质量检查"

    local quality_passed=true

    # Pyright类型检查
    if [[ -n "$PYRIGHT_CMD" ]]; then
        print_info "运行Pyright类型检查..."
        cd "$PROJECT_ROOT"

        if $PYRIGHT_CMD src/core/agent; then
            print_success "Pyright检查通过"
        else
            print_error "Pyright检查失败"
            quality_passed=false
        fi
    else
        print_warning "跳过Pyright检查（未安装pyright）"
    fi

    # Pylint代码风格检查
    if [[ -n "$PYLINT_CMD" ]]; then
        print_info "运行Pylint代码风格检查..."
        cd "$PROJECT_ROOT"

        # 创建临时pylint配置文件
        cat > .pylintrc << EOF
[MASTER]
load-plugins=pylint.extensions.no_self_use

[FORMAT]
max-line-length=88
indent-string='    '

[BASIC]
good-names=i,j,k,ex,Run,_

[TYPECHECK]
ignored-modules=cv2

[MISCELLANEOUS]
notes=FIXME,XXX,TODO

[VARIABLES]
init-import=no
dummy-variables-rgx=_+$|dummy

[SIMILARITIES]
min-similarity-lines=4
ignore-comments=yes
ignore-docstrings=yes
ignore-imports=no

[DESIGN]
max-args=7
max-locals=15
max-returns=6
max-branchs=12
max-statements=50
max-parents=7
max-attributes=7
min-public-methods=2
max-public-methods=20
max-bool-expr=5
EOF

        if $PYLINT_CMD --rcfile=.pylintrc src/core/agent/ --score=yes; then
            print_success "Pylint检查通过"
            rm -f .pylintrc
        else
            print_error "Pylint检查失败"
            rm -f .pylintrc
            quality_passed=false
        fi
    else
        print_warning "跳过Pylint检查（未安装pylint）"
    fi

    if [[ "$quality_passed" == "true" ]]; then
        print_success "所有代码质量检查通过"
        return 0
    else
        print_error "代码质量检查失败"
        return 1
    fi
}

# 清理临时文件
cleanup() {
    if [[ "$KEEP_OUTPUT" != "true" ]]; then
        print_info "清理临时文件..."
        cd "$AGENT_TEST_DIR"
        rm -rf .pytest_cache htmlcov coverage.xml .coverage
        print_success "清理完成"
    fi
}

# 主函数
main() {
    local command="all"
    local verbose=false
    local quiet=false
    local keep_output=false
    local no_coverage=false
    local fast=false

    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            all|basic|interface|react|reflect|coverage|quality|install|help)
                command="$1"
                shift
                ;;
            -v|--verbose)
                verbose=true
                shift
                ;;
            -q|--quiet)
                quiet=true
                shift
                ;;
            -k|--keep)
                keep_output=true
                shift
                ;;
            --no-coverage)
                no_coverage=true
                shift
                ;;
            --fast)
                fast=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                print_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # 设置全局变量
    VERBOSE="$verbose"
    KEEP_OUTPUT="$keep_output"

    # 静默模式处理
    if [[ "$quiet" == "true" ]]; then
        exec 1>/dev/null
        print_info() { echo -e "${BLUE}[INFO]${NC} $1" >&2; }
        print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1" >&2; }
        print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1" >&2; }
        print_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
    fi

    print_header "Agent模块测试套件"

    # 检查帮助命令
    if [[ "$command" == "help" ]]; then
        show_help
        exit 0
    fi

    # 检测环境
    if ! detect_python_env; then
        print_error "环境检测失败"
        exit 1
    fi

    # 验证项目结构
    if ! validate_project_structure; then
        print_error "项目结构验证失败"
        exit 1
    fi

    # 安装依赖（如果需要）
    if [[ "$command" == "install" ]]; then
        if install_dependencies; then
            print_success "依赖安装完成"
            exit 0
        else
            print_error "依赖安装失败"
            exit 1
        fi
    fi

    local start_time=$(date +%s)
    local test_passed=true

    # 执行命令
    case "$command" in
        "all")
            print_info "运行所有Agent测试..."
            if ! run_basic_tests; then
                test_passed=false
            fi
            if ! run_component_tests "react"; then
                test_passed=false
            fi
            if ! run_component_tests "reflect"; then
                test_passed=false
            fi
            ;;
        "basic")
            run_basic_tests || test_passed=false
            ;;
        "interface")
            run_component_tests "interface" || test_passed=false
            ;;
        "react")
            run_component_tests "react" || test_passed=false
            ;;
        "reflect")
            run_component_tests "reflect" || test_passed=false
            ;;
        "coverage")
            if [[ "$no_coverage" != "true" ]]; then
                generate_coverage_report || test_passed=false
            else
                print_info "跳过覆盖率生成 (--no-coverage)"
            fi
            ;;
        "quality")
            run_quality_checks || test_passed=false
            ;;
        *)
            print_error "未知命令: $command"
            show_help
            exit 1
            ;;
    esac

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # 清理
    cleanup

    # 显示结果
    echo
    print_header "测试完成"
    echo "总耗时: ${duration}秒"

    if [[ "$test_passed" == "true" ]]; then
        print_success "所有测试通过！✅"
        exit 0
    else
        print_error "测试失败！❌"
        exit 1
    fi
}

# 捕获中断信号
trap cleanup EXIT

# 运行主函数
main "$@"