#!/usr/bin/env python3
"""
状态机测试运行器 - Python版本（修复版）

这是一个功能完整的测试运行脚本，用于运行状态机相关的所有测试。
"""

import sys
import os
import subprocess
import argparse
import time
from pathlib import Path
from typing import Optional, List


class Colors:
    """终端颜色定义"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    CYAN = '\033[0;36m'
    WHITE = '\033[1;37m'
    NC = '\033[0m'  # No Color


class TestRunner:
    """测试运行器类"""

    def __init__(self):
        self.script_dir = Path(__file__).parent
        self.project_root = self.script_dir.parent.parent  # tests/state_machine -> project_root
        # 所有测试文件
        self.basic_test_file = self.script_dir / "test_state_machine.py"
        self.corner_test_file = self.script_dir / "test_corner_cases.py"
        self.task_test_file = self.script_dir / "test_task.py"
        self.tree_task_test_file = self.script_dir / "test_tree_task.py"
        self.workflow_test_file = self.script_dir / "test_workflow.py"
        self.helpers_test_file = self.script_dir / "test_helpers.py"
        self.all_test_files = [
            self.basic_test_file,
            self.corner_test_file,
            self.task_test_file,
            self.tree_task_test_file,
            self.workflow_test_file,
            self.helpers_test_file
        ]
        self.python_cmd = self._find_python_command()
        self.pip_cmd = self._find_pip_command()

    def _find_python_command(self) -> str:
        """智能检测Python命令"""
        commands = [
            "uv run python",  # 优先使用uv
            "python3",        # 标准python3
            "python",         # 备用python
        ]

        for cmd in commands:
            if self._test_command(cmd):
                print(f"{Colors.GREEN}✓ 使用Python命令: {cmd}{Colors.NC}")
                return cmd

        print(f"{Colors.YELLOW}⚠ 未找到合适的Python命令，使用默认: python3{Colors.NC}")
        return "python3"

    def _find_pip_command(self) -> str:
        """智能检测pip命令"""
        commands = [
            "uv pip",  # uv的pip
            "pip3",    # 标准pip3
            "pip",     # 备用pip
        ]

        for cmd in commands:
            if self._test_command(cmd.replace("pip", "pip --version")):
                print(f"{Colors.GREEN}✓ 使用包管理命令: {cmd}{Colors.NC}")
                return cmd

        return "pip3"

    def _test_command(self, cmd: str) -> bool:
        """测试命令是否可用"""
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                timeout=5,
                text=True
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _validate_environment(self) -> bool:
        """验证运行环境"""
        print(f"{Colors.BLUE}正在验证运行环境...{Colors.NC}")

        # 检查测试文件是否存在
        for test_file in self.all_test_files:
            if not test_file.exists():
                print(f"{Colors.RED}❌ 测试文件不存在: {test_file}{Colors.NC}")
                return False

        # 检查Python环境
        if not self._test_command(f"{self.python_cmd} --version"):
            print(f"{Colors.RED}❌ Python环境不可用: {self.python_cmd}{Colors.NC}")
            return False

        print(f"{Colors.GREEN}✓ 环境验证通过{Colors.NC}")
        return True

    def _install_dependencies(self) -> bool:
        """安装测试依赖"""
        print(f"{Colors.BLUE}正在检查测试依赖...{Colors.NC}")

        dependencies = [
            "pytest",
            "pytest-cov",
            "pytest-mock",
            "pytest-asyncio",
            "pydantic",
        ]

        failed_deps = []

        for dep in dependencies:
            if not self._test_command(f'{self.python_cmd} -c "import {dep.split("-")[0]}"'):
                print(f"{Colors.YELLOW}⚠ 需要安装依赖: {dep}{Colors.NC}")
                install_cmd = f"{self.pip_cmd} install {dep}"
                print(f"{Colors.CYAN}执行: {install_cmd}{Colors.NC}")

                try:
                    result = subprocess.run(
                        install_cmd.split(),
                        capture_output=True,
                        text=True,
                        timeout=120
                    )
                    if result.returncode == 0:
                        print(f"{Colors.GREEN}✓ {dep} 安装成功{Colors.NC}")
                    else:
                        print(f"{Colors.RED}❌ {dep} 安装失败: {result.stderr}{Colors.NC}")
                        failed_deps.append(dep)
                except subprocess.TimeoutExpired:
                    print(f"{Colors.RED}❌ {dep} 安装超时{Colors.NC}")
                    failed_deps.append(dep)
            else:
                print(f"{Colors.GREEN}✓ 依赖已存在: {dep}{Colors.NC}")

        if failed_deps:
            print(f"{Colors.RED}❌ 以下依赖安装失败: {', '.join(failed_deps)}{Colors.NC}")
            return False

        print(f"{Colors.GREEN}✓ 所有依赖检查完成{Colors.NC}")
        return True

    def _run_command(self, cmd: str, cwd: Optional[Path] = None) -> bool:
        """执行命令的通用方法"""
        print(f"{Colors.CYAN}执行: {cmd}{Colors.NC}")

        try:
            result = subprocess.run(
                cmd.split(),
                cwd=cwd or self.project_root,
                text=True,
                timeout=300  # 5分钟超时
            )

            if result.returncode == 0:
                print(f"{Colors.GREEN}✓ 命令执行成功{Colors.NC}")
                return True
            else:
                print(f"{Colors.RED}❌ 命令执行失败，返回码: {result.returncode}{Colors.NC}")
                if result.stderr:
                    print(f"{Colors.RED}错误信息: {result.stderr}{Colors.NC}")
                return False

        except subprocess.TimeoutExpired:
            print(f"{Colors.RED}❌ 命令执行超时{Colors.NC}")
            return False
        except Exception as e:
            print(f"{Colors.RED}❌ 命令执行异常: {e}{Colors.NC}")
            return False

    def run_all_tests(self) -> bool:
        """运行所有测试"""
        print(f"{Colors.WHITE}=== 运行所有测试 (包含所有新增测试) ==={Colors.NC}")

        cmd = f"{self.python_cmd} -m pytest {' '.join(map(str, self.all_test_files))} -v"
        return self._run_command(cmd)

    def run_basic_tests(self) -> bool:
        """运行基础功能测试"""
        print(f"{Colors.WHITE}=== 运行基础功能测试 ==={Colors.NC}")
        cmd = f"{self.python_cmd} -m pytest {self.basic_test_file} -v"
        return self._run_command(cmd)

    def run_corner_tests(self) -> bool:
        """运行Corner Cases测试"""
        print(f"{Colors.WHITE}=== 运行Corner Cases测试 ==={Colors.NC}")
        cmd = f"{self.python_cmd} -m pytest {self.corner_test_file} -v"
        return self._run_command(cmd)

    def run_task_tests(self) -> bool:
        """运行Task测试"""
        print(f"{Colors.WHITE}=== 运行Task测试 ==={Colors.NC}")
        cmd = f"{self.python_cmd} -m pytest {self.task_test_file} -v"
        return self._run_command(cmd)

    def run_tree_task_tests(self) -> bool:
        """运行Tree Task测试"""
        print(f"{Colors.WHITE}=== 运行Tree Task测试 ==={Colors.NC}")
        cmd = f"{self.python_cmd} -m pytest {self.tree_task_test_file} -v"
        return self._run_command(cmd)

    def run_workflow_tests(self) -> bool:
        """运行Workflow测试"""
        print(f"{Colors.WHITE}=== 运行Workflow测试 ==={Colors.NC}")
        cmd = f"{self.python_cmd} -m pytest {self.workflow_test_file} -v"
        return self._run_command(cmd)

    def run_helpers_tests(self) -> bool:
        """运行Helpers测试"""
        print(f"{Colors.WHITE}=== 运行Helpers测试 ==={Colors.NC}")
        cmd = f"{self.python_cmd} -m pytest {self.helpers_test_file} -v"
        return self._run_command(cmd)

    def run_coverage(self) -> bool:
        """生成覆盖率报告"""
        print(f"{Colors.WHITE}=== 生成覆盖率报告 ==={Colors.NC}")

        cmd = f"{self.python_cmd} -m pytest {' '.join(map(str, self.all_test_files))} --cov=src.state_machine --cov-report=html --cov-report=term"
        return self._run_command(cmd)

    def run_quality_check(self) -> bool:
        """运行代码质量检查 - pyright 和 pylint"""
        print(f"{Colors.WHITE}=== 运行代码质量检查 ==={Colors.NC}")

        # 运行 pyright
        print(f"{Colors.CYAN}运行 pyright 检查...{Colors.NC}")
        pyright_success = self._run_command(f"{self.python_cmd} -m pyright src/state_machine")

        # 运行 pylint
        print(f"{Colors.CYAN}运行 pylint 检查...{Colors.NC}")
        pylint_success = self._run_command(f"{self.python_cmd} -m pylint src/state_machine")

        if pyright_success and pylint_success:
            print(f"{Colors.GREEN}✓ 所有质量检查通过{Colors.NC}")
            return True
        else:
            print(f"{Colors.RED}❌ 质量检查失败{Colors.NC}")
            return False

    def run_single_test(self, test_name: str) -> bool:
        """运行单个测试"""
        print(f"{Colors.WHITE}=== 运行单个测试: {test_name} ==={Colors.NC}")

        # 智能匹配测试名称
        if test_name.startswith("Test"):
            cmd = f"{self.python_cmd} -m pytest {self.basic_test_file}::{test_name} -v"
        else:
            cmd = f"{self.python_cmd} -m pytest {' '.join(map(str, self.all_test_files))} -k {test_name} -v"

        return self._run_command(cmd)

    def run_specific_category(self, category: str) -> bool:
        """运行特定类别的测试"""
        print(f"{Colors.WHITE}=== 运行测试类别: {category} ==={Colors.NC}")

        # 预定义的测试类别
        categories = {
            "base": "TestBaseStateMachine",
            "task": "TestBaseTask",
            "tree": "TestBaseTreeTaskNode",
            "builder": "TestStateMachineBuilder",
            "integration": "TestIntegration"
        }

        if category in categories:
            return self.run_single_test(categories[category])
        else:
            print(f"{Colors.YELLOW}⚠ 未知的测试类别: {category}{Colors.NC}")
            print(f"{Colors.CYAN}可用类别: {', '.join(categories.keys())}{Colors.NC}")
            return False

    def run_verbose(self) -> bool:
        """详细模式运行测试"""
        print(f"{Colors.WHITE}=== 详细模式测试 ==={Colors.NC}")

        cmd = f"{self.python_cmd} -m pytest {' '.join(map(str, self.all_test_files))} -vv -s"
        return self._run_command(cmd)

    def install_deps(self) -> bool:
        """安装依赖"""
        print(f"{Colors.WHITE}=== 安装测试依赖 ==={Colors.NC}")
        return self._install_dependencies()

    def show_help(self) -> None:
        """显示帮助信息"""
        help_text = f"""
{Colors.WHITE}状态机测试运行器 - Python版本{Colors.NC}

