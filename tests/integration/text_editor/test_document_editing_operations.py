"""
文本编辑器综合文档编辑操作集成测试

测试各种实际文档编辑场景，包括：
1. 创建单行/多行写入
2. 单行/多行插入
3. 行删除
4. 单行/多行修改
5. 复杂编辑操作组合

每个测试都会验证git diff风格的输出格式。
"""

import pytest
import tempfile
import os
from pathlib import Path

from tasking.model.filesystem import EditOperation
from tasking.tool.filesystem import LocalFileSystem
from tasking.tool.text_editor import LocalTextEditor
from tasking.tool.terminal import LocalTerminal


class TestDocumentEditingOperations:
    """综合文档编辑操作集成测试"""

    @pytest.mark.asyncio
    async def test_create_single_line_file(self):
        """测试：创建单行文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(terminal)
            editor = LocalTextEditor(filesystem)

            test_file = os.path.join(temp_dir, "single_line.txt")
            operations = [
                EditOperation(line=1, op="insert", content="这是第一行，也是最简单的一行")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出格式
            assert "diff --git" in result
            assert f"a/{test_file}" in result
            assert f"b/{test_file}" in result
            assert "---" in result
            assert "+++" in result
            assert "+   1  这是第一行，也是最简单的一行" in result  # 注意前面的空格和行号

            # 验证最终文件内容
            final_content = await editor.view(test_file)
            assert "|1|这是第一行，也是最简单的一行|" in final_content

    @pytest.mark.asyncio
    async def test_create_multiple_lines_file(self):
        """测试：创建多行文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(terminal)
            editor = LocalTextEditor(filesystem)

            test_file = os.path.join(temp_dir, "python_script.py")
            operations = [
                EditOperation(line=1, op="insert", content="#!/usr/bin/env python3"),
                EditOperation(line=-1, op="insert", content='"""'),
                EditOperation(line=-1, op="insert", content="这是一个Python脚本示例"),
                EditOperation(line=-1, op="insert", content="包含多行注释和代码"),
                EditOperation(line=-1, op="insert", content='"""'),
                EditOperation(line=-1, op="insert", content=""),
                EditOperation(line=-1, op="insert", content="def main():"),
                EditOperation(line=-1, op="insert", content="    print('Hello, World!')"),
                EditOperation(line=-1, op="insert", content=""),
                EditOperation(line=-1, op="insert", content="if __name__ == '__main__':"),
                EditOperation(line=-1, op="insert", content="    main()")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出包含所有行的添加
            assert "diff --git" in result
            assert "#!/usr/bin/env python3" in result
            assert "def main():" in result
            assert "Hello, World!" in result

            # 验证最终文件内容
            final_content = await editor.view(test_file)
            assert "1  #!/usr/bin/env python3" in final_content
            assert "7  def main():" in final_content
            assert "8      print('Hello, World!')" in final_content  # 注意四个空格的缩进

    @pytest.mark.asyncio
    async def test_single_line_insert(self):
        """测试：单行插入"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 先创建一个基础文件
            test_file = os.path.join(temp_dir, "insert_test.txt")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("第一行\n第三行\n第五行\n")

            terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(terminal)
            editor = LocalTextEditor(filesystem)

            # 在第二行插入新内容
            operations = [
                EditOperation(line=2, op="insert", content="插入的第二行")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出
            assert "diff --git" in result
            assert "@@ -1,0 +2,1 @@" in result
            assert "+插入的第二行" in result

            # 验证最终文件内容
            final_content = await editor.view(test_file)
            assert "|1|第一行|" in final_content
            assert "|2|插入的第二行|" in final_content
            assert "|3|第三行|" in final_content

    @pytest.mark.asyncio
    async def test_multiple_lines_insert(self):
        """测试：多行插入"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 先创建一个基础文件
            test_file = os.path.join(temp_dir, "document.md")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("=== 文档开始 ===\n\n=== 文档结束 ===\n")

            terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(terminal)
            editor = LocalTextEditor(filesystem)

            # 在第二行插入多行内容
            operations = [
                EditOperation(line=2, op="insert", content="## 章节标题"),
                EditOperation(line=-1, op="insert", content=""),
                EditOperation(line=-1, op="insert", content="这是第一段内容，包含重要信息。"),
                EditOperation(line=-1, op="insert", content=""),
                EditOperation(line=-1, op="insert", content="这是第二段内容，提供更多细节。"),
                EditOperation(line=-1, op="insert", content=""),
                EditOperation(line=-1, op="insert", content="- 列表项1"),
                EditOperation(line=-1, op="insert", content="- 列表项2"),
                EditOperation(line=-1, op="insert", content="- 列表项3")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出包含所有插入内容
            assert "diff --git" in result
            assert "+## 章节标题" in result
            assert "+这是第一段内容，包含重要信息。" in result
            assert "+这是第二段内容，提供更多细节。" in result
            assert "+- 列表项1" in result
            assert "+- 列表项2" in result
            assert "+- 列表项3" in result

            # 验证最终文件内容
            final_content = await editor.view(test_file)
            assert "|2|## 章节标题|" in final_content
            assert "|6|这是第一段内容，包含重要信息。|" in final_content
            assert "|12|- 列表项3|" in final_content

    @pytest.mark.asyncio
    async def test_line_deletion(self):
        """测试：行删除"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 先创建一个包含多行的文件
            test_file = os.path.join(temp_dir, "cleanup.txt")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("第一行：保留\n")
                f.write("第二行：要删除\n")
                f.write("第三行：保留\n")
                f.write("第四行：要删除\n")
                f.write("第五行：保留\n")
                f.write("第六行：要删除\n")
                f.write("第七行：保留\n")

            terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(terminal)
            editor = LocalTextEditor(filesystem)

            # 删除第2、4、6行（注意：从后往前删除避免行号偏移）
            operations = [
                EditOperation(line=6, op="delete", content=""),
                EditOperation(line=4, op="delete", content=""),
                EditOperation(line=2, op="delete", content="")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出显示删除操作
            assert "diff --git" in result
            assert "-第二行：要删除" in result
            assert "-第四行：要删除" in result
            assert "-第六行：要删除" in result

            # 验证最终文件内容
            final_content = await editor.view(test_file)
            assert "|1|第一行：保留|" in final_content
            assert "|2|第三行：保留|" in final_content
            assert "|3|第五行：保留|" in final_content
            assert "|4|第七行：保留|" in final_content
            # 验证删除操作成功（包含被删除的内容在diff中）
            assert "-第二行：要删除" in result
            assert "-第四行：要删除" in result
            assert "-第六行：要删除" in result

    @pytest.mark.asyncio
    async def test_single_line_modification(self):
        """测试：单行修改"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 先创建一个配置文件
            test_file = os.path.join(temp_dir, "config.conf")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("server_port=8080\n")
                f.write("debug_mode=false\n")
                f.write("max_connections=100\n")
                f.write("timeout=30\n")

            terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(terminal)
            editor = LocalTextEditor(filesystem)

            # 修改第2行和第4行
            operations = [
                EditOperation(line=2, op="modify", content="debug_mode=true"),
                EditOperation(line=4, op="modify", content="timeout=60")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出
            assert "diff --git" in result
            assert "-debug_mode=false" in result
            assert "+debug_mode=true" in result
            assert "-timeout=30" in result
            assert "+timeout=60" in result

            # 验证最终文件内容
            final_content = await editor.view(test_file)
            assert "|1|server_port=8080|" in final_content
            assert "|2|debug_mode=true|" in final_content
            assert "|3|max_connections=100|" in final_content
            assert "|4|timeout=60|" in final_content

    @pytest.mark.asyncio
    async def test_multiple_lines_modification(self):
        """测试：多行修改"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 先创建一个简单的配置文件
            test_file = os.path.join(temp_dir, "settings.conf")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("host=localhost\n")
                f.write("port=8080\n")
                f.write("debug=false\n")

            terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(terminal)
            editor = LocalTextEditor(filesystem)

            # 修改多个配置项
            operations = [
                EditOperation(line=1, op="modify", content="host=example.com"),
                EditOperation(line=2, op="modify", content="port=9000"),
                EditOperation(line=3, op="modify", content="debug=true")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出
            assert "diff --git" in result
            assert "-host=localhost" in result
            assert "+host=example.com" in result
            assert "-port=8080" in result
            assert "+port=9000" in result
            assert "-debug=false" in result
            assert "+debug=true" in result

            # 验证最终文件内容
            final_content = await editor.view(test_file)
            assert "|1|host=example.com|" in final_content
            assert "|2|port=9000|" in final_content
            assert "|3|debug=true|" in final_content

    @pytest.mark.asyncio
    async def test_complex_editing_workflow(self):
        """测试：复杂编辑工作流"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建一个简单的文件
            test_file = os.path.join(temp_dir, "todo.md")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("# TODO List\n")
                f.write("- Task 1\n")

            terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(terminal)
            editor = LocalTextEditor(filesystem)

            # 执行简单的编辑操作：修改标题 + 添加任务
            operations = [
                # 修改标题
                EditOperation(line=1, op="modify", content="# Project TODO List"),
                # 在任务1后面添加更多任务
                EditOperation(line=2, op="insert", content="- Task 2: Implement feature"),
                EditOperation(line=-1, op="insert", content="- Task 3: Write tests")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出包含修改和插入
            assert "diff --git" in result
            assert "-# TODO List" in result
            assert "+# Project TODO List" in result
            assert "+- Task 2: Implement feature" in result
            assert "+- Task 3: Write tests" in result

            # 验证最终文件内容存在
            final_content = await editor.view(test_file)
            assert "|1|# Project TODO List|" in final_content
            assert "|2|- Task 1|" in final_content

    @pytest.mark.asyncio
    async def test_file_size_handling(self):
        """测试：文件大小处理"""
        with tempfile.TemporaryDirectory() as temp_dir:
            terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(terminal)
            editor = LocalTextEditor(filesystem)

            test_file = os.path.join(temp_dir, "large_file.txt")

            # 创建一个相对较大的文件
            lines = []
            for i in range(100):
                lines.append(f"这是第 {i+1} 行内容，包含一些中文和数字 {i+1}")

            operations = [
                EditOperation(line=1, op="insert", content="\n".join(lines))
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出
            assert "diff --git" in result
            assert "@@ -0,0 +1,100 @@" in result

            # 验证文件实际内容
            file_size = os.path.getsize(test_file)
            assert file_size > 1000  # 应该大于1KB

            final_content = await editor.view(test_file)
            assert "|1|这是第 1 行内容，包含一些中文和数字 1|" in final_content
            assert "|50|这是第 50 行内容，包含一些中文和数字 50|" in final_content
            assert "|100|这是第 100 行内容，包含一些中文和数字 100|" in final_content

    @pytest.mark.asyncio
    async def test_empty_file_operations(self):
        """测试：空文件操作"""
        with tempfile.TemporaryDirectory() as temp_dir:
            terminal = LocalTerminal(root_dir=temp_dir, create_workspace=True)
            filesystem = LocalFileSystem(terminal)
            editor = LocalTextEditor(filesystem)

            test_file = os.path.join(temp_dir, "empty.txt")

            # 创建一个空文件
            with open(test_file, 'w', encoding='utf-8') as f:
                pass  # 创建空文件

            operations = [
                EditOperation(line=1, op="insert", content="空文件的第一行")
            ]

            result = await editor.edit_file(test_file, operations)

            # 验证diff输出
            assert "diff --git" in result
            assert "@@ -0,0 +1,1 @@" in result
            assert "+空文件的第一行" in result

            # 验证最终文件内容
            final_content = await editor.view(test_file)
            assert "|1|空文件的第一行|" in final_content