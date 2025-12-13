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
import time
import fcntl
import platform
from abc import ABC, abstractmethod
from uuid import uuid4
from typing import List, Optional
from pathlib import Path

from loguru import logger

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
        "regex": r'(shutdown -h now)|(reboot now)',  # 强制关机重启
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

    # 4. 软件包/系统管理命令（非人类允许时拦截）
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
_PATH_SENSITIVE_COMMANDS = ["find", "grep", "ls", "cp", "mv", "rm", "cat", "sed"]

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
    def cd_to_workspace(self) -> None:
        """切换终端当前目录"""

    @abstractmethod
    def get_current_dir(self) -> str:
        """获取终端当前会话的工作目录（与bash状态实时同步）。

        Returns:
            str: 当前目录绝对路径（如"/home/user/safe_w录切换到
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

        安全检查顺序（严格遵循）：
        1. 允许命令列表检查（非空时，仅允许列表内命令）
        2. 脚本执行检查（若禁用，拒绝所有脚本解释器命令）
        3. 逃逸禁止命令检查（拒绝嵌套在引号/反引号中的禁止命令）
        4. 禁止命令列表检查（拒绝列表内的危险命令）
        5. 路径范围检查（所有涉及路径的命令，均需在工作空间内）

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
    def run_command(
        self, command: str, allow_by_human: bool = False, timeout: Optional[float] = None
    ) -> str:
        """执行bash命令，返回输出并同步终端状态（含安全校验）。

        Args:
            command: 待执行的bash命令（如"grep 'key' ./file.txt"、"find ./src -name '*.py'"）。
            allow_by_human: 被人类允许执行
            timeout: 超时时间（秒），None表示不限制超时

        Returns:
            str: 命令标准输出（已过滤空行与标记）。

        Raises:
            RuntimeError: 终端未启动或工作空间未初始化。
            PermissionError: 命令未通过安全校验（如在黑名单、路径越界）。
            subprocess.SubprocessError: 命令执行中发生IO错误。
            TimeoutError: 命令执行超时。
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
    """
    _terminal_id: str                   # 终端唯一标识符
    _root_dir: str                      # 根目录路径（绝对路径）
    _workspace: str                     # 工作空间（绝对路径，默认为root_dir）
    _current_dir: str                   # 终端当前目录（与bash实时同步）
    _process: subprocess.Popen[str]     # 长期bash进程
    _allowed_commands: List[str]        # 允许命令列表（白名单）
    _disable_script_execution: bool     # 是否禁用脚本执行
    _lock: threading.RLock              # 线程锁，确保线程安全
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
            RuntimeError: 终端进程启动失败。
        """
        # 检查当前系统，仅支持类Unix系统（Linux、macOS等）
        if platform.system() not in {"Linux", "Darwin"}:
            raise RuntimeError(
                f"LocalTerminal仅支持类Unix系统，当前系统为：{platform.system()}"
            )
        
        self._terminal_id = uuid4().hex  # 生成唯一终端ID
        self._lock = threading.RLock()   # 初始化线程锁（可重入锁）

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

        # 4. 初始化终端状态，启动进程
        self._current_dir = ""
        self.open()  # 自动启动终端进程

        # 5. 直接切换到工作空间目录（初始化时允许从任何目录切换）
        logger.info(f"🔄 切换到工作空间目录：{self._workspace}")
        try:
            # 直接发送cd命令，绕过安全检查（因为这是初始化步骤）
            if not self._process or not self._process.stdin:
                raise RuntimeError("终端进程或输入流未初始化")
            cd_cmd = f"cd {self._workspace}\n"
            self._process.stdin.write(cd_cmd)
            self._process.stdin.flush()

            # 同步当前目录（现在目录已经在workspace内，使用正常同步方法）
            self._sync_current_dir()
            logger.info(f"✅ 已切换到工作空间目录：{self._current_dir}")
        except Exception as e:
            logger.error(f"❌ 切换到工作空间目录失败：{e}")
            raise

        # 6. 运行初始化命令
        self._init_commands = init_commands if init_commands is not None else []
        for cmd in self._init_commands:
            self.run_command(cmd)

    def get_id(self) -> str:
        return self._terminal_id

    def get_workspace(self) -> str:
        if not self._workspace:
            raise RuntimeError("工作空间未初始化（内部错误）")
        return self._workspace

    def cd_to_workspace(self) -> None:
        """切换终端当前目录到workspace根目录（支持含特殊字符的路径）"""
        workspace = self.get_workspace()
        try:
            if not self._process or not self._process.stdin:
                raise RuntimeError("终端进程或输入流未初始化")
            
            # 用shlex.quote转义路径（处理空格、引号等特殊字符）
            quoted_workspace = shlex.quote(workspace)
            cd_cmd = f"cd {quoted_workspace}\n"
            self._process.stdin.write(cd_cmd)
            self._process.stdin.flush()

            # 同步当前目录
            self._sync_current_dir()
            logger.info(f"🔄 已切换到workspace目录（含特殊字符处理）：{workspace}")
        except Exception as e:
            logger.error(f"❌ 切换到workspace目录失败：{e}")
            raise

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
            )
            logger.info(f"✅ 终端进程启动成功（PID: {self._process.pid}）")

        except Exception as e:
            raise RuntimeError(f"终端进程启动失败：{str(e)}") from e
        
    def _get_real_current_dir(self) -> str:
        """私有辅助方法：获取进程真实当前工作目录（避免pwd被篡改）。
        
        优先级：
        1. Linux：/proc/self/cwd（内核维护，不可篡改）；
        2. 其他系统：pwd -P（强制物理路径，忽略PWD环境变量）。
        
        Returns:
            str: 真实当前目录绝对路径。
        
        Raises:
            RuntimeError: 获取真实目录失败。
        """
        # 场景1：Linux系统（优先使用/proc/self/cwd）
        proc_cwd_path = "/proc/self/cwd"
        if os.path.exists(proc_cwd_path) and os.path.islink(proc_cwd_path):
            try:
                # 读取符号链接指向的真实路径（内核保证准确性）
                real_cwd = os.readlink(proc_cwd_path)
                # 转为绝对路径（处理符号链接可能的相对路径）
                real_cwd_abs = os.path.abspath(real_cwd)
                logger.debug(f"📌 从/proc/self/cwd获取真实目录：{real_cwd_abs}")
                return real_cwd_abs
            except (OSError, ValueError) as e:
                logger.warning(f"⚠️ /proc/self/cwd读取失败，降级使用pwd -P：{str(e)[:50]}")

        # 场景2：非Linux系统（降级使用pwd -P）
        try:
            # pwd -P：强制获取物理路径，忽略PWD环境变量和符号链接
            result = subprocess.check_output(
                ["pwd", "-P"],
                stdin=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                cwd=self._root_dir  # 避免父进程目录影响
            )
            real_cwd_abs = result.strip()
            logger.debug(f"📌 从pwd -P获取真实目录：{real_cwd_abs}")
            return real_cwd_abs
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"获取真实目录失败（pwd -P执行错误）：{e.output.strip()}") from e
        except Exception as e:
            raise RuntimeError(f"获取真实目录失败：{str(e)[:50]}") from e

    def _sync_current_dir(self) -> None:
        """私有方法：同步bash会话的真实当前目录到_current_dir（防篡改）。
        
        优化点：
        1. 用/proc/self/cwd或pwd -P替代pwd，避免被环境变量篡改；
        2. 新增真实目录的根目录校验，确保安全边界。
        """
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("无法同步当前目录：终端未运行或已退出")

        try:
            # 步骤1：获取进程真实当前目录（核心修改：替换pwd命令）
            real_cwd = self._get_real_current_dir()

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
            else:
                logger.info(f"🔄 同步终端当前目录：{real_cwd} (在workspace外，但在root_dir内)")

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
        # 使用正则表达式分割命令
        parts = _COMMAND_SEPARATORS_PATTERN.split(command)

        # 过滤空命令并去除首尾空格
        commands: list[str] = []
        for part in parts:
            trimmed = part.strip()
            if trimmed:  # 只保留非空命令
                commands.append(trimmed)

        return commands

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

            # 4. 检查当前独立命令是否命中任一脚本规则
            for rule in script_rules:
                # 用正则匹配：忽略大小写（已预处理小写，此处可简化）
                match = re.search(rule, single_cmd_stripped)
                if match:
                    # 特殊排除：避免将“目录路径”误判为脚本（如 ./dir/ 不是脚本）
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

        # 步骤2：正则匹配「命令执行型嵌套」（支持转义/未转义引号）
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
        cmd_parts = shlex.split(command_path.strip())
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
            cmd_parts = shlex.split(command)
            if not cmd_parts:
                return True

            cmd_name = self._extract_command_name(cmd_parts[0])
            # 非路径敏感命令直接放行
            if cmd_name not in _PATH_SENSITIVE_COMMANDS:
                return True

            # 遍历所有参数，逐个校验路径
            for arg in cmd_parts[1:]:
                arg_stripped = arg.strip()
                # 排除非路径参数（URL、纯选项等）
                if arg_stripped.startswith(("http://", "https://")) or arg_stripped.startswith("-"):
                    continue
                if not arg_stripped or arg_stripped == "/":
                    continue

                # 解析路径（处理~用户目录、相对路径）
                try:
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
                elif not allow_by_human and not abs_path.startswith(self._workspace):
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

    def _read_command_output_nonblocking(self, timeout: Optional[float], command: str) -> list[str]:
        """私有方法：使用非阻塞方式读取命令输出。

        Args:
            timeout: 超时时间（秒）
            command: 执行的命令（用于错误信息）

        Returns:
            list[str]: 命令输出行列表

        Raises:
            TimeoutError: 命令执行超时
            RuntimeError: 终端进程意外退出
        """
        if not self._process:
            raise RuntimeError("终端进程未初始化")

        output: list[str] = []
        start_time = time.time()

        while True:
            # 检查是否超时
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise TimeoutError(f"命令执行超时（{timeout}秒）：{command}")

            # 使用非阻塞方式检查进程状态
            if self._process.poll() is not None:
                # 进程已退出，读取剩余输出
                if self._process.stdout:
                    remaining_output = self._process.stdout.read()
                    if remaining_output:
                        for line in remaining_output.splitlines():
                            line_clean = line.rstrip("\n")
                            if line_clean == _COMMAND_DONE_MARKER:
                                break
                            if line_clean.strip():
                                output.append(line_clean)
                break

            # 尝试非阻塞读取
            line = self._try_nonblocking_read()
            if line is None:
                # 没有数据可读，等待一小段时间
                time.sleep(0.01)
                continue

            # 处理读取到的行
            line_clean = line.rstrip("\n")
            if line_clean == _COMMAND_DONE_MARKER:
                break  # 遇到标记，停止读取
            if line_clean.strip():
                output.append(line_clean)

        return output

    def _try_nonblocking_read(self) -> str | None:
        """私有方法：尝试非阻塞读取一行输出。

        Returns:
            str | None: 读取到的行，如果没有数据则返回None

        Raises:
            RuntimeError: 终端进程意外退出
        """
        if not self._process or not self._process.stdout:
            return None

        try:
            # 设置文件描述符为非阻塞模式
            fd = self._process.stdout.fileno()
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            # 尝试读取数据
            try:
                line = self._process.stdout.readline()
                return line if line else None
            except OSError:
                # 没有数据可读
                return None
            finally:
                # 恢复阻塞模式
                fcntl.fcntl(fd, fcntl.F_SETFL, flags)

        except (AttributeError, OSError) as exc:
            # 如果fcntl操作失败，使用简单的阻塞读取
            if self._process.stdout:
                line = self._process.stdout.readline()
                if not line:
                    if self._process and self._process.poll() is not None:
                        raise RuntimeError(
                            f"终端进程意外退出（PID: {self._process.pid}），命令执行中断"
                        ) from exc
                    return None
                return line
            return None

    def _sync_directory_if_needed(self, command: str) -> None:
        """私有方法：如果命令包含cd操作，同步当前目录。

        Args:
            command: 执行的命令
        """
        cmd_lower = command.strip().lower()
        if "cd " in cmd_lower or cmd_lower == "cd":
            self._sync_current_dir()

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

    def run_command(
        self, command: str, allow_by_human: bool = False, timeout: float | None = None
    ) -> str:
        """执行bash命令，返回输出并同步终端状态（含安全校验）。

        Args:
            command: 待执行的bash命令（如"grep 'key' ./file.txt"、"find ./src -name '*.py'"）。
            allow_by_human: 被人类允许执行
            timeout: 超时时间（秒），None表示不限制超时

        Returns:
            str: 命令标准输出（已过滤空行与标记）。

        Raises:
            RuntimeError: 终端未启动或工作空间未初始化。
            PermissionError: 命令未通过安全校验（如在黑名单、路径越界）。
            subprocess.SubprocessError: 命令执行中发生IO错误。
            TimeoutError: 命令执行超时。
        """
        # 1. 前置校验：终端状态
        self._validate_terminal_state()

        # 2. 安全校验（传入allow_by_human，控制是否绕过白名单/脚本限制）
        if not self.check_command(command, allow_by_human):
            raise PermissionError(f"命令未通过安全校验，拒绝执行：{command}")

        try:
            # 3. 包装命令：附加完成标记，确保准确分割输出
            wrapped_cmd = f"{command} && echo '{_COMMAND_DONE_MARKER}'\n"
            if self._process and self._process.stdin:
                self._process.stdin.write(wrapped_cmd)
                self._process.stdin.flush()
            logger.info(f"📤 已发送命令到终端：{command}")

            # 4. 读取命令输出（直到遇到完成标记或超时）
            output = self._read_command_output_nonblocking(timeout, command)

            # 5. 状态同步：若命令包含cd，更新当前目录
            self._sync_directory_if_needed(command)

            # 6. 返回清理后的输出
            result = "\n".join(output)
            logger.info(f"📥 命令执行完成，输出长度：{len(result)} 字符")
            return result

        except TimeoutError:
            # 超时处理，直接重新抛出
            raise
        except OSError as e:
            raise subprocess.SubprocessError(
                f"命令执行中发生IO错误：{str(e)}（命令：{command}）"
            ) from e

    def close(self) -> None:
        if not self._process or self._process.poll() is not None:
            logger.info("ℹ️ 终端进程已关闭或未启动，无需重复操作")
            return

        pid = self._process.pid  # 保存PID用于日志
        self.acquire()  # 确保线程安全关闭

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
            if hasattr(self, '_process'):
                del self._process
            self._current_dir = ""
            self.release()  # 释放锁


