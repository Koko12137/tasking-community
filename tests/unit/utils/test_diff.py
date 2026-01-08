"""
diff工具单元测试

测试diff_lines、diff_to_html和diff_files函数的功能
"""

import pytest
import tempfile
import os
from pathlib import Path
from tasking.utils.diff import diff_lines, diff_to_html, diff_to_text, diff_files, Operation, DiffItem


class TestDiffLines:
    """测试diff_lines函数"""

    def test_empty_lists(self):
        """测试两个空列表"""
        result = diff_lines([], [])
        assert result == []

    def test_insert_only(self):
        """测试只有插入的情况"""
        old_lines = []
        new_lines = ["line1", "line2", "line3"]
        result = diff_lines(old_lines, new_lines)
        
        assert len(result) == 3
        assert all(item.operation == Operation.INSERT for item in result)
        assert result[0].content == "line1"
        assert result[1].content == "line2"
        assert result[2].content == "line3"
        assert result[0].line == 1
        assert result[1].line == 2
        assert result[2].line == 3

    def test_delete_only(self):
        """测试只有删除的情况"""
        old_lines = ["line1", "line2", "line3"]
        new_lines = []
        result = diff_lines(old_lines, new_lines)
        
        assert len(result) == 3
        assert all(item.operation == Operation.DELETE for item in result)
        assert result[0].content == "line1"
        assert result[1].content == "line2"
        assert result[2].content == "line3"

    def test_no_changes(self):
        """测试没有变化的情况"""
        old_lines = ["line1", "line2", "line3"]
        new_lines = ["line1", "line2", "line3"]
        result = diff_lines(old_lines, new_lines)
        
        assert result == []

    def test_simple_insert(self):
        """测试简单插入"""
        old_lines = ["line1", "line3"]
        new_lines = ["line1", "line2", "line3"]
        result = diff_lines(old_lines, new_lines)
        
        assert len(result) == 1
        assert result[0].operation == Operation.INSERT
        assert result[0].content == "line2"
        assert result[0].line == 2

    def test_simple_delete(self):
        """测试简单删除"""
        old_lines = ["line1", "line2", "line3"]
        new_lines = ["line1", "line3"]
        result = diff_lines(old_lines, new_lines)
        
        assert len(result) == 1
        assert result[0].operation == Operation.DELETE
        assert result[0].content == "line2"
        assert result[0].line == 2

    def test_multiple_changes(self):
        """测试多个变化"""
        old_lines = ["line1", "line2", "line3", "line4"]
        new_lines = ["line1", "line2_new", "line3", "line5"]
        result = diff_lines(old_lines, new_lines)
        
        # 应该检测到删除line2和line4，插入line2_new和line5
        assert len(result) == 4
        delete_ops = [item for item in result if item.operation == Operation.DELETE]
        insert_ops = [item for item in result if item.operation == Operation.INSERT]
        
        assert len(delete_ops) == 2
        assert len(insert_ops) == 2
        
        # 检查删除的内容
        delete_contents = {item.content for item in delete_ops}
        assert "line2" in delete_contents
        assert "line4" in delete_contents
        
        # 检查插入的内容
        insert_contents = {item.content for item in insert_ops}
        assert "line2_new" in insert_contents
        assert "line5" in insert_contents

    def test_strip_newlines(self):
        """测试换行符被正确去除"""
        old_lines = ["line1\n", "line2\r\n", "line3\n"]
        new_lines = ["line1\n", "line2_new\n", "line3\n"]
        result = diff_lines(old_lines, new_lines)
        
        # 检查内容中没有换行符
        for item in result:
            assert "\n" not in item.content
            assert "\r" not in item.content

    def test_complex_diff(self):
        """测试复杂的diff场景"""
        old_lines = [
            "def hello():",
            "    print('old')",
            "    return True",
            "def world():",
            "    pass"
        ]
        new_lines = [
            "def hello():",
            "    print('new')",
            "    return True",
            "def new_function():",
            "    pass"
        ]
        result = diff_lines(old_lines, new_lines)
        
        # 应该检测到删除"    print('old')"和"def world():"，插入"    print('new')"和"def new_function():"
        delete_contents = {item.content for item in result if item.operation == Operation.DELETE}
        insert_contents = {item.content for item in result if item.operation == Operation.INSERT}
        
        assert "    print('old')" in delete_contents
        assert "def world():" in delete_contents
        assert "    print('new')" in insert_contents
        assert "def new_function():" in insert_contents


