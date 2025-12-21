from abc import ABC, abstractmethod

from .terminal import ITerminal
from .filesystem import IFileSystem


class IGitTool(ABC):

    @abstractmethod
    def get_terminal(self) -> ITerminal:
        """获取关联的终端实例。

        Returns:
            ITerminal: 关联的终端实例。
        """
        raise NotImplementedError

    @abstractmethod
    def get_filesystem(self) -> IFileSystem:
        """获取关联的文件系统实例。

        Returns:
            IFileSystem: 关联的文件系统实例。
        """
        raise NotImplementedError

    @abstractmethod
    async def add(self, file_path: str) -> str:
        """添加文件。

        Args:
            file_path: 文件路径。

        Returns:
            str: 添加结果消息。
        """
        raise NotImplementedError

    @abstractmethod
    async def commit(self, message: str) -> str:
        """提交代码。

        Args:
            message: 提交消息。

        Returns:
            str: 提交结果消息。
        """
        raise NotImplementedError

    @abstractmethod
    async def push(self) -> str:
        """推送代码。

        Args:
            message: 推送消息。

        Returns:
            str: 推送结果消息。
        """
        raise NotImplementedError

    @abstractmethod
    async def pull(self) -> str:
        """拉取代码。

        Returns:
            str: 拉取结果消息。
        """
        raise NotImplementedError
