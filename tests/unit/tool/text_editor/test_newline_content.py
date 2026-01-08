"""Test for handling newline-containing content in single-line EditOperations"""

import asyncio
import os
import tempfile
import pytest
from tasking.model.filesystem import EditOperation
from tasking.tool.text_editor import LocalTextEditor


class MockTerminal:
    """模拟终端对象"""
    def check_path(self, path):
        return (path, path)

    def get_workspace(self):
        return os.getcwd()


class MockFileSystem:
    """模拟文件系统对象"""
    async def open_file(self, file_path, mode, encoding):
        with open(file_path, 'r', encoding=encoding) as f:
            return f.read()

    async def save_file(self, file_path, content, encoding, replace):
        with open(file_path, 'w' if replace else 'a', encoding=encoding) as f:
            f.write(content)
        return f"文件已保存：{file_path}"

    def file_exists(self, file_path):
        return os.path.exists(file_path)

    def get_terminal(self):
        return MockTerminal()


@pytest.mark.asyncio
async def test_write_insert_modify_newline_content():
    """测试写入、插入和修改包含换行符的内容"""

    # 创建临时文件
    temp_dir = tempfile.mkdtemp()
    temp_file = os.path.join(temp_dir, "test_newline_content.py")

    try:
        # 初始化文件系统和编辑器
        fs = MockFileSystem()
        editor = LocalTextEditor(fs)

        # 1. 测试写入包含换行符的内容
        print("=== 测试1: 写入包含换行符的内容 ===")
        initial_content = r"print('Hello,\nWorld!')"

        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(initial_content + "\n")

        content = await editor.view(temp_file)
        print(f"视图输出:\n{content}")
        print()

        # 2. 测试插入包含换行符的单行
        print("=== 测试2: 插入包含换行符的单行内容 ===")
        insert_op = EditOperation(line=1, op="insert", content=r"print('Line with\nnewlines')")
        result = await editor.edit_file(temp_file, [insert_op])
        print(f"修改结果:\n{result}")

        content = await editor.view(temp_file)
        print(f"视图输出:\n{content}")
        print()

        # 3. 测试修改包含换行符的单行
        print("=== 测试3: 修改包含换行符的单行内容 ===")
        modify_op = EditOperation(line=2, op="modify", content=r"print('Modified line with\nmore\nnewlines')")
        result = await editor.edit_file(temp_file, [modify_op])
        print(f"修改结果:\n{result}")

        content = await editor.view(temp_file)
        print(f"视图输出:\n{content}")
        print()

        # 4. 验证文件读取和写入的一致性
        print("=== 测试4: 验证文件一致性 ===")
        with open(temp_file, 'r', encoding='utf-8') as f:
            file_content = f.read()
        print(f"文件实际内容:")
        print(repr(file_content))

        # 验证文件内容未被意外拆分
        assert '\n' in file_content
        assert r"print('Line with\nnewlines')" in file_content
        assert r"print('Modified line with\nmore\nnewlines')" in file_content

        print("\n✅ 所有测试通过！包含换行符的内容处理正常。")

    finally:
        # 清理临时文件和目录
        if os.path.exists(temp_file):
            os.unlink(temp_file)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


if __name__ == "__main__":
    asyncio.run(test_write_insert_modify_newline_content())