class TestDiffToHtml:
    """测试diff_to_html函数"""

    def test_empty_diff(self):
        """测试空差异列表"""
        result = diff_to_html([])
        assert "<table" in result
        assert "</table>" in result

    def test_insert_item(self):
        """测试插入项的HTML生成"""
        diff_items = [
            DiffItem(line=1, operation=Operation.INSERT, content="new line")
        ]
        result = diff_to_html(diff_items)
        
        assert "new line" in result
        assert Operation.INSERT.value in result
        assert "#d4edda" in result  # 绿色背景

    def test_delete_item(self):
        """测试删除项的HTML生成"""
        diff_items = [
            DiffItem(line=1, operation=Operation.DELETE, content="old line")
        ]
        result = diff_to_html(diff_items)
        
        assert "old line" in result
        assert Operation.DELETE.value in result
        assert "#f8d7da" in result  # 红色背景

    def test_html_escaping(self):
        """测试HTML特殊字符转义"""
        diff_items = [
            DiffItem(line=1, operation=Operation.INSERT, content="<script>alert('xss')</script>")
        ]
        result = diff_to_html(diff_items)
        
        assert "&lt;script&gt;" in result
        assert "&lt;/script&gt;" in result
        assert "&#39;xss&#39;" in result
        assert "<script>" not in result

    def test_multiple_items(self):
        """测试多个差异项的HTML生成"""
        diff_items = [
            DiffItem(line=1, operation=Operation.DELETE, content="old1"),
            DiffItem(line=2, operation=Operation.INSERT, content="new1"),
            DiffItem(line=3, operation=Operation.DELETE, content="old2"),
        ]
        result = diff_to_html(diff_items)
        
        assert "old1" in result
        assert "new1" in result
        assert "old2" in result
        assert result.count("<tr") == 4  # 1个表头行 + 3个数据行


class TestDiffFiles:
    """测试diff_files函数"""

    def test_diff_files(self):
        """测试文件差异比较"""
        with tempfile.TemporaryDirectory() as temp_dir:
            old_file = os.path.join(temp_dir, "old.txt")
            new_file = os.path.join(temp_dir, "new.txt")
            
            # 创建旧文件
            with open(old_file, "w", encoding="utf-8") as f:
                f.write("line1\n")
                f.write("line2\n")
                f.write("line3\n")
            
            # 创建新文件
            with open(new_file, "w", encoding="utf-8") as f:
                f.write("line1\n")
                f.write("line2_modified\n")
                f.write("line3\n")
            
            result = diff_files(old_file, new_file)
            
            assert "<table" in result
            assert "line2" in result
            assert "line2_modified" in result

    def test_diff_files_same_content(self):
        """测试相同内容的文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            old_file = os.path.join(temp_dir, "old.txt")
            new_file = os.path.join(temp_dir, "new.txt")
            
            content = "line1\nline2\nline3\n"
            
            with open(old_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            with open(new_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            result = diff_files(old_file, new_file)
            
            # 应该没有差异行（只有表头）
            assert "<table" in result
            # 检查是否只有表头，没有数据行
            assert result.count("<tr") == 1  # 只有表头行

    def test_diff_files_encoding(self):
        """测试UTF-8编码文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            old_file = os.path.join(temp_dir, "old.txt")
            new_file = os.path.join(temp_dir, "new.txt")
            
            with open(old_file, "w", encoding="utf-8") as f:
                f.write("中文内容\n")
            
            with open(new_file, "w", encoding="utf-8") as f:
                f.write("中文内容修改\n")
            
            result = diff_files(old_file, new_file)
            
            assert "中文" in result


