#!/usr/bin/env python3
"""
统一测试运行脚本

提供完整的测试套件执行，包括单元测试、集成测试、覆盖率报告和代码质量检查
"""

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import NoReturn


class TestRunner:
    """统一测试运行器"""

    def __init__(self) -> None:
        self.project_root = Path(__file__).parent.parent
        self.test_dir = self.project_root / "tests"
        self.src_dir = self.project_root / "src"

    def detect_environment(self) -> str:
        """检测Python环境"""
        # 优先使用 uv
        if subprocess.run(["which", "uv"], capture_output=True).returncode == 0:
            return "uv"

        # 降级到 python3
        if subprocess.run(["which", "python3"], capture_output=True).returncode == 0:
            return "python3"

        # 最后尝试 python
        if subprocess.run(["which", "python"], capture_output=True).returncode == 0:
            return "python"

        raise RuntimeError("未找到可用的Python环境")

    def get_command_prefix(self) -> list[str]:
        """获取命令前缀"""
        env = self.detect_environment()
        if env == "uv":
            return ["uv", "run", "python"]
        return [env]

    def run_command(self, cmd: list[str], capture_output: bool = False) -> subprocess.CompletedProcess:
        """运行命令"""
        prefix = self.get_command_prefix()
        full_cmd = prefix + cmd

        print(f"执行命令: {' '.join(full_cmd)}")

        if capture_output:
            return subprocess.run(full_cmd, capture_output=True, text=True, cwd=self.project_root)
        else:
            return subprocess.run(full_cmd, cwd=self.project_root)

    def install_dependencies(self) -> bool:
        """安装测试依赖"""
        print("📦 安装测试依赖...")

        cmd = self.get_command_prefix() + ["-m", "pip", "install", "pytest", "pytest-cov", "pytest-asyncio"]

        try:
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ 依赖安装成功")
                return True
            else:
                print(f"❌ 依赖安装失败: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ 依赖安装异常: {e}")
            return False

    def run_unit_tests(self) -> bool:
        """运行单元测试"""
        print("\n🧪 运行单元测试...")

        cmd = [
            "-m", "pytest",
            "tests/unit/",
            "-v",
            "--tb=short"
        ]

        try:
            result = self.run_command(cmd, capture_output=True)
            if result.returncode == 0:
                print("✅ 单元测试通过")
                print(result.stdout)
                return True
            else:
                print("❌ 单元测试失败")
                print(result.stdout)
                print(result.stderr)
                return False
        except Exception as e:
            print(f"❌ 单元测试执行异常: {e}")
            return False

    def run_integration_tests(self) -> bool:
        """运行集成测试"""
        print("\n🔗 运行集成测试...")

        cmd = [
            "-m", "pytest",
            "tests/integration/",
            "-v",
            "--tb=short"
        ]

        try:
            result = self.run_command(cmd, capture_output=True)
            if result.returncode == 0:
                print("✅ 集成测试通过")
                print(result.stdout)
                return True
            else:
                print("❌ 集成测试失败")
                print(result.stdout)
                print(result.stderr)
                return False
        except Exception as e:
            print(f"❌ 集成测试执行异常: {e}")
            return False

    def run_coverage_report(self) -> bool:
        """生成覆盖率报告"""
        print("\n📊 生成覆盖率报告...")

        cmd = [
            "-m", "pytest",
            "tests/",
            "--cov=tasking",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--cov-fail-under=80"
        ]

        try:
            result = self.run_command(cmd, capture_output=True)
            if result.returncode == 0:
                print("✅ 覆盖率报告生成成功")
                print(result.stdout)
                return True
            else:
                print("❌ 覆盖率不足或生成失败")
                print(result.stdout)
                print(result.stderr)
                return False
        except Exception as e:
            print(f"❌ 覆盖率报告生成异常: {e}")
            return False

    def run_quality_check(self) -> bool:
        """运行代码质量检查"""
        print("\n🔍 运行代码质量检查...")

        # Pyright 检查
        print("  • 运行 Pyright 类型检查...")
        try:
            result = subprocess.run(
                self.get_command_prefix() + ["-m", "pyright", "tasking/"],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("    ✅ Pyright 检查通过")
            else:
                print("    ❌ Pyright 检查失败")
                print(result.stdout)
                print(result.stderr)
                return False
        except Exception as e:
            print(f"    ❌ Pyright 检查异常: {e}")
            return False

        # Pylint 检查
        print("  • 运行 Pylint 代码质量检查...")
        try:
            result = subprocess.run(
                self.get_command_prefix() + ["-m", "pylint", "tasking/", "--score=yes"],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("    ✅ Pylint 检查通过")
                # 提取评分
                if "Your code has been rated at" in result.stdout:
                    score_line = [line for line in result.stdout.split('\n')
                                if "Your code has been rated at" in line][0]
                    print(f"    📈 {score_line.strip()}")
                return True
            else:
                print("    ❌ Pylint 检查失败")
                print(result.stdout)
                print(result.stderr)
                return False
        except Exception as e:
            print(f"    ❌ Pylint 检查异常: {e}")
            return False

    def run_all_tests(self) -> bool:
        """运行所有测试"""
        print("🚀 开始运行完整测试套件...")
        print("=" * 60)

        success = True

        # 1. 单元测试
        if not self.run_unit_tests():
            success = False

        # 2. 集成测试
        if not self.run_integration_tests():
            success = False

        # 3. 覆盖率报告
        if not self.run_coverage_report():
            success = False

        # 4. 代码质量检查
        if not self.run_quality_check():
            success = False

        print("\n" + "=" * 60)
        if success:
            print("🎉 所有测试和检查都通过了！")
        else:
            print("❌ 部分测试或检查失败，请查看上面的详细信息")

        return success

    def run_specific_test(self, test_path: str) -> bool:
        """运行特定测试"""
        print(f"🧪 运行特定测试: {test_path}")

        cmd = ["-m", "pytest", test_path, "-v", "--tb=short"]

        try:
            result = self.run_command(cmd, capture_output=True)
            if result.returncode == 0:
                print("✅ 测试通过")
                print(result.stdout)
                return True
            else:
                print("❌ 测试失败")
                print(result.stdout)
                print(result.stderr)
                return False
        except Exception as e:
            print(f"❌ 测试执行异常: {e}")
            return False


def main() -> NoReturn:
    """主函数"""
    parser = argparse.ArgumentParser(description="统一测试运行脚本")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["all", "unit", "integration", "coverage", "quality", "install", "test"],
        help="要执行的命令"
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="测试路径（仅在使用 'test' 命令时有效）"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出"
    )

    args = parser.parse_args()

    runner = TestRunner()

    try:
        if not args.command or args.command == "help":
            parser.print_help()
            sys.exit(0)
        elif args.command == "install":
            success = runner.install_dependencies()
        elif args.command == "unit":
            success = runner.run_unit_tests()
        elif args.command == "integration":
            success = runner.run_integration_tests()
        elif args.command == "coverage":
            success = runner.run_coverage_report()
        elif args.command == "quality":
            success = runner.run_quality_check()
        elif args.command == "test":
            if not args.path:
                print("❌ 使用 'test' 命令时必须指定测试路径")
                sys.exit(1)
            success = runner.run_specific_test(args.path)
        elif args.command == "all":
            success = runner.run_all_tests()
        else:
            print(f"❌ 未知命令: {args.command}")
            sys.exit(1)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n⏹️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试运行器异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()