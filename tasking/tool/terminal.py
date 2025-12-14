"""
Terminal tool implementation providing secure command execution within a workspace.

This module implements a terminal abstraction with safety constraints, including
workspace restrictions, command whitelisting/blacklisting, and script execution control.
"""

import asyncio
import os
import subprocess
import shlex
import re
import platform
import signal
from abc import ABC, abstractmethod
from uuid import uuid4
from pathlib import Path
from typing import List, Optional

from loguru import logger
from asyncer import syncify

# ------------------------------
# 核心常量定义（私有，避免外部修改）
# ------------------------------
# 命令执行完成标记（用于分割输出）
_COMMAND_DONE_MARKER = "__SINGLE_THREAD_TERMINAL_EXEC_DONE__"

# 禁止命令正则列表（支持复杂匹配：批量删除、跨层级删除、提权变体）
# 优先级：绝对禁止（无论是否人类允许）> 条件禁止（非人类允许时拦截）
# 使用更宽松的 typing（object），在使用处统一转换为 str/decoded bytes
_PROHIBITED_REGEX: list[dict[str, object]] = [
    # 1. 绝对禁止命令（即使人类允许也拦截，系统级危险操作）
    {
        "regex": r'rm -rf\s+/',                  # 根目录删除（rm -rf /、rm -rf /xxx）
        "desc": "系统根目录删除",
        "is_absolute": True
    },
    {
        "regex": r'(dd if=/dev/(zero|null))|(> /dev/sda)',  # 硬件破坏
        "desc": "硬件写入破坏",
        "is_absolute": True
    },
    {
        "regex": r'(mkfs)|(fdisk\s+/)|(format)',  # 磁盘格式化
        "desc": "磁盘格式化",
        "is_absolute": True
    },
    {
        "regex": r'(shutdown\s+(-h\s+)?now)|(reboot\s+now)',  # 强制关机重启（shutdown now、shutdown -h now、reboot now）
        "desc": "强制关机/重启",
        "is_absolute": True
    },

    # 2. 高风险操作拦截（批量/跨层级删除，无论是否人类允许均拦截）
    {
        "regex": r'rm -rf\s+(\*|\./\*|\.\*)',    # 批量删除（rm -rf *、rm -rf ./*）
        "desc": "workspace内批量删除",
        "is_absolute": True  # 批量删除风险过高，即使人类允许也拦截
    },
    {
        "regex": r'rm -rf\s+\.\.(\/|$)',         # 跨层级删除（rm -rf ../、rm -rf ../xxx）
        "desc": "跨层级删除",
        "is_absolute": True
    },

    # 3. 提权命令拦截（所有变体，无论是否人类允许均拦截）
    {
        "regex": r'\bsudo\b',                    # 提权命令（sudo、sudo -i、/usr/bin/sudo）
        "desc": "sudo提权",
        "is_absolute": True
    },
    {
        "regex": r'\bsu\b',                      # su提权（su、su root、su -）
        "desc": "su提权",
        "is_absolute": True
    },
    {
        "regex": r'(passwd root)|(chpasswd)',    # 根密码修改
        "desc": "根密码修改",
        "is_absolute": True
    },

    # 4. 文件权限修改命令（非人类允许时拦截）
    {
        "regex": r'\bchmod\b',                    # 文件权限修改（chmod、chmod 777、chmod +x）
        "desc": "文件权限修改",
        "is_absolute": False
    },
    
    # 5. 软件包/系统管理命令（非人类允许时拦截）
    {
        "regex": r'(apt\s+)|(apt-get\s+)|(yum\s+)|(dnf\s+)|(brew\s+)|(dpkg\s+)|(rpm\s+)',
        "desc": "软件包管理",
        "is_absolute": False
    }
]

# 命令分隔符正则表达式（用于分割复合命令）
_COMMAND_SEPARATORS_PATTERN = re.compile(
    r'[;&|]|&&|\|\||\n',
    re.IGNORECASE
)
# 路径类命令清单（需重点校验路径参数的命令，用于强化日志提示）
_PATH_SENSITIVE_COMMANDS = ["find", "grep", "ls", "cp", "mv", "rm", "cat", "sed", "cd"]

# rm命令精准删除校验正则（仅允许单个具体路径，排除通配符/批量符号）
_RM_SAFE_PATH_PATTERN = re.compile(r'^[\w./-]+$')  # 只允许字母、数字、./-，无*、..


class ITerminal(ABC):
    """终端操作抽象接口，新增允许命令列表与脚本执行控制能力。

    安全检查顺序（严格遵循）：
    1. 允许命令列表检查（非空时，仅允许列表内命令）
    2. 脚本执行检查（若禁用，拒绝所有脚本解释器命令）
    3. 逃逸禁止命令检查（拒绝嵌套在引号/反引号中的禁止命令）
    4. 禁止命令列表检查（拒绝列表内的危险命令）
    5. 路径范围检查（所有涉及路径的命令，均需在工作空间内）
    """

    @abstractmethod
    def get_id(self) -> str:
        """获取终端唯一标识符（实例化时自动生成）。

        Returns:
            str: 终端唯一ID字符串（如"terminal_1234567890"）。
        """
        raise NotImplementedError

    @abstractmethod
    def get_workspace(self) -> str:
        """获取终端绑定的工作空间绝对路径（初始化后不可修改）。

        Returns:
            str: 工作空间绝对路径（如"/home/user/safe_ws"）。

        Raises:
            RuntimeError: 工作空间未初始化（构造函数强制注入，理论不触发）。
        """
        raise NotImplementedError
    
    @abstractmethod
    async def cd_to_workspace(self) -> None:
        """切换终端当前目录"""
        raise NotImplementedError

    @abstractmethod
    def get_current_dir(self) -> str:
        """获取终端当前会话的工作目录（与bash状态实时同步）。

        Returns:
            str: 当前目录绝对路径（如"/home/user/safe_w录切换到workspace根目录，并同步内部状态。

        Raises:
            RuntimeError: workspace未初始化或终端未启动。
        """
        raise NotImplementedError

    @abstractmethod
    def get_allowed_commands(self) -> List[str]:
        """获取终端允许执行的命令列表（白名单）。

        规则：
        - 列表为空时：允许除「禁止命令列表」外的所有命令
        - 列表非空时：仅允许包含列表中命令的操作（如允许"ls"则允许"ls -l"）

        Returns:
            List[str]: 允许命令列表（如["ls", "cd", "touch", "grep"]）。
        """
        raise NotImplementedError

    @abstractmethod
    def is_script_execution_disabled(self) -> bool:
        """获取是否禁用脚本执行的开关状态。

        禁用时拒绝所有脚本解释器命令（如python、bash、go run等）。

        Returns:
            bool: True=禁用脚本执行，False=允许脚本执行。
        """
        raise NotImplementedError

    @abstractmethod
    def open(self) -> None:
        """启动长期bash进程，初始化终端会话（实例化时自动调用）。

        Raises:
            RuntimeError: 进程已运行或启动失败（如bash未安装、权限不足）。
        """
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """优雅关闭终端进程，释放资源（必须显式调用）。

        流程：关闭输入管道→发送终止信号→5秒超时后强制杀死。

        Raises:
            RuntimeError: 进程超时未退出（强制杀死后抛出）。
        """
        raise NotImplementedError

    @abstractmethod
    async def acquire(self) -> None:
        """获取终端使用信号量，确保并发安全。

        同一时刻只能有一个任务获取此信号量并使用终端。
        调用方必须在完成终端操作后调用 release() 释放信号量。

        建议使用模式：
        ```
        await terminal.acquire()
        try:
            await terminal.run_command("ls")
        finally:
            await terminal.release()
        ```

        Raises:
            RuntimeError: 终端未启动或信号量获取失败。
        """
        raise NotImplementedError

    @abstractmethod
    async def release(self) -> None:
        """释放终端使用信号量，唤醒等待的任务。

        Raises:
            RuntimeError: 终端未启动或信号量释放失败。
            RuntimeError: 未获取信号量就尝试释放。
        """
        raise NotImplementedError

    @abstractmethod
    def check_command(self, command: str, allow_by_human: bool = False) -> bool:
        """按固定顺序执行命令安全校验，返回是否可执行。
        重点强化：find/grep等路径类命令的越界拦截，所有路径参数需在工作空间内。

        安全检查顺序（严格遵循）：
        1. 允许命令列表检查（非空时，仅允许列表内命令）
        2. 脚本执行检查（若禁用，拒绝所有脚本解释器命令）
        3. 逃逸禁止命令检查（拒绝嵌套在引号/反引号中的禁止命令）
        4. 禁止命令列表检查（拒绝列表内的危险命令）
        5. 路径范围检查（所有涉及路径的命令，均需在工作空间内）

        Args:
            command: 待校验的bash命令字符串。
            allow_by_human: 是否由人类用户允许执行（True时跳过白名单和脚本限制）

        Returns:
            bool: True=命令安全可执行，False=命令不安全。

        Raises:
            RuntimeError: 工作空间未初始化或当前目录未同步。
        """
        raise NotImplementedError

    @abstractmethod
    async def run_command(
        self, command: str, allow_by_human: bool = False, timeout: Optional[float] = None
    ) -> str:
        """执行bash命令，返回输出并同步终端状态（异步版本，含安全校验）。

        Args:
            command: 待执行的bash命令（如"grep 'key' ./file.txt"、"find ./src -name '*.py'"）。
            allow_by_human: 被人类允许执行
            timeout: 超时时间（秒），None表示不限制超时。使用协程超时机制。

        Returns:
            str: 命令标准输出（已过滤空行与标记）。

        Raises:
            RuntimeError: 终端未启动或工作空间未初始化。
            PermissionError: 命令未通过安全校验（如在黑名单、路径越界）。
            subprocess.SubprocessError: 命令执行中发生IO错误。
            TimeoutError: 命令执行超时。
        """
        raise NotImplementedError

    @abstractmethod
    async def read_process(self, stop_word: str) -> str:
        """读取终端输出。

        Returns:
            str: 终端标准输出。
        """
        raise NotImplementedError

    @abstractmethod
    async def write_process(self, data: str) -> None:
        """写入终端输入并等待输出完成。

        Args:
            data: 要写入的数据。
            
        Note:
            写入后会等待命令执行完成（通过读取完成标记）。
        """
        raise NotImplementedError