{Colors.CYAN}基本使用:{Colors.NC}
  python run_state_machine_tests.py all                    运行所有测试
  python run_state_machine_tests.py basic                  运行基础功能测试
  python run_state_machine_tests.py corner/corners         运行Corner Cases测试
  python run_state_machine_tests.py coverage               生成覆盖率报告
  python run_state_machine_tests.py quality                运行代码质量检查 (pyright & pylint)
  python run_state_machine_tests.py install                安装测试依赖
  python run_state_machine_tests.py help                   显示此帮助信息

{Colors.CYAN}精确控制:{Colors.NC}
  python run_state_machine_tests.py single [test_name]     运行单个测试
  python run_state_machine_tests.py [category]             运行特定类别测试

{Colors.CYAN}可用测试类别:{Colors.NC}
  basic         - 基础功能测试 (test_state_machine.py)
  corner        - Corner Cases测试 (test_corner_cases.py)
  task          - 任务测试 (test_task.py)
  tree          - 树形任务测试 (test_tree_task.py)
  workflow      - 工作流测试 (test_workflow.py)
  helpers       - 测试辅助函数 (test_helpers.py)

{Colors.CYAN}其他选项:{Colors.NC}
  verbose       - 详细模式运行测试
  clean         - 清理测试文件

{Colors.YELLOW}示例:{Colors.NC}
  python run_state_machine_tests.py all
  python run_state_machine_tests.py single TestBaseStateMachine
  python run_state_machine_tests.py task
  python run_state_machine_tests.py coverage
  python run_state_machine_tests.py quality
