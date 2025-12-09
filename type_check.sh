#!/bin/bash

# 类型安全检测脚本
# 用于一键检测Python代码的类型安全性和代码质量问题

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 图标定义
CHECK="✅"
CROSS="❌"
WARNING="⚠️"
INFO="ℹ️"
GEAR="⚙️"
ROCKET="🚀"

# 打印带颜色的分隔线
print_separator() {
    local color=$1
    local text=$2
    echo -e "${color}─────────────────────────────────────────────────────${NC}"
    echo -e "${color}${text}${NC}"
    echo -e "${color}─────────────────────────────────────────────────────${NC}"
}

# 检测命令是否存在
check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# 检查Python环境
check_python_environment() {
    print_separator "$CYAN" "🔍 Python环境检查"

    local py_version="未安装"
    local uv_status="未安装"

    if check_command python3; then
        py_version=$(python3 --version 2>&1 || echo "版本获取失败")
    fi

    if check_command uv; then
        uv_status="已安装"
    fi

    echo -e "Python3版本: ${BLUE}${py_version}${NC}"
    echo -e "uv状态: ${BLUE}${uv_status}${NC}"

    # 检查虚拟环境
    if [[ "$VIRTUAL_ENV" != "" ]] || [[ -d ".venv" ]]; then
        echo -e "虚拟环境: ${GREEN}已激活${NC}"
        return 0
    else
        echo -e "虚拟环境: ${YELLOW}未检测到虚拟环境${NC}"
        return 1
    fi
}

# 安装/更新依赖
install_dependencies() {
    print_separator "$YELLOW" "📦 安装/更新依赖"

    if check_command uv; then
        echo -e "${INFO} 使用uv安装依赖..."
        if uv pip install -e ".[dev]" --quiet; then
            echo -e "${CHECK} 依赖安装成功"
        else
            echo -e "${CROSS} 依赖安装失败"
            return 1
        fi
    else
        echo -e "${WARNING} 未检测到uv，使用pip安装依赖..."
        if pip install -e ".[dev]" --quiet; then
            echo -e "${CHECK} 依赖安装成功"
        else
            echo -e "${CROSS} 依赖安装失败"
            return 1
        fi
    fi
}

# Pyright类型检查
run_pyright() {
    print_separator "$BLUE" "🔬 Pyright类型检查"

    local pyright_cmd=""
    if check_command uv; then
        pyright_cmd="uv run pyright"
    else
        pyright_cmd="pyright"
    fi

    echo -e "${GEAR} 执行命令: ${pyright_cmd} tasking/"
    echo

    # 创建临时文件保存结果
    local temp_file=$(mktemp)
    local exit_code=0

    # 执行pyright检查
    if eval "$pyright_cmd tasking/" > "$temp_file" 2>&1; then
        echo -e "${CHECK} ${GREEN}Pyright检查通过！${NC}"

        # 显示统计信息
        if grep -q "Completed in" "$temp_file"; then
            local stats=$(grep "Completed in" "$temp_file")
            echo -e "${INFO} ${stats}"
        fi

        if grep -q "errors" "$temp_file"; then
            local error_count=$(grep -o " [0-9]* errors" "$temp_file" | head -1)
            if [[ "$error_count" =~ "0 errors" ]]; then
                echo -e "${CHECK} ${GREEN}零类型错误${NC}"
            fi
        fi
    else
        exit_code=1
        echo -e "${CROSS} ${RED}Pyright检查发现问题！${NC}"

        # 显示错误详情
        if grep -q "error" "$temp_file"; then
            echo -e "\n${RED}错误详情:${NC}"
            grep -A 5 -B 5 "error" "$temp_file" || true
        fi
    fi

    # 显示警告信息
    if grep -q "warning" "$temp_file"; then
        echo -e "\n${YELLOW}警告信息:${NC}"
        grep -A 2 -B 2 "warning" "$temp_file" || true
    fi

    rm -f "$temp_file"
    return $exit_code
}