class LocalTerminal(ITerminal):
    """本地终端实现类，支持允许命令列表、脚本禁用与状态同步。

    核心特性：
    - 构造函数强制注入根目录，工作空间默认为根目录
    - 允许列表（白名单）与禁止列表（黑名单）双重控制
    - 默认禁用脚本执行，防止通过脚本逃逸工作空间限制
    - 实时同步终端当前目录，支持cd命令在工作空间内自由跳转
    - 人类允许时可以跳出workspace，但绝对禁止危险命令
    - 强化路径校验：find/grep等路径类命令均需通过工作空间边界检查
    - 线程安全：通过 threading.RLock 确保同一时刻只有一个线程使用终端

    平台支持：
    - ✅ Linux：完全支持（使用 /proc/<pid>/cwd 获取真实目录）
    - ✅ macOS (Darwin)：完全支持（使用 pwd -P 获取真实目录）
    - ❌ Windows：不支持（需要 bash 和 /proc 文件系统）
    - ❌ 其他系统：不支持

    注意：此实现依赖于 Unix/Linux 系统的特性（如 bash、/proc 文件系统），
    在 Windows 系统上无法运行。如需 Windows 支持，请使用其他终端实现。
    """
    _terminal_id: str                   # 终端唯一标识符
    _root_dir: str                      # 根目录路径（绝对路径）
    _workspace: str                     # 工作空间（绝对路径，默认为root_dir）
    _current_dir: str                   # 终端当前目录（与bash实时同步）
    _process: subprocess.Popen[str]     # 长期bash进程
    _allowed_commands: List[str]        # 允许命令列表（白名单）
    _disable_script_execution: bool     # 是否禁用脚本执行
    _lock: asyncio.Lock                 # 异步锁，确保并发安全
    _init_commands: list[str]           # 初始化命令

    def __init__(
        self,
        root_dir: str,
        workspace: str | None = None,
        create_workspace: bool = False,
        allowed_commands: list[str] | None = None,
        disable_script_execution: bool = True,
        init_commands: list[str] | None = None,
    ) -> None:
        """终端实例化构造函数，强制注入工作空间与安全控制参数。

        Args:
            root_dir: 根目录路径（必须为绝对路径），所有工作空间的基准路径（必需参数）。
            workspace: 终端绑定的工作空间路径（相对于root_dir，或root_dir下的绝对路径，默认为None则使用root_dir）。
            create_workspace: 工作空间不存在时是否自动创建（默认False）。
            allowed_commands: 允许命令列表（白名单），默认空列表（允许除禁止外的所有命令）。
            disable_script_execution: 是否禁用脚本执行（默认True，拒绝python/bash等脚本）。

        Raises:
            ValueError: root_dir不是绝对路径，或绝对路径的workspace不在root_dir下。
            FileNotFoundError: 根目录或工作空间不存在且create_workspace=False。
            NotADirectoryError: root_dir或workspace路径存在但不是目录。
            RuntimeError: 终端进程启动失败或不支持当前操作系统。
        """
        # 检查当前系统，仅支持类Unix系统（Linux、macOS等）
        current_system = platform.system()
        if current_system not in {"Linux", "Darwin"}:
            supported_systems = "Linux 和 macOS (Darwin)"
            raise RuntimeError(
                f"LocalTerminal 仅支持类 Unix 系统（{supported_systems}），"
                f"当前系统为：{current_system}\n"
                f"\n"
                f"原因：此实现依赖于 Unix/Linux 系统特性：\n"
                f"  - bash shell（Windows 默认使用 cmd/PowerShell）\n"
                f"  - /proc 文件系统（用于获取进程真实目录）\n"
                f"  - fcntl 模块（用于非阻塞 I/O）\n"
                f"\n"
                f"解决方案：\n"
                f"  - 在 Linux 或 macOS 系统上运行\n"
                f"  - 在 Windows 上使用 WSL (Windows Subsystem for Linux)\n"
                f"  - 或使用其他支持 Windows 的终端实现"
            )
        
        self._terminal_id = uuid4().hex  # 生成唯一终端ID
        self._lock = asyncio.Lock()      # 初始化异步锁

        # 1. 处理根目录：必须传入绝对路径
        if not os.path.isabs(root_dir):
            raise ValueError(f"root_dir必须是绝对路径，当前传入：{root_dir}")

        root_dir_abs = os.path.abspath(root_dir)
        if not os.path.exists(root_dir_abs):
            raise FileNotFoundError(f"根目录不存在：{root_dir_abs}")
        if not os.path.isdir(root_dir_abs):
            raise NotADirectoryError(f"根目录路径不是目录：{root_dir_abs}")
        self._root_dir = root_dir_abs

        # 2. 处理工作空间：基于根目录解析工作空间路径
        if workspace is None:
            # 如果workspace为None，默认使用root_dir作为workspace
            workspace_abs = self._root_dir
            logger.info(f"📁 工作空间未指定，使用根目录作为工作空间：{workspace_abs}")
        elif os.path.isabs(workspace):
            # 如果workspace是绝对路径，必须确保在root_dir下
            workspace_abs = os.path.abspath(workspace)
            if not workspace_abs.startswith(self._root_dir):
                raise ValueError(
                    f"绝对路径的工作空间必须在root_dir下：\n"
                    f"  root_dir: {self._root_dir}\n"
                    f"  workspace: {workspace_abs}"
                )
        else:
            # 如果workspace是相对路径，相对于root_dir解析
            workspace_abs = os.path.abspath(os.path.join(self._root_dir, workspace))

        # 3. 校验工作空间，必要时创建
        if not os.path.exists(workspace_abs):
            if create_workspace:
                os.makedirs(workspace_abs, exist_ok=True)
                logger.info(f"📁 自动创建工作空间：{workspace_abs}")
            else:
                raise FileNotFoundError(
                    f"工作空间不存在：{workspace_abs}，可设置create_workspace=True自动创建"
                )
        if not os.path.isdir(workspace_abs):
            raise NotADirectoryError(f"路径不是目录，无法作为工作空间：{workspace_abs}")
        self._workspace = workspace_abs

        # 2. 初始化安全控制参数（处理默认值，避免外部修改内部列表）
        self._allowed_commands = allowed_commands.copy() if allowed_commands else []
        self._disable_script_execution = disable_script_execution

        # 3. 初始化终端状态，启动进程
        self._current_dir = ""
        self.open()  # 自动启动终端进程

        self._init_commands = init_commands if init_commands is not None else []
        # 4. 同步运行异步初始化命令
        try:
            # 优先尝试 syncify（正常情况）
            try:
                syncify(self.run_init_commands)()
            except Exception as syncify_error:
                # syncify失败时，尝试使用 asyncio.run（无事件循环情况）
                try:
                    asyncio.run(self.run_init_commands())
                except RuntimeError:
                    # 也有事件循环，但syncify不兼容（如pytest async模式），使用concurrent.futures
                    logger.warning(f"syncify和asyncio.run都失败，使用ThreadPoolExecutor fallback: {syncify_error}")
                    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(lambda: asyncio.run(self.run_init_commands()))
                        try:
                            future.result(timeout=10)
                        except FutureTimeoutError:
                            raise RuntimeError("终端初始化超时")
        except Exception as e:
            logger.error(f"终端初始化失败: {e}")
            raise

    async def run_init_commands(self) -> None:
        """运行初始化命令（异步版本）"""
        # 直接切换到工作空间目录（初始化时允许从任何目录切换）
        logger.info(f"🔄 切换到工作空间目录：{self._workspace}")
        try:
            # 直接发送cd命令，绕过安全检查（因为这是初始化步骤）
            # 使用 shlex.quote 转义路径，处理特殊字符
            quoted_workspace = shlex.quote(self._workspace)
            cd_cmd = f"cd {quoted_workspace}"
            await self.write_process(cd_cmd)
            # 同步当前目录（现在目录已经在workspace内，使用正常同步方法）
            await self._sync_current_dir()
            logger.info(f"✅ 已切换到工作空间目录：{self._current_dir}")
        except Exception as e:
            logger.error(f"❌ 切换到工作空间目录失败：{e}")
            raise

        for cmd in self._init_commands:
            try:
                await self.run_command(cmd)
                logger.info(f"✅ 初始化命令执行成功：{cmd}")
            except Exception as e:
                logger.error(f"❌ 初始化命令执行失败：{cmd}，错误：{e}")

    def get_id(self) -> str:
        return self._terminal_id

    def get_workspace(self) -> str:
        if not self._workspace:
            raise RuntimeError("工作空间未初始化（内部错误）")
        return self._workspace

    async def cd_to_workspace(self) -> None:
        """切换终端当前目录到workspace根目录（支持含特殊字符的路径）"""
        workspace = self.get_workspace()
        try:
            # 用shlex.quote转义路径（处理空格、引号等特殊字符）
            quoted_workspace = shlex.quote(workspace)
            # 使用 write_process 执行 cd 命令（会自动等待完成标记）
            cd_cmd = f"cd {quoted_workspace}"
            await self._execute_with_timeout(cd_cmd, timeout=5.0)  # 5s timeout for cd

            # 同步当前目录
            await self._sync_current_dir()
            logger.info(f"🔄 已切换到workspace目录（含特殊字符处理）：{workspace}")
        except Exception as e:
            logger.error(f"❌ 切换到workspace目录失败：{e}")
            raise

    async def acquire(self) -> None:
        """获取终端使用信号量，确保并发安全"""
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("终端未运行或已退出")
        current_task = asyncio.current_task()
        task_name = current_task.get_name() if current_task else 'unknown'
        logger.debug(f"🔒 任务 {task_name} 获取终端锁")
        await self._lock.acquire()

    async def release(self) -> None:
        """释放终端使用信号量，唤醒等待的任务"""
        # 检查进程是否存在（在关闭过程中可能已被删除）
        if hasattr(self, '_process') and self._process:
            if self._process.poll() is not None:
                raise RuntimeError("终端未运行或已退出")
        # 如果进程不存在，可能是正在关闭，仍然尝试释放锁
        self._lock.release()
        current_task = asyncio.current_task()
        task_name = current_task.get_name() if current_task else 'unknown'
        logger.debug(f"🔓 任务 {task_name} 释放终端锁")

    def get_current_dir(self) -> str:
        if self._current_dir == "":
            raise RuntimeError(
                "终端当前目录未同步，可能终端未启动，需先调用open()"
            )
        return self._current_dir

    def get_allowed_commands(self) -> List[str]:
        # 返回列表副本，防止外部修改内部状态（防御性编程）
        return self._allowed_commands.copy()

    def is_script_execution_disabled(self) -> bool:
        return self._disable_script_execution

    def open(self) -> None:
        # 检查进程是否已运行（避免重复启动）
        if hasattr(self, '_process') and self._process and self._process.poll() is None:
            raise RuntimeError(f"终端进程已在运行（PID: {self._process.pid}），无需重复启动")

        try:
            # 启动长期bash进程（配置双向管道与行缓冲）
            # 指定工作目录为workspace，避免后续cd操作
            self._process = subprocess.Popen(
                args=["bash"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 错误流合并到stdout，统一处理
                text=True,                 # 文本模式（避免字节流转换）
                bufsize=1,                 # 行缓冲，确保实时输出
                shell=False,               # 列表传参，防止命令注入
                close_fds=True,            # 关闭无关文件描述符，减少资源占用
                encoding='utf-8',
                errors='replace',
                cwd=self._workspace,  # 直接指定工作目录
            )
            logger.info(f"✅ 终端进程启动成功（PID: {self._process.pid}），工作目录：{self._workspace}")

        except Exception as e:
            raise RuntimeError(f"终端进程启动失败：{str(e)}") from e
        
    async def _get_real_current_dir(self) -> str:
        """私有辅助方法：获取bash子进程的真实当前工作目录（避免pwd被篡改）。
        
        优先级：
        1. Linux：/proc/<pid>/cwd（bash子进程的当前目录，内核维护，不可篡改）；
        2. 其他系统：通过bash执行pwd -P（强制物理路径，忽略PWD环境变量）。
        
        Returns:
            str: 真实当前目录绝对路径。
        
        Raises:
            RuntimeError: 获取真实目录失败。
        """
        if not self._process:
            raise RuntimeError("终端进程未启动，无法获取当前目录")
        
        # 场景1：Linux系统（优先使用/proc/<pid>/cwd获取bash子进程的目录）
        proc_cwd_path = f"/proc/{self._process.pid}/cwd"
        if os.path.exists(proc_cwd_path) and os.path.islink(proc_cwd_path):
            try:
                # 读取符号链接指向的真实路径（内核保证准确性）
                real_cwd = os.readlink(proc_cwd_path)
                # 转为绝对路径（处理符号链接可能的相对路径）
                real_cwd_abs = os.path.abspath(real_cwd)
                logger.debug(f"📌 从/proc/{self._process.pid}/cwd获取真实目录：{real_cwd_abs}")
                return real_cwd_abs
            except (OSError, ValueError) as e:
                logger.warning(f"⚠️ /proc/{self._process.pid}/cwd读取失败，降级使用pwd -P：{str(e)[:50]}")

        # 场景2：非Linux系统或/proc不可用（通过bash执行pwd -P）
        # 注意：这里需要通过bash进程执行pwd，而不是直接使用subprocess
        # 因为我们需要获取bash子进程的当前目录，而不是Python进程的目录
        try:
            # 发送 pwd 命令（使用与 run_command 相同的格式）
            wrapped_cmd = f"pwd -P"
            output = await self._execute_with_timeout(wrapped_cmd, timeout=5.0)  # 5s timeout for pwd
            return output.strip()
            
        except Exception as e:
            # 最后的fallback：使用root_dir
            logger.warning(f"⚠️ 获取bash当前目录失败：{str(e)[:50]}，使用root_dir作为fallback")
            return self._root_dir

    async def _sync_current_dir(self) -> None:
        """私有方法：同步bash会话的真实当前目录到_current_dir（防篡改）。
        
        优化点：
        1. 用/proc/self/cwd或pwd -P替代pwd，避免被环境变量篡改；
        2. 新增真实目录的根目录校验，确保安全边界。
        """
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("无法同步当前目录：终端未运行或已退出")

        try:
            # 步骤1：获取进程真实当前目录（核心修改：替换pwd命令）
            real_cwd = await self._get_real_current_dir()

            # 步骤2：校验真实目录是否在根目录范围内（安全边界）
            if not real_cwd.startswith(self._root_dir):
                raise RuntimeError(
                    f"当前目录（{real_cwd}）超出根目录（{self._root_dir}），安全边界违规\n"
                    f"警告：可能存在目录篡改攻击！"
                )

            # 步骤3：更新当前目录状态
            # old_dir = self._current_dir
            self._current_dir = real_cwd

            # 日志提示（区分是否在workspace内）
            if real_cwd.startswith(self._workspace):
                logger.info(f"🔄 同步终端当前目录：{real_cwd} (在workspace内)")

        except Exception as e:
            raise RuntimeError(f"目录同步失败：{str(e)}") from e

    def _split_commands(self, command: str) -> list[str]:
        """私有方法：将复合命令按分隔符分割成独立的命令列表。

        支持的分隔符包括：
        - 分号 (;)
        - 管道符 (|)
        - 逻辑 AND (&&)
        - 逻辑 OR (||)
        - 换行符 (\n)

        Args:
            command: 待分割的bash命令字符串。

        Returns:
            list[str]: 分割后的独立命令列表（去除首尾空格）。
        """
        try:
            if not _COMMAND_SEPARATORS_PATTERN.search(command):
                return [command.strip()] if command.strip() else []

            commands: list[str] = []
            current_command = ""
            in_single_quote = False
            in_double_quote = False
            i = 0

            while i < len(command):
                char = command[i]
                if char == "'" and not in_double_quote:
                    in_single_quote = not in_single_quote
                    current_command += char
                elif char == '"' and not in_single_quote:
                    in_double_quote = not in_double_quote
                    current_command += char
                elif char == "\\" and (in_single_quote or in_double_quote):
                    current_command += char
                    i += 1
                    if i < len(command):
                        current_command += command[i]
                elif not in_single_quote and not in_double_quote:
                    if i < len(command) - 1 and command[i:i+2] in ("&&", "||"):
                        if current_command.strip():
                            commands.append(current_command.strip())
                        current_command = ""
                        i += 1
                    elif char in (";", "|", "\n"):
                        if current_command.strip():
                            commands.append(current_command.strip())
                        current_command = ""
                    else:
                        current_command += char
                else:
                    current_command += char

                i += 1

            if current_command.strip():
                commands.append(current_command.strip())

            return commands if commands else [command.strip()] if command.strip() else []
        except Exception:
            parts = _COMMAND_SEPARATORS_PATTERN.split(command)
            commands = [p.strip() for p in parts if p.strip()]
            return commands if commands else [command.strip()] if command.strip() else []

    def _is_script_command(self, command: str) -> bool:
        """私有方法：判断命令是否包含脚本执行（支持复合命令+带路径解释器检测）。

        1. 支持匹配带路径的脚本解释器（如 /usr/bin/python、./venv/bash）；
        2. 用正则确保解释器名不被误判（如避免"pythonic"被当作python）；
        3. 覆盖脚本文件全路径场景（如 /home/user/script.sh、~/docs/test.py）；

        Args:
            command: 待判断的bash命令字符串（支持复合命令）。

        Returns:
            bool: True=包含脚本执行（任一命令是脚本），False=不包含脚本执行。
        """
        # 1. 预处理命令：去除首尾空格，统一转为小写（避免大小写误判）
        command_clean = command.strip().lower()
        if not command_clean:
            return False  # 空命令无脚本风险

        # 2. 定义“支持路径的脚本规则”：正则列表（覆盖解释器+脚本文件）
        # 规则说明：
        # - (^|\s|/)：匹配命令开头、空格或路径分隔符（确保是独立的解释器/脚本名）
        # - [\w./-]*：匹配路径（如 /usr/bin/、./venv/、~/）
        # - ($|\s|;)：匹配命令结尾、空格或分隔符（避免部分匹配，如"pythonic"）
        script_rules = [
            # 规则1：脚本解释器（支持路径，如 /usr/bin/python、./bash）
            r'(^|\s|/)[\w./-]*(python|python3|python2)($|\s|;)',  # Python
            r'(^|\s|/)[\w./-]*(bash|sh|zsh|ksh|csh)($|\s|;)',     # Shell
            r'(^|\s|/)[\w./-]*(go)($|\s|;)\s+run',                # Go run（需跟run参数）
            r'(^|\s|/)[\w./-]*(go)($|\s|;)\s+test',               # Go test
            r'(^|\s|/)[\w./-]*(node|npm|yarn|pnpm)($|\s|;)',       # JS/TS
            r'(^|\s|/)[\w./-]*(perl|ruby|php|lua)($|\s|;)',        # 其他解释器
            # 规则2：直接执行的脚本文件（带路径+后缀，如 ./script.sh、/home/test.py）
            r'(^|\s|/)[\w./-]+\.(sh|py|go|js)($|\s|;)',           # 后缀匹配
            r'(^|\s)\./[\w./-]*($|\s|;)'                          # 相对路径执行（如 ./script）
        ]

        # 3. 分割复合命令（逐条检查，避免漏判）
        independent_commands = self._split_commands(command_clean)
        for single_cmd in independent_commands:
            single_cmd_stripped = single_cmd.strip()
            if not single_cmd_stripped:
                continue  # 跳过空命令片段

            # 排除重定向操作符后的文件名（如 echo 'hello' > test.sh 中的 test.sh 不是脚本执行）
            # 移除重定向操作符及其后的内容（>、>>、<、2>、&> 等）
            cmd_without_redirect = re.sub(r'\s*[<>]+\s*\S+', '', single_cmd_stripped)
            cmd_without_redirect = re.sub(r'\s*2>\s*\S+', '', cmd_without_redirect)
            cmd_without_redirect = re.sub(r'\s*&\s*[<>]\s*\S+', '', cmd_without_redirect)
            
            # 4. 检查当前独立命令是否命中任一脚本规则（使用去除重定向后的命令）
            for rule in script_rules:
                # 用正则匹配：忽略大小写（已预处理小写，此处可简化）
                match = re.search(rule, cmd_without_redirect)
                if match:
                    # 特殊排除：避免将"目录路径"误判为脚本（如 ./dir/ 不是脚本）
                    matched_str = match.group(0).strip()
                    # 排除场景1：以 / 结尾（是目录，如 /usr/bin/）
                    if matched_str.endswith('/'):
                        continue
                    # 排除场景2：无后缀的纯路径目录（如 ./venv/bin）
                    if '/' in matched_str and not any(ext in matched_str for ext in ['.sh', '.py', '.go', '.js']) and not any(inter in matched_str for inter in ['python', 'bash', 'sh', 'node', 'go']):
                        continue

                    # 命中有效脚本规则，记录日志并返回True
                    logger.debug(f"⚠️ 检测到脚本执行命令：{single_cmd_stripped}（匹配规则：{rule}）")
                    return True

        # 所有命令均未命中脚本规则
        return False

    def _is_prohibited_command(self, command: str, allow_by_human: bool) -> bool:
        """私有方法：检查命令是否包含禁止命令（正则匹配，覆盖批量/提权/跨层级）。

        核心逻辑：
        - 绝对禁止命令：无论是否人类允许，均拦截（如批量删除、提权、根目录操作）
        - 条件禁止命令：仅当非人类允许时拦截（如软件包管理）
        """
        command_stripped = command.strip()
        if not command_stripped:
            return False

        # 统一转为小写，避免大小写误判
        cmd_lower = command_stripped.lower()
        # 提取命令名（如 "/usr/bin/sudo" → "sudo"）
        cmd_name = self._extract_command_name(command_stripped.split()[0] if command_stripped.split() else "")
        # 遍历禁止命令正则列表，逐个匹配
        for prohib in _PROHIBITED_REGEX:
            # 取出原始 pattern 并确保为 str（若为 bytes 则 decode）
            raw_pattern = prohib.get("regex", "")
            if isinstance(raw_pattern, bytes):
                regex = raw_pattern.decode("utf-8", errors="ignore")
            else:
                regex = str(raw_pattern)

            desc = str(prohib.get("desc", ""))
            is_absolute = bool(prohib.get("is_absolute", False))

            # 如果没有有效的正则表达式，跳过该条规则
            if not regex:
                continue

            # 正则匹配（忽略大小写）
            if re.search(regex, cmd_lower, re.IGNORECASE):
                # 判定逻辑：绝对禁止命令直接拦截；条件禁止命令仅非人类允许时拦截
                if is_absolute or (not is_absolute and not allow_by_human):
                    logger.error(
                        f"❌ 命令包含禁止操作：\n"
                        f"  禁止类型：{desc}\n"
                        f"  匹配规则：{regex}\n"
                        f"  执行命令：{command_stripped}"
                    )
                    return True

        # 额外校验：rm命令的路径是否为“精准路径”（排除通配符/特殊符号）
        if cmd_name == "rm":
            # 拆分rm命令的参数（如 "rm -rf ./tmp/log.txt" → ["./tmp/log.txt"]）
            try:
                cmd_parts = shlex.split(command_stripped)
                # 提取路径参数（跳过命令名和选项，如 -rf、-f）
                path_args = [p for p in cmd_parts[1:] if not p.startswith("-")]
                for path in path_args:
                    # 检查路径是否含危险符号（*、..），或不符合精准路径规则
                    if "*" in path or ".." in path or not re.match(_RM_SAFE_PATH_PATTERN, path.strip()):
                        logger.error(
                            f"❌ rm命令路径非法（非精准删除）：\n"
                            f"  非法路径：{path}\n"
                            f"  禁止原因：含通配符(*)、跨层级(..)，或路径格式不合法\n"
                            f"  执行命令：{command_stripped}"
                        )
                        return True
            except ValueError:
                # 命令语法错误（如未闭合引号），保守判定为危险
                logger.warning(f"❌ rm命令语法错误（可能含恶意构造）：{command_stripped}")
                return True

        # 无禁止命令匹配
        return False

    def _has_escaped_prohibited_cmd(self, command: str, allow_by_human: bool = False) -> bool:
        """私有方法：检查命令中是否包含嵌套（逃逸）的禁止命令（支持转义引号）。
        
        核心优化：
        1. 处理转义引号（如 \\"xxx\\"、\\'xxx\\'）和未转义引号；
        2. 仅匹配命令执行场景（bash -c、sh -c等），避免普通参数误判；
        3. 递归校验嵌套命令，确保无遗漏。
        """
        command_stripped = command.strip()
        if not command_stripped:
            return False

        # 步骤1：先检查基础禁止命令（复用已有逻辑）
        if self._is_prohibited_command(command_stripped, allow_by_human):
            return True

        # 步骤2：检查命令替换 $() 和 ``
        # 匹配 $(...) 和 `...`
        substitution_patterns = [
            r'\$\(([^)]+)\)',  # $(command)
            r'`([^`]+)`',      # `command`
        ]
        
        for pattern in substitution_patterns:
            matches = re.finditer(pattern, command_stripped)
            for match in matches:
                nested_cmd = match.group(1).strip()
                if nested_cmd:
                    # 递归检查嵌套命令
                    if self._is_prohibited_command(nested_cmd, allow_by_human):
                        logger.error(
                            f"❌ 命令替换包含禁止操作：{match.group(0)} → {nested_cmd}"
                        )
                        return True
                    # 检查嵌套命令的路径约束（如 find / 应该被拦截）
                    if not self._check_path_constraints(nested_cmd, allow_by_human):
                        logger.error(
                            f"❌ 命令替换中的路径超出范围：{match.group(0)} → {nested_cmd}"
                        )
                        return True
                    # 递归检查嵌套命令中的逃逸命令
                    if self._has_escaped_prohibited_cmd(nested_cmd, allow_by_human):
                        return True

        # 步骤3：正则匹配「命令执行型嵌套」（支持转义/未转义引号）
        # 正则说明：
        # - ^.*?(bash|sh|python|python3|node|go) -c\s*：匹配执行命令的解释器（如 bash -c）
        # - (?:\\\\['"]|['"]])：匹配开头的转义引号（\\\\\"）或未转义引号（"）
        # - (.*?)：非贪婪匹配引号内的嵌套命令
        # - (?:\\\\\1|(?<!\\\\)\1)：匹配结尾的转义引号（\\\\\"）或未转义引号（"，确保未被转义）
        escaped_cmd_pattern = re.compile(
            r'^.*?(bash|sh|python|python3|node|go) -c\s*(?P<quote>(?:\\\\[\'"]|[\'"]))(?P<content>.*?)(?:\\\\(?P=quote)|(?<!\\\\)(?P=quote))',
            re.IGNORECASE | re.DOTALL  # DOTALL 允许匹配换行符
        )
        matches = escaped_cmd_pattern.finditer(command_stripped)
        if not matches:
            return False  # 无命令执行型嵌套，直接返回

        # 步骤3：提取并校验嵌套命令（处理转义字符）
        for match in matches:
            interpreter = match.group(1).lower()
            nested_content = match.group("content").strip()
            if not nested_content:
                continue

            # 清理嵌套内容中的转义符（如 \\" → "，\\' → '）
            cleaned_content = re.sub(r'\\\\([\'"])', r'\1', nested_content)
            logger.debug(
                f"⚠️ 检测到转义嵌套命令：{interpreter} -c '{nested_content}'\n"
                f"   清理后命令：{cleaned_content}"
            )

            # 递归检查嵌套命令（复用 _is_prohibited_command，确保逻辑一致）
            if self._is_prohibited_command(cleaned_content, allow_by_human):
                logger.error(
                    f"❌ 转义嵌套命令包含禁止操作：{interpreter} -c '{cleaned_content}'"
                )
                return True

        # 嵌套内容中无禁止命令
        return False

    def _validate_command_basic(self, command: str) -> tuple[str, bool]:
        """私有方法：命令基础校验。

        Args:
            command: 待校验的bash命令字符串。

        Returns:
            tuple[str, bool]: (处理后的命令, 是否通过校验)

        Raises:
            RuntimeError: 工作空间未初始化或当前目录未同步。
        """
        # 前置状态校验
        if not self._workspace:
            raise RuntimeError("无法检查命令：工作空间未初始化")
        if self._current_dir == "":
            raise RuntimeError("无法检查命令：终端当前目录未同步")

        command_stripped = command.strip()
        if not command_stripped:
            logger.error("❌ 空命令，拒绝执行")
            return command_stripped, False

        return command_stripped, True
    
    def _extract_command_name(self, command_path: str) -> str:
        """私有辅助方法：从命令路径中提取真实命令名（去路径前缀）。
        
        示例：
        - "/usr/bin/sudo" → "sudo"
        - "./venv/bash" → "bash"
        - "python3" → "python3"
        - "/usr/local/bin/go run" → "go"（仅取第一个命令词）
        
        Args:
            command_path: 带路径或不带路径的命令字符串（如 "/usr/bin/sudo"）。
        
        Returns:
            str: 提取后的纯命令名（小写，统一匹配格式）。
        """
        # 1. 拆分命令词（仅取第一个，排除参数，如 "go run" → "go"）
        try:
            cmd_parts = shlex.split(command_path.strip())
        except ValueError:
            # 引号未闭合等语法错误，使用简单分割
            cmd_parts = command_path.strip().split()
        if not cmd_parts:
            return ""
        
        # 2. 提取命令路径中的文件名（去路径）
        raw_cmd = cmd_parts[0]
        cmd_name = raw_cmd.split("/")[-1]
        
        # 3. 统一转为小写，避免大小写误判（如 "Sudo" → "sudo"）
        return cmd_name.lower()

    def _check_allowed_commands(self, command_stripped: str, allow_by_human: bool) -> bool:
        """私有方法：检查允许命令列表（第一步）。

        Args:
            command_stripped: 待检查的命令字符串（已去除首尾空格）
            allow_by_human: 是否由人类用户允许执行

        Returns:
            bool: True=通过检查，False=不通过
        """
        if not allow_by_human:  # 仅当非人类允许时，强制检查白名单
            if self._allowed_commands:
                command_lower = command_stripped.lower()
                is_allowed = any(
                    allowed_cmd.lower() in command_lower
                    for allowed_cmd in self._allowed_commands
                )
                if not is_allowed:
                    logger.error(
                        f"❌ 命令不在允许列表内：{command_stripped}\n"
                        f"    允许命令列表：{self._allowed_commands}"
                    )
                    return False
            logger.info("✅ 第一步：允许列表检查通过")
            return True
        else:
            logger.info("✅ 人类用户允许，跳过允许列表检查")  # 跳过白名单
            return True

    def _check_script_execution(self, command_stripped: str, allow_by_human: bool) -> bool:
        """私有方法：检查脚本执行（第二步）。

        Args:
            command_stripped: 待检查的命令字符串（已去除首尾空格）
            allow_by_human: 是否由人类用户允许执行

        Returns:
            bool: True=通过检查，False=不通过
        """
        if not allow_by_human and self._disable_script_execution:  # 仅当"非人类允许"且"禁用脚本"时检查
            if self._is_script_command(command_stripped):
                logger.error(
                    f"❌ 命令是脚本执行（已禁用）：{command_stripped}"
                )
                return False
            logger.info("✅ 第二步：脚本执行检查通过")
            return True
        else:
            if allow_by_human:
                logger.info("✅ 人类用户允许，跳过脚本执行检查")  # 跳过脚本限制
            else:
                logger.info("✅ 第二步：脚本执行检查通过（脚本执行未禁用）")
            return True

    def _check_path_constraints(self, command: str, allow_by_human: bool) -> bool:
        """唯一的路径安全检查入口（强化rm命令精准路径校验）。

        新增逻辑：
        - rm命令：仅允许workspace内的单个具体路径（无*、..）
        - 其他路径命令：保留原逻辑（允许workspace内合法路径）
        """
        try:
            # 尝试使用 shlex.split，但如果引号未闭合则使用简单分割
            try:
                cmd_parts = shlex.split(command)
            except ValueError:
                # 引号未闭合等语法错误，使用简单分割
                cmd_parts = command.split()
            if not cmd_parts:
                return True

            cmd_name = self._extract_command_name(cmd_parts[0])
            # 非路径敏感命令直接放行
            if cmd_name not in _PATH_SENSITIVE_COMMANDS:
                return True
            
            # echo 命令的参数不应该被当作路径检查（echo 只是输出文本）
            if cmd_name == "echo":
                return True
            
            # sed 命令的特殊处理：sed 的参数格式是 sed [options] 'script' [file...]
            # 需要跳过 sed 脚本（引号内的内容），只检查文件路径
            if cmd_name == "sed":
                # sed 命令格式：sed [options] 'script' [file...]
                # 找到第一个非选项参数（通常是 sed 脚本），然后检查后面的文件路径
                file_args: list[str] = []
                skip_next = False
                script_found = False
                for arg in cmd_parts[1:]:
                    if skip_next:
                        skip_next = False
                        continue
                    arg_stripped = arg.strip()
                    # 跳过选项（如 -i, -e, -f）
                    if arg_stripped.startswith("-"):
                        # -i 选项可能带参数（如 -i.bak），需要跳过
                        if "=" in arg_stripped:
                            continue
                        # 某些选项需要参数（如 -f scriptfile），跳过下一个参数
                        if arg_stripped in ("-f", "-e", "--expression", "--file"):
                            skip_next = True
                            continue
                        continue
                    # 跳过 sed 脚本（引号内的内容，或包含 sed 操作符的内容）
                    # sed 脚本通常包含 /、s/、d、a\、i\、c\ 等操作符
                    if (arg_stripped.startswith("'") and arg_stripped.endswith("'")) or \
                       (arg_stripped.startswith('"') and arg_stripped.endswith('"')) or \
                       ("/" in arg_stripped and ("s/" in arg_stripped or "/d" in arg_stripped or "/a" in arg_stripped or "/i" in arg_stripped or "/c" in arg_stripped)) or \
                       (not script_found and ("s/" in arg_stripped or "/d" in arg_stripped or "/a" in arg_stripped or "/i" in arg_stripped or "/c" in arg_stripped)):
                        script_found = True
                        continue
                    # 剩余的参数应该是文件路径（在找到脚本之后）
                    if script_found and arg_stripped and not arg_stripped.startswith("-"):
                        file_args.append(arg_stripped)
                
                # 检查文件路径
                for file_arg in file_args:
                    if not file_arg or file_arg == "/":
                        continue
                    try:
                        if os.path.isabs(file_arg):
                            path_obj = Path(file_arg).expanduser()
                        else:
                            path_obj = Path(self._current_dir).joinpath(file_arg).expanduser()
                        abs_path = str(path_obj.resolve(strict=False))
                    except (ValueError, OSError) as e:
                        logger.warning(f"⚠️ sed文件路径参数{file_arg}不是合法本地路径，跳过校验：{str(e)[:50]}")
                        continue
                    
                    # 检查路径是否在允许范围内
                    if not abs_path.startswith(self._root_dir):
                        logger.error(
                            f"❌ sed命令文件路径超出根目录范围：\n"
                            f"  根目录：{self._root_dir}\n"
                            f"  非法路径：{abs_path}\n"
                            f"  执行命令：{command}"
                        )
                        return False
                    
                    # 非人类允许时，必须在 workspace 内
                    if not allow_by_human and not abs_path.startswith(self._workspace):
                        logger.error(
                            f"❌ sed命令文件路径超出workspace：\n"
                            f"  workspace：{self._workspace}\n"
                            f"  非法路径：{abs_path}\n"
                            f"  执行命令：{command}\n"
                            f"  提示：如需跳出workspace，请使用 allow_by_human=True"
                        )
                        return False
                
                # sed 命令检查完成
                return True

            # 特殊处理：cd 命令必须检查目标路径
            if cmd_name == "cd":
                # cd 命令的参数是目标目录
                if len(cmd_parts) > 1:
                    target_dir = cmd_parts[1].strip()
                else:
                    # cd 无参数，切换到 home 目录，允许
                    return True
                
                # 排除非路径参数
                if target_dir.startswith("-"):
                    return True  # cd - 等选项，允许
                
                # 解析目标路径
                try:
                    if os.path.isabs(target_dir):
                        path_obj = Path(target_dir).expanduser()
                    else:
                        path_obj = Path(self._current_dir).joinpath(target_dir).expanduser()
                    abs_path = str(path_obj.resolve(strict=False))
                except (ValueError, OSError) as e:
                    logger.warning(f"⚠️ cd目标路径{target_dir}不是合法本地路径，跳过校验：{str(e)[:50]}")
                    return True  # 路径解析失败，保守允许
                
                # 检查目标路径是否在允许范围内
                if not abs_path.startswith(self._root_dir):
                    logger.error(
                        f"❌ cd命令目标路径超出根目录范围：\n"
                        f"  根目录：{self._root_dir}\n"
                        f"  非法路径：{abs_path}\n"
                        f"  执行命令：{command}"
                    )
                    return False
                
                # cd 命令：非人类允许时必须在workspace内
                if not allow_by_human and not abs_path.startswith(self._workspace):
                    logger.error(
                        f"❌ cd命令目标路径超出workspace：\n"
                        f"  workspace：{self._workspace}\n"
                        f"  非法路径：{abs_path}\n"
                        f"  提示：如需跳出workspace，请使用 allow_by_human=True"
                    )
                    return False
                
                # cd 命令校验通过
                return True

            # 特殊处理 find 命令：find 的第一个非选项参数是搜索路径
            if cmd_name == "find":
                # find 命令格式：find [path] [options] [expression]
                # 第一个非选项参数是搜索路径
                path_found = False
                for arg in cmd_parts[1:]:
                    arg_stripped = arg.strip()
                    if not arg_stripped:
                        continue
                    # 跳过选项参数（如 -name、-type、-mtime 等）
                    if arg_stripped.startswith("-"):
                        continue
                    # 第一个非选项参数是搜索路径
                    if not path_found:
                        path_found = True
                        # 检查这个路径（包括 "/"）
                        if arg_stripped == "/":
                            # "/" 是根目录，肯定超出 root_dir
                            logger.error(
                                f"❌ find命令搜索路径超出根目录范围：\n"
                                f"  根目录：{self._root_dir}\n"
                                f"  非法路径：/\n"
                                f"  执行命令：{command}"
                            )
                            return False
                        try:
                            if os.path.isabs(arg_stripped):
                                path_obj = Path(arg_stripped).expanduser()
                            else:
                                path_obj = Path(self._current_dir).joinpath(arg_stripped).expanduser()
                            abs_path = str(path_obj.resolve(strict=False))
                        except (ValueError, OSError) as e:
                            logger.warning(f"⚠️ find路径参数{arg_stripped}不是合法本地路径，跳过校验：{str(e)[:50]}")
                            continue
                        
                        # 检查路径是否在允许范围内
                        if not abs_path.startswith(self._root_dir):
                            logger.error(
                                f"❌ find命令搜索路径超出根目录范围：\n"
                                f"  根目录：{self._root_dir}\n"
                                f"  非法路径：{abs_path}\n"
                                f"  执行命令：{command}"
                            )
                            return False
                        # find 命令只需要检查第一个路径参数
                        break
                # find 命令检查完成
                return True
            
            # 遍历所有参数，逐个校验路径（非cd、非find命令）
            for arg in cmd_parts[1:]:
                arg_stripped = arg.strip()
                # 排除非路径参数（URL、纯选项等）
                if arg_stripped.startswith(("http://", "https://")) or arg_stripped.startswith("-"):
                    continue
                if not arg_stripped or arg_stripped == "/":
                    continue

                # 解析路径（处理~用户目录、相对路径、绝对路径）
                try:
                    # 如果是绝对路径，直接使用；否则相对于当前目录
                    if os.path.isabs(arg_stripped):
                        path_obj = Path(arg_stripped).expanduser()
                    else:
                        path_obj = Path(self._current_dir).joinpath(arg_stripped).expanduser()
                    abs_path = str(path_obj.resolve(strict=False))
                except (ValueError, OSError) as e:
                    logger.warning(f"⚠️ 参数{arg}不是合法本地路径，跳过校验：{str(e)[:50]}")
                    continue

                # 1. 基础路径边界校验（必须在root_dir内，底线）
                if not abs_path.startswith(self._root_dir):
                    logger.error(
                        f"❌ 路径超出根目录范围：\n"
                        f"  根目录：{self._root_dir}\n"
                        f"  非法路径：{abs_path}\n"
                        f"  执行命令：{command}"
                    )
                    return False

                # 2. rm命令额外校验：必须在workspace内（即使人类允许也不放宽）
                if cmd_name == "rm":
                    if not abs_path.startswith(self._workspace):
                        logger.error(
                            f"❌ rm命令路径超出workspace（仅允许workspace内删除）：\n"
                            f"  workspace：{self._workspace}\n"
                            f"  非法路径：{abs_path}\n"
                            f"  执行命令：{command}"
                        )
                        return False

                # 3. 其他命令：非人类允许时必须在workspace内
                if cmd_name != "rm" and not allow_by_human and not abs_path.startswith(self._workspace):
                    logger.error(
                        f"❌ 路径超出workspace：\n"
                        f"  workspace：{self._workspace}\n"
                        f"  非法路径：{abs_path}\n"
                        f"  提示：如需跳出workspace，请使用 allow_by_human=True"
                    )
                    return False

            return True

        except ValueError as e:
            logger.error(f"❌ 命令语法错误（如未闭合引号）：{command}，错误：{e}")
            return False
        except Exception as e:
            logger.error(f"❌ 路径校验意外错误：{str(e)[:50]}，命令：{command}")
            return False

    def _validate_terminal_state(self) -> None:
        """私有方法：验证终端状态是否可以执行命令。

        Raises:
            RuntimeError: 终端未运行、未初始化或输入输出流未准备就绪。
        """
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("终端未运行或已退出，需先调用open()启动")
        if not self._workspace:
            raise RuntimeError("无法执行命令：工作空间未初始化")
        if not self._process.stdin or not self._process.stdout:
            raise RuntimeError("终端进程输入/输出流未初始化")

    async def _sync_directory_if_needed(self, command: str) -> None:
        """私有方法：如果命令包含cd操作，同步当前目录。

        Args:
            command: 执行的命令
        """
        cmd_lower = command.strip().lower()
        if "cd " in cmd_lower or cmd_lower == "cd":
            await self._sync_current_dir()

    def check_command(self, command: str, allow_by_human: bool = False) -> bool:
        """按固定顺序执行命令安全校验（允许列表→脚本→逃逸→禁止列表→路径）。

        重点强化：find/grep等路径类命令的越界拦截，所有路径参数需在工作空间内。
        支持复合命令检查：通过分隔符分割的每个独立命令都会通过完整的安全校验流程。

        安全检查顺序（严格遵循）：
        1. 允许命令列表检查（非空时，仅允许列表内命令）
        2. 脚本执行检查（若禁用，拒绝所有脚本解释器命令）
        3. 逃逸禁止命令检查（拒绝嵌套在引号/反引号中的禁止命令）
        4. 禁止命令列表检查（拒绝列表内的危险命令）
        5. 路径范围检查（所有涉及路径的命令，均需在工作空间内）

        Args:
            command: 待校验的bash命令字符串（如"find ./src -name '*.py'"、"grep 'key' ./file.txt"）。
            allow_by_human: 是否由人类用户允许执行（True时跳过白名单和脚本限制）

        Returns:
            bool: True=命令安全可执行，False=命令不安全。

        Raises:
            RuntimeError: 工作空间未初始化或当前目录未同步。
        """
        # 第0步：基础校验
        command_stripped, is_valid = self._validate_command_basic(command)
        if not is_valid:
            return False

        # 分割命令为独立命令列表
        commands = self._split_commands(command_stripped)

        # 对每个独立命令进行完整的安全校验
        for i, cmd in enumerate(commands, 1):
            logger.info(f"🔍 检查第 {i}/{len(commands)} 个命令：{cmd}")

            # 第1步：允许命令列表检查（人类允许时跳过）
            if not self._check_allowed_commands(cmd, allow_by_human):
                logger.error(f"❌ 命令 {i} 未通过允许列表检查：{cmd}")
                return False

            # 第2步：脚本执行检查（人类允许时跳过）
            if not self._check_script_execution(cmd, allow_by_human):
                # 错误日志已在 _check_script_execution 中记录
                return False

            # 第3步：禁止命令检查（统一检查）
            if not self._is_prohibited_command(cmd, allow_by_human):
                logger.info(f"✅ 命令 {i} 通过禁止命令检查")
            else:
                logger.error(f"❌ 命令 {i} 包含禁止操作：{cmd}")
                return False

            # 第4步：逃逸禁止命令检查
            if self._has_escaped_prohibited_cmd(cmd, allow_by_human):
                # 错误日志已在 _has_escaped_prohibited_cmd 中记录
                return False
            logger.info(f"✅ 命令 {i} 通过逃逸禁止命令检查")

            # 第5步：路径范围检查（人类允许时可绕过workspace限制）
            if not self._check_path_constraints(cmd, allow_by_human):
                # 错误日志已在 _check_path_constraints 中记录
                return False

            logger.info(f"✅ 命令 {i} 通过所有安全校验")

        # 所有命令都通过了校验
        if len(commands) > 1:
            logger.info(f"✅ 复合命令安全可执行，共 {len(commands)} 个独立命令：{command_stripped}")
        else:
            logger.info(f"✅ 命令安全可执行：{command_stripped}")
        return True

    async def run_command(
        self, command: str, allow_by_human: bool = False, timeout: float | None = None
    ) -> str:
        """执行bash命令，返回输出并同步终端状态（异步版本，含安全校验）。

        Args:
            command: 待执行的bash命令（如"grep 'key' ./file.txt"、"find ./src -name '*.py'"）。
            allow_by_human: 被人类允许执行
            timeout: 超时时间（秒），None表示等待 indefinitely。如果未指定，则等待命令自然完成。

        Returns:
            str: 命令标准输出（已过滤空行与标记）。

        Raises:
            RuntimeError: 终端未启动或工作空间未初始化。
            PermissionError: 命令未通过安全校验（如在黑名单、路径越界）。
            subprocess.SubprocessError: 命令执行中发生IO错误。
            TimeoutError: 命令执行超时。
        """
        # 获取异步锁，确保并发安全
        await self.acquire()
        try:
            # 1. 前置校验：终端状态
            self._validate_terminal_state()

            # 2. 安全校验（传入allow_by_human，控制是否绕过白名单/脚本限制）
            if not self.check_command(command, allow_by_human):
                raise PermissionError(f"命令未通过安全校验，拒绝执行：{command}")

            # 3. 调用超时包装协程
            result = await self._execute_with_timeout(command, timeout)

            # 4. 检查命令是否执行失败（检查输出中的错误信息）
            error_indicators = ["command not found", "No such file or directory", "Permission denied"]
            if any(indicator.lower() in result.lower() for indicator in error_indicators):
                raise subprocess.SubprocessError(
                    f"命令执行失败：{command}\n输出：{result[:200]}"
                )

            # 5. 状态同步：若命令包含cd，更新当前目录
            await self._sync_directory_if_needed(command)

            # 6. 返回清理后的输出
            logger.info(f"📥 命令执行完成，输出长度：{len(result)} 字符")
            return result

        except (TimeoutError, PermissionError):
            # 超时和权限错误，直接重新抛出
            raise
        except OSError as e:
            raise subprocess.SubprocessError(
                f"命令执行中发生IO错误：{str(e)}（命令：{command}）"
            ) from e
        finally:
            # 释放异步锁
            await self.release()

    async def read_process(self, stop_word: str) -> str:
        """读取终端输出。

        Args:
            stop_word: 遇到该停止词时结束读取。

        Returns:
            str: 终端输出。

        Raises:
            RuntimeError: 终端未启动或输出流不可用。
        """
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("终端未运行或已退出")
        if not self._process.stdout:
            raise RuntimeError("终端输出流不可用")

        data: list[str] = []
        loop = asyncio.get_event_loop()

        while True:
            # Use run_in_executor to make blocking readline() async
            line = await loop.run_in_executor(None, self._process.stdout.readline)
            if line.strip() == stop_word:
                break
            data.append(line.rstrip('\n\r'))

        return '\n'.join(data)

    async def write_process(self, data: str) -> None:
        """写入终端输入（简化版本，不等待完成）。

        Args:
            data: 要写入的数据。

        Raises:
            RuntimeError: 终端未启动或输入流不可用。

        Note:
            这是纯粹的写入操作，不等待命令执行完成。
            如需等待完成，请使用异步的 run_command 方法。
        """
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("终端未运行或已退出")
        if not self._process.stdin:
            raise RuntimeError("终端输入流不可用")

        # 添加换行符（如果需要）
        if not data.endswith('\n'):
            data += '\n'

        # 写入命令
        self._process.stdin.write(data)
        self._process.stdin.flush()

    def close(self) -> None:
        # 检查进程是否存在
        if not self._process or self._process.poll() is not None:
            logger.info("ℹ️ 终端进程已关闭或未启动，无需重复操作")
            # 重置状态
            self._process = None
            self._current_dir = ""
            return

        pid = self._process.pid  # 保存PID用于日志

        # 在同步上下文中尝试获取锁，如果已经被获取则跳过
        try:
            # 检查锁是否可用，如果不可用则跳过锁获取
            if self._lock.locked():
                logger.debug("🔒 终端锁已被其他任务持有，跳过锁获取进行关闭")
            else:
                # 在同步上下文中，我们需要创建一个新的事件循环来获取锁
                # 但是close()方法通常在程序退出时调用，此时可能没有运行的事件循环
                # 为了避免阻塞，我们跳过锁获取
                logger.debug("🔒 在同步上下文中关闭终端，跳过锁获取")
        except Exception:
            # 忽略锁获取失败，继续关闭进程
            pass

        try:
            # 1. 关闭输入管道（告知进程无更多输入）
            if self._process.stdin:
                self._process.stdin.close()
            # 2. 发送终止信号，等待退出（超时5秒）
            self._process.terminate()
            self._process.wait(timeout=5)
            logger.info(f"✅ 终端进程（PID: {pid}）优雅关闭成功")

        except subprocess.TimeoutExpired:
            # 3. 超时未退出，强制杀死进程
            self._process.kill()
            raise RuntimeError(
                f"终端进程（PID: {pid}）超时未退出，已强制杀死"
            ) from None

        except Exception as e:
            raise RuntimeError(
                f"关闭终端进程失败：{str(e)}（PID: {pid}）"
            ) from e

        finally:
            # 释放锁（在删除 _process 之前）
            try:
                # 对于close方法，我们直接释放锁而不等待（因为可能没有活跃的事件循环）
                if self._lock.locked():
                    # 尝试非阻塞释放
                    if hasattr(self._lock, 'release'):
                        self._lock.release()
            except (RuntimeError, AttributeError):
                # 如果锁已经被释放或进程不存在，忽略错误
                pass
            finally:
                # 重置状态
                self._process = None
                self._current_dir = ""

    async def _execute_with_timeout(self, command: str, timeout: Optional[float] = None) -> str:
        """使用协程超时包装执行命令。

        Args:
            command: 要执行的命令
            timeout: 超时时间（秒）

        Returns:
            str: 命令输出（可能包含超时信息）
        """
        # Append the done marker to the command
        command_with_marker = f"{command}; echo '{_COMMAND_DONE_MARKER}'"
        await self.write_process(command_with_marker)
        # 2. 创建协程任务
        read_task = asyncio.create_task(self.read_process(_COMMAND_DONE_MARKER))

        # 3. 启动命令执行协程
        try:
            if timeout is None:
                # No timeout specified - wait indefinitely
                result = await read_task
                return result
            else:
                result = await asyncio.wait_for(
                    read_task,
                    timeout=timeout,
                )
                return result
        except asyncio.TimeoutError:
            try:
                # 超时处理：发送中断信号并返回部分结果
                await self._handle_command_timeout(command, 5.0)
            except Exception:
                return "终端错误，执行命令失败。"

            # 取消读取任务但不抛出异常
            if not read_task.done():
                read_task.cancel()
                try:
                    # 尝试获取已读取的部分结果
                    partial_result = await read_task
                except asyncio.CancelledError:
                    # 任务被取消，返回空结果
                    partial_result = ""
            else:
                partial_result = ""

            # 返回部分结果和超时信息
            timeout_msg = f"\n[命令执行超时 ({timeout}s)]"
            return partial_result + timeout_msg

    async def _handle_command_timeout(self, command: str, timeout: float) -> None:
        """处理命令超时：发送SIGINT信号并写入错误信息。

        Args:
            command: 超时的命令
            timeout: 超时时间
        """
        if self._process and self._process.poll() is None:
            # 1. 发送SIGINT信号
            self._process.send_signal(signal.SIGINT)

            # 2. 写入错误信息到stderr（合并到stdout）
            error_msg = f"\nError: Command timeout after {timeout}s: {command}\n"
            logger.warning(f"⏰ 命令执行超时（{timeout}秒）：{command}")

            # 由于stderr合并到stdout，直接写入stdin
            try:
                await self.write_process(f"echo \"{error_msg}\" >&2 && echo '{_COMMAND_DONE_MARKER}'")
            except Exception:
                # 如果写入失败，只记录日志
                logger.error(f"❌ 无法写入超时错误信息到终端")
                raise
