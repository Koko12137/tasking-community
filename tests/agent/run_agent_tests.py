#!/usr/bin/env python3
"""
Agent Tests Runner (Python Version)
版本: 1.0
描述: Agent模块测试套件的跨平台运行脚本，包含环境检测、测试执行、代码质量检查
"""

import argparse
import os
import sys
import subprocess
import time
import shutil
from pathlib import Path
from typing import List, Tuple, Optional


class Colors:
    """终端颜色定义"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color


class AgentTestRunner:
    """Agent测试运行器"""

    def __init__(self):
        # 路径设置
        self.script_dir = Path(__file__).parent.absolute()
        self.project_root = self.script_dir.parent.parent
        self.agent_test_dir = self.script_dir

        # 命令配置
        self.python_cmd = None
        self.pytest_cmd = None
        self.pyright_cmd = None
        self.pylint_cmd = None

        # 运行选项
        self.verbose = False
        self.quiet = False
        self.keep_output = False
        self.no_coverage = False
        self.fast = False

    @staticmethod
    def print_color(message: str, color: str = Colors.NC) -> None:
        """打印带颜色的消息"""
        if not hasattr(AgentTestRunner, '_quiet_mode') or not AgentTestRunner._quiet_mode:
            print(f"{color}{message}{Colors.NC}")

    def print_info(self, message: str) -> None:
        """打印信息消息"""
        self.print_color(f"[INFO] {message}", Colors.BLUE)

    def print_success(self, message: str) -> None:
        """打印成功消息"""
        self.print_color(f"[SUCCESS] {message}", Colors.GREEN)

    def print_warning(self, message: str) -> None:
        """打印警告消息"""
        self.print_color(f"[WARNING] {message}", Colors.YELLOW)

    def print_error(self, message: str) -> None:
        """打印错误消息"""
        self.print_color(f"[ERROR] {message}", Colors.RED)

    def print_header(self, message: str) -> None:
        """打印标题消息"""
        self.print_color(f"=== {message} ===", Colors.BOLD + Colors.CYAN)

    def check_command(self, cmd: str) -> bool:
        """检查命令是否存在"""
        return shutil.which(cmd) is not None

    def detect_python_env(self) -> bool:
        """检测Python环境"""
        self.print_info("检测Python环境...")

        # 首先检查uv
        if self.check_command('uv'):
            try:
                # 测试uv是否工作正常
                subprocess.run(['uv', '--version'], capture_output=True, check=True)
                self.python_cmd = ['uv', 'run', 'python']
                self.pytest_cmd = ['uv', 'run', 'pytest']
                self.pyright_cmd = ['uv', 'run', 'pyright']
                self.pylint_cmd = ['uv', 'run', 'pylint']
                self.print_success("检测到uv环境")
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

        # 回退到系统Python
        if self.check_command('python3'):
            self.python_cmd = ['python3']
            self.pytest_cmd = ['python3', '-m', 'pytest']

            if self.check_command('pyright'):
                self.pyright_cmd = ['pyright']
            else:
                self.pyright_cmd = None
                self.print_warning("pyright未安装，将跳过类型检查")

            if self.check_command('pylint'):
                self.pylint_cmd = ['pylint']
            else:
                self.pylint_cmd = None
                self.print_warning("pylint未安装，将跳过代码风格检查")

            self.print_success("使用系统Python3环境")
            return True

        # 最后检查python
        if self.check_command('python'):
            self.python_cmd = ['python']
            self.pytest_cmd = ['python', '-m', 'pytest']
            self.print_success("使用系统Python环境")
            return True

        self.print_error("未找到Python环境，请安装Python 3.12+或uv")
        return False

    def validate_project_structure(self) -> bool:
        """验证项目结构"""
        self.print_info("验证项目结构...")

        required_dirs = [
            self.project_root / "src",
            self.project_root / "src" / "core",
            self.project_root / "src" / "core" / "agent",
            self.agent_test_dir
        ]

        required_files = [
            self.project_root / "pyproject.toml",
            self.project_root / "src" / "core" / "agent" / "interface.py",
            self.project_root / "src" / "core" / "agent" / "base.py",
            self.agent_test_dir / "test_base_agent.py",
            self.agent_test_dir / "test_interface.py",
            self.agent_test_dir / "test_simple.py",
            self.agent_test_dir / "test_react.py",
            self.agent_test_dir / "test_helpers.py"
        ]

        for dir_path in required_dirs:
            if not dir_path.exists():
                self.print_error(f"缺少必需目录: {dir_path}")
                return False

        for file_path in required_files:
            if not file_path.exists():
                self.print_error(f"缺少必需文件: {file_path}")
                return False

        self.print_success("项目结构验证通过")
        return True

    def install_dependencies(self) -> bool:
        """安装测试依赖"""
        self.print_info("安装测试依赖...")

        os.chdir(self.project_root)

        try:
            # 安装pytest和相关依赖
            cmd = self.python_cmd + ['-m', 'pip', 'install', 'pytest', 'pytest-cov', 'pytest-asyncio']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.print_success("依赖安装完成")
            return True
        except subprocess.CalledProcessError as e:
            self.print_error(f"依赖安装失败: {e}")
            return False

    def run_command(self, cmd: List[str], cwd: Optional[Path] = None, capture_output: bool = False) -> Tuple[bool, str]:
        """运行命令"""
        try:
            if cwd:
                result = subprocess.run(cmd, cwd=cwd, capture_output=capture_output, text=True, check=True)
            else:
                result = subprocess.run(cmd, capture_output=capture_output, text=True, check=True)
            return True, result.stdout if capture_output else ""
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            return False, error_msg

    def run_basic_tests(self) -> bool:
        """运行基础功能测试"""
        self.print_header("运行基础功能测试")

        test_files = [
            "test_base_agent.py",
            "test_interface.py",
            "test_helpers.py"
        ]

        pytest_args = []
        if self.verbose:
            pytest_args.append("-v")
        pytest_args.extend(["-x", "--tb=short"])

        for test_file in test_files:
            test_path = self.agent_test_dir / test_file
            if test_path.exists():
                self.print_info(f"运行测试: {test_file}")

                cmd = self.pytest_cmd + [test_file] + pytest_args
                success, output = self.run_command(cmd, self.agent_test_dir)

                if success:
                    self.print_success(f"测试通过: {test_file}")
                else:
                    self.print_error(f"测试失败: {test_file}")
                    if self.verbose:
                        print(output)
                    return False
            else:
                self.print_warning(f"测试文件不存在: {test_file}")

        return True

    def run_component_tests(self, component: str) -> bool:
        """运行特定组件测试"""
        self.print_header(f"运行{component}组件测试")

        test_file = f"test_{component.lower()}.py"
        test_path = self.agent_test_dir / test_file

        if not test_path.exists():
            self.print_error(f"测试文件不存在: {test_file}")
            return False

        pytest_args = []
        if self.verbose:
            pytest_args.append("-v")
        pytest_args.extend(["-x", "--tb=short"])

        self.print_info(f"运行测试: {test_file}")

        cmd = self.pytest_cmd + [test_file] + pytest_args
        success, output = self.run_command(cmd, self.agent_test_dir)

        if success:
            self.print_success(f"测试通过: {test_file}")
            return True
        else:
            self.print_error(f"测试失败: {test_file}")
            if self.verbose:
                print(output)
            return False

    def generate_coverage_report(self) -> bool:
        """生成覆盖率报告"""
        self.print_header("生成测试覆盖率报告")

        coverage_args = [
            "--cov=src.core.agent",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--cov-report=xml"
        ]

        if self.verbose:
            coverage_args.append("-v")

        self.print_info("生成覆盖率报告...")

        cmd = self.pytest_cmd + ["."] + coverage_args
        success, output = self.run_command(cmd, self.agent_test_dir)

        if success:
            self.print_success("覆盖率报告生成完成")
            if self.keep_output:
                htmlcov_path = self.agent_test_dir / "htmlcov" / "index.html"
                self.print_info(f"HTML覆盖率报告保存在: {htmlcov_path}")
            else:
                self.print_info("使用 --keep 参数保留HTML覆盖率报告")
            return True
        else:
            self.print_error("覆盖率报告生成失败")
            if self.verbose:
                print(output)
            return False

    def run_quality_checks(self) -> bool:
        """运行代码质量检查"""
        self.print_header("运行代码质量检查")

        quality_passed = True

        # Pyright类型检查
        if self.pyright_cmd:
            self.print_info("运行Pyright类型检查...")
            os.chdir(self.project_root)

            cmd = self.pyright_cmd + ["src/core/agent"]
            success, output = self.run_command(cmd, capture_output=True)

            if success:
                self.print_success("Pyright检查通过")
            else:
                self.print_error("Pyright检查失败")
                if self.verbose:
                    print(output)
                quality_passed = False
        else:
            self.print_warning("跳过Pyright检查（未安装pyright）")

        # Pylint代码风格检查
        if self.pylint_cmd:
            self.print_info("运行Pylint代码风格检查...")
            os.chdir(self.project_root)

            # 创建临时pylint配置文件
            pylint_config = """[MASTER]
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
"""

            pylintrc_path = self.project_root / ".pylintrc"
            try:
                with open(pylintrc_path, 'w') as f:
                    f.write(pylint_config)

                cmd = self.pylint_cmd + ["--rcfile", str(pylintrc_path), "src/core/agent/", "--score=yes"]
                success, output = self.run_command(cmd, capture_output=True)

                if success or "10/10" in output:  # Pylint有时会返回非零但评分是10/10
                    self.print_success("Pylint检查通过")
                else:
                    self.print_error("Pylint检查失败")
                    if self.verbose:
                        print(output)
                    quality_passed = False
            finally:
                if pylintrc_path.exists():
                    pylintrc_path.unlink()
        else:
            self.print_warning("跳过Pylint检查（未安装pylint）")

        if quality_passed:
            self.print_success("所有代码质量检查通过")
            return True
        else:
            self.print_error("代码质量检查失败")
            return False

    def cleanup(self) -> None:
        """清理临时文件"""
        if not self.keep_output:
            self.print_info("清理临时文件...")
            os.chdir(self.agent_test_dir)

            cleanup_dirs = [".pytest_cache", "htmlcov"]
            cleanup_files = ["coverage.xml", ".coverage"]

            for dir_name in cleanup_dirs:
                dir_path = self.agent_test_dir / dir_name
                if dir_path.exists():
                    shutil.rmtree(dir_path)

            for file_name in cleanup_files:
                file_path = self.agent_test_dir / file_name
                if file_path.exists():
                    file_path.unlink()

            self.print_success("清理完成")

    def run(self, command: str = "all") -> int:
        """主运行函数"""
        self.print_header("Agent模块测试套件")

        # 检测环境
        if not self.detect_python_env():
            self.print_error("环境检测失败")
            return 1

        # 验证项目结构
        if not self.validate_project_structure():
            self.print_error("项目结构验证失败")
            return 1

        # 处理安装命令
        if command == "install":
            if self.install_dependencies():
                self.print_success("依赖安装完成")
                return 0
            else:
                self.print_error("依赖安装失败")
                return 1

        start_time = time.time()
        test_passed = True

        try:
            # 执行命令
            if command == "all":
                self.print_info("运行所有Agent测试...")
                if not self.run_basic_tests():
                    test_passed = False
                if not self.run_component_tests("simple"):
                    test_passed = False
                if not self.run_component_tests("react"):
                    test_passed = False

            elif command == "basic":
                test_passed = self.run_basic_tests()

            elif command in ["interface", "simple", "react"]:
                test_passed = self.run_component_tests(command)

            elif command == "coverage":
                if not self.no_coverage:
                    test_passed = self.generate_coverage_report()
                else:
                    self.print_info("跳过覆盖率生成 (--no-coverage)")

            elif command == "quality":
                test_passed = self.run_quality_checks()

            else:
                self.print_error(f"未知命令: {command}")
                return 1

        finally:
            # 清理
            self.cleanup()

        end_time = time.time()
        duration = int(end_time - start_time)

        # 显示结果
        print()
        self.print_header("测试完成")
        print(f"总耗时: {duration}秒")

        if test_passed:
            self.print_success("所有测试通过！✅")
            return 0
        else:
            self.print_error("测试失败！❌")
            return 1


def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Agent模块测试运行脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    %(prog)s all                    # 运行所有测试
    %(prog)s basic -v               # 运行基础测试并显示详细输出
    %(prog)s coverage --keep        # 生成覆盖率报告并保留文件
    %(prog)s quality --no-coverage  # 运行质量检查但不生成覆盖率

环境要求:
    - Python 3.12+
    - uv (推荐) 或 python3/pytest

更多信息请参考: tests/agent/README.md
        """
    )

    parser.add_argument(
        "command",
        choices=["all", "basic", "interface", "simple", "react", "coverage", "quality", "install"],
        nargs="?",
        default="all",
        help="要执行的命令"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细输出模式"
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="静默模式（只显示错误）"
    )

    parser.add_argument(
        "-k", "--keep",
        action="store_true",
        help="保留测试输出文件"
    )

    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="跳过覆盖率生成"
    )

    parser.add_argument(
        "--fast",
        action="store_true",
        help="快速模式（跳过一些耗时测试）"
    )

    return parser.parse_args()


def main() -> int:
    """主函数"""
    args = parse_arguments()

    # 设置静默模式
    if args.quiet:
        AgentTestRunner._quiet_mode = True

    # 创建运行器
    runner = AgentTestRunner()
    runner.verbose = args.verbose
    runner.quiet = args.quiet
    runner.keep_output = args.keep
    runner.no_coverage = args.no_coverage
    runner.fast = args.fast

    # 运行测试
    return runner.run(args.command)


if __name__ == "__main__":
    sys.exit(main())