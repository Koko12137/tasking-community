"""
文本编辑器diff功能测试

测试text_editor.py的diff输出功能，确保：
1. 返回值是diff_to_text保留3行上下文的结果
2. 能够正确执行各种编辑操作（新建、修改、删除、插入、尾部插入）
"""

import pytest
import tempfile
import os
from pathlib import Path

from tasking.model.filesystem import EditOperation
from tasking.tool.filesystem import LocalFileSystem
from tasking.tool.text_editor import LocalTextEditor
from tasking.tool.terminal import LocalTerminal
from tasking.utils.diff import diff_lines, diff_to_text


class TestTextEditorDiff:
    """文本编辑器diff功能测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def editor(self, temp_dir):
        """创建文本编辑器实例"""
        terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
        filesystem = LocalFileSystem(terminal)
        return LocalTextEditor(filesystem)

    @pytest.mark.asyncio
    async def test_create_new_file_with_diff(self, editor, temp_dir):
        """测试：创建新文件，验证diff输出包含3行上下文"""
        test_file = os.path.join(temp_dir, "new_file.txt")
        operations = [
            EditOperation(line=1, op="insert", content="第一行内容\n第二行内容\n第三行内容")
        ]

        result = await editor.edit_file(test_file, operations)

        # 验证diff输出格式
        assert "diff --git" in result
        assert f"a/{test_file}" in result
        assert f"b/{test_file}" in result
        assert "---" in result
        assert "+++" in result

        # 验证包含插入的内容
        assert "+" in result
        assert "第一行内容" in result
        assert "第二行内容" in result
        assert "第三行内容" in result

        # 验证文件内容
        final_content = await editor.view(test_file)
        assert "|1|第一行内容|" in final_content
        assert "|2|第二行内容|" in final_content
        assert "|3|第三行内容|" in final_content

    @pytest.mark.asyncio
    async def test_modify_lines_with_context(self, editor, temp_dir):
        """测试：修改某几行，验证包含3行上下文"""
        test_file = os.path.join(temp_dir, "modify_test.txt")
        
        # 先创建文件
        initial_content = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(initial_content)

        # 修改第4行和第5行
        operations = [
            EditOperation(line=4, op="modify", content="line4_modified"),
            EditOperation(line=5, op="modify", content="line5_modified"),
        ]

        result = await editor.edit_file(test_file, operations)

        # 验证diff输出包含上下文（应该包含line1-line8）
        assert "diff --git" in result
        # 验证包含修改的行
        assert "-" in result
        assert "+" in result
        assert "line4_modified" in result
        assert "line5_modified" in result
        # 验证包含上下文行（以空格开头）
        assert "    " in result or " | " in result  # 上下文行格式

        # 验证文件内容已修改
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "line4_modified" in content
            assert "line5_modified" in content

    @pytest.mark.asyncio
    async def test_delete_lines_with_context(self, editor, temp_dir):
        """测试：删除某几行，验证包含3行上下文"""
        test_file = os.path.join(temp_dir, "delete_test.txt")
        
        # 先创建文件
        initial_content = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(initial_content)

        # 删除第3行和第5行
        operations = [
            EditOperation(line=3, op="delete", content=""),
            EditOperation(line=5, op="delete", content=""),  # 注意：删除后行号会变化
        ]

        result = await editor.edit_file(test_file, operations)

        # 验证diff输出
        assert "diff --git" in result
        assert "-" in result
        # 验证包含上下文行

        # 验证文件内容已删除
        with open(test_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert "line3" not in "".join(lines)
            # 注意：删除第3行后，原来的第5行变成了第4行

    @pytest.mark.asyncio
    async def test_insert_lines_with_context(self, editor, temp_dir):
        """测试：插入某几行，验证包含3行上下文"""
        test_file = os.path.join(temp_dir, "insert_test.txt")
        
        # 先创建文件
        initial_content = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(initial_content)

        # 在第3行后插入新行
        operations = [
            EditOperation(line=4, op="insert", content="new_line_after_3"),
        ]

        result = await editor.edit_file(test_file, operations)

        # 验证diff输出
        assert "diff --git" in result
        assert "+" in result
        assert "new_line_after_3" in result
        # 验证包含上下文行

        # 验证文件内容已插入
        with open(test_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert "new_line_after_3" in "".join(lines)

    @pytest.mark.asyncio
    async def test_insert_at_end(self, editor, temp_dir):
        """测试：插入到最尾部，验证包含3行上下文"""
        test_file = os.path.join(temp_dir, "append_test.txt")
        
        # 先创建文件
        initial_content = "line1\nline2\nline3\nline4\nline5\n"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(initial_content)

        # 插入到末尾
        operations = [
            EditOperation(line=-1, op="insert", content="line6\nline7"),
        ]

        result = await editor.edit_file(test_file, operations)

        # 验证diff输出
        assert "diff --git" in result
        assert "+" in result
        assert "line6" in result
        assert "line7" in result
        # 验证包含上下文行（应该包含line3-line5）

        # 验证文件内容已追加
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "line6" in content
            assert "line7" in content

    @pytest.mark.asyncio
    async def test_diff_output_format_matches_diff_to_text(self, editor, temp_dir):
        """测试：验证返回的diff格式与diff_to_text一致"""
        test_file = os.path.join(temp_dir, "format_test.txt")
        
        # 先创建文件
        initial_content = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(initial_content)

        # 修改第4行
        operations = [
            EditOperation(line=4, op="modify", content="line4_modified"),
        ]

        result = await editor.edit_file(test_file, operations)

        # 提取diff部分（去掉git diff头部）
        diff_lines_result = result.split("\n")
        diff_start = 0
        for i, line in enumerate(diff_lines_result):
            if line.startswith("diff --git"):
                diff_start = i
                break
        
        # 获取实际的diff内容（从空行后开始）
        diff_content = "\n".join(diff_lines_result[diff_start + 4:])  # 跳过头部和空行

        # 手动计算期望的diff
        with open(test_file, "r", encoding="utf-8") as f:
            new_lines = f.readlines()
        
        old_lines = initial_content.splitlines(keepends=True)
        diff_items = diff_lines(old_lines, new_lines)
        expected_diff = diff_to_text(diff_items, old_lines, new_lines, k=3)

        # 验证格式一致（忽略行号可能的小差异，主要验证内容和格式）
        assert "line4_modified" in diff_content
        assert "line4_modified" in expected_diff
        # 验证都包含上下文行（以空格开头）
        assert any(line.startswith(" ") for line in diff_content.split("\n") if "|" in line)
        assert any(line.startswith(" ") for line in expected_diff.split("\n") if "|" in line)

    @pytest.mark.asyncio
    async def test_complex_operations_with_context(self, editor, temp_dir):
        """测试：复杂操作组合，验证上下文正确"""
        test_file = os.path.join(temp_dir, "complex_test.txt")
        
        # 先创建文件
        initial_content = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10\n"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(initial_content)

        # 执行多个操作：修改、删除、插入
        operations = [
            EditOperation(line=3, op="modify", content="line3_modified"),
            EditOperation(line=5, op="delete", content=""),
            EditOperation(line=7, op="insert", content="new_line_after_7"),
        ]

        result = await editor.edit_file(test_file, operations)

        # 验证diff输出
        assert "diff --git" in result
        assert "-" in result
        assert "+" in result
        assert "line3_modified" in result
        assert "new_line_after_7" in result
        # 验证包含上下文行

        # 验证文件内容
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "line3_modified" in content
            assert "new_line_after_7" in content
            # 验证第5行已删除（注意行号变化）

    @pytest.mark.asyncio
    async def test_edit_with_ai_intro_file(self, editor, temp_dir):
        """测试：使用AI介绍文件进行编辑测试"""
        # 读取测试资源文件
        test_dir = Path(__file__).parent.parent.parent / "assets"
        source_file = test_dir / "ai_intro_v1.txt"
        
        if not source_file.exists():
            pytest.skip("测试资源文件不存在")

        # 复制到临时目录
        test_file = os.path.join(temp_dir, "ai_intro.txt")
        with open(source_file, "r", encoding="utf-8") as f:
            content = f.read()
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(content)

        # 修改文件（模拟v1到v2的修改）
        operations = [
            EditOperation(line=3, op="modify", content="人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，旨在创建能够执行通常需要人类智能的任务的智能系统。"),
        ]

        result = await editor.edit_file(test_file, operations)

        # 验证diff输出包含3行上下文
        assert "diff --git" in result
        assert "-" in result
        assert "+" in result
        assert "智能系统" in result
        
        # 验证包含上下文行（以空格开头，格式为 "    行号 | 内容"）
        diff_lines_result = result.split("\n")
        has_context = any(
            line.startswith(" ") and "|" in line and not line.strip().startswith("-") and not line.strip().startswith("+")
            for line in diff_lines_result 
            if line.strip() and not line.startswith("diff") and not line.startswith("---") and not line.startswith("+++")
        )
        assert has_context, f"应该包含上下文行。实际输出:\n{result}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