"""
        print(help_text)

    def clean_files(self) -> bool:
        """清理测试文件"""
        print(f"{Colors.WHITE}=== 清理测试文件 ==={Colors.NC}")

        files_to_clean = [
            ".coverage",
            "htmlcov/",
            ".pytest_cache/",
            "__pycache__/",
            "*.pyc",
            "*.pyo"
        ]

        cleaned_count = 0
        for pattern in files_to_clean:
            if pattern.endswith("/"):
                # 目录清理
                dir_path = self.project_root / pattern.rstrip("/")
                if dir_path.exists():
                    import shutil
                    try:
                        shutil.rmtree(dir_path)
                        print(f"{Colors.GREEN}✓ 清理目录: {dir_path}{Colors.NC}")
                        cleaned_count += 1
                    except Exception as e:
                        print(f"{Colors.YELLOW}⚠ 清理目录失败 {dir_path}: {e}{Colors.NC}")
            else:
                # 文件清理
                for file_path in self.project_root.glob(pattern):
                    try:
                        file_path.unlink()
                        print(f"{Colors.GREEN}✓ 清理文件: {file_path}{Colors.NC}")
                        cleaned_count += 1
                    except Exception as e:
                        print(f"{Colors.YELLOW}⚠ 清理文件失败 {file_path}: {e}{Colors.NC}")

        print(f"{Colors.GREEN}✓ 清理完成，共处理 {cleaned_count} 个文件/目录{Colors.NC}")
        return True

    def run(self, args: argparse.Namespace) -> bool:
        """主运行方法 - 命令分发"""
        print(f"{Colors.PURPLE}状态机测试运行器 (Python版本){Colors.NC}")
        print(f"{Colors.CYAN}项目根目录: {self.project_root}{Colors.NC}")
        print(f"{Colors.CYAN}测试文件: {len(self.all_test_files)} 个文件{Colors.NC}")
        print()

        # 环境验证
        if not self._validate_environment():
            return False

        # 命令分发
        if args.command == "all":
            return self.run_all_tests()
        elif args.command == "basic":
            return self.run_basic_tests()
        elif args.command in ["corner", "corners"]:
            return self.run_corner_tests()
        elif args.command == "task":
            return self.run_task_tests()
        elif args.command == "tree":
            return self.run_tree_task_tests()
        elif args.command == "workflow":
            return self.run_workflow_tests()
        elif args.command == "helpers":
            return self.run_helpers_tests()
        elif args.command == "coverage":
            return self.run_coverage()
        elif args.command == "quality":
            return self.run_quality_check()
        elif args.command == "install":
            return self.install_deps()
        elif args.command == "help":
            self.show_help()
            return True
        elif args.command == "single":
            if not args.test_name:
                print(f"{Colors.RED}❌ 使用single命令时必须指定测试名称{Colors.NC}")
                return False
            return self.run_single_test(args.test_name)
        elif args.command == "verbose":
            return self.run_verbose()
        elif args.command == "clean":
            return self.clean_files()
        elif args.command in ["base"]:
            return self.run_specific_category(args.command)
        else:
            print(f"{Colors.RED}❌ 未知命令: {args.command}{Colors.NC}")
            self.show_help()
            return False


def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="状态机测试运行器 (Python版本)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_state_machine_tests.py all
  python run_state_machine_tests.py single TestBaseStateMachine
  python run_state_machine_tests.py coverage
  python run_state_machine_tests.py task
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 基本命令
    all_parser = subparsers.add_parser("all", help="运行所有测试 (包含所有新增测试)")
    basic_parser = subparsers.add_parser("basic", help="运行基础功能测试")
    corner_parser = subparsers.add_parser("corner", help="运行Corner Cases测试")
    corners_parser = subparsers.add_parser("corners", help="运行Corner Cases测试")
    subparsers.add_parser("coverage", help="生成覆盖率报告")
    subparsers.add_parser("quality", help="运行代码质量检查 (pyright & pylint)")
    subparsers.add_parser("install", help="安装测试依赖")
    subparsers.add_parser("help", help="显示帮助信息")
    subparsers.add_parser("verbose", help="详细模式运行测试")
    subparsers.add_parser("clean", help="清理测试文件")

    # 单个测试命令
    single_parser = subparsers.add_parser("single", help="运行单个测试")
    single_parser.add_argument("test_name", help="测试名称或类名")

    # 类别测试命令
    subparsers.add_parser("task", help="运行task测试")
    subparsers.add_parser("tree", help="运行tree测试")
    subparsers.add_parser("workflow", help="运行workflow测试")
    subparsers.add_parser("helpers", help="运行helpers测试")
    subparsers.add_parser("base", help="运行base测试")

    return parser.parse_args()


def handle_interrupt(signum, frame):
    """键盘中断处理"""
    print(f"\n{Colors.YELLOW}⚠ 测试被用户中断{Colors.NC}")
    sys.exit(130)


def main():
    """主函数"""
    import signal

    # 注册中断处理
    signal.signal(signal.SIGINT, handle_interrupt)

    try:
        # 解析参数
        args = parse_arguments()

        # 如果没有提供命令，显示帮助
        if not args.command:
            print(f"{Colors.YELLOW}⚠ 未指定命令，显示帮助信息{Colors.NC}")
            args.command = "help"

        # 创建运行器并执行
        runner = TestRunner()
        success = runner.run(args)

        # 退出
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠ 程序被中断{Colors.NC}")
        sys.exit(130)
    except Exception as e:
        print(f"{Colors.RED}❌ 程序异常: {e}{Colors.NC}")
        sys.exit(1)


if __name__ == "__main__":
    main()