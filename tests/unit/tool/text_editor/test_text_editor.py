"""
文本编辑器单元测试

测试新的文本编辑器架构，包括：
1. LocalTextEditor 基础功能测试
2. 文件存在/不存在情况下的操作测试
3. 内存编辑和异步IO功能测试
"""

import pytest
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch

from tasking.tool.text_editor import LocalTextEditor, ITextEditor
from tasking.tool.filesystem import IFileSystem, LocalFileSystem
from tasking.model.filesystem import EditOperation
from tasking.tool.terminal import ITerminal, LocalTerminal


class MockTerminal(ITerminal):
    """模拟终端实现，用于测试"""

    def __init__(self, workspace: str = "/tmp/test"):
        self.workspace = workspace
        self.current_dir = workspace
        self.allowed_commands = ["echo", "sed", "cat", "rm", "mkdir", "wc"]
        self.script_execution_disabled = True
        self.process = None
        self._id = "mock_terminal"

    def get_workspace(self) -> str:
        return self.workspace

    def get_current_dir(self) -> str:
        return self.current_dir

    def get_allowed_commands(self) -> list[str]:
        return self.allowed_commands

    def is_script_execution_disabled(self) -> bool:
        return self.script_execution_disabled

    def get_id(self) -> str:
        return self._id

    def is_running(self) -> bool:
        return True

    async def run_command(self, command: str, allow_by_human: bool = False) -> str:
        """模拟命令执行"""
        # 简单的命令模拟
        if command.startswith("echo"):
            # 提取echo的内容，注意保持原有的引号格式
            if ">>" in command:
                # 重定向的echo命令
                parts = command.split(">>")
                echo_part = parts[0]
                content = echo_part[4:].strip().strip("'\"")
                return content + "\n"
            else:
                content = command[4:].strip().strip("'\"")
                return content + "\n"
        elif command.startswith("cat"):
            # 模拟cat命令
            return "file content\n"
        elif command.startswith("wc -l"):
            # 模拟行数统计
            return "10\n"
        elif "sed" in command:
            # 模拟sed命令
            return ""
        elif command.startswith("rm"):
            # 模拟删除命令
            return ""
        else:
            return f"Executed: {command}"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def cd_to_workspace(self) -> None:
        self.current_dir = self.workspace

    def check_path(self, path: str) -> tuple[str, str]:
        """解析文件路径并进行鉴权：返回（绝对路径，相对于 workspace 的相对路径）"""
        return self.resolve_path(path)

    def resolve_path(self, path: str) -> tuple[str, str]:
        """解析文件路径并进行鉴权"""
        import os
        if not path:
            raise ValueError("文件路径不能为空")

        # 规范化路径
        normalized_path = os.path.normpath(path)

        # 解析绝对路径
        if os.path.isabs(normalized_path):
            file_abs = os.path.normpath(normalized_path)
        else:
            file_abs = os.path.normpath(os.path.join(self.current_dir, normalized_path))

        # 确保路径是绝对路径
        if not os.path.isabs(file_abs):
            file_abs = os.path.abspath(file_abs)

        # 再次规范化
        file_abs = os.path.normpath(file_abs)

        # 校验路径是否在 workspace 内
        workspace_abs = os.path.normpath(os.path.abspath(self.workspace))
        
        try:
            common_path = os.path.commonpath([workspace_abs, file_abs])
            if common_path != workspace_abs:
                raise RuntimeError(f"文件路径超出 workspace 范围：{file_abs}")
        except ValueError:
            raise RuntimeError(f"文件路径无效或超出 workspace 范围：{file_abs}")

        # 双重验证
        if not file_abs.startswith(workspace_abs):
            raise RuntimeError(f"文件路径超出 workspace 范围：{file_abs}")

        # 计算相对路径
        file_rel = os.path.relpath(file_abs, workspace_abs)
        
        # 防止相对路径包含 `..`
        if '..' in file_rel.split(os.sep):
            raise RuntimeError(f"检测到不安全的相对路径：{file_rel}")

        return file_abs, file_rel

    async def check_command(self, command: str) -> tuple[bool, str]:
        return True, "Command allowed"

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def acquire(self) -> None:
        pass

    async def release(self) -> None:
        pass

    async def write_process(self, data: str) -> None:
        pass

    async def read_process(self) -> str:
        return ""


