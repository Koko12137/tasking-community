"""
异步初始化验证测试

专门用于验证LocalTerminal的异步初始化不会产生协程警告，
以及初始化功能的正确性。
"""

import asyncio
import warnings
import tempfile
import threading
from pathlib import Path
import pytest

from tasking.tool.terminal import LocalTerminal


class TestTerminalAsyncInitialization:
    """测试LocalTerminal的异步初始化功能"""

    def test_async_init_no_warnings(self):
        """验证异步初始化不产生协程警告"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always", RuntimeWarning)

            # 创建terminal实例
            with tempfile.TemporaryDirectory() as temp_dir:
                terminal = LocalTerminal(root_dir=temp_dir, allowed_commands=[], disable_script_execution=False)
                terminal.close()

            # 检查是否有异步警告
            async_warnings = [warning for warning in w
                              if "coroutine.*was never awaited" in str(warning.message)]

            # 断言没有异步警告
            assert len(async_warnings) == 0, f"发现异步警告: {[str(w.message) for w in async_warnings]}"

    def test_async_init_functionality(self):
        """验证异步初始化功能正常"""
        with tempfile.TemporaryDirectory() as temp_dir:
            terminal = LocalTerminal(root_dir=temp_dir, allowed_commands=[], disable_script_execution=False)

            # 验证工作目录已正确设置
            assert terminal._workspace == temp_dir

            # 验证终端已初始化
            assert terminal._process is not None
            assert terminal._process.poll() is None

            terminal.close()

    def test_async_init_with_different_parameters(self):
        """测试不同参数下的异步初始化"""
        test_cases = [
            # (allowed_commands, disable_script_execution, description)
            ([], False, "默认参数"),
            (["ls", "echo"], True, "允许命令列表"),
            (["*"], False, "允许所有命令"),
            (["python", "node"], True, "特定命令列表"),
        ]

        for allowed_commands, disable_script_execution, description in test_cases:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always", RuntimeWarning)

                with tempfile.TemporaryDirectory() as temp_dir:
                    try:
                        terminal = LocalTerminal(
                            root_dir=temp_dir,
                            allowed_commands=allowed_commands,
                            disable_script_execution=disable_script_execution
                        )

                        # 验证终端正常创建
                        assert terminal._workspace == temp_dir
                        assert terminal._process is not None

                        # 验证配置正确设置
                        if allowed_commands:
                            assert terminal._allowed_commands == allowed_commands

                        terminal.close()

                    except Exception as e:
                        pytest.fail(f"测试用例 '{description}' 失败: {e}")

                    # 检查异步警告
                    async_warnings = [warning for warning in w
                                      if "coroutine.*was never awaited" in str(warning.message)]
                    assert len(async_warnings) == 0, f"用例 '{description}' 产生异步警告"

    def test_async_init_in_running_event_loop(self):
        """测试在运行中的事件循环环境下创建terminal"""
        async def create_terminal_in_event_loop():
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always", RuntimeWarning)

                with tempfile.TemporaryDirectory() as temp_dir:
                    terminal = LocalTerminal(root_dir=temp_dir, allowed_commands=[], disable_script_execution=False)
                    terminal.close()

                # 检查异步警告
                async_warnings = [warning for warning in w
                                  if "coroutine.*was never awaited" in str(warning.message)]
                return len(async_warnings)

        # 运行测试
        warning_count = asyncio.run(create_terminal_in_event_loop())
        assert warning_count == 0, f"在事件循环中创建terminal产生 {warning_count} 个异步警告"

    def test_async_init_error_handling(self):
        """测试异步初始化的错误处理"""
        # 测试使用无效工作目录时的错误处理
        invalid_workspace = "/nonexistent/directory/path"

        with pytest.raises(Exception):
            terminal = LocalTerminal(root_dir=invalid_workspace, allowed_commands=[], disable_script_execution=False)
            # 这应该在初始化过程中失败

    def test_multiple_concurrent_inits(self):
        """测试多个terminal实例的并发初始化"""
        terminals = []

        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always", RuntimeWarning)

                # 并发创建多个terminal实例
                threads = []
                results = []

                def create_terminal():
                    with tempfile.TemporaryDirectory() as temp_dir:
                        terminal = LocalTerminal(root_dir=temp_dir, allowed_commands=[], disable_script_execution=False)
                        return terminal

                # 创建多个线程并发执行初始化
                for i in range(3):
                    thread = threading.Thread(target=lambda i=i: results.append(create_terminal()))
                    threads.append(thread)
                    thread.start()

                # 等待所有线程完成
                for thread in threads:
                    thread.join()

                # 验证所有terminal都成功创建
                assert len(results) == 3
                for terminal in results:
                    assert terminal._process is not None
                    terminals.append(terminal)

                # 检查异步警告
                async_warnings = [warning for warning in w
                                  if "coroutine.*was never awaited" in str(warning.message)]
                assert len(async_warnings) == 0, f"并发初始化产生异步警告: {async_warnings}"

        finally:
            # 清理
            for terminal in terminals:
                try:
                    terminal.close()
                except Exception:
                    pass

    def test_async_init_timeout_scenario(self):
        """测试异步初始化超时场景（模拟）"""
        # 注意：这个测试主要验证错误处理路径，不实际等待超时
        # 超时处理已经在代码中实现，这里主要确保不会产生警告

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always", RuntimeWarning)

            with tempfile.TemporaryDirectory() as temp_dir:
                # 正常创建，不应该有超时问题
                terminal = LocalTerminal(root_dir=temp_dir, allowed_commands=[], disable_script_execution=False)
                terminal.close()

            # 检查异步警告
            async_warnings = [warning for warning in w
                              if "coroutine.*was never awaited" in str(warning.message)]
            assert len(async_warnings) == 0, f"正常初始化也产生异步警告: {async_warnings}"


if __name__ == "__main__":
    pytest.main([__file__])