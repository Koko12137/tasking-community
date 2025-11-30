"""
Document editor tool implementation for line-based file editing.

This module provides a secure document editor that operates within a terminal's
workspace constraints, supporting line-level modifications across multiple files.
"""

import os
import shlex
from typing import List

from .terminal import ITerminal
from .terminal import SingleThreadTerminal


class DocumentEditor:
    """基于 ITerminal 的文档行级修改工具类（支持多文件+新建控制）。
    
    核心特性：
    1. 依赖注入 ITerminal，复用其 workspace 安全约束和长期会话；
    2. edit 接口动态传入文件路径，支持编辑多个文件；
    3. 新增 allow_create 参数，控制文件不存在时是否允许新建；
    4. 支持删除/修改/新增行操作，自动处理行号偏移和特殊字符转义；
    5. 兼容 Linux/macOS 的 sed 语法差异。
    """

    def __init__(self, terminal: ITerminal) -> None:
        """初始化文档编辑器，仅绑定终端实例（不固定文件路径）。
        
        Args:
            terminal: ITerminal 实现类实例（如 SingleThreadTerminal），提供命令执行能力，
                      所有文件操作均受其 workspace 安全约束限制。
        
        Raises:
            RuntimeError: 若终端未启动或工作空间未初始化。
        """
        self._terminal = terminal
        self._workspace = terminal.get_workspace()

        # 校验终端状态（确保已启动且有工作空间）
        if not self._workspace:
            raise RuntimeError("终端工作空间未初始化，无法创建文档编辑器")
        # Check if terminal has a process (for implementation classes that have it)
        if hasattr(terminal, "_process"):
            process = getattr(terminal, "_process", None)
            if process and process.poll() is not None:
                raise RuntimeError("终端未运行或已退出，无法创建文档编辑器")

        # 记录 sed 兼容参数（Linux: -i; macOS: -i ''）
        self._sed_inplace_arg = self._get_sed_compatible_arg()

    def _get_sed_compatible_arg(self) -> List[str]:
        """获取 sed 原地修改的兼容参数（处理 Linux/macOS 差异）。"""
        try:
            # 测试 sed -i 是否支持（Linux）
            self._terminal.run_command("sed -i 's/a/a/' /dev/null 2>/dev/null")
            return ["-i"]
        except (OSError, RuntimeError, PermissionError):
            # 不支持则使用 macOS 语法（-i ''）
            return ["-i", ""]

    def _escape_sed_content(self, content: str) -> str:
        """转义 sed 命令中的特殊字符（避免语法错误）。

        需转义的字符：
        - /：sed 分隔符，替换为 \/
        - &：sed 引用匹配内容，替换为 \&
        - \：转义字符本身，替换为 \\
        - 换行符：替换为 \\n（保持多行内容）
        """
        if not content:
            return ""
        escaped = content.replace("\\", "\\\\")  # 转义 \\
        escaped = escaped.replace("/", "\\/")    # 转义 \/
        escaped = escaped.replace("&", "\\&")    # 转义 \&
        escaped = escaped.replace("\n", "\\n")   # 转义换行符
        return escaped

    def _resolve_file_path(self, file_path: str) -> tuple[str, str]:
        """解析文件路径：返回（绝对路径，相对于 workspace 的相对路径）。
        
        路径规则：
        - 绝对路径：必须在终端 workspace 内（由 Terminal 安全校验保障）；
        - 相对路径：基于终端当前目录解析，最终仍需在 workspace 内。
        
        Returns:
            tuple[str, str]: (文件绝对路径, 相对于 workspace 的相对路径)
        """
        # 解析绝对路径
        if os.path.isabs(file_path):
            file_abs = file_path
        else:
            file_abs = os.path.abspath(os.path.join(self._terminal.get_current_dir(), file_path))

        # 校验路径是否在 workspace 内（依赖 Terminal 的安全约束）
        if not file_abs.startswith(self._workspace):
            raise RuntimeError(f"文件路径超出 workspace 范围：{file_abs}（workspace：{self._workspace}）")

        # 计算相对于 workspace 的相对路径（用于终端内执行命令，避免路径过长）
        file_rel = os.path.relpath(file_abs, self._workspace)
        return file_abs, file_rel

    def _get_file_line_count(self, file_rel: str) -> int:
        """获取文件的总行数（用于校验行号有效性）。
        
        Args:
            file_rel: 相对于 workspace 的文件路径（终端内可直接访问）
        
        Returns:
            int: 文件总行数（文件不存在返回 0）
        """
        try:
            # 执行 wc -l 命令统计行数（过滤空行影响）
            cmd = f"wc -l < {shlex.quote(file_rel)} 2>/dev/null"
            output = self._terminal.run_command(cmd)
            return int(output.strip()) if output.strip().isdigit() else 0
        except Exception:
            # 命令执行失败（如文件不存在），返回 0
            return 0

    def _ensure_parent_dir(self, file_abs: str) -> None:
        """确保文件的父目录存在（避免新建文件时目录不存在）。"""
        parent_dir = os.path.dirname(file_abs)
        if not os.path.exists(parent_dir):
            # 通过终端创建父目录（确保在 workspace 内）
            parent_dir_rel = os.path.relpath(parent_dir, self._workspace)
            cmd = f"mkdir -p {shlex.quote(parent_dir_rel)}"
            self._terminal.run_command(cmd)
            print(f"📁 自动创建父目录：{parent_dir}")

    def edit(self,
             file_path: str,
             lines: List[int],
             ops: List[str],
             contents: List[str],
             allow_create: bool = False) -> None:
        """行级修改文档：支持删除（delete）、修改（modify）、新增（insert），动态指定文件路径。
        
        核心规则：
        1. 三个入参列表（lines/ops/contents）长度必须完全一致（一一对应每行操作）；
        2. 行号从 1 开始，insert 操作支持 0（文件开头）、-1（文件末尾）；
        3. allow_create：文件不存在时是否允许新建（仅对 insert 操作有效，modify/delete 仍需文件存在）；
        4. 自动按行号降序执行操作，避免删除/插入导致的行号偏移；
        5. 自动转义特殊字符，避免 sed 命令语法错误。
        
        Args:
            file_path: 目标文件路径（支持相对路径/绝对路径，必须在 workspace 内）；
            lines: 操作行号列表（如 [2, 5] 表示操作第 2 行和第 5 行）；
            ops: 操作类型列表（仅支持 'delete'/'modify'/'insert'，如 ['modify', 'insert']）；
            contents: 操作内容列表（delete 操作忽略内容，modify/insert 需传对应内容）；
            allow_create: 文件不存在时是否允许新建（默认 False，不允许）。
        
        Raises:
            ValueError: 若入参列表长度不一致、操作类型非法、行号格式错误；
            FileNotFoundError: 若文件不存在且不允许新建（allow_create=False），或 modify/delete 操作时文件不存在；
            RuntimeError: 若文件路径超出 workspace 范围、行号超出文件实际行数、命令执行失败。
        """
        # 1. 基础参数校验（长度+类型+行号格式）
        if len(lines) != len(ops) != len(contents):
            raise ValueError(f"入参列表长度不一致：lines={len(lines)}, ops={len(ops)}, contents={len(contents)}")
        
        allowed_ops = {"delete", "modify", "insert"}
        for idx, op in enumerate(ops):
            if op not in allowed_ops:
                raise ValueError(f"非法操作类型（索引 {idx}）：{op}，仅支持 {allowed_ops}")
        
        for idx, (line, op) in enumerate(zip(lines, ops)):
            if not isinstance(line, int):
                raise ValueError(f"行号必须为整数（索引 {idx}）：{line}")
            # insert 允许 0（开头）、-1（末尾），其他操作行号必须 ≥1
            if op != "insert" and line < 1:
                raise ValueError(f"非 insert 操作的行号必须 ≥1（索引 {idx}）：{line}")

        # 2. 解析文件路径并校验
        file_abs, file_rel = self._resolve_file_path(file_path)
        file_exists = os.path.exists(file_abs)

        # 3. 文件存在性校验（结合 allow_create 和操作类型）
        for idx, (line, op) in enumerate(zip(lines, ops)):
            # modify/delete 操作必须要求文件存在（无论 allow_create 是什么）
            if op in ("modify", "delete") and not file_exists:
                raise FileNotFoundError(
                    f"文件不存在，无法执行 {op} 操作（索引 {idx}）：{file_abs}（allow_create={allow_create}）"
                )
            # insert 操作：文件不存在且不允许新建 → 报错
            if op == "insert" and not file_exists and not allow_create:
                raise FileNotFoundError(
                    f"文件不存在，且不允许新建（allow_create=False），无法执行 insert 操作（索引 {idx}）：{file_abs}"
                )

        # 4. 若允许新建且文件不存在 → 确保父目录存在（避免写入失败）
        if not file_exists and allow_create:
            self._ensure_parent_dir(file_abs)
            # 新建空文件（避免 sed 操作空文件报错）
            self._terminal.run_command(f"touch {shlex.quote(file_rel)}")
            print(f"📄 自动新建文件：{file_abs}")
            file_exists = True  # 新建后标记为存在

        # 5. 校验行号有效性（modify/delete 行号不能超出文件实际行数）
        line_count = self._get_file_line_count(file_rel) if file_exists else 0
        for idx, (line, op) in enumerate(zip(lines, ops)):
            if op in ("modify", "delete"):
                if line > line_count:
                    raise RuntimeError(
                        f"{op} 操作行号超出文件实际行数（索引 {idx}）：行号 {line}，文件总行数 {line_count}，文件：{file_abs}"
                    )

        # 6. 预处理操作：按行号降序排序（避免行号偏移）
        processed_ops = []
        for line, op, content in zip(lines, ops, contents):
            if op == "insert":
                # insert 操作的 -1 转为极大值（最后执行），0 转为 1（最先执行）
                sort_key = float("inf") if line == -1 else 1 if line == 0 else line
            else:
                sort_key = line
            # 负号实现降序排序（sort 升序 = 原始行号降序）
            processed_ops.append((-sort_key, line, op, content))
        processed_ops.sort()

        # 7. 生成并执行每个操作的 sed 命令
        for _, line, op, content in processed_ops:
            escaped_content = self._escape_sed_content(content)
            file_rel_quoted = shlex.quote(file_rel)  # 转义文件路径中的特殊字符

            # 生成 sed 命令（基于操作类型）
            if op == "delete":
                # 删除第 N 行：sed -i '{line}d' file
                cmd = f"sed {''.join(self._sed_inplace_arg)} '{line}d' {file_rel_quoted}"
            elif op == "modify":
                # 修改第 N 行：sed -i '{line}c\内容' file（c 表示 replace）
                cmd = f"sed {''.join(self._sed_inplace_arg)} '{line}c\\{escaped_content}' {file_rel_quoted}"
            elif op == "insert":
                if line == 0:
                    # 插入到文件开头：sed -i '1i\内容' file
                    cmd = f"sed {''.join(self._sed_inplace_arg)} '1i\\{escaped_content}' {file_rel_quoted}"
                elif line == -1:
                    # 插入到文件末尾：sed -i '$i\内容' file（$ 表示最后一行）
                    cmd = f"sed {''.join(self._sed_inplace_arg)} '$i\\{escaped_content}' {file_rel_quoted}"
                else:
                    # 插入到第 N 行之前：sed -i '{line}i\内容' file
                    cmd = f"sed {''.join(self._sed_inplace_arg)} '{line}i\\{escaped_content}' {file_rel_quoted}"
            else:
                raise ValueError(f"未处理的操作类型：{op}")

            # 执行命令（依赖 Terminal 的安全校验，确保在 workspace 内）
            try:
                self._terminal.run_command(cmd)
                content_summary = content[:50] + "..." if len(content) > 50 else content
                print(f"✅ 执行成功：{op} 行 {line} → 文件：{file_abs}，内容：{content_summary}")
            except Exception as e:
                raise RuntimeError(
                    f"执行失败：{op} 行 {line} → 文件：{file_abs}，错误：{str(e)}"
                ) from e