class MockFileSystem:
    """Mock file system for testing"""

    def __init__(self, terminal: ITerminal):
        self._terminal = terminal
        self._workspace = terminal.get_workspace()
        self._existing_files = {"existing.txt", "test.py", "existing_test.txt", "existing_module.py"}
        # 模拟文件内容
        self._file_contents: dict[str, str] = {
            "existing_test.txt": "line1\nline2\nline3\nline4\nline5\nline6\n",
            "existing_module.py": "import sys\n\ndef old_function():\n    pass\n\nclass MyClass:\n    pass\n\ndef another_function():\n    return False\n",
        }

    def get_terminal(self) -> ITerminal:
        return self._terminal

    def file_exists(self, file_path: str) -> bool:
        # Simple simulation: files starting with "new_" don't exist
        return not file_path.startswith("new_")

    async def open_file(self, file_path: str, file_type: str, encoding: str) -> str:
        """模拟打开文件"""
        if not self.file_exists(file_path):
            raise FileNotFoundError(f"文件不存在：{file_path}")
        # 返回模拟的文件内容
        return self._file_contents.get(file_path, "default content\n")

    async def new_file(self, file_path: str, file_type: str, content: str, encoding: str) -> str:
        # Mock new file creation
        # 保存文件内容以便后续读取
        self._file_contents[file_path] = content
        return f"文件创建成功: {file_path}"


class MockTextEditor(LocalTextEditor):
    """用于测试的模拟文本编辑器"""

    def __init__(self, mock_filesystem):
        # Call parent constructor properly
        super().__init__(mock_filesystem)

    def file_exists(self, file_path: str) -> bool:
        # 简单模拟：假设以 "new_" 开头的文件不存在，其他都存在
        return not file_path.startswith("new_")

    # Override edit_file to use mock implementation
    async def edit_file(self, file_path: str, operations: list[EditOperation]) -> str:
        """模拟编辑文件实现"""
        file_exists = self.file_exists(file_path)
        
        # 获取编辑前的文件内容
        old_lines: list[str] = []
        if file_exists:
            try:
                old_file = await self._file_system.open_file(file_path, "text", "utf-8")
                if isinstance(old_file, bytes):
                    old_file = old_file.decode('utf-8')
                old_lines = old_file.splitlines(keepends=True)
                if not old_lines or (len(old_lines) == 1 and not old_lines[0].endswith('\n')):
                    if old_lines:
                        old_lines[-1] = old_lines[-1] + '\n'
                    else:
                        old_lines = ['\n']
            except Exception:
                pass
        
        # 在内存中应用所有编辑操作
        new_lines = self._apply_operations_in_memory(old_lines, operations, file_exists)
        
        # 写入文件
        content = ''.join(new_lines)
        return await self._file_system.new_file(file_path, "text", content, "utf-8")


class TestBaseTextEditor:
    """基础文本编辑器测试"""

    @pytest.fixture
    def mock_terminal(self):
        return MockTerminal()

    @pytest.fixture
    def text_editor(self, mock_terminal):
        mock_filesystem = MockFileSystem(mock_terminal)
        return MockTextEditor(mock_filesystem)

    @pytest.mark.asyncio
    async def test_edit_new_file(self, text_editor):
        """测试编辑新文件"""
        operations = [
            EditOperation(line=0, op="insert", content="First line"),
            EditOperation(line=-1, op="insert", content="Second line")
        ]

        result = await text_editor.edit_file("new_test.txt", operations)

        # Mock result should indicate successful file creation
        assert "文件创建成功: new_test.txt" in result

    @pytest.mark.asyncio
    async def test_edit_existing_file(self, text_editor):
        """测试编辑存在文件"""
        operations = [
            EditOperation(line=1, op="insert", content="New line at start"),
            EditOperation(line=5, op="delete", content=""),
            EditOperation(line=3, op="modify", content="Modified line")
        ]

        result = await text_editor.edit_file("existing_test.txt", operations)

        # 验证命令执行
        assert result is not None

    def test_validate_operations_for_new_file(self, text_editor):
        """测试新文件操作验证"""
        # 合法的insert操作
        valid_ops = [
            EditOperation(line=0, op="insert", content="Content"),
            EditOperation(line=1, op="insert", content="Content"),
            EditOperation(line=-1, op="insert", content="Content")
        ]

        # 不应该抛出异常
        text_editor._validate_operations(valid_ops, False)

        # 非法的delete操作
        invalid_ops = [EditOperation(line=1, op="delete", content="")]

        with pytest.raises(ValueError, match="文件不存在时只允许insert操作"):
            text_editor._validate_operations(invalid_ops, False)

        # 非法的行号
        invalid_line_ops = [EditOperation(line=5, op="insert", content="Content")]

        with pytest.raises(ValueError, match="新建文件只支持行号 0、1 或 -1"):
            text_editor._validate_operations(invalid_line_ops, False)