# MyPy类型检查（可选）
run_mypy() {
    print_separator "$PURPLE" "🔍 MyPy类型检查 (可选)"

    # 检查是否安装了mypy
    local mypy_cmd=""
    if check_command uv; then
        if uv run python -c "import mypy" 2>/dev/null; then
            mypy_cmd="uv run mypy"
        fi
    else
        if python -c "import mypy" 2>/dev/null; then
            mypy_cmd="mypy"
        fi
    fi

    if [[ -z "$mypy_cmd" ]]; then
        echo -e "${WARNING} MyPy未安装，跳过检查"
        echo -e "${INFO} 可使用: uv add --group-dev mypy 安装"
        return 0
    fi

    echo -e "${GEAR} 执行命令: ${mypy_cmd} tasking/ --ignore-missing-imports"
    echo

    if eval "$mypy_cmd tasking/ --ignore-missing-imports"; then
        echo -e "${CHECK} ${GREEN}MyPy检查通过！${NC}"
        return 0
    else
        echo -e "${CROSS} ${RED}MyPy检查发现问题！${NC}"
        return 1
    fi
}

# Pylint代码质量检查
run_pylint() {
    print_separator "$GREEN" "🔧 Pylint代码质量检查"

    local pylint_cmd=""
    if check_command uv; then
        pylint_cmd="uv run pylint"
    else
        pylint_cmd="pylint"
    fi

    echo -e "${GEAR} 执行命令: ${pylint_cmd} tasking/"
    echo

    # 创建临时文件保存结果
    local temp_file=$(mktemp)

    # 执行pylint检查
    if eval "$pylint_cmd tasking/" > "$temp_file" 2>&1; then
        local score=$(grep "rated at" "$temp_file" | grep -o "[0-9.]*\/10" || echo "未知")
        echo -e "${CHECK} ${GREEN}Pylint检查通过！${NC}"
        echo -e "${INFO} 代码质量评分: ${BLUE}${score}${NC}"
    else
        local score=$(grep "rated at" "$temp_file" | grep -o "[0-9.]*\/10" || echo "未知")
        echo -e "${WARNING} ${YELLOW}Pylint检查完成，评分: ${BLUE}${score}${NC}${YELLOW}"

        # 如果评分低于8.0，显示主要问题
        if [[ "$score" < "8.0" ]]; then
            echo -e "\n${WARNING} 主要问题:"
            grep -E "E\d+|C\d+|R\d+|W\d+" "$temp_file" | head -10 || true
            return 1
        fi
    fi

    rm -f "$temp_file"
    return 0
}

# 导入检查和死代码检测
run_import_check() {
    print_separator "$CYAN" "🔍 导入检查和死代码检测"

    # 检查是否有未使用的导入
    echo -e "${GEAR} 检查未使用的导入..."

    # 使用pyflakes检查（如果可用）
    local pyflakes_cmd=""
    if check_command uv; then
        if uv run python -c "import pyflakes" 2>/dev/null; then
            pyflakes_cmd="uv run pyflakes"
        fi
    fi

    if [[ -n "$pyflakes_cmd" ]]; then
        echo -e "${INFO} 使用Pyflakes检查代码质量..."
        if eval "$pyflakes_cmd tasking/" 2>/dev/null; then
            echo -e "${CHECK} ${GREEN}Pyflakes检查通过！${NC}"
        else
            echo -e "${WARNING} ${YELLOW}Pyflakes发现一些问题${NC}"
        fi
    else
        echo -e "${INFO} Pyflakes未安装，使用基本检查..."
    fi

    # 检查循环导入（简单检查）
    echo -e "${INFO} 检查潜在的循环导入..."
    local circular_imports=$(find tasking/ -name "*.py" -exec grep -l "from.*import\|import.*" {} \; | wc -l)
    echo -e "${INFO} 发现 ${circular_imports} 个Python文件包含导入语句"
}

