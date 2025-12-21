"""
基础文本编辑器模块，提供统一的文本编辑抽象接口

该模块实现了文本编辑的核心逻辑，包括：
1. 基础的文本编辑器抽象接口
2. 内存中的编辑操作处理
3. 异步文件IO写入
4. 统一的编辑流程和diff输出
"""

import os
from abc import ABC, abstractmethod

from ..model.filesystem import EditOperation
from ..utils.diff import diff_lines, diff_to_text
from .filesystem import IFileSystem


class ITextEditor(ABC):
    """文本编辑器接口"""

    @abstractmethod
    async def open_file(self, file_path: str) -> str:
        """打开文件"""
        raise NotImplementedError("open_file 方法未实现")

    @abstractmethod
    async def edit_file(self, file_path: str, operations: list[EditOperation]) -> str:
        """编辑文件的主入口

        **重要要求：**
        - 每个 EditOperation 对象仅支持**单行内容**
        - 如需插入/修改多行内容，请使用多个 EditOperation 对象
        - 内容中的换行符将自动转义，避免干扰文件结构

        Args:
            file_path: 目标文件路径
            operations: 编辑操作列表

        Returns:
            所有操作执行结果的拼接字符串
        """
        raise NotImplementedError("edit_file 方法未实现")

    @abstractmethod
    async def view(self, file_path: str) -> str:
        """查看文件内容，按行切分并标注行号

        Args:
            file_path: 目标文件路径

        Returns:
            带行号的文件内容字符串

        Raises:
            FileNotFoundError: 文件不存在
            RuntimeError: 读取文件失败
        """
        raise NotImplementedError("view 方法未实现")