class TestLocalFileSystemRefactored:
    """重构后的文件系统测试"""

    @pytest.fixture
    def mock_terminal(self):
        return MockTerminal()

    @pytest.fixture
    def filesystem(self, mock_terminal):
        # Mock terminal needs proper workspace for LocalFileSystem
        mock_terminal.workspace = "/tmp/test"
        return LocalFileSystem(terminal_instance=mock_terminal)

    def test_file_exists(self, filesystem):
        """测试文件存在性检查"""
        # 这个测试需要实际的文件系统，这里只是示例
        assert isinstance(filesystem.file_exists("some_file.txt"), bool)

    
    def test_file_path_resolution(self, filesystem):
        """测试文件路径解析"""
        # 测试相对路径
        file_abs, file_rel = filesystem._terminal.check_path("test.txt")
        assert file_abs.startswith(filesystem._workspace)
        assert file_rel == "test.txt"

    def test_search_params_validation(self, filesystem):
        """测试搜索参数验证"""
        from tasking.model import SearchParams, SearchPattern, FileFilter

        # 合法参数
        valid_params = SearchParams(
            content_pattern=SearchPattern(pattern="test"),
            search_paths=["."]
        )
        filesystem._validate_search_params(valid_params)  # 不应该抛出异常

        # 非法参数：空搜索模式
        invalid_params = SearchParams(
            content_pattern=SearchPattern(pattern=""),
            search_paths=["."]
        )
        with pytest.raises(ValueError, match="搜索模式不能为空"):
            filesystem._validate_search_params(invalid_params)

    def test_find_command_building(self, filesystem):
        """测试find命令构建"""
        from tasking.model import SearchParams, SearchPattern, FileFilter

        params = SearchParams(
            content_pattern=SearchPattern(pattern="test"),
            file_filter=FileFilter(name_patterns=["*.py"], extensions=["py", "js"]),
            search_paths=["src", "tests"]
        )

        resolved_paths = [
            ("/tmp/test/src", "src"),
            ("/tmp/test/tests", "tests")
        ]

        cmd = filesystem._build_find_command(params, resolved_paths)

        # Check that the command contains the right elements
        assert "find" in cmd
        assert "-type f" in cmd
        # Note: shlex.quote adds quotes to filenames
        assert "'*.py'" in cmd or "*.py" in cmd

    def test_grep_command_building(self, filesystem):
        """测试grep命令构建"""
        from tasking.model import SearchParams, SearchPattern, FileFilter, OutputFormat

        params = SearchParams(
            content_pattern=SearchPattern(
                pattern="test.*pattern",
                is_regex=True,
                case_sensitive=False
            ),
            output_format=OutputFormat(
                context_lines=3,
                show_line_numbers=True,
                show_filename=True
            )
        )

        cmd = filesystem._build_grep_command(params)

        assert "grep" in cmd
        assert "-E" in cmd  # regex
        assert "-i" in cmd  # case insensitive
        assert "-C 3" in cmd  # context lines
        assert "-n" in cmd  # line numbers
        assert "-H" in cmd  # filename
        assert "test.*pattern" in cmd


