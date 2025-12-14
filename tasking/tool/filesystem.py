"""
File system tool implementation with terminal integration.

This module provides a comprehensive file system tool that operates within a terminal's
workspace constraints, supporting both text editing and binary file operations.
"""

import os
import shlex
import base64
import mimetypes
import subprocess
from abc import ABC, abstractmethod
from typing import List, Literal, Optional
from dataclasses import dataclass

from loguru import logger

from .terminal import ITerminal


class IFileSystem(ABC):
    """文件系统接口"""

    @abstractmethod
    def get_terminal(self) -> ITerminal:
        """获取关联的终端实例。

        Returns:
            ITerminal: 关联的终端实例。
        """
        raise NotImplementedError("get_terminal 方法未实现")

    @abstractmethod
    async def run_command(self, command: str) -> str:
        """在终端中执行命令。

        Args:
            command: 要执行的命令字符串。

        Returns:
            命令的标准输出结果。
        """
        raise NotImplementedError("run_command 方法未实现")

    @abstractmethod
    def open_file(self, file_path: str) -> str:
        """打开并读取文件内容。

        Args:
            file_path: 目标文件路径。

        Returns:
            文件的base64编码内容。
        """
        raise NotImplementedError("open_file 方法未实现")

    @abstractmethod
    async def edit(self, file_path: str, operations: List['EditOperation']) -> None:
        """行级修改文本文件。

        Args:
            file_path: 目标文件路径。
            operations: 编辑操作列表。

        Raises:
            NotImplementedError: 未实现该方法。
        """
        raise NotImplementedError("edit 方法未实现")


@dataclass
class EditOperation:
    """文本编辑操作数据模型，表示单个行级编辑操作。

    核心字段：
    - line: 操作行号（从1开始，insert支持0=开头、-1=末尾）
    - op: 操作类型（'insert'/'modify'/'delete'）
    - content: 操作内容（delete操作可为空）
    """
    line: int
    op: Literal['insert', 'modify', 'delete']
    content: str