# ------------------------------
# 示例用法（验证多文件+新建控制）
# ------------------------------
if __name__ == "__main__":
    try:
        # 1. 初始化 Terminal（强制注入 workspace，自动创建）
        test_workspace = os.path.join(os.getcwd(), "multi_doc_edit_workspace")
        terminal = SingleThreadTerminal(
            workspace=test_workspace,
            create_workspace=True
        )
        print(f"📋 Terminal 初始化完成：")
        print(f"   工作空间：{terminal.get_workspace()}")
        print(f"   当前目录：{terminal.get_current_dir()}\n")

        # 2. 初始化文档编辑器（仅绑定 Terminal，不固定文件）
        editor = DocumentEditor(terminal=terminal)
        print(f"✅ 文档编辑器初始化完成（支持多文件编辑）\n")

        # 3. 测试1：编辑不存在的文件（allow_create=True → 新建并插入内容）
        print("=== 测试1：新建文件并插入内容（allow_create=True） ===")
        file1 = "doc1.txt"  # 相对路径（workspace 根目录）
        editor.edit(
            file_path=file1,
            lines=[0, -1],
            ops=["insert", "insert"],
            contents=["doc1 开头的第一行", "doc1 末尾的最后一行"],
            allow_create=True  # 允许新建
        )
        # 查看文件内容
        cat_output = terminal.run_command(f"cat {shlex.quote(file1)}")
        print(f"📄 {file1} 内容：\n{cat_output}\n")

        # 4. 测试2：编辑已存在的文件（modify+delete 操作）
        print("=== 测试2：编辑已存在文件（modify+delete） ===")
        editor.edit(
            file_path=file1,
            lines=[2, 1],
            ops=["delete", "modify"],
            contents=["忽略", "doc1 修改后的第一行"],
            allow_create=False  # 无需新建（文件已存在）
        )
        # 查看文件内容
        cat_output = terminal.run_command(f"cat {shlex.quote(file1)}")
        print(f"📄 {file1} 修改后内容：\n{cat_output}\n")

        # 5. 测试3：编辑子目录文件（自动创建父目录）
        print("=== 测试3：编辑子目录文件（自动创建父目录） ===")
        file2 = "subdir/doc2.txt"  # 子目录文件（父目录不存在）
        editor.edit(
            file_path=file2,
            lines=[0, 2],
            ops=["insert", "insert"],
            contents=["子目录文件 doc2 的第一行", "子目录文件 doc2 的第三行"],
            allow_create=True
        )
        # 查看文件内容
        cat_output = terminal.run_command(f"cat {shlex.quote(file2)}")
        print(f"📄 {file2} 内容：\n{cat_output}\n")

        # 6. 测试4：编辑不存在的文件（allow_create=False → 报错）
        print("=== 测试4：文件不存在且不允许新建（allow_create=False） ===")
        file3 = "nonexistent_doc.txt"
        try:
            editor.edit(
                file_path=file3,
                lines=[0],
                ops=["insert"],
                contents=["测试内容"],
                allow_create=False  # 不允许新建
            )
        except FileNotFoundError as e:
            print(f"✅ 预期错误：{e}\n")

        # 7. 测试5：modify 不存在的文件（无论 allow_create 均报错）
        print("=== 测试5：modify 不存在的文件 ===")
        try:
            editor.edit(
                file_path=file3,
                lines=[1],
                ops=["modify"],
                contents=["测试修改"],
                allow_create=True  # 即使允许新建，modify 仍需文件存在
            )
        except FileNotFoundError as e:
            print(f"✅ 预期错误：{e}\n")

    except Exception as e:
        print(f"❌ 示例执行异常：{str(e)}")
    finally:
        # 清理资源
        terminal = locals().get('terminal')
        if terminal:
            terminal.close()
        print("✅ 资源清理完成")