# 集成测试：测试整个编辑流程
class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_complete_edit_workflow(self):
        """测试完整的编辑工作流程"""
        mock_terminal = MockTerminal()
        mock_terminal.workspace = "/tmp/test"
        mock_filesystem = MockFileSystem(mock_terminal)
        text_editor = MockTextEditor(mock_filesystem)

        # 模拟编辑一个不存在的文件
        operations = [
            EditOperation(line=0, op="insert", content="#!/usr/bin/env python3"),
            EditOperation(line=-1, op="insert", content='print("Hello World")')
        ]

        result = await text_editor.edit_file("new_script.py", operations)

        # 验证结果
        assert "文件创建成功: new_script.py" in result

    @pytest.mark.asyncio
    async def test_complex_edit_operations(self):
        """测试复杂的编辑操作"""
        mock_terminal = MockTerminal()
        mock_terminal.workspace = "/tmp/test"

        # 模拟编辑一个存在的文件 - 使用MockTextEditor来测试
        mock_filesystem = MockFileSystem(mock_terminal)
        mock_editor = MockTextEditor(mock_filesystem)
        operations = [
            EditOperation(line=1, op="insert", content="import os"),
            EditOperation(line=5, op="delete", content=""),
            EditOperation(line=3, op="modify", content="def new_function():"),
            EditOperation(line=10, op="insert", content="return True")
        ]

        result = await mock_editor.edit_file("existing_module.py", operations)

        # 验证命令执行（具体结果取决于mock的实现）
        assert result is not None