# ------------------------------
# 示例用法（验证新增功能：禁止命令+路径越界防护）
# ------------------------------
if __name__ == "__main__":
    try:
        # 测试配置：允许基础命令+find/grep+chmod，禁用脚本，默认禁止命令
        # 使用终端实际启动的目录作为根目录
        # 简单起见，使用绝对路径指定一个明确的目录
        TEST_ROOT_DIR = "/home/koko/Projects/tasking"
        TEST_WORKSPACE = "safe_terminal_test"
        terminal = LocalTerminal(
            root_dir=TEST_ROOT_DIR,
            workspace=TEST_WORKSPACE,
            create_workspace=True,
            allowed_commands=[  # 允许路径类命令+chmod
                "ls", "cd", "touch", "mkdir", "grep", "find", "cat", "chmod"
            ],
            disable_script_execution=True
        )
        print("\n📋 初始配置：")
        print(f"   工作空间：{terminal.get_workspace()}")
        print(f"   当前目录：{terminal.get_current_dir()}")
        print(f"   允许命令：{terminal.get_allowed_commands()}")
        print(f"   禁用脚本：{terminal.is_script_execution_disabled()}\n")

        # 1. 测试正常路径类命令（find/grep在工作空间内）
        print("=" * 60)
        print("1. 测试正常路径命令：find ./ -name '*.txt' + grep 'test' ./test.txt")
        # 创建测试文件
        terminal.run_command("touch test.txt && echo 'test content' > test.txt")
        # 执行find（查找工作空间内的txt文件）
        FIND_OUTPUT = terminal.run_command("find ./ -name '*.txt'")
        print(f"find输出：\n{FIND_OUTPUT}")
        # 执行grep（搜索工作空间内的文件）
        GREP_OUTPUT = terminal.run_command("grep 'test' ./test.txt")
        print(f"grep输出：\n{GREP_OUTPUT}\n")

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

        # 新增测试：人类允许执行"不在白名单但非黑名单"的命令（如head命令，默认不在允许列表）
        print("=" * 60)
        print("7. 测试人类允许：执行不在白名单的命令（head test.txt）")
        try:
            # allow_by_human=True，绕过白名单（允许列表无head）
            HEAD_OUTPUT = terminal.run_command("head -n 1 test.txt", allow_by_human=True)
            print(f"head输出：\n{HEAD_OUTPUT}")
        except PermissionError as e:
            print(f"预期错误：{e}\n")

        # 新增测试：人类允许执行其他命令
        print("=" * 60)
        print("8. 测试其他文件操作命令（file test.txt）")
        try:
            FILE_OUTPUT = terminal.run_command("file test.txt", allow_by_human=True)
            print(f"file命令输出：\n{FILE_OUTPUT}\n")
        except PermissionError as e:
            print(f"错误：{e}\n")

        # 新增测试：超时控制测试
        print("=" * 60)
        print("9. 测试超时控制：sleep 5 但只等待2秒超时")
        try:
            # 使用超时参数，2秒后应该超时
            terminal.run_command("sleep 5", timeout=2.0)
        except TimeoutError as e:
            print(f"预期超时错误：{e}\n")
        except Exception as e:
            print(f"其他错误：{e}\n")

        # 10. 新功能测试：人类允许时可以跳出workspace访问上级目录
        print("=" * 60)
        print("10. 测试人类允许：跳出workspace访问上级目录")
        try:
            # 不使用allow_by_human时应该被拒绝
            terminal.run_command("ls ../")
        except PermissionError as e:
            print(f"预期错误（无人类允许）：{e}")

        try:
            # 使用allow_by_human=True时应该被允许
            PARENT_OUTPUT = terminal.run_command("ls ../", allow_by_human=True)
            print(f"✅ 人类允许时成功访问上级目录，输出：\n{PARENT_OUTPUT[:200]}...\n")
        except PermissionError as e:
            print(f"意外错误：{e}\n")

        # 11. 新功能测试：人类允许时可以cd到workspace外
        print("=" * 60)
        print("11. 测试人类允许：cd到workspace外的目录")
        try:
            # 不使用allow_by_human时应该被拒绝
            terminal.run_command("cd ../")
        except PermissionError as e:
            print(f"预期错误（无人类允许）：{e}")

        try:
            # 使用allow_by_human=True时应该被允许
            terminal.run_command("cd ../", allow_by_human=True)
            current_dir = terminal.get_current_dir()
            print(f"✅ 人类允许时成功cd到上级目录，当前目录：{current_dir}")
            # 切回workspace以便后续测试
            terminal.cd_to_workspace()
        except PermissionError as e:
            print(f"意外错误：{e}\n")

        # 12. 新功能测试：绝对禁止命令即使人类允许也不行
        print("=" * 60)
        print("12. 测试绝对禁止命令：即使人类允许也不行")
        dangerous_commands = [
            "rm -rf /",
            "dd if=/dev/zero",
            "shutdown -h now",
            "mkfs"
        ]
        for cmd in dangerous_commands:
            try:
                terminal.run_command(cmd, allow_by_human=True)
                print(f"❌ 危险命令被执行：{cmd}")
            except PermissionError as e:
                print(f"✅ 危险命令被正确阻止：{cmd}")

        # 13. 新功能测试：workspace为None时默认使用root_dir
        print("=" * 60)
        print("13. 测试workspace为None时默认使用root_dir")
        try:
            terminal_no_ws = LocalTerminal(
                root_dir=TEST_ROOT_DIR,
                workspace=None,  # 明确设为None
                create_workspace=False,
                allowed_commands=["ls", "pwd", "echo"],
                disable_script_execution=True
            )
            workspace = terminal_no_ws.get_workspace()
            print(f"✅ workspace为None时，工作空间默认为：{workspace}")
            print(f"   是否等于root_dir：{workspace == TEST_ROOT_DIR}")
            terminal_no_ws.close()
        except Exception as e:
            print(f"错误：{e}")
            
        # 新增测试：验证精准删除、批量删除拦截、跨层级删除拦截
        print("=" * 60)
        print("14. 测试rm命令精准删除与批量拦截")
        # 14.1 允许：workspace内精准删除单个文件
        try:
            terminal.run_command("mkdir -p ./tmp && echo 'test' > ./tmp/log.txt")  # 准备测试文件
            terminal.run_command("rm -rf ./tmp/log.txt")  # 精准删除
            print("✅ 允许：workspace内精准删除（rm -rf ./tmp/log.txt）")
        except PermissionError as e:
            print(f"❌ 意外错误：{e}")

        # 14.2 拦截：批量删除（rm -rf *）
        try:
            terminal.run_command("rm -rf *")
            print("❌ 错误：批量删除未被拦截")
        except PermissionError as e:
            print(f"✅ 拦截：批量删除（rm -rf *），原因：{str(e)[:100]}")

        # 14.3 拦截：跨层级删除（rm -rf ../test.txt）
        try:
            terminal.run_command("rm -rf ../test.txt")
            print("❌ 错误：跨层级删除未被拦截")
        except PermissionError as e:
            print(f"✅ 拦截：跨层级删除（rm -rf ../test.txt），原因：{str(e)[:100]}")

        # 新增测试：验证提权命令拦截（sudo、su变体）
        print("=" * 60)
        print("15. 测试提权命令拦截")
        priv_commands = [
            "sudo -i",          # sudo带参数
            "/usr/bin/sudo ls", # 带路径的sudo
            "su root",          # su提权
            "sudoers",          # 编辑sudo配置
        ]
        for cmd in priv_commands:
            try:
                terminal.run_command(cmd, allow_by_human=True)  # 即使人类允许也拦截
                print(f"❌ 错误：提权命令{cmd}未被拦截")
            except PermissionError as e:
                print(f"✅ 拦截：提权命令{cmd}，原因：{str(e)[:80]}")

        # 新增测试：验证含特殊字符的workspace切换
        print("=" * 60)
        print("16. 测试含特殊字符的workspace切换")
        try:
            # 创建含空格和引号的workspace（如 "safe ws'2024"）
            special_ws = os.path.join(TEST_ROOT_DIR, "safe ws'2024")
            terminal_special = LocalTerminal(
                root_dir=TEST_ROOT_DIR,
                workspace=special_ws,
                create_workspace=True,
                allowed_commands=["ls", "pwd"],
            )
            print(f"✅ 成功创建并切换到含特殊字符的workspace：{terminal_special.get_workspace()}")
            terminal_special.close()
        except Exception as e:
            print(f"❌ 特殊字符workspace处理错误：{e}")

    except Exception as e:
        print(f"\n❌ 示例执行异常：{str(e)}")
    finally:
        # 确保终端关闭
        terminal = locals().get('terminal')
        if terminal:
            print("\n" + "=" * 60)
            terminal.close()
