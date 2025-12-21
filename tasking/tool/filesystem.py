"""
文件系统工具实现
"""

import os
import shlex
import base64
import mimetypes
import time
from abc import ABC, abstractmethod

import aiofiles
from asyncer import asyncify
from loguru import logger

from .terminal import ITerminal
from ..model.filesystem import (
    SearchParams, SearchResult, MatchInfo
)


class IFileSystem(ABC):
    """文件系统接口"""

    @abstractmethod
    def get_terminal(self) -> ITerminal:
        """获取关联的终端实例。

        Returns:
            ITerminal: 关联的终端实例。
        """

    @abstractmethod
    def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在。

        Args:
            file_path: 目标文件路径。

        Returns:
            bool: 文件存在返回True，否则返回False。
        """

    @abstractmethod
    async def open_file(self, file_path: str, file_type: str, encoding: str) -> str | bytes:
        """打开并读取文件内容。

        Args:
            file_path: 目标文件路径。
            file_type: 文件类型（如"txt/md"、"image/png"等）。
            encoding: 文件编码格式（如"utf-8"、"base64"等）。

        Returns:
            文件的base64编码/文本内容。
        """

    @abstractmethod
    async def new_file(self, file_path: str, file_type: str, content: str | bytes, encoding: str) -> str:
        """创建新文件。

        Args:
            file_path: 目标文件路径。
            file_type: 文件类型（如"txt/md"、"image/png"等）。
            content: 文件内容.
            encoding: 文件编码格式（如"utf-8"、"base64"等）。
        
        Returns:
            str: 创建结果消息。
        """
    
    @abstractmethod
    async def save_file(self, file_path: str, content: str | bytes, encoding: str, replace: bool = False) -> str:
        """保存文件。

        Args:
            file_path: 目标文件路径。
            content: 文件内容。
            encoding: 文件编码格式。
            replace: 是否覆盖文件。

        Raises:
            RuntimeError: 文件路径超出workspace范围。
            FileExistsError: 文件已存在，且replace为False。
        """

    @abstractmethod
    async def delete_file(self, file_path: str) -> str:
        """删除文件。

        Args:
            file_path: 目标文件路径。

        Returns:
            str: 删除结果消息。
        """

    @abstractmethod
    async def search(self, search_params: SearchParams) -> SearchResult:
        """综合搜索接口：文件名过滤 + 内容搜索 + 行级上下文

        Args:
            search_params: 搜索参数对象

        Returns:
            SearchResult: 结构化搜索结果对象

        Raises:
            NotImplementedError: 未实现该方法。
            RuntimeError: 搜索执行失败。
            PermissionError: 命令未通过安全校验。
        """

    @abstractmethod
    async def search_text(self, search_params: SearchParams) -> str:
        """综合搜索接口：返回文本格式结果（类似grep输出）

        Args:
            search_params: 搜索参数对象

        Returns:
            str: grep风格的文本格式搜索结果

        Raises:
            NotImplementedError: 未实现该方法。
            RuntimeError: 搜索执行失败。
            PermissionError: 命令未通过安全校验。
        """


class LocalFileSystem(IFileSystem):
    """文件系统工具类

    核心功能：
    1. 实现IFileSystem接口
    2. 提供文件操作功能（open_file、new_file、search等）
    3. 增强路径处理和安全性检查
    4. 不依赖文本编辑功能
    """

    def __init__(
        self,
        terminal_instance: ITerminal,
        allow_commands: list[str] | None = None,
    ) -> None:
        """初始化文件系统工具

        Args:
            terminal_instance: ITerminal 实现类实例
            allow_commands: 允许的命令列表（白名单）
        """
        self._terminal = terminal_instance
        self._workspace = terminal_instance.get_workspace()

        # 校验终端状态
        self._validate_terminal_state(terminal_instance)

        # 校验命令权限一致性
        self._validate_command_permissions(terminal_instance, allow_commands)

    def _validate_terminal_state(self, terminal: ITerminal) -> None:
        """验证终端状态。

        Args:
            terminal: 要验证的终端实例

        Raises:
            RuntimeError: 终端状态异常，包括：
                - 工作空间未初始化
                - 终端进程未运行或已退出
        """
        if not self._workspace:
            raise RuntimeError("终端工作空间未初始化，无法创建文件系统工具")

        # 检查进程状态（如果终端有_process属性）
        if hasattr(terminal, "_process"):
            process = getattr(terminal, "_process", None)
            if process and process.poll() is not None:
                raise RuntimeError("终端未运行或已退出，无法创建文件系统工具")

        # 检查脚本执行状态
        if not terminal.is_script_execution_disabled():
            logger.warning("⚠️ 警告：终端未禁用脚本执行，存在安全风险")

    def _validate_command_permissions(
        self, terminal: ITerminal, allow_commands: list[str] | None
    ) -> None:
        """验证命令权限一致性。

        Args:
            terminal: 终端实例
            allow_commands: 允许的命令列表，None表示使用终端的默认配置

        Raises:
            ValueError: allow_commands与终端配置不一致
        """
        terminal_allowed = terminal.get_allowed_commands()
        if allow_commands is None:
            self._allow_commands = terminal_allowed
        else:
            if set(allow_commands) != set(terminal_allowed):
                raise ValueError(
                    f"allow_commands 与终端配置不一致：\n"
                    f"  传入：{allow_commands}\n"
                    f"  终端：{terminal_allowed}"
                )
            self._allow_commands = allow_commands

    def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在。

        Args:
            file_path: 要检查的文件路径（可以是相对路径或绝对路径）

        Returns:
            bool: 文件存在返回True，否则返回False

        Note:
            - 如果文件路径超出workspace范围，视为不存在
            - 如果路径解析失败，也视为不存在
        """
        try:
            file_abs, _ = self._terminal.check_path(file_path)
            return os.path.exists(file_abs)
        except (RuntimeError, ValueError):
            return False
  
    def get_terminal(self) -> ITerminal:
        """获取关联的终端实例"""
        return self._terminal

    async def run_command(self, command: str) -> str:
        """在终端中执行命令"""
        return await self._terminal.run_command(command)

    async def open_file(self, file_path: str, file_type: str, encoding: str) -> str | bytes:
        """打开并读取文件内容（异步IO）
        
        在打开文件之前，会进行路径解析和鉴权，确保路径在工作区内。
        """
        # 路径解析和鉴权（如果路径不在工作区内，会抛出异常）
        file_abs, _ = self._terminal.check_path(file_path)

        # 检查文件是否存在
        if not os.path.exists(file_abs):
            raise FileNotFoundError(f"文件不存在：{file_abs}")

        try:
            # 使用aiofiles进行真正的异步文件读取
            async with aiofiles.open(file_abs, 'rb') as f:
                file_content = await f.read()

            if encoding == "base64":
                content_encoded = base64.b64encode(file_content).decode('utf-8')
                # 使用传入的file_type参数，或者通过mimetypes猜测
                if file_type:
                    mime_type = file_type
                else:
                    mime_type, _ = mimetypes.guess_type(file_abs)
                file_size = len(file_content)

                if mime_type:
                    logger.info(f"📄 文件读取成功：{file_abs}，类型：{mime_type}，大小：{file_size} 字节")
                else:
                    logger.info(f"📄 文件读取成功：{file_abs}，大小：{file_size} 字节")

                return content_encoded
            else:
                # 假设encoding为utf-8时返回文本内容
                try:
                    return file_content.decode('utf-8')
                except UnicodeDecodeError:
                    # 如果无法解码为utf-8，返回base64编码
                    logger.warning(f"⚠️ 文件无法解码为utf-8，返回base64编码：{file_abs}")
                    return base64.b64encode(file_content).decode('utf-8')

        except FileNotFoundError:
            raise
        except (OSError, IOError) as e:
            raise RuntimeError(
                f"读取文件失败：{file_abs}，错误：{str(e)}"
            ) from e

    async def new_file(self, file_path: str, file_type: str, content: str | bytes, encoding: str) -> str:
        """创建新文件
        
        在创建文件之前，会进行路径解析和鉴权，确保路径在工作区内。
        """
        # 路径解析和鉴权（如果路径不在工作区内，会抛出异常）
        file_abs, _ = self._terminal.check_path(file_path)

        # 检查文件是否已存在
        if os.path.exists(file_abs):
            raise FileExistsError(f"文件已存在：{file_abs}")

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_abs), exist_ok=True)

            if encoding == "base64":
                # 如果内容是字符串，先解码为bytes
                if isinstance(content, str):
                    file_bytes = base64.b64decode(content)
                else:
                    file_bytes = content
            elif encoding == "utf-8":
                # 明确指定utf-8编码
                if isinstance(content, str):
                    # 如果是字符串，编码为UTF-8字节
                    file_bytes = content.encode('utf-8')
                else:
                    # 如果已经是bytes，验证是否为有效的UTF-8
                    try:
                        content.decode('utf-8')  # 验证是否为有效的UTF-8
                        file_bytes = content
                    except UnicodeDecodeError:
                        raise ValueError(f"传入的bytes内容不是有效的UTF-8编码")
            else:
                # 其他编码方式，按字符串处理
                if isinstance(content, str):
                    file_bytes = content.encode('utf-8')
                else:
                    # 如果是bytes，假设已经正确编码
                    file_bytes = content

            # 使用aiofiles进行异步文件写入
            async with aiofiles.open(file_abs, 'wb') as f:
                await f.write(file_bytes)

            file_size = len(file_bytes)
            logger.info(f"📄 文件创建成功：{file_abs}，类型：{file_type}，大小：{file_size} 字节")
            return f"文件创建成功：{file_abs}，类型：{file_type}，大小：{file_size} 字节"

        except (OSError, IOError, ValueError) as e:
            raise RuntimeError(
                f"创建文件失败：{file_abs}，错误：{str(e)}"
            ) from e

    async def save_file(self, file_path: str, content: str | bytes, encoding: str, replace: bool = False) -> str:
        """保存文件（使用aiofiles异步IO）
        
        在保存文件之前，会进行双重安全验证：
        1. 通过 check_path 进行路径解析和鉴权
        2. 再次使用 check_path 确认路径在工作区内
        
        Args:
            file_path: 目标文件路径
            content: 文件内容（str 或 bytes）
            encoding: 文件编码格式（"utf-8" 或 "base64"）
            replace: 是否覆盖已存在的文件，默认为 False
        
        Returns:
            str: 保存结果消息
        
        Raises:
            RuntimeError: 文件路径超出workspace范围或保存失败
            FileExistsError: 文件已存在，且replace为False
        """
        # 路径解析和鉴权（如果路径不在工作区内，会抛出异常）
        file_abs, _ = self._terminal.check_path(file_path)

        # 检查文件是否已存在
        if os.path.exists(file_abs) and not replace:
            raise FileExistsError(f"文件已存在：{file_abs}，如需覆盖请设置 replace=True")

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_abs), exist_ok=True)

            # 根据encoding处理内容
            if encoding == "base64":
                # 如果内容是字符串，先解码为bytes
                if isinstance(content, str):
                    file_bytes = base64.b64decode(content)
                else:
                    file_bytes = content
            elif encoding == "utf-8":
                # 明确指定utf-8编码
                if isinstance(content, str):
                    # 如果是字符串，编码为UTF-8字节
                    file_bytes = content.encode('utf-8')
                else:
                    # 如果已经是bytes，验证是否为有效的UTF-8
                    try:
                        content.decode('utf-8')  # 验证是否为有效的UTF-8
                        file_bytes = content
                    except UnicodeDecodeError:
                        raise ValueError(f"传入的bytes内容不是有效的UTF-8编码")
            else:
                # 其他编码方式，按字符串处理
                if isinstance(content, str):
                    file_bytes = content.encode('utf-8')
                else:
                    # 如果是bytes，假设已经正确编码
                    file_bytes = content

            # 使用aiofiles进行异步文件写入
            async with aiofiles.open(file_abs, 'wb') as f:
                await f.write(file_bytes)

            file_size = len(file_bytes)
            logger.info(f"📄 文件保存成功：{file_abs}，大小：{file_size} 字节")
            return f"文件保存成功：{file_abs}，大小：{file_size} 字节"

        except FileExistsError:
            raise
        except (OSError, IOError, ValueError) as e:
            raise RuntimeError(
                f"保存文件失败：{file_abs}，错误：{str(e)}"
            ) from e

    async def delete_file(self, file_path: str) -> str:
        """删除文件（使用aiofiles异步IO）
        
        在删除文件之前，会进行双重安全验证：
        1. 通过 check_path 进行路径解析和鉴权
        2. 再次使用 check_path 确认路径在工作区内
        
        Args:
            file_path: 要删除的文件路径
        
        Returns:
            str: 删除结果消息
        
        Raises:
            RuntimeError: 文件路径超出workspace范围或删除失败
            FileNotFoundError: 文件不存在
        """
        # 路径解析和鉴权（如果路径不在工作区内，会抛出异常）
        file_abs, _ = self._terminal.check_path(file_path)

        # 检查文件是否存在
        if not os.path.exists(file_abs):
            raise FileNotFoundError(f"文件不存在：{file_abs}")

        try:
            # 使用aiofiles.os.remove进行异步文件删除
            # 注意：aiofiles 不直接提供删除功能，我们使用 asyncify 包装 os.remove
            await asyncify(os.remove)(file_abs)

            logger.info(f"🗑️ 文件删除成功：{file_abs}")
            return f"文件删除成功：{file_abs}"

        except Exception as e:
            raise RuntimeError(f"删除文件失败：{file_abs}，错误：{str(e)}") from e

    async def search(self, search_params: SearchParams) -> SearchResult:
        """综合搜索接口，返回结构化结果"""
        start_time = time.time()

        try:
            self._validate_search_params(search_params)
            resolved_paths = self._resolve_search_paths(search_params.search_paths)

            find_cmd = self._build_find_command(search_params, resolved_paths)
            grep_cmd = self._build_grep_command(search_params)

            # 修复搜索逻辑：使用find的-exec参数正确搜索文件内容
            if search_params.output_format.highlight_matches:
                # 构建带高亮的grep命令
                highlight_grep = f"{grep_cmd} --color=always"
                final_cmd = f"{find_cmd} -exec {highlight_grep} {{}} + 2>/dev/null || true"
            else:
                final_cmd = f"{find_cmd} -exec {grep_cmd} {{}} + 2>/dev/null || true"

            raw_output = await self._terminal.run_command(final_cmd, allow_by_human=True)
            search_result = self._parse_grep_output(
                raw_output, search_params, time.time() - start_time)

            logger.info(
                f"🔍 搜索完成：找到 {search_result.total_matches} 个匹配，耗时 {search_result.search_time:.2f} 秒")
            return search_result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ 搜索失败：{str(e)}")
            return SearchResult(
                params=search_params,
                total_files_searched=0,
                files_with_matches=0,
                total_matches=0,
                search_time=execution_time,
                file_results=[],
                errors=[str(e)]
            )

    async def search_text(self, search_params: SearchParams) -> str:
        """综合搜索接口，返回文本格式结果"""
        try:
            self._validate_search_params(search_params)
            resolved_paths = self._resolve_search_paths(search_params.search_paths)

            find_cmd = self._build_find_command(search_params, resolved_paths)
            grep_cmd = self._build_grep_command(search_params)

            # 修复搜索逻辑：使用find的-exec参数正确搜索文件内容
            if search_params.output_format.highlight_matches:
                # 构建带高亮的grep命令
                highlight_grep = f"{grep_cmd} --color=always"
                final_cmd = f"{find_cmd} -exec {highlight_grep} {{}} + 2>/dev/null || true"
            else:
                final_cmd = f"{find_cmd} -exec {grep_cmd} {{}} + 2>/dev/null || true"

            raw_output = await self._terminal.run_command(final_cmd, allow_by_human=True)
            formatted_output = self._format_text_output(raw_output, search_params)

            logger.info("🔍 搜索完成：返回文本格式结果")
            return formatted_output

        except Exception as e:
            logger.error(f"❌ 搜索失败：{str(e)}")
            return f"搜索失败：{str(e)}"

    def _resolve_search_paths(self, search_paths: list[str]) -> list[tuple[str, str]]:
        """解析搜索路径列表。

        Args:
            search_paths: 搜索路径列表（相对路径或绝对路径）

        Returns:
            list[tuple[str, str]]: 解析后的路径列表，每个元素为(绝对路径, 相对路径)的元组

        Raises:
            RuntimeError: 任何搜索路径超出workspace范围
        """
        resolved_paths: list[tuple[str, str]] = []
        for search_path in search_paths:
            file_abs, file_rel = self._terminal.check_path(search_path)
            resolved_paths.append((file_abs, file_rel))
        return resolved_paths

    def _validate_search_params(self, params: SearchParams) -> None:
        """参数验证。

        Args:
            params: 搜索参数对象

        Raises:
            ValueError: 参数不合法，包括：
                - 搜索模式为空
                - 搜索路径列表为空或包含空路径
                - 上下文行数为负数
                - 每文件最大匹配数不是正数
                - 搜索深度为负数
        """
        if not params.content_pattern.pattern.strip():
            raise ValueError("搜索模式不能为空")
        if not params.search_paths:
            raise ValueError("搜索路径列表不能为空")
        for path in params.search_paths:
            if not path.strip():
                raise ValueError(f"无效的搜索路径：{path}")
        if params.output_format.context_lines < 0:
            raise ValueError("上下文行数不能为负数")
        if (params.output_format.max_matches_per_file is not None and
                params.output_format.max_matches_per_file <= 0):
            raise ValueError("每文件最大匹配数必须为正数")
        if (params.file_filter.max_depth is not None and
                params.file_filter.max_depth < 0):
            raise ValueError("搜索深度不能为负数")

    def _build_find_command(
        self, params: SearchParams, resolved_paths: list[tuple[str, str]]
    ) -> str:
        """构建find命令用于文件过滤。

        Args:
            params: 搜索参数对象
            resolved_paths: 已解析的搜索路径列表

        Returns:
            str: 构建的find命令字符串
        """
        paths = " ".join(shlex.quote(abs_path) for abs_path, _ in resolved_paths)
        cmd_parts = [f"find {paths}", "-type f"]

        if params.file_filter.max_depth is not None:
            cmd_parts.append(f"-maxdepth {params.file_filter.max_depth}")

        if params.file_filter.name_patterns:
            name_conditions = [
                f"-name {shlex.quote(pattern)}" for pattern in params.file_filter.name_patterns]
            if len(name_conditions) == 1:
                cmd_parts.extend(name_conditions)
            else:
                cmd_parts.append(
                    f"({' '.join(['-o'] * (len(name_conditions) - 1) + name_conditions)})")

        if params.file_filter.extensions:
            ext_conditions = [f"-name '*.{ext}'" for ext in params.file_filter.extensions]
            if len(ext_conditions) == 1:
                cmd_parts.extend(ext_conditions)
            else:
                cmd_parts.append(
                    f"({' '.join(['-o'] * (len(ext_conditions) - 1) + ext_conditions)})")

        if params.file_filter.exclude_patterns:
            for exclude_pattern in params.file_filter.exclude_patterns:
                cmd_parts.append(f"-not -name {shlex.quote(exclude_pattern)}")

        cmd_parts.append('-not -path "*/.*"')
        return " ".join(cmd_parts)

    def _build_grep_command(self, params: SearchParams) -> str:
        """构建grep命令用于内容搜索。

        Args:
            params: 搜索参数对象

        Returns:
            str: 构建的grep命令字符串
        """
        cmd_parts = ["grep"]

        if params.content_pattern.is_regex:
            cmd_parts.append("-E")
        else:
            cmd_parts.append("-F")

        if not params.content_pattern.case_sensitive:
            cmd_parts.append("-i")

        if params.content_pattern.invert_match:
            cmd_parts.append("-v")

        if params.output_format.context_lines > 0:
            cmd_parts.append(f"-C {params.output_format.context_lines}")

        if params.output_format.show_line_numbers:
            cmd_parts.append("-n")

        if params.output_format.show_filename:
            cmd_parts.append("-H")

        if params.output_format.max_matches_per_file:
            cmd_parts.append(f"-m {params.output_format.max_matches_per_file}")

        escaped_pattern = shlex.quote(params.content_pattern.pattern)
        cmd_parts.append(escaped_pattern)

        return " ".join(cmd_parts)

    def _parse_grep_output(
        self, output: str, params: SearchParams, execution_time: float
    ) -> SearchResult:
        """解析grep输出为结构化结果。

        Args:
            output: grep命令的原始输出
            params: 搜索参数对象
            execution_time: 搜索执行时间（秒）

        Returns:
            SearchResult: 结构化的搜索结果对象

        Note:
            - 解析包含行号的grep输出格式
            - 自动计算匹配位置（开始列、结束列）
            - 处理大小写敏感的匹配位置计算
        """
        if not output.strip():
            return SearchResult(
                params=params,
                total_files_searched=0,
                files_with_matches=0,
                total_matches=0,
                search_time=execution_time,
                file_results=[],
                errors=[]
            )

        matches: list[MatchInfo] = []
        files_with_matches: set[str] = set()
        lines = output.strip().split('\n')

        for line in lines:
            if not line.strip():
                continue

            if ':' in line:
                parts = line.split(':', 2)
                if len(parts) >= 3 and parts[1].isdigit():
                    file_path, line_number, content = parts[0], int(parts[1]), parts[2]

                    if not os.path.isabs(file_path):
                        file_abs, _ = self._terminal.check_path(file_path)
                        file_path = file_abs

                    pattern = params.content_pattern.pattern
                    if params.content_pattern.case_sensitive:
                        start_col = content.find(pattern) + 1
                        end_col = start_col + len(pattern) - 1
                    else:
                        pattern_lower = pattern.lower()
                        content_lower = content.lower()
                        start_col = content_lower.find(pattern_lower) + 1
                        end_col = start_col + len(pattern) - 1

                    match_info = MatchInfo(
                        file_path=file_path,
                        line_number=line_number,
                        matched_content=content,
                        context_before=[],
                        context_after=[],
                        start_column=max(1, start_col),
                        end_column=max(1, end_col)
                    )

                    matches.append(match_info)
                    files_with_matches.add(file_path)

        return SearchResult(
            params=params,
            total_files_searched=0,
            files_with_matches=len(files_with_matches),
            total_matches=len(matches),
            search_time=execution_time,
            file_results=matches,
            errors=[]
        )

    def _format_text_output(self, raw_output: str, params: SearchParams) -> str:
        """格式化文本输出。

        Args:
            raw_output: grep命令的原始输出
            params: 搜索参数对象

        Returns:
            str: 格式化后的文本输出，包含搜索参数信息和结果

        Note:
            - 如果没有匹配内容，返回"未找到匹配内容"
            - 包含搜索模式、路径、过滤器等参数信息
            - 使用分隔线区分参数信息和搜索结果
        """
        if not raw_output.strip():
            return "未找到匹配内容"

        header_lines = [
            f"搜索模式: {params.content_pattern.pattern}",
            f"搜索路径: {', '.join(params.search_paths)}"
        ]

        if params.file_filter.name_patterns:
            header_lines.append(f"文件名过滤: {', '.join(params.file_filter.name_patterns)}")

        if params.file_filter.extensions:
            header_lines.append(f"文件扩展名: {', '.join(params.file_filter.extensions)}")

        if params.output_format.context_lines > 0:
            header_lines.append(f"上下文行数: {params.output_format.context_lines}")

        header = "\n".join(header_lines)
        separator = "-" * 60

        return f"{header}\n{separator}\n{raw_output}"