class LocalTextEditor(ITextEditor):
    """基础文本编辑器实现"""

    def __init__(self, file_system: IFileSystem):
        """初始化文本编辑器

        Args:
            file_system: 文件系统实例，用于获取终端和文件操作
        """
        self._file_system = file_system

    async def open_file(self, file_path: str) -> str:
        """打开文件"""
        content = await self._file_system.open_file(file_path, "text", "utf-8")
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        return content

    async def edit_file(self, file_path: str, operations: list[EditOperation]) -> str:
        """编辑文件的主入口

        Args:
            file_path: 目标文件路径
            operations: 编辑操作列表

        Returns:
            所有操作执行结果的拼接字符串，包含编辑前后对比
        """
        if not operations:
            raise ValueError("操作列表不能为空")

        allowed_path = self._file_system.get_terminal().check_path(file_path)
        if not allowed_path:
            raise RuntimeError(f"路径超出workspace范围：{file_path}")
        file_abs, _ = self._file_system.get_terminal().check_path(file_path)
        # 检查文件是否存在
        file_exists = self._file_system.file_exists(file_abs)

        # 验证操作合法性
        self._validate_operations(operations, file_exists)

        # 获取编辑前的完整文件内容（用于diff）
        # lines 中每行不包含换行符，只是纯文本内容
        old_lines: list[str] = []
        if file_exists:
            try:
                old_file = await self._file_system.open_file(file_abs, "text", "utf-8")
                if isinstance(old_file, bytes):
                    old_file = old_file.decode('utf-8')
                # 使用 splitlines(keepends=False) 获取不包含换行符的行列表
                # 恢复内容中的转义换行符
                old_lines = [line.replace('\\n', '\n') for line in old_file.splitlines(keepends=False)]
                # 如果文件为空或只有换行符，old_lines 可能为空列表，这是正常的
            except Exception:
                pass  # 如果读取失败，old_lines保持为空

        # 在内存中应用所有编辑操作
        new_lines = self._apply_operations_in_memory(old_lines, operations, file_exists)
        # 异步写入文件
        edit_result = await self._write_file_async(file_abs, new_lines)

        # 为diff生成转义版本的内容（显示时用转义的换行符）
        old_lines_escaped = [line.replace('\n', '\\n') for line in old_lines]
        new_lines_escaped = [line.replace('\n', '\\n') for line in new_lines]

        # 生成对比输出（使用diff.py的函数，默认保留3行上下文）
        diff_output = self._format_diff_output(file_abs, old_lines_escaped, new_lines_escaped, k=3)

        # 组合结果
        if diff_output:
            return diff_output + "\n\n" + edit_result
        return edit_result

    def _execute_delete_operation(self, new_lines: list[str], op: EditOperation) -> None:
        """执行删除操作"""
        if op.line == -1:
            # 删除最后一行
            if new_lines:
                new_lines.pop()
        elif 1 <= op.line <= len(new_lines):
            # 删除指定行
            del new_lines[op.line - 1]
        elif op.line == 0 or op.line == 1:
            # 删除第一行
            if new_lines:
                del new_lines[0]
        else:
            raise ValueError(f"删除行号超出范围：{op.line}，文件共有 {len(new_lines)} 行")

    def _execute_insert_operation(self, new_lines: list[str], op: EditOperation) -> None:
        """执行插入操作（单行内容）"""
        # 直接使用内容，已由_preprocess_operations处理为单行
        content = op.content

        if op.line == 0 or op.line == 1:
            # 插入到开头
            new_lines.insert(0, content)
        elif op.line == -1:
            # 插入到末尾
            new_lines.append(content)
        else:
            # 插入到指定行之前
            if 1 <= op.line <= len(new_lines):
                new_lines.insert(op.line - 1, content)
            else:
                raise ValueError(f"插入行号超出范围：{op.line}，文件共有 {len(new_lines)} 行")


    def _execute_modify_operation(self, new_lines: list[str], op: EditOperation) -> None:
        """执行修改操作"""
        # 不再转义换行符，保持原始内容
        escaped_content = op.content
        if op.line == -1:
            # 修改最后一行
            if new_lines:
                new_lines[-1] = escaped_content
            else:
                # 空文件修改最后一行相当于插入
                new_lines.append(escaped_content)
        elif op.line == 0 or op.line == 1:
            # 修改第一行
            if new_lines:
                new_lines[0] = escaped_content
            else:
                # 空文件修改第一行相当于插入
                new_lines.append(escaped_content)
        elif 1 <= op.line <= len(new_lines):
            # 修改指定行
            new_lines[op.line - 1] = escaped_content
        else:
            raise ValueError(f"修改行号超出范围：{op.line}，文件共有 {len(new_lines)} 行")

    def _apply_operations_in_memory(
        self,
        old_lines: list[str],
        operations: list[EditOperation],
        file_exists: bool
    ) -> list[str]:
        """在内存中应用所有编辑操作
        1. 不按行号排序，严格按照传入顺序执行
        2. 保留内容中的原始换行符，不进行转义处理

        Args:
            old_lines: 原始文件内容（按行分割，不包含换行符）
            operations: 编辑操作列表
            file_exists: 文件是否存在

        Returns:
            编辑后的文件内容（按行分割，不包含换行符）
        """
        # 创建副本，避免修改原始列表
        new_lines = old_lines.copy() if old_lines else []

        # 如果文件不存在，从空列表开始
        if not file_exists:
            new_lines = []

        # 严格按照传入顺序执行操作，不排序，不合并
        for op in operations:
            if op.op == "delete":
                self._execute_delete_operation(new_lines, op)
            elif op.op == "insert":
                # 严格插入单行内容，不自动拆分多行
                # 如需插入多行，请使用多个EditOperation对象
                self._execute_insert_operation(new_lines, op)
            elif op.op == "modify":
                self._execute_modify_operation(new_lines, op)

        return new_lines

    async def _write_file_async(self, file_path: str, lines: list[str]) -> str:
        """异步写入文件（使用filesystem.save_file方法）

        Args:
            file_path: 文件路径
            lines: 文件内容（按行分割，不包含换行符）

        Returns:
            写入结果消息
        """
        # 将行列表合并为完整内容，每行之间用换行符连接
        # 如果文件不为空，在最后添加一个换行符（符合 Unix 文件格式）
        # 写入时转义行内容中的换行符，避免干扰文件结构
        if not lines:
            content = ''
        else:
            content = '\n'.join(line.replace('\n', '\\n') for line in lines) + '\n'
        # 使用filesystem的save_file方法进行保存（覆盖模式）
        return await self._file_system.save_file(file_path, content, "utf-8", replace=True)

    def _validate_operations(self, operations: list[EditOperation], file_exists: bool) -> None:
        """验证操作列表的合法性"""
        allowed_ops = {"insert", "delete", "modify"}

        for idx, op in enumerate(operations):
            # 验证操作类型
            if op.op not in allowed_ops:
                raise ValueError(f"非法操作类型（索引 {idx}）：{op.op}，仅支持 {allowed_ops}")

            # 文件不存在时的验证
            if not file_exists:
                # 空文件/不存在文件的 delete -1 操作默认忽略，不报错
                if op.op == "delete" and op.line == -1:
                    continue  # 跳过验证，后续执行时会自动忽略
                if op.op != "insert":
                    raise ValueError(f"文件不存在时只允许insert操作（索引 {idx}）：{op.op}")
                # 新建文件允许的行号：0（开头），1（第一行），-1（末尾）
                if op.line not in [0, 1, -1]:
                    raise ValueError(f"新建文件只支持行号 0、1 或 -1（索引 {idx}）：行号 {op.line}")


    async def view(self, file_path: str) -> str:
        """查看文件内容，按行切分并标注行号

        Args:
            file_path: 目标文件路径

        Returns:
            带行号的文件内容字符串，格式为表格形式，或文件不存在/为空的提示信息
        """
        # 检查文件是否存在
        allowed_path = self._file_system.get_terminal().check_path(file_path)
        if not allowed_path:
            raise RuntimeError(f"路径超出workspace范围：{file_path}")
        file_abs, _ = self._file_system.get_terminal().check_path(file_path)
        file_exists = self._file_system.file_exists(file_abs)

        # 如果文件不存在，返回提示信息
        if not file_exists:
            return "文件不存在或为空,编辑时会自动创建"

        try:
            # 检查文件大小
            file_size = os.path.getsize(file_abs)

            # 如果文件为空，返回提示信息
            if file_size == 0:
                return "文件不存在或为空,编辑时会自动创建"

            # 使用文件系统的open_file方法读取文件内容
            content = await self._file_system.open_file(file_abs, "text", "utf-8")

            # 如果返回的是bytes，尝试解码为字符串
            if isinstance(content, bytes):
                try:
                    content = content.decode('utf-8')
                except UnicodeDecodeError:
                    raise RuntimeError(f"文件无法解码为UTF-8格式：{file_path}")

            # 按行分割内容
            lines = content.split('\n')
            # 构建表格格式的输出
            result_lines: list[str] = []
            # 为每一行添加行号
            for i, line in enumerate(lines, 1):
                result_lines.append(f"{i}  {line}")

            # 重新拼接为字符串
            return '\n'.join(result_lines)

        except Exception:
            # 如果发生异常，也返回提示信息
            return "文件不存在或为空,编辑时会自动创建"

    async def _get_lines_content(self, file_path: str, line_numbers: list[int]) -> dict[int, str]:
        """获取文件指定行号的内容

        Args:
            file_path: 目标文件路径
            line_numbers: 要获取的行号列表

        Returns:
            行号到内容的映射字典，如果行号超出范围则返回空字符串
        """
        result: dict[int, str] = {}

        try:
            # 使用文件系统的open_file方法读取文件内容
            content = await self._file_system.open_file(file_path, "text", "utf-8")

            # 如果返回的是bytes，尝试解码为字符串
            if isinstance(content, bytes):
                try:
                    content = content.decode('utf-8')
                except UnicodeDecodeError:
                    return result

            # 按行分割内容
            lines = content.split('\n')

            # 获取指定行号的内容
            for line_num in line_numbers:
                if 1 <= line_num <= len(lines):
                    result[line_num] = lines[line_num - 1]
                else:
                    result[line_num] = ""

        except Exception:
            # 如果读取失败，所有行号都返回空字符串
            for line_num in line_numbers:
                result[line_num] = ""

        return result

    def _format_diff_output(
        self,
        file_path: str,
        old_lines: list[str],
        new_lines: list[str],
        k: int = 3
    ) -> str:
        """格式化编辑前后的对比输出，使用diff.py的函数

        Args:
            file_path: 文件路径
            old_lines: 编辑前的完整文件内容（按行分割）
            new_lines: 编辑后的完整文件内容（按行分割）
            k: 保留变化内容的上下 k 行内容，默认 3 行

        Returns:
            文本格式的差异显示（类似git diff风格）
        """
        # 如果文件内容为空，不显示diff
        if not old_lines and not new_lines:
            return ""
        
        # 如果内容相同，不显示diff
        if old_lines == new_lines:
            return ""
        
        # 使用diff.py的函数计算差异
        diff_items = diff_lines(old_lines, new_lines)
        
        # 如果没有差异，不显示diff
        if not diff_items:
            return ""
        
        # 生成git diff风格的头部
        lines: list[str] = []
        lines.append(f"diff --git a/{file_path} b/{file_path}")
        lines.append(f"--- a/{file_path}")
        lines.append(f"+++ b/{file_path}")
        lines.append("")
        
        # 使用diff_to_text生成差异内容（带上下文）
        diff_text = diff_to_text(diff_items, old_lines, new_lines, k=k)
        lines.append(diff_text)
        
        return "\n".join(lines)