class FileSystem(IFileSystem):
    """基于 ITerminal 的文件系统工具类，支持文本编辑和二进制文件操作。

    核心特性：
    1. 依赖注入 ITerminal，复用其 workspace 安全约束和长期会话；
    2. edit 接口动态传入文件路径，支持编辑多个文本文件；
    3. open_file 接口支持读取任意文件并返回 base64 编码内容；
    4. run_command 接口提供终端命令执行能力；
    5. get_terminal 接口返回关联的终端实例；
    6. 支持删除/修改/新增行操作，自动处理行号偏移和特殊字符转义；
    7. 兼容 Linux/macOS 的 sed 语法差异；
    8. 检查终端的 allow_commands 与自身 allow_commands 的一致性；
    9. 检查终端是否禁用脚本执行（确保安全性）。
    """

    def __init__(
        self,
        terminal_instance: ITerminal,
        allow_commands: Optional[List[str]] = None
    ) -> None:
        """初始化文件系统工具，仅绑定终端实例（不固定文件路径）。

        Args:
            terminal_instance: ITerminal 实现类实例（如 LocalTerminal），提供命令执行能力，
                             所有文件操作均受其 workspace 安全约束限制。
            allow_commands: 允许的命令列表（白名单），必须与终端的 allow_commands 一致，
                           用于确保命令执行权限一致。默认为 None（继承终端设置）。

        Raises:
            RuntimeError: 若终端未启动、工作空间未初始化或命令列表不一致。
            ValueError: 若 allow_commands 与终端配置不一致。
        """
        self._terminal = terminal_instance
        self._workspace = terminal_instance.get_workspace()

        # 校验终端状态（确保已启动且有工作空间）
        if not self._workspace:
            raise RuntimeError("终端工作空间未初始化，无法创建文本编辑器")
        # Check if terminal has a process (for implementation classes that have it)
        if hasattr(terminal_instance, "_process"):
            process = getattr(terminal_instance, "_process", None)
            if process and process.poll() is not None:
                raise RuntimeError("终端未运行或已退出，无法创建文本编辑器")

        # 检查脚本执行状态（确保安全性）
        if not terminal_instance.is_script_execution_disabled():
            logger.warning("⚠️ 警告：终端未禁用脚本执行，存在安全风险")

        # 校验 allow_commands 与终端的一致性
        terminal_allowed = terminal_instance.get_allowed_commands()
        if allow_commands is None:
            # 未指定时继承终端设置
            self._allow_commands = terminal_allowed
        else:
            # 指定了则必须与终端一致
            if set(allow_commands) != set(terminal_allowed):
                raise ValueError(
                    f"allow_commands 与终端配置不一致：\n"
                    f"  传入：{allow_commands}\n"
                    f"  终端：{terminal_allowed}"
                )
            self._allow_commands = allow_commands

        # 记录 sed 兼容参数（Linux: -i; macOS: -i ''）
        self._sed_inplace_arg = self._get_sed_compatible_arg()

    def _get_sed_compatible_arg(self) -> List[str]:
        """获取 sed 原地修改的兼容参数（处理 Linux/macOS 差异）。"""
        try:
            # 简单的平台检测：Linux 使用 -i，macOS 使用 -i ''
            import platform
            system = platform.system()
            if system == "Darwin":
                return ["-i", ""]
            else:  # Linux and others
                return ["-i"]
        except Exception:
            # 默认使用 macOS 兼容模式（更安全）
            return ["-i", ""]

    def _escape_sed_content(self, content: str) -> str:
        r"""转义 sed 命令中的特殊字符（避免语法错误）。

        需转义的字符：
        - /：sed 分隔符，替换为 \\/
        - &：sed 引用匹配内容，替换为 \\&
        - \\：转义字符本身，替换为 \\\\
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

    async def _get_file_line_count(self, file_rel: str) -> int:
        """获取文件的总行数（用于校验行号有效性）。

        Args:
            file_rel: 相对于 workspace 的文件路径（终端内可直接访问）

        Returns:
            int: 文件总行数（文件不存在返回 0）
        """
        try:
            # 执行 wc -l 命令统计行数（过滤空行影响）
            # 使用 ls 检查文件是否存在（在允许列表中），如果文件不存在，wc 会失败，捕获异常
            cmd = f"wc -l < {shlex.quote(file_rel)} 2>/dev/null"
            try:
                output = await self._terminal.run_command(cmd)
                output_clean = output.strip().split('\n')[-1].strip()
                return int(output_clean) if output_clean.isdigit() else 0
            except (OSError, RuntimeError, subprocess.SubprocessError):
                # 文件不存在或命令失败，返回 0
                return 0
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
            # 命令执行失败（如文件不存在），返回 0
            return 0

    async def _ensure_parent_dir(self, file_abs: str) -> None:
        """确保文件的父目录存在（避免新建文件时目录不存在）。"""
        parent_dir = os.path.dirname(file_abs)
        if not os.path.exists(parent_dir):
            # 通过终端创建父目录（确保在 workspace 内）
            parent_dir_rel = os.path.relpath(parent_dir, self._workspace)
            cmd = f"mkdir -p {shlex.quote(parent_dir_rel)}"
            await self._terminal.run_command(cmd)
            logger.info(f"📁 自动创建父目录：{parent_dir}")

    async def edit(
        self,
        file_path: str,
        operations: List[EditOperation]
    ) -> None:
        """行级修改文本：支持删除（delete）、修改（modify）、新增（insert），动态指定文件路径。

        核心规则：
        1. operations 列表包含所有编辑操作，每个操作使用 EditOperation 表示；
        2. 行号从 1 开始，insert 操作支持 0（文件开头）、-1（文件末尾）；
        3. 默认允许新建文件（不支持新建则无法使用 insert 操作）；
        4. 自动按行号降序执行操作，避免删除/插入导致的行号偏移；
        5. 自动转义特殊字符，避免 sed 命令语法错误。

        Args:
            file_path: 目标文件路径（支持相对路径/绝对路径，必须在 workspace 内）；
            operations: 编辑操作列表（每个操作包含行号、操作类型和内容）。

        Raises:
            ValueError: 若操作类型非法、行号格式错误；
            FileNotFoundError: 若 modify/delete 操作时文件不存在；
            RuntimeError: 若文件路径超出 workspace 范围、行号超出文件实际行数、命令执行失败。
        """
        # 1. 基础参数校验
        if not operations:
            raise ValueError("operations 列表不能为空")

        allowed_ops = {"delete", "modify", "insert"}
        for idx, op in enumerate(operations):
            if op.op not in allowed_ops:
                raise ValueError(f"非法操作类型（索引 {idx}）：{op.op}，仅支持 {allowed_ops}")
            if not isinstance(op.line, int): # pyright: ignore[reportUnnecessaryIsInstance]
                raise ValueError(f"行号必须为整数（索引 {idx}）：{op.line}")
            # insert 允许 0（开头）、-1（末尾），其他操作行号必须 ≥1
            if op.op != "insert" and op.line < 1:
                raise ValueError(f"非 insert 操作的行号必须 ≥1（索引 {idx}）：{op.line}")

        # 2. 解析文件路径并校验
        file_abs, file_rel = self._resolve_file_path(file_path)
        file_exists = os.path.exists(file_abs)

        # 3. 文件存在性校验
        for idx, op in enumerate(operations):
            # modify/delete 操作必须要求文件存在
            if op.op in ("modify", "delete") and not file_exists:
                raise FileNotFoundError(
                    f"文件不存在，无法执行 {op.op} 操作（索引 {idx}）：{file_abs}"
                )

        # 4. 若文件不存在则创建（默认允许新建）
        if not file_exists:
            await self._ensure_parent_dir(file_abs)
            # 新建空文件（避免 sed 操作空文件报错）
            await self._terminal.run_command(f"touch {shlex.quote(file_rel)}")
            logger.info(f"📄 自动新建文件：{file_abs}")
            file_exists = True

        # 5. 校验行号有效性（modify/delete 行号不能超出文件实际行数）
        line_count = await self._get_file_line_count(file_rel) if file_exists else 0
        for idx, op in enumerate(operations):
            if op.op in ("modify", "delete"):
                if op.line > line_count:
                    raise RuntimeError(
                        f"{op.op} 操作行号超出文件实际行数（索引 {idx}）："
                        f"行号 {op.line}，文件总行数 {line_count}，文件：{file_abs}"
                    )

        # 6. 预处理操作：按行号降序排序（避免行号偏移）
        processed_ops: list[tuple[float, EditOperation]] = []
        for op in operations:
            if op.op == "insert":
                # insert 操作的 -1 转为极大值（最后执行），0 转为 1（最先执行）
                sort_key = float("inf") if op.line == -1 else 1 if op.line == 0 else op.line
            else:
                sort_key = op.line
            # 负号实现降序排序（sort 升序 = 原始行号降序）
            processed_ops.append((-sort_key, op))
        processed_ops.sort()

        # 7. 生成并执行每个操作的 sed 命令
        for _, op in processed_ops:
            escaped_content = self._escape_sed_content(op.content)
            file_rel_quoted = shlex.quote(file_rel)  # 转义文件路径中的特殊字符

            # 生成 sed 命令（基于操作类型）
            if op.op == "delete":
                # 删除第 N 行：sed -i '{line}d' file
                cmd = f"sed {''.join(self._sed_inplace_arg)} '{op.line}d' {file_rel_quoted}"
            elif op.op == "modify":
                # 修改第 N 行：sed -i '{line}c\内容' file（c 表示 replace）
                sed_args = ''.join(self._sed_inplace_arg)
                cmd = f"sed {sed_args} '{op.line}c\\{escaped_content}\\' {file_rel_quoted}"
            elif op.op == "insert":
                if op.line == 0:
                    # 插入到文件开头：对于空文件，使用 echo；对于非空文件，使用 sed
                    # 检查文件是否为空（使用 wc -l）
                    line_count = await self._get_file_line_count(file_rel)
                    if line_count == 0:
                        # 空文件，直接使用 echo 写入
                        cmd = f"echo '{escaped_content}' > {file_rel_quoted}"
                    else:
                        # 非空文件，使用 sed 的 1i 命令
                        sed_args = ''.join(self._sed_inplace_arg)
                        cmd = f"sed {sed_args} '1i\\{escaped_content}\\' {file_rel_quoted}"
                elif op.line == -1:
                    # 插入到文件末尾：echo >> file
                    # 对于 echo 命令，需要使用 shlex.quote 而不是 sed 转义
                    quoted_content = shlex.quote(op.content)
                    append_cmd = f"echo {quoted_content} >> {file_rel_quoted}"
                    cmd = append_cmd
                else:
                    # 插入到第 N 行之前：sed -i '{line}i\内容' file
                    sed_args = ''.join(self._sed_inplace_arg)
                    if not escaped_content:
                        # 空内容时，使用两步操作插入空行
                        # 方法：先使用 echo 追加空行到文件末尾，然后使用 sed 移动到正确位置
                        prev_line = op.line - 1
                        if prev_line > 0:
                            # 在第N-1行后插入空行
                            # 使用 sed 'Na\' 命令，如果失败则使用临时文件方法
                            # 先尝试 sed 'Na\'，如果失败则使用 echo + sed 组合
                            temp_marker = f"__EMPTY_{op.line}__"
                            # 先追加标记行
                            await self._terminal.run_command(f"echo '{temp_marker}' >> {file_rel_quoted}", allow_by_human=True)
                            # 使用 sed 将标记行移动到第N-1行后，然后删除标记（实际上就是插入空行）
                            # 使用 sed 的 r 命令读取空行
                            temp_empty = f"{file_rel_quoted}.empty"
                            await self._terminal.run_command(f"echo '' > {temp_empty}", allow_by_human=True)
                            # 使用 allow_by_human=True 来执行复合命令（包含多个 sed 和 rm 命令）
                            cmd1 = f"sed {sed_args} '{prev_line}r {temp_empty}' {file_rel_quoted}"
                            cmd2 = f"rm {temp_empty}"
                            cmd3 = f"sed {sed_args} '/{temp_marker}/d' {file_rel_quoted}"
                            await self._terminal.run_command(cmd1, allow_by_human=True)
                            await self._terminal.run_command(cmd2, allow_by_human=True)
                            await self._terminal.run_command(cmd3, allow_by_human=True)
                            content_summary = op.content[:50] + "..." if len(op.content) > 50 else op.content
                            logger.info(f"✅ 执行成功：{op.op} 行 {op.line} → 文件：{file_abs}，内容：{content_summary}")
                            continue  # 跳过后续的 run_command 调用
                        else:
                            # 在第1行前插入空行
                            temp_empty = f"{file_rel_quoted}.empty"
                            await self._terminal.run_command(f"echo '' > {temp_empty}", allow_by_human=True)
                            cmd = f"sed {sed_args} '1r {temp_empty}' {file_rel_quoted} && rm {temp_empty}"
                    else:
                        cmd = f"sed {sed_args} '{op.line}i\\{escaped_content}\\' {file_rel_quoted}"
            else:
                raise ValueError(f"未处理的操作类型：{op.op}")

            # 执行命令（依赖 Terminal 的安全校验，确保在 workspace 内）
            try:
                await self._terminal.run_command(cmd, allow_by_human=True)
                content_summary = op.content[:50] + "..." if len(op.content) > 50 else op.content
                logger.info(f"✅ 执行成功：{op.op} 行 {op.line} → 文件：{file_abs}，内容：{content_summary}")
            except Exception as e:
                raise RuntimeError(
                    f"执行失败：{op.op} 行 {op.line} → 文件：{file_abs}，错误：{str(e)}"
                ) from e

    def get_terminal(self) -> ITerminal:
        """获取关联的终端实例。

        Returns:
            ITerminal: 关联的终端实例。
        """
        return self._terminal

    async def run_command(self, command: str) -> str:
        """在终端中执行命令。

        Args:
            command: 要执行的命令字符串。

        Returns:
            命令的标准输出结果。
        """
        return await self._terminal.run_command(command)

    def open_file(self, file_path: str) -> str:
        """打开并读取文件内容。

        Args:
            file_path: 目标文件路径。

        Returns:
            文件的base64编码内容。
        """
        # 解析文件路径并校验
        file_abs, _ = self._resolve_file_path(file_path)

        # 检查文件是否存在
        if not os.path.exists(file_abs):
            raise FileNotFoundError(f"文件不存在：{file_abs}")

        # 检查文件是否在工作空间内（双重校验）
        if not file_abs.startswith(self._workspace):
            raise RuntimeError(f"文件路径超出 workspace 范围：{file_abs}")

        try:
            # 读取文件内容
            with open(file_abs, 'rb') as f:
                file_content = f.read()

            # 转换为 base64 编码
            content_encoded = base64.b64encode(file_content).decode('utf-8')

            # 尝试检测文件类型
            mime_type, _ = mimetypes.guess_type(file_abs)
            file_size = len(file_content)
            if mime_type:
                logger.info(
                    f"📄 文件读取成功：{file_abs}，类型：{mime_type}，大小：{file_size} 字节"
                )
            else:
                logger.info(f"📄 文件读取成功：{file_abs}，大小：{file_size} 字节")

            return content_encoded

        except (OSError, IOError) as e:
            raise RuntimeError(f"读取文件失败：{file_abs}，错误：{str(e)}") from e