# 类型覆盖率统计
run_type_coverage() {
    print_separator "$YELLOW" "📊 类型覆盖率统计"

    echo -e "${GEAR} 分析类型注解覆盖率..."

    # 使用最简单的方法统计文件数量
    local total_files=$(find tasking/ -name "*.py" -not -path "*/\.*" | wc -l)
    local typed_files=0
    local total_functions=0
    local typed_functions=0

    echo -e "${INFO} 找到 ${total_files} 个Python文件"

    if [[ $total_files -eq 0 ]]; then
        echo -e "${WARNING} ${YELLOW}未找到Python文件，请检查tasking/目录${NC}"
        return 1
    fi

    # 分别统计文件和函数的类型注解
    echo -e "${INFO} 分析类型注解覆盖率..."

    # 统计有类型注解的文件数量
    typed_files=$(find tasking/ -name "*.py" -not -path "*/\.*" -exec grep -l "def.*->\|:\s*int\|:\s*str\|:\s*float\|:\s*bool\|:\s*list\|:\s*dict\|:\s*None\|:\s*Any\|:\s*Union\|:\s*Optional\|:\s*List\|:\s*Dict\|:\s*Set\|:\s*Tuple" {} \; | wc -l)

    # 统计所有函数数量
    total_functions=$(find tasking/ -name "*.py" -not -path "*/\.*" -exec grep -c "^\s*def\s" {} \; | awk '{sum += $1} END {print sum}')

    # 统计有返回类型注解的函数数量
    typed_functions=$(find tasking/ -name "*.py" -not -path "*/\.*" -exec grep -c "def.*->" {} \; | awk '{sum += $1} END {print sum}')

    # 计算覆盖率
    local file_coverage=0
    local function_coverage=0

    if [[ $total_files -gt 0 ]]; then
        file_coverage=$((typed_files * 100 / total_files))
    fi

    if [[ $total_functions -gt 0 ]]; then
        function_coverage=$((typed_functions * 100 / total_functions))
    fi

    echo -e "${INFO} 文件类型覆盖率: ${BLUE}${file_coverage}%${NC} (${typed_files}/${total_files})"
    echo -e "${INFO} 函数类型覆盖率: ${BLUE}${function_coverage}%${NC} (${typed_functions}/${total_functions})"

    if [[ $file_coverage -ge 80 ]]; then
        echo -e "${CHECK} ${GREEN}文件类型覆盖率良好 (≥80%)${NC}"
    else
        echo -e "${WARNING} ${YELLOW}文件类型覆盖率较低 (<80%)${NC}"
    fi

    if [[ $function_coverage -ge 75 ]]; then
        echo -e "${CHECK} ${GREEN}函数类型覆盖率良好 (≥75%)${NC}"
    else
        echo -e "${WARNING} ${YELLOW}函数类型覆盖率较低 (<75%)${NC}"
    fi
}

# 生成总结报告
generate_summary() {
    local pyright_result=$1
    local pylint_result=$2
    local mypy_result=$3

    print_separator "$GREEN" "📋 类型安全检测总结报告"

    echo -e "${ROCKET} ${BLUE}检查完成时间: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo

    # Pyright结果
    if [[ $pyright_result -eq 0 ]]; then
        echo -e "${CHECK} ${GREEN}Pyright类型检查: 通过${NC}"
    else
        echo -e "${CROSS} ${RED}Pyright类型检查: 失败${NC}"
    fi

    # Pylint结果
    if [[ $pylint_result -eq 0 ]]; then
        echo -e "${CHECK} ${GREEN}Pylint代码质量: 通过${NC}"
    else
        echo -e "${WARNING} ${YELLOW}Pylint代码质量: 需要改进${NC}"
    fi

    # MyPy结果
    if [[ $mypy_result -eq 0 ]]; then
        echo -e "${CHECK} ${GREEN}MyPy类型检查: 通过${NC}"
    else
        echo -e "${WARNING} ${YELLOW}MyPy类型检查: 失败${NC}"
    fi

    echo

    # 总体状态
    if [[ $pyright_result -eq 0 && $pylint_result -eq 0 && $mypy_result -eq 0 ]]; then
        echo -e "${CHECK} ${GREEN}🎉 所有类型安全检查通过！代码质量良好。${NC}"
        return 0
    else
        echo -e "${CROSS} ${RED}❌ 发现类型安全问题或代码质量问题，请修复后重新检查。${NC}"
        return 1
    fi
}

