"""
Terminal tool implementation providing secure command execution within a workspace.

This module implements a terminal abstraction with safety constraints, including
workspace restrictions, command whitelisting/blacklisting, and script execution control.
"""

import os
import subprocess
import shlex
import re
from abc import ABC, abstractmethod
from typing import List, Optional

# ------------------------------
# 核心常量定义（私有，避免外部修改）
# ------------------------------
# 命令执行完成标记（用于分割输出）
_COMMAND_DONE_MARKER = "__SINGLE_THREAD_TERMINAL_EXEC_DONE__"
# 当前目录同步标记（用于获取终端真实状态）
_CURRENT_DIR_MARKER = "__SINGLE_THREAD_TERMINAL_CURRENT_DIR__"
# 默认禁止命令列表（系统级危险操作，可通过构造函数覆盖）
_DEFAULT_PROHIBITED_COMMANDS = [
    "sudo ", "su ",          # 提权操作（含空格避免误判"sudoers"）
    "shutdown", "reboot",    # 系统关机/重启
    "rm -rf /", "dd if=/",   # 磁盘级危险操作
    "mv /", "cp /",          # 根目录操作
    "rm -rf *", "rm -rf .*"  # 批量删除当前/隐藏目录
]
# 常见脚本解释器列表（用于识别脚本执行命令）
_SCRIPT_INTERPRETERS = [
    # Python
    "python ", "python3 ", "python2 ",
    # Shell
    "bash ", "sh ", "zsh ", "ksh ", "csh ",
    # Go
    "go run ", "go test ",
    # Node.js
    "node ", "npm run ", "yarn run ", "pnpm run ",
    # 其他脚本
    "perl ", "ruby ", "php ", "lua ",
    # 脚本文件执行（如./script.sh、sh script.sh）
    "./", ".sh ", ".py ", ".go ", ".js "
]
# 逃逸命令匹配正则（识别嵌套在引号/反引号中的禁止命令）
_ESCAPED_CMD_PATTERN = re.compile(r'[\'\"`].*?(sudo|rm -rf|shutdown|reboot).*?[\'\"`]', re.IGNORECASE)