class TestDiffOutput:
    """专门测试diff输出功能的测试类"""

    @pytest.mark.asyncio
    async def test_diff_output_for_new_file(self):
        """测试新建文件时的diff输出"""
        mock_terminal = MockTerminal()
        mock_terminal.workspace = "/tmp/test"

        # 创建一个支持实际文件操作的文件系统
        with tempfile.TemporaryDirectory() as temp_dir:
            # 使用真实的LocalTerminal
            real_terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(real_terminal)
            editor = LocalTextEditor(filesystem)

            test_file = os.path.join(temp_dir, "new_test.txt")
            operations = [
                EditOperation(line=1, op="insert", content="第一行内容"),
                EditOperation(line=-1, op="insert", content="第二行内容")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出格式（使用新的diff_to_text格式）
            assert "diff --git" in result
            assert f"a/{test_file}" in result
            assert f"b/{test_file}" in result
            assert "---" in result
            assert "+++" in result
            # 新格式：使用 "行号 | 内容" 格式
            assert "+" in result  # 应该包含插入标记
            assert "第一行内容" in result
            assert "第二行内容" in result

    @pytest.mark.asyncio
    async def test_diff_output_for_modify_operation(self):
        """测试修改操作的diff输出"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建一个初始文件
            test_file = os.path.join(temp_dir, "modify_test.txt")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("原始第一行\n原始第二行\n原始第三行\n")

            # 设置编辑器
            real_terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(real_terminal)
            editor = LocalTextEditor(filesystem)

            # 修改第二行
            operations = [
                EditOperation(line=2, op="modify", content="修改后的第二行")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出（使用新的diff_to_text格式，包含上下文）
            assert "diff --git" in result
            assert "-" in result  # 删除标记
            assert "+" in result  # 插入标记
            assert "原始第二行" in result
            assert "修改后的第二行" in result
            # 验证包含上下文行（以空格开头）
            assert any(line.startswith(" ") and "|" in line for line in result.split("\n") if line.strip())

    @pytest.mark.asyncio
    async def test_diff_output_for_delete_operation(self):
        """测试删除操作的diff输出"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建一个初始文件
            test_file = os.path.join(temp_dir, "delete_test.txt")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("第一行\n要删除的第二行\n第三行\n")

            # 设置编辑器
            real_terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(real_terminal)
            editor = LocalTextEditor(filesystem)

            # 删除第二行
            operations = [
                EditOperation(line=2, op="delete", content="")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出（使用新的diff_to_text格式，包含上下文）
            assert "diff --git" in result
            assert "-" in result  # 删除标记
            assert "要删除的第二行" in result
            # 验证包含上下文行
            assert any(line.startswith(" ") and "|" in line for line in result.split("\n") if line.strip())

    @pytest.mark.asyncio
    async def test_diff_output_for_insert_operation(self):
        """测试插入操作的diff输出"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建一个初始文件
            test_file = os.path.join(temp_dir, "insert_test.txt")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("第一行\n第三行\n")

            # 设置编辑器
            real_terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(real_terminal)
            editor = LocalTextEditor(filesystem)

            # 在第二行插入新行
            operations = [
                EditOperation(line=2, op="insert", content="插入的新行")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出（使用新的diff_to_text格式，包含上下文）
            assert "diff --git" in result
            assert "+" in result  # 插入标记
            assert "插入的新行" in result
            # 验证包含上下文行
            assert any(line.startswith(" ") and "|" in line for line in result.split("\n") if line.strip())

    @pytest.mark.asyncio
    async def test_diff_output_multiple_operations(self):
        """测试多个操作的diff输出"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建一个初始文件
            test_file = os.path.join(temp_dir, "multi_test.txt")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("第一行\n第二行\n第三行\n")

            # 设置编辑器
            real_terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(real_terminal)
            editor = LocalTextEditor(filesystem)

            # 执行多个操作
            operations = [
                EditOperation(line=1, op="modify", content="修改后的第一行"),
                EditOperation(line=3, op="delete", content=""),
                EditOperation(line=2, op="insert", content="插入的新第二行")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证所有操作的diff输出都存在（使用新的diff_to_text格式）
            assert "diff --git" in result

            # 验证修改操作
            assert "-" in result
            assert "+" in result
            assert "第一行" in result or "修改后的第一行" in result

            # 验证插入操作
            assert "插入的新第二行" in result

            # 验证删除操作
            assert "第三行" in result or "-" in result

    @pytest.mark.asyncio
    async def test_diff_output_empty_file_operations(self):
        """测试空文件操作的diff输出"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建一个空文件
            test_file = os.path.join(temp_dir, "empty_test.txt")
            with open(test_file, 'w', encoding='utf-8') as f:
                pass  # 创建空文件

            # 设置编辑器
            real_terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(real_terminal)
            editor = LocalTextEditor(filesystem)

            # 向空文件添加内容
            operations = [
                EditOperation(line=1, op="insert", content="空文件的第一行")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出（使用新的diff_to_text格式）
            assert "diff --git" in result
            assert "+" in result  # 插入标记
            assert "空文件的第一行" in result

    @pytest.mark.asyncio
    async def test_get_lines_content_method(self):
        """测试获取文件指定行号内容的方法"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建测试文件
            test_file = os.path.join(temp_dir, "line_test.txt")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("第一行\n第二行\n第三行\n第四行\n第五行\n")

            # 设置编辑器
            real_terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(real_terminal)
            editor = LocalTextEditor(filesystem)

            # 测试获取指定行号内容
            lines_content = await editor._get_lines_content(test_file, [1, 3, 5])

            assert lines_content[1] == "第一行"
            assert lines_content[3] == "第三行"
            assert lines_content[5] == "第五行"

            # 测试获取超出范围的行号
            lines_content = await editor._get_lines_content(test_file, [10])
            assert lines_content[10] == ""

    def test_format_diff_output_method(self):
        """测试diff输出格式化方法"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "format_test.txt")

            # 设置编辑器
            real_terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(real_terminal)
            editor = LocalTextEditor(filesystem)

            # 创建测试文件内容
            old_lines = ["原始内容\n"]
            new_lines = ["修改后的内容\n"]

            # 测试格式化输出（使用新的方法签名）
            diff_output = editor._format_diff_output(
                test_file, old_lines, new_lines, k=3
            )

            assert "diff --git" in diff_output
            assert f"a/{test_file}" in diff_output
            assert f"b/{test_file}" in diff_output
            assert "---" in diff_output
            assert "+++" in diff_output
            assert "-" in diff_output  # 删除标记
            assert "+" in diff_output  # 插入标记
            assert "原始内容" in diff_output
            assert "修改后的内容" in diff_output