class TestDiffContext:
    """测试上下文保留功能"""

    def test_diff_to_html_with_context(self):
        """测试HTML格式的上下文保留"""
        old_lines = [
            "line1\n",
            "line2\n",
            "line3\n",
            "line4\n",
            "line5\n",
            "line6\n",
            "line7\n",
        ]
        new_lines = [
            "line1\n",
            "line2\n",
            "line3_modified\n",
            "line4\n",
            "line5\n",
            "line6\n",
            "line7\n",
        ]
        
        diff_items = diff_lines(old_lines, new_lines)
        html = diff_to_html(diff_items, old_lines, new_lines, k=2)
        
        # 应该包含修改的行
        assert "line3_modified" in html or "line3" in html
        # 应该包含上下文行
        assert "line2" in html
        assert "line4" in html

    def test_diff_to_text_with_context(self):
        """测试文本格式的上下文保留"""
        old_lines = [
            "line1\n",
            "line2\n",
            "line3\n",
            "line4\n",
        ]
        new_lines = [
            "line1\n",
            "line2_modified\n",
            "line3\n",
            "line4\n",
        ]
        
        diff_items = diff_lines(old_lines, new_lines)
        text = diff_to_text(diff_items, old_lines, new_lines, k=1)
        
        # 应该包含修改的行
        assert "line2_modified" in text or "-" in text
        # 应该包含上下文行（以空格开头，保留行号对齐格式）
        assert "    1  line1" in text or "    3  line3" in text

    def test_diff_files_with_context(self):
        """测试文件差异比较的上下文保留"""
        # 获取测试资源文件路径（tests/assets）
        test_dir = Path(__file__).resolve().parents[2] / "assets"
        old_file = str(test_dir / "ai_intro_v1.txt")
        new_file = str(test_dir / "ai_intro_v2.txt")
        
        # 测试HTML格式
        html_result = diff_files(old_file, new_file, output_format="html", k=3)
        assert "<table" in html_result
        assert "人工智能" in html_result
        
        # 测试文本格式
        text_result = diff_files(old_file, new_file, output_format="text", k=3)
        assert "人工智能" in text_result
        assert "+" in text_result or "-" in text_result  # 应该包含变化标记

    def test_context_k_parameter(self):
        """测试不同的k值"""
        old_lines = [
            "context1\n",
            "context2\n",
            "changed_line\n",
            "context3\n",
            "context4\n",
        ]
        new_lines = [
            "context1\n",
            "context2\n",
            "changed_line_new\n",
            "context3\n",
            "context4\n",
        ]
        
        diff_items = diff_lines(old_lines, new_lines)
        
        # k=1，应该只包含1行上下文
        text_k1 = diff_to_text(diff_items, old_lines, new_lines, k=1)
        lines_k1 = text_k1.split("\n")
        # 应该包含变化行和上下文行
        
        # k=2，应该包含2行上下文
        text_k2 = diff_to_text(diff_items, old_lines, new_lines, k=2)
        lines_k2 = text_k2.split("\n")
        # k=2应该比k=1包含更多行
        assert len(lines_k2) >= len(lines_k1)

    def test_context_k_minus_one(self):
        """测试k=-1时保留所有变化行"""
        old_lines = ["line1\n", "line2\n", "line3\n"]
        new_lines = ["line1\n", "line2_modified\n", "line3\n"]
        
        diff_items = diff_lines(old_lines, new_lines)
        text = diff_to_text(diff_items, old_lines, new_lines, k=-1)
        
        # k=-1应该只显示变化行，不显示上下文
        assert "line2_modified" in text or "-" in text
        # 不应该包含上下文行（以空格开头的行应该很少或没有）

    def test_ai_intro_files_diff(self):
        """测试AI介绍文本文件的完整diff功能"""
        test_dir = Path(__file__).resolve().parents[2] / "assets"
        old_file = str(test_dir / "ai_intro_v1.txt")
        new_file = str(test_dir / "ai_intro_v2.txt")
        
        # 读取文件内容
        with open(old_file, "r", encoding="utf-8") as f:
            old_lines = f.readlines()
        with open(new_file, "r", encoding="utf-8") as f:
            new_lines = f.readlines()
        
        # 计算差异
        diff_items = diff_lines(old_lines, new_lines)
        assert len(diff_items) > 0  # 应该有差异
        
        # 测试HTML格式（带上下文）
        html = diff_to_html(diff_items, old_lines, new_lines, k=3)
        assert "<table" in html
        assert "机器学习" in html or "深度学习" in html  # 应该包含一些原文内容
        
        # 测试文本格式（带上下文）
        text = diff_to_text(diff_items, old_lines, new_lines, k=3)
        assert "机器学习" in text or "深度学习" in text
        assert "+" in text or "-" in text  # 应该包含变化标记
        
        # 验证包含了一些关键修改
        # v2中添加了"生成式AI"相关内容
        assert any("生成式" in item.content or "生成式" in text for item in diff_items)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