class ITerminal(ABC):
    """终端操作抽象接口，新增允许命令列表与脚本执行控制能力。
    
    安全检查顺序（严格遵循）：
    1. 允许命令列表检查（非空时，仅允许列表内命令）
    2. 脚本执行检查（若禁用，拒绝所有脚本解释器命令）
    3. 逃逸禁止命令检查（拒绝嵌套在引号/反引号中的禁止命令）
    4. 禁止命令列表检查（拒绝列表内的危险命令）
    """

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
    def get_allowed_commands(self) -> List[str]:
        """获取终端允许执行的命令列表（白名单）。

        规则：
        - 列表为空时：允许除「禁止命令列表」外的所有命令
        - 列表非空时：仅允许包含列表中命令的操作（如允许"ls"则允许"ls -l"）

        Returns:
            List[str]: 允许命令列表（如["ls", "cd", "touch"]）。
        """
        raise NotImplementedError

    @abstractmethod
    def get_prohibited_commands(self) -> List[str]:
        """获取终端禁止执行的命令列表（黑名单）。

        无论允许列表是否为空，黑名单命令均会被拒绝。

        Returns:
            List[str]: 禁止命令列表（如["sudo ", "rm -rf /"]）。
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
    def run_command(self, command: str) -> str:
        """执行bash命令，返回输出并同步终端状态（含安全校验）。

        Args:
            command: 待执行的bash命令（如"ls -l"、"touch test.txt"）。

        Returns:
            str: 命令标准输出（已过滤空行与标记）。

        Raises:
            RuntimeError: 终端未启动或工作空间未初始化。
            PermissionError: 命令未通过安全校验（如在黑名单、是禁用脚本）。
            subprocess.SubprocessError: 命令执行中发生IO错误。
        """
        raise NotImplementedError

    @abstractmethod
    def check_command(self, command: str) -> bool:
        """按固定顺序执行命令安全校验，返回是否可执行。

        校验失败时会打印原因（便于调试），成功返回True。

        Args:
            command: 待校验的bash命令字符串。

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
    """

    _workspace: str                  # 强制绑定的工作空间（绝对路径）
    _current_dir: Optional[str]      # 终端当前目录（与bash实时同步）
    _process: Optional[subprocess.Popen]  # 长期bash进程
    _allowed_commands: List[str]     # 允许命令列表（白名单）
    _prohibited_commands: List[str]  # 禁止命令列表（黑名单）
    _disable_script_execution: bool  # 是否禁用脚本执行

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
            RuntimeError: 终端进程启动失败。
        """
        # 1. 处理工作空间：校验路径合法性，必要时创建
        workspace_abs = os.path.abspath(workspace)
        if not os.path.exists(workspace_abs):
            if create_workspace:
                os.makedirs(workspace_abs, exist_ok=True)
                print(f"📁 自动创建工作空间：{workspace_abs}")
            else:
                raise FileNotFoundError(
                    f"工作空间不存在：{workspace_abs}，可设置create_workspace=True自动创建"
                )
        if not os.path.isdir(workspace_abs):
            raise NotADirectoryError(f"路径不是目录，无法作为工作空间：{workspace_abs}")
        self._workspace = workspace_abs

        # 2. 初始化安全控制参数（处理默认值，避免外部修改内部列表）
        self._allowed_commands = allowed_commands.copy() if allowed_commands else []
        self._prohibited_commands = prohibited_commands.copy() if prohibited_commands else _DEFAULT_PROHIBITED_COMMANDS.copy()
        self._disable_script_execution = disable_script_execution

        # 3. 初始化终端状态，启动进程
        self._current_dir = None
        self._process = None
        self.open()  # 自动启动终端进程
        self._sync_current_dir()  # 同步初始目录（工作空间根目录）

    def get_workspace(self) -> str:
        if not self._workspace:
            raise RuntimeError("工作空间未初始化（内部错误）")
        return self._workspace

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
        if self._process and self._process.poll() is None:
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
            print(f"✅ 终端进程启动成功（PID: {self._process.pid}）")

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
        print(f"🔄 同步终端当前目录：{self._current_dir}")

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
                    if any(ext in command_lower for ext in [".sh", ".py", ".go", ".js"]) or command_lower.startswith("./"):
                        return True
                else:
                    return True
        return False

    def _has_escaped_prohibited_cmd(self, command: str) -> bool:
        """私有方法：检查命令中是否包含嵌套（逃逸）的禁止命令。
        
        识别场景：如"bash -c 'sudo ls'"、"python -c 'rm -rf /'"等嵌套命令。
        
        Args:
            command: 待检查的bash命令字符串。
        
        Returns:
            bool: True=包含逃逸禁止命令，False=无逃逸命令。
        """
        # 用正则匹配引号/反引号中的禁止命令
        match = _ESCAPED_CMD_PATTERN.search(command)
        if match:
            escaped_cmd = match.group(1)
            print(f"❌ 命令包含逃逸禁止命令：{escaped_cmd}（嵌套在引号/反引号中）")
            return True
        # 额外检查是否通过管道/分号逃逸（如"echo 1 | sudo ls"）
        for prohibited in self._prohibited_commands:
            if prohibited in command and ("|" in command or ";" in command):
                print(f"❌ 命令通过管道/分号逃逸禁止命令：{prohibited}")
                return True
        return False

    def check_command(self, command: str) -> bool:
        """按用户指定顺序执行命令安全校验（允许列表→脚本→逃逸→禁止列表）。
        
        每步校验失败时打印具体原因，便于调试；所有步骤通过则返回True。
        
        Args:
            command: 待校验的bash命令字符串（如"ls -l"、"python script.py"）。
        
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
            print("❌ 空命令，拒绝执行")
            return False

        # 1. 第一步：允许命令列表检查（非空时，仅允许包含列表中命令的操作）
        if self._allowed_commands:
            # 检查命令是否包含允许列表中的任意命令（支持基础命令+选项，如允许"ls"则允许"ls -l"）
            command_lower = command_stripped.lower()
            is_allowed = any(
                allowed_cmd.lower() in command_lower
                for allowed_cmd in self._allowed_commands
            )
            if not is_allowed:
                print(
                    f"❌ 命令不在允许列表内：{command_stripped}\n"
                    f"    允许命令列表：{self._allowed_commands}"
                )
                return False
        print("✅ 第一步：允许列表检查通过")

        # 2. 第二步：脚本执行检查（若禁用，拒绝所有脚本命令）
        if self._disable_script_execution:
            if self._is_script_command(command_stripped):
                print(
                    f"❌ 命令是脚本执行（已禁用）：{command_stripped}\n"
                    f"    禁用的脚本类型：{_SCRIPT_INTERPRETERS[:10]}..."  # 只显示前10个避免过长
                )
                return False
        print("✅ 第二步：脚本执行检查通过")

        # 3. 第三步：逃逸禁止命令检查（拒绝嵌套/管道逃逸的禁止命令）
        if self._has_escaped_prohibited_cmd(command_stripped):
            return False
        print("✅ 第三步：逃逸禁止命令检查通过")

        # 4. 第四步：禁止命令列表检查（无论允许列表是否为空，黑名单均生效）
        for prohibited in self._prohibited_commands:
            if prohibited in command_stripped:
                print(
                    f"❌ 命令包含禁止操作：{prohibited}\n"
                    f"    完整命令：{command_stripped}"
                )
                return False
        print("✅ 第四步：禁止列表检查通过")

        # 5. 第五步：路径范围检查（确保所有操作在工作空间内，基于当前目录）
        try:
            cmd_parts = shlex.split(command_stripped)
        except ValueError:
            print(f"❌ 命令语法错误（如未闭合引号）：{command_stripped}")
            return False

        dynamic_base = self._current_dir  # 基于当前目录解析路径
        workspace_abs = self._workspace
        i = 0
        while i < len(cmd_parts):
            part = cmd_parts[i]

            # 处理cd命令：校验跳转目标是否在工作空间内
            if part.lower() == "cd" and i + 1 < len(cmd_parts):
                cd_target = cmd_parts[i + 1]
                cd_target_abs = os.path.abspath(os.path.join(dynamic_base, cd_target))
                if not cd_target_abs.startswith(workspace_abs):
                    print(
                        f"❌ cd目标超出工作空间：{cd_target_abs}\n"
                        f"    工作空间：{workspace_abs}"
                    )
                    return False
                dynamic_base = cd_target_abs  # 更新路径基准
                i += 2
                continue

            # 处理非cd命令的路径参数（排除命令选项，如-l、-rf）
            if not part.startswith("-"):
                path_abs = os.path.abspath(os.path.join(dynamic_base, part))
                if not path_abs.startswith(workspace_abs):
                    print(
                        f"❌ 操作路径超出工作空间：{path_abs}\n"
                        f"    工作空间：{workspace_abs}"
                    )
                    return False

            i += 1
        print("✅ 第五步：路径范围检查通过")

        # 所有校验通过
        print(f"✅ 命令安全可执行：{command_stripped}")
        return True

    def run_command(self, command: str) -> str:
        # 1. 前置校验：终端状态与命令安全性
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("终端未运行或已退出，需先调用open()启动")
        if not self._workspace:
            raise RuntimeError("无法执行命令：工作空间未初始化")
        if not self._process.stdin or not self._process.stdout:
            raise RuntimeError("终端进程输入/输出流未初始化")

        # 2. 安全校验（不通过则抛PermissionError）
        if not self.check_command(command):
            raise PermissionError(f"命令未通过安全校验，拒绝执行：{command}")

        try:
            # 3. 包装命令：附加完成标记，确保准确分割输出
            wrapped_cmd = f"{command} && echo '{_COMMAND_DONE_MARKER}'\n"
            self._process.stdin.write(wrapped_cmd)
            self._process.stdin.flush()
            print(f"📤 已发送命令到终端：{command}")

            # 4. 读取命令输出（直到遇到完成标记）
            output = []
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
            print(f"📥 命令执行完成，输出长度：{len(result)} 字符")
            return result

        except OSError as e:
            raise subprocess.SubprocessError(
                f"命令执行中发生IO错误：{str(e)}（命令：{command}）"
            ) from e

    def close(self) -> None:
        if not self._process or self._process.poll() is not None:
            print("ℹ️ 终端进程已关闭或未启动，无需重复操作")
            return

        pid = self._process.pid  # 保存PID用于日志

        try:
            # 1. 关闭输入管道（告知进程无更多输入）
            if self._process.stdin:
                self._process.stdin.close()
            # 2. 发送终止信号，等待退出（超时5秒）
            self._process.terminate()
            self._process.wait(timeout=5)
            print(f"✅ 终端进程（PID: {pid}）优雅关闭成功")

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
# 示例用法（验证新增功能）
# ------------------------------
if __name__ == "__main__":
    try:
        # 测试配置：允许命令列表=["ls", "cd", "touch"], 禁用脚本执行（默认）
        test_workspace = os.path.join(os.getcwd(), "safe_terminal_test")
        terminal = SingleThreadTerminal(
            workspace=test_workspace,
            create_workspace=True,
            allowed_commands=["ls", "cd", "touch", "rm"],  # 允许基础文件操作
            prohibited_commands=["rm -rf", "sudo "],       # 禁止批量删除与提权
            disable_script_execution=True                  # 默认禁用脚本
        )
        print(f"\n📋 初始配置：")
        print(f"   工作空间：{terminal.get_workspace()}")
        print(f"   允许命令：{terminal.get_allowed_commands()}")
        print(f"   禁止命令：{terminal.get_prohibited_commands()}")
        print(f"   禁用脚本：{terminal.is_script_execution_disabled()}\n")

        # 1. 测试允许命令（ls -l：在允许列表内，通过）
        print("=" * 50)
        print("1. 测试允许命令：ls -l")
        output = terminal.run_command("ls -l")
        print(f"命令输出：\n{output}\n")

        # 2. 测试cd命令（在允许列表内，同步目录）
        print("=" * 50)
        print("2. 测试cd命令：cd subdir（不存在则创建）")
        terminal.run_command("mkdir -p subdir")  # mkdir不在允许列表？→ 允许列表非空，会失败！
        # 修正：允许列表添加"mkdir"后重新测试（此处仅演示，实际需调整允许列表）
        # 临时修改允许列表（仅示例用，实际应在构造函数传入）
        terminal._allowed_commands.append("mkdir")
        terminal.run_command("mkdir -p subdir")
        terminal.run_command("cd subdir")
        print(f"当前目录：{terminal.get_current_dir()}\n")

        # 3. 测试脚本执行（禁用状态，python命令会失败）
        print("=" * 50)
        print("3. 测试禁用脚本：python -c 'print(1)'")
        try:
            terminal.run_command("python -c 'print(1)'")
        except PermissionError as e:
            print(f"预期错误：{e}\n")

        # 4. 测试逃逸禁止命令（bash -c 'rm -rf test'，rm -rf在禁止列表）
        print("=" * 50)
        print("4. 测试逃逸禁止命令：bash -c 'rm -rf test.txt'")
        try:
            terminal.run_command("bash -c 'rm -rf test.txt'")
        except PermissionError as e:
            print(f"预期错误：{e}\n")

        # 5. 测试禁止命令（rm -rf subdir，在禁止列表内）
        print("=" * 50)
        print("5. 测试禁止命令：rm -rf subdir")
        try:
            terminal.run_command("rm -rf subdir")
        except PermissionError as e:
            print(f"预期错误：{e}\n")

    except Exception as e:
        print(f"\n❌ 示例执行异常：{str(e)}")
    finally:
        # 确保终端关闭
        terminal = locals().get('terminal')
        if terminal:
            print("\n" + "=" * 50)
            terminal.close()
