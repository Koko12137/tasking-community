"""
Terminal tool implementation providing secure command execution within a workspace.

This module implements a terminal abstraction with safety constraints, including
workspace restrictions, command whitelisting/blacklisting, and script execution control.
"""

import os
import subprocess
import shlex
import re
import threading
from abc import ABC, abstractmethod
from uuid import uuid4
from typing import List, Optional

from loguru import logger

# ------------------------------
# 核心常量定义（私有，避免外部修改）
# ------------------------------
# 命令执行完成标记（用于分割输出）
_COMMAND_DONE_MARKER = "__SINGLE_THREAD_TERMINAL_EXEC_DONE__"
# 当前目录同步标记（用于获取终端真实状态）
_CURRENT_DIR_MARKER = "__SINGLE_THREAD_TERMINAL_CURRENT_DIR__"
# 默认禁止命令列表（系统安装类命令，含空格避免误判）
_DEFAULT_PROHIBITED_COMMANDS = [
    "sudo ", "su ",             # 提权命令
    "shutdown", "reboot",       # 系统重启/关机
    "rm -rf /", "dd if=/",      # 危险删除/覆盖
    "mv /", "cp /",             # 系统文件移动/复制
    "rm -rf *", "rm -rf .*",    # 批量删除操作
    "apt ", "apt-get ", "yum ", "dnf ", "brew ", "dpkg ", "rpm "    # 软件包管理命令
]
# 常见脚本解释器列表（用于识别脚本执行命令）
_SCRIPT_INTERPRETERS = [
    "python ", "python3 ", "python2 ",              # Python
    "bash ", "sh ", "zsh ", "ksh ", "csh ",         # Shell脚本
    "go run ", "go test ",                          # Go语言
    "node ", "npm run ", "yarn run ", "pnpm run ",  # JavaScript/TypeScript
    "perl ", "ruby ", "php ", "lua ",               # 其他脚本语言
    "./", ".sh ", ".py ", ".go ", ".js "            # 直接执行脚本文件
]
# 逃逸命令匹配正则（新增安装类命令，防止嵌套逃逸）
_ESCAPED_CMD_PATTERN = re.compile(
    r'[\'\"`].*?(sudo|rm -rf|shutdown|reboot|apt|apt-get|yum|dnf|brew|dpkg|rpm).*?[\'\"`]',
    re.IGNORECASE
)
# 路径类命令清单（需重点校验路径参数的命令，用于强化日志提示）
_PATH_SENSITIVE_COMMANDS = ["find", "grep", "ls", "cp", "mv", "rm", "cat", "sed"]


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
    def get_current_dir(self) -> str:
        """获取终端当前会话的工作目录（与bash状态实时同步）。

        Returns:
            str: 当前目录绝对路径（如"/home/user/safe_ws/subdir"）。

        Raises:
            RuntimeError: 终端未启动或目录同步失败。
        """
        raise NotImplementedError

    @abstractmethod
    def cd_to_workspace(self) -> None:
        """切换终端当前目录到workspace根目录（执行cd命令）。

        通过执行 `cd <workspace路径>` 命令，将终端当前工作目录切换到
        workspace根目录，并同步内部状态。

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
    def get_prohibited_commands(self) -> List[str]:
        """获取终端禁止执行的命令列表（黑名单）。

        无论允许列表是否为空，黑名单命令均会被拒绝。

        Returns:
            List[str]: 禁止命令列表（如["sudo ", "chmod ", "apt "]）。
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
    def run_command(self, command: str, allow_by_human: bool = False) -> str:
        """执行bash命令，返回输出并同步终端状态（含安全校验）。

        Args:
            command: 待执行的bash命令（如"grep 'key' ./file.txt"、"find ./src -name '*.py'"）。
            allow_by_human: 被人类允许执行

        Returns:
            str: 命令标准输出（已过滤空行与标记）。

        Raises:
            RuntimeError: 终端未启动或工作空间未初始化。
            PermissionError: 命令未通过安全校验（如在黑名单、路径越界）。
            subprocess.SubprocessError: 命令执行中发生IO错误。
        """
        raise NotImplementedError

    @abstractmethod
    def acquire(self) -> None:
        """获取终端使用信号量，确保线程安全。

        同一时刻只能有一个线程/协程获取此信号量并使用终端。
        调用方必须在完成终端操作后调用 release() 释放信号量。

        建议使用模式：
        ```
        terminal.acquire()
        try:
            terminal.run_command("ls")
        finally:
            terminal.release()
        ```

        Raises:
            RuntimeError: 终端未启动或信号量获取失败。
        """
        raise NotImplementedError

    @abstractmethod
    def release(self) -> None:
        """释放终端使用信号量，唤醒等待的线程。

        Raises:
            RuntimeError: 终端未启动或信号量释放失败。
            RuntimeError: 未获取信号量就尝试释放。
        """
        raise NotImplementedError

    @abstractmethod
    def check_command(self, command: str, allow_by_human: bool = False) -> bool:
        """按固定顺序执行命令安全校验，返回是否可执行。
        重点强化：find/grep等路径类命令的越界拦截，所有路径参数需在工作空间内。

        Args：
            command: 待校验的bash命令字符串。
            allow_by_human: 是否由人类用户允许执行（True时跳过白名单和脚本限制）

        Returns:
            bool: True=命令安全可执行，False=命令不安全。

        Raises:
            RuntimeError: 工作空间未初始化或当前目录未同步。
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


class SingleThreadTerminal(ITerminal):
    """单线程终端实现类，支持允许命令列表、脚本禁用与状态同步。

    核心特性：
    - 构造函数强制注入工作空间，确保所有操作在指定范围内
    - 允许列表（白名单）与禁止列表（黑名单）双重控制
    - 默认禁用脚本执行，防止通过脚本逃逸工作空间限制
    - 实时同步终端当前目录，支持cd命令在工作空间内自由跳转
    - 强化路径校验：find/grep等路径类命令均需通过工作空间边界检查
    - 线程安全：通过 threading.RLock 确保同一时刻只有一个线程使用终端
    """
    _terminal_id: str                # 终端唯一标识符
    _workspace: str                  # 强制绑定的工作空间（绝对路径）
    _current_dir: Optional[str]      # 终端当前目录（与bash实时同步）
    _process: Optional[subprocess.Popen[str]]  # 长期bash进程
    _allowed_commands: List[str]     # 允许命令列表（白名单）
    _prohibited_commands: List[str]  # 禁止命令列表（黑名单）
    _disable_script_execution: bool  # 是否禁用脚本执行
    _lock: threading.RLock           # 线程锁，确保线程安全

    def __init__(
        self,
        workspace: str,
        create_workspace: bool = False,
        allowed_commands: Optional[List[str]] = None,
        prohibited_commands: Optional[List[str]] = None,
        disable_script_execution: bool = True
    ) -> None:
        """终端实例化构造函数，强制注入工作空间与安全控制参数。

        Args:
            workspace: 终端绑定的工作空间路径（支持相对路径，自动转为绝对路径）。
            create_workspace: 工作空间不存在时是否自动创建（默认False）。
            allowed_commands: 允许命令列表（白名单），默认空列表（允许除禁止外的所有命令）。
            prohibited_commands: 禁止命令列表（黑名单），默认使用_DEFAULT_PROHIBITED_COMMANDS。
            disable_script_execution: 是否禁用脚本执行（默认True，拒绝python/bash等脚本）。

        Raises:
            FileNotFoundError: 工作空间不存在且create_workspace=False。
            NotADirectoryError: workspace路径存在但不是目录。
            RuntimeError: 终端进程启动失败或不兼容Windows系统。
        """
        # 0. Windows系统兼容性检查
        if os.name == 'nt':
            raise RuntimeError(
                "当前系统为Windows，本终端工具不支持Windows环境。\n"
                "请使用Linux/macOS/WSL环境运行。"
            )

        self._terminal_id = uuid4().hex  # 生成唯一终端ID
        self._lock = threading.RLock()   # 初始化线程锁（可重入锁）
        # 1. 处理工作空间：校验路径合法性，必要时创建
        workspace_abs = os.path.abspath(workspace)
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
        default_prohibited = _DEFAULT_PROHIBITED_COMMANDS.copy()
        self._prohibited_commands = (
            prohibited_commands.copy() if prohibited_commands else default_prohibited
        )
        self._disable_script_execution = disable_script_execution

        # 3. 初始化终端状态，启动进程
        self._current_dir = None
        self._process = None
        self.open()  # 自动启动终端进程
        self._sync_current_dir()  # 同步初始目录（工作空间根目录）

    def get_id(self) -> str:
        return self._terminal_id

    def get_workspace(self) -> str:
        if not self._workspace:
            raise RuntimeError("工作空间未初始化（内部错误）")
        return self._workspace

    def cd_to_workspace(self) -> None:
        """切换终端当前目录到workspace根目录（执行cd命令）"""
        workspace = self.get_workspace()
        # 执行 cd 命令切换到 workspace
        self.run_command(f"cd {workspace}", allow_by_human=True)
        logger.info(f"🔄 已切换终端当前目录到workspace：{workspace}")

    def acquire(self) -> None:
        """获取终端使用信号量，确保线程安全"""
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("终端未运行或已退出")
        logger.debug(f"🔒 线程 {threading.current_thread().name} 获取终端锁")
        self._lock.acquire()

    def release(self) -> None:
        """释放终端使用信号量，唤醒等待的线程"""
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("终端未运行或已退出")
        self._lock.release()
        logger.debug(f"🔓 线程 {threading.current_thread().name} 释放终端锁")

    def get_current_dir(self) -> str:
        if self._current_dir is None:
            raise RuntimeError(
                "终端当前目录未同步，可能终端未启动，需先调用open()"
            )
        return self._current_dir

    def get_allowed_commands(self) -> List[str]:
        # 返回列表副本，防止外部修改内部状态（防御性编程）
        return self._allowed_commands.copy()

    def get_prohibited_commands(self) -> List[str]:
        return self._prohibited_commands.copy()

    def is_script_execution_disabled(self) -> bool:
        return self._disable_script_execution

    def open(self) -> None:
        # 检查进程是否已运行（避免重复启动）
        if self._process and self._process.poll() is not None:
            raise RuntimeError(f"终端进程已在运行（PID: {self._process.pid}），无需重复启动")

        try:
            # 启动长期bash进程（配置双向管道与行缓冲）
            self._process = subprocess.Popen(
                args=["bash"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 错误流合并到stdout，统一处理
                text=True,                 # 文本模式（避免字节流转换）
                bufsize=1,                 # 行缓冲，确保实时输出
                shell=False,               # 列表传参，防止命令注入
                close_fds=True             # 关闭无关文件描述符，减少资源占用
            )
            logger.info(f"✅ 终端进程启动成功（PID: {self._process.pid}）")

        except Exception as e:
            raise RuntimeError(f"终端进程启动失败：{str(e)}") from e

    def _sync_current_dir(self) -> None:
        """私有方法：同步bash会话的真实当前目录到_current_dir。

        通过发送pwd命令+特殊标记，提取终端当前目录，确保状态准确性。

        Raises:
            RuntimeError: 终端未启动、进程意外退出或目录提取失败。
        """
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("无法同步当前目录：终端未运行或已退出")

        if not self._process.stdin or not self._process.stdout:
            raise RuntimeError("终端进程输入/输出流未初始化")

        # 发送pwd命令+标记，避免与正常输出混淆
        sync_cmd = f"pwd && echo '{_CURRENT_DIR_MARKER}'\n"
        self._process.stdin.write(sync_cmd)
        self._process.stdin.flush()

        # 读取输出，提取当前目录
        current_dir = None
        while True:
            line = self._process.stdout.readline()
            if not line:
                # 无输出且进程已终止，说明意外退出
                if self._process.poll() is not None:
                    raise RuntimeError(f"终端进程意外退出（PID: {self._process.pid}）")
                continue

            line_clean = line.rstrip("\n")
            if line_clean == _CURRENT_DIR_MARKER:
                break  # 遇到标记，停止读取
            if current_dir is None:
                current_dir = line_clean  # pwd输出仅一行，取第一行

        # 校验当前目录是否在工作空间内（防止异常情况）
        if not current_dir:
            raise RuntimeError("获取当前目录失败：pwd命令返回空值")
        if not current_dir.startswith(self._workspace):
            raise RuntimeError(
                f"当前目录（{current_dir}）超出工作空间（{self._workspace}），可能存在安全风险"
            )

        self._current_dir = current_dir
        logger.info(f"🔄 同步终端当前目录：{self._current_dir}")

    def _is_script_command(self, command: str) -> bool:
        """私有方法：判断命令是否为脚本执行命令（基于_SCRIPT_INTERPRETERS）。

        Args:
            command: 待判断的bash命令字符串。

        Returns:
            bool: True=命令是脚本执行（如python、bash），False=非脚本命令。
        """
        command_lower = command.strip().lower()
        # 检查命令是否包含常见脚本解释器（忽略大小写）
        for interpreter in _SCRIPT_INTERPRETERS:
            if interpreter.lower() in command_lower:
                # 特殊处理脚本文件（如./script.sh、test.py）
                if interpreter in ["./", ".sh ", ".py ", ".go ", ".js "]:
                    # 确保是文件执行，而非普通路径（如"./dir"是目录跳转，不算脚本）
                    script_extensions = [".sh", ".py", ".go", ".js"]
                    is_script_file = any(ext in command_lower for ext in script_extensions)
                    if is_script_file or command_lower.startswith("./"):
                        return True
                else:
                    return True
        return False

    def _has_escaped_prohibited_cmd(self, command: str) -> bool:
        """私有方法：检查命令中是否包含嵌套（逃逸）的禁止命令。

        识别场景：如"bash -c 'apt install git'"、"sh -c 'chmod 777 test.txt'"等嵌套命令。

        Args:
            command: 待检查的bash命令字符串。

        Returns:
            bool: True=包含逃逸禁止命令，False=无逃逸命令。
        """
        # 1. 匹配引号/反引号中的禁止命令（含新增的chmod/安装类命令）
        match = _ESCAPED_CMD_PATTERN.search(command)
        if match:
            escaped_cmd = match.group(1)
            logger.error(f"❌ 命令包含逃逸禁止命令：{escaped_cmd}（嵌套在引号/反引号中）")
            return True

        # 2. 检查管道/分号逃逸（如"echo 1 | apt update"、"ls; chmod 777 test.txt"）
        for prohibited in self._prohibited_commands:
            if prohibited in command and ("|" in command or ";" in command):
                logger.error(f"❌ 命令通过管道/分号逃逸禁止命令：{prohibited}")
                return True

        return False

    def check_command(self, command: str, allow_by_human: bool = False) -> bool:
        """按固定顺序执行命令安全校验（允许列表→脚本→逃逸→禁止列表→路径）。

        重点强化：find/grep等路径类命令的越界拦截，所有路径参数需在工作空间内。

        Args:
            command: 待校验的bash命令字符串（如"find ./src -name '*.py'"、"grep 'key' ./file.txt"）。
            allow_by_human: 是否由人类用户允许执行（True时跳过白名单和脚本限制）

        Returns:
            bool: True=命令安全可执行，False=命令不安全。

        Raises:
            RuntimeError: 工作空间未初始化或当前目录未同步。
        """
        # 前置状态校验
        if not self._workspace:
            raise RuntimeError("无法检查命令：工作空间未初始化")
        if self._current_dir is None:
            raise RuntimeError("无法检查命令：终端当前目录未同步")
        command_stripped = command.strip()
        if not command_stripped:
            logger.error("❌ 空命令，拒绝执行")
            return False

        # 1. 第一步：允许命令列表检查（人类允许时跳过）
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
        else:
            logger.info("✅ 人类用户允许，跳过允许列表检查")  # 跳过白名单

        # 2. 第二步：脚本执行检查（人类允许时跳过）
        if not allow_by_human and self._disable_script_execution:  # 仅当“非人类允许”且“禁用脚本”时检查
            if self._is_script_command(command_stripped):
                logger.error(
                    f"❌ 命令是脚本执行（已禁用）：{command_stripped}\n"
                    f"    禁用的脚本类型：{_SCRIPT_INTERPRETERS[:10]}..."
                )
                return False
            logger.info("✅ 第二步：脚本执行检查通过")
        else:
            if allow_by_human:
                logger.info("✅ 人类用户允许，跳过脚本执行检查")  # 跳过脚本限制
            else:
                logger.info("✅ 第二步：脚本执行检查通过（脚本执行未禁用）")

        # 3. 第三步：逃逸禁止命令检查（强制执行，不可绕过）
        if self._has_escaped_prohibited_cmd(command_stripped):
            return False
        logger.info("✅ 第三步：逃逸禁止命令检查通过")

        # 4. 第四步：禁止命令列表检查（强制执行，不可绕过）
        for prohibited in self._prohibited_commands:
            if prohibited in command_stripped:
                logger.error(
                    f"❌ 命令包含禁止操作：{prohibited}\n"
                    f"    完整命令：{command_stripped}"
                )
                return False
        logger.info("✅ 第四步：禁止列表检查通过")

        # 5. 第五步：路径范围检查（强制执行，不可绕过）
        try:
            cmd_parts = shlex.split(command_stripped)
        except ValueError:
            logger.error(f"❌ 命令语法错误（如未闭合引号）：{command_stripped}")
            return False
        dynamic_base = self._current_dir
        workspace_abs = self._workspace
        cmd_name = cmd_parts[0].lower() if cmd_parts else ""
        i = 0
        while i < len(cmd_parts):
            part = cmd_parts[i]
            # 处理cd命令：校验跳转目标是否在工作空间内
            if part.lower() == "cd" and i + 1 < len(cmd_parts):
                cd_target = cmd_parts[i + 1]
                cd_target_abs = os.path.abspath(os.path.join(dynamic_base, cd_target))
                if not cd_target_abs.startswith(workspace_abs):
                    logger.error(
                        f"❌ cd目标超出工作空间：{cd_target_abs}\n"
                        f"    工作空间：{workspace_abs}"
                    )
                    return False
                dynamic_base = cd_target_abs
                i += 2
                continue
            # 处理路径类命令的参数（find/grep等，跳过选项，校验所有路径参数）
            if not part.startswith("-"):
                # 解析绝对路径（处理相对路径如"../src"、"./file.txt"）
                path_abs = os.path.abspath(os.path.join(dynamic_base, part))

                # 校验路径是否在工作空间内（排除非路径参数，如grep的关键词）
                # 逻辑：若为路径敏感命令，且参数是目录/文件，则必须在工作空间内
                is_path_sensitive = cmd_name in _PATH_SENSITIVE_COMMANDS
                is_valid_path = os.path.isdir(path_abs) or os.path.isfile(path_abs)
                if is_path_sensitive and is_valid_path:
                    if not path_abs.startswith(workspace_abs):
                        logger.error(
                            f"❌ {cmd_name.upper()}操作路径超出工作空间：{path_abs}\n"
                            f"    工作空间：{workspace_abs}"
                        )
                        return False
            i += 1
        logger.info("✅ 第五步：路径范围检查通过（含find/grep路径校验）")

        # 所有校验通过
        logger.info(f"✅ 命令安全可执行：{command_stripped}")
        return True

    def run_command(self, command: str, allow_by_human: bool = False) -> str:
        # 1. 前置校验：终端状态与命令安全性
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("终端未运行或已退出，需先调用open()启动")
        if not self._workspace:
            raise RuntimeError("无法执行命令：工作空间未初始化")
        if not self._process.stdin or not self._process.stdout:
            raise RuntimeError("终端进程输入/输出流未初始化")

        # 2. 安全校验（传入allow_by_human，控制是否绕过白名单/脚本限制）
        if not self.check_command(command, allow_by_human):
            raise PermissionError(f"命令未通过安全校验，拒绝执行：{command}")

        try:
            # 3. 包装命令：附加完成标记，确保准确分割输出
            wrapped_cmd = f"{command} && echo '{_COMMAND_DONE_MARKER}'\n"
            self._process.stdin.write(wrapped_cmd)
            self._process.stdin.flush()
            logger.info(f"📤 已发送命令到终端：{command}")

            # 4. 读取命令输出（直到遇到完成标记）
            output: list[str] = []
            while True:
                line: str = self._process.stdout.readline()
                # 处理进程意外退出的情况
                if not line:
                    if self._process.poll() is not None:
                        raise RuntimeError(f"终端进程意外退出（PID: {self._process.pid}），命令执行中断")
                    continue

                line_clean = line.rstrip("\n")
                if line_clean == _COMMAND_DONE_MARKER:
                    break  # 遇到标记，停止读取
                # 过滤空行（避免输出中大量无效空行）
                if line_clean.strip():
                    output.append(line_clean)

            # 5. 状态同步：若命令包含cd，更新当前目录
            cmd_lower = command.strip().lower()
            if "cd " in cmd_lower or cmd_lower == "cd":
                self._sync_current_dir()

            # 6. 返回清理后的输出
            result = "\n".join(output)
            logger.info(f"📥 命令执行完成，输出长度：{len(result)} 字符")
            return result

        except OSError as e:
            raise subprocess.SubprocessError(
                f"命令执行中发生IO错误：{str(e)}（命令：{command}）"
            ) from e

    def close(self) -> None:
        if not self._process or self._process.poll() is not None:
            logger.info("ℹ️ 终端进程已关闭或未启动，无需重复操作")
            return

        pid = self._process.pid  # 保存PID用于日志

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
            # 重置状态，避免后续调用异常
            self._process = None
            self._current_dir = None


# ------------------------------
# 示例用法（验证新增功能：禁止命令+路径越界防护）
# ------------------------------
if __name__ == "__main__":
    try:
        # 测试配置：允许基础命令+find/grep，禁用脚本，默认禁止命令
        test_workspace = os.path.abspath("safe_terminal_test")
        terminal = SingleThreadTerminal(
            workspace=test_workspace,
            create_workspace=True,
            allowed_commands=["ls", "cd", "touch", "mkdir", "grep", "find", "cat"],  # 允许路径类命令
            disable_script_execution=True
        )
        print(f"\n📋 初始配置：")
        print(f"   工作空间：{terminal.get_workspace()}")
        print(f"   允许命令：{terminal.get_allowed_commands()}")
        print(f"   禁止命令：{terminal.get_prohibited_commands()}")
        print(f"   禁用脚本：{terminal.is_script_execution_disabled()}\n")

        # 1. 测试正常路径类命令（find/grep在工作空间内）
        print("=" * 60)
        print("1. 测试正常路径命令：find ./ -name '*.txt' + grep 'test' ./test.txt")
        # 创建测试文件
        terminal.run_command("touch test.txt && echo 'test content' > test.txt")
        # 执行find（查找工作空间内的txt文件）
        find_output = terminal.run_command("find ./ -name '*.txt'")
        print(f"find输出：\n{find_output}")
        # 执行grep（搜索工作空间内的文件）
        grep_output = terminal.run_command("grep 'test' ./test.txt")
        print(f"grep输出：\n{grep_output}\n")

        # 2. 测试允许命令（chmod修改权限 - 现在允许）
        print("=" * 60)
        print("2. 测试允许命令：chmod 777 test.txt")
        try:
            terminal.run_command("chmod 777 test.txt")
            print("✅ chmod 命令执行成功\n")
        except PermissionError as e:
            print(f"错误：{e}\n")

        # 3. 测试禁止命令（apt安装）
        print("=" * 60)
        print("3. 测试禁止命令：apt install git")
        try:
            terminal.run_command("apt install git")
        except PermissionError as e:
            print(f"预期错误：{e}\n")

        # 4. 测试路径越界（grep外部文件）
        print("=" * 60)
        print("4. 测试路径越界：grep 'key' /home/outside/test.txt")
        try:
            terminal.run_command("grep 'key' /home/outside/test.txt")
        except PermissionError as e:
            print(f"预期错误：{e}\n")

        # 5. 测试路径越界（find外部目录）
        print("=" * 60)
        print("5. 测试路径越界：find /home/outside -name '*.py'")
        try:
            terminal.run_command("find /home/outside -name '*.py'")
        except PermissionError as e:
            print(f"预期错误：{e}\n")

        # 6. 测试逃逸禁止命令（bash -c 'apt update'）
        print("=" * 60)
        print("6. 测试逃逸禁止命令：bash -c 'apt update'")
        try:
            terminal.run_command("bash -c 'apt update'")
        except PermissionError as e:
            print(f"预期错误：{e}\n")

        # 新增测试：人类允许执行“不在白名单但非黑名单”的命令（如head命令，默认不在允许列表）
        print("=" * 60)
        print("7. 测试人类允许：执行不在白名单的命令（head test.txt）")
        try:
            # allow_by_human=True，绕过白名单（允许列表无head）
            head_output = terminal.run_command("head -n 1 test.txt", allow_by_human=True)
            print(f"head输出：\n{head_output}")
        except PermissionError as e:
            print(f"预期错误：{e}\n")

        # 新增测试：人类允许执行其他命令
        print("=" * 60)
        print("8. 测试其他文件操作命令（file test.txt）")
        try:
            file_output = terminal.run_command("file test.txt", allow_by_human=True)
            print(f"file命令输出：\n{file_output}\n")
        except PermissionError as e:
            print(f"错误：{e}\n")

    except Exception as e:
        print(f"\n❌ 示例执行异常：{str(e)}")
    finally:
        # 确保终端关闭
        terminal = locals().get('terminal')
        if terminal:
            print("\n" + "=" * 60)
            terminal.close()