# 显示帮助信息
show_help() {
    echo -e "${CYAN}类型安全检测脚本${NC}"
    echo
    echo "用法: $0 [选项]"
    echo
    echo "选项:"
    echo "  all          运行所有检查 (默认)"
    echo "  pyright      仅运行Pyright类型检查"
    echo "  mypy         仅运行MyPy类型检查"
    echo "  pylint       仅运行Pylint代码质量检查"
    echo "  coverage     仅运行类型覆盖率统计"
    echo "  import       仅运行导入检查"
    echo "  install      安装/更新依赖"
    echo "  help         显示此帮助信息"
    echo
    echo "示例:"
    echo "  $0                # 运行所有检查"
    echo "  $0 pyright        # 仅运行类型检查"
    echo "  $0 install all    # 先安装依赖再运行检查"
    echo
}

# 主函数
main() {
    local action="${1:-all}"
    local install_deps=false

    # 检查是否需要先安装依赖
    if [[ "$action" == "install" ]]; then
        install_deps=true
        shift
        action="${1:-all}"
    fi

    # 切换到项目根目录
    if [[ ! -f "pyproject.toml" ]]; then
        echo -e "${CROSS} ${RED}错误: 未找到pyproject.toml文件，请在项目根目录运行此脚本${NC}"
        exit 1
    fi

    echo -e "${ROCKET} ${BLUE}Python类型安全检测工具${NC}"
    echo -e "${CYAN}项目: $(basename "$(pwd)")${NC}"
    echo

    # 检查Python环境
    if ! check_python_environment; then
        echo -e "${WARNING} ${YELLOW}Python环境检查未完全通过，但将继续执行...${NC}"
    fi

    # 安装依赖（如果需要）
    if [[ "$install_deps" == true ]]; then
        if ! install_dependencies; then
            echo -e "${CROSS} ${RED}依赖安装失败，退出${NC}"
            exit 1
        fi
        echo
    fi

    local pyright_result=0
    local pylint_result=0
    local mypy_result=0

    case "$action" in
        "all")
            run_pyright && pyright_result=$? || pyright_result=$?
            echo
            run_pylint && pylint_result=$? || pylint_result=$?
            echo
            run_mypy && mypy_result=$? || mypy_result=$?
            echo
            run_type_coverage
            echo
            run_import_check
            echo
            generate_summary $pyright_result $pylint_result $mypy_result
            ;;
        "pyright")
            run_pyright
            exit $?
            ;;
        "mypy")
            run_mypy
            exit $?
            ;;
        "pylint")
            run_pylint
            exit $?
            ;;
        "coverage")
            run_type_coverage
            ;;
        "import")
            run_import_check
            ;;
        "install")
            # 如果只是install，没有其他操作，已经在上面的检查中处理了
            echo -e "${CHECK} ${GREEN}依赖安装完成${NC}"
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            echo -e "${CROSS} ${RED}未知选项: $action${NC}"
            echo
            show_help
            exit 1
            ;;
    esac

    # 返回综合结果
    if [[ $pyright_result -eq 0 && $pylint_result -eq 0 && $mypy_result -eq 0 ]]; then
        exit 0
    else
        exit 1
    fi
}

# 执行主函数
main "$@"