from .interface import IContext
from ...model import Message, Role


class BaseContext(IContext):
    """扩展后的上下文接口，支持状态机上下文管理"""
    _context: list[Message]

    def __init__(self) -> None:
        self._context = []

    def get_context_data(self) -> list[Message]:
        """获取当前上下文字典

        Returns:
            当前上下文字典
        """
        return self._context

    def append_context_data(self, data: Message) -> None:
        """新增上下文数据

        Args:
            data: 需要新增的上下文数据
        """
        if data.role == Role.SYSTEM:
            # 系统消息不允许接在 用户/ASSISTANT/工具 消息后面
            if self._context and self._context[-1].role != Role.SYSTEM:
                raise ValueError("系统消息不能接在用户/助手/工具消息后面")
            self._context.append(data)

        elif data.role == Role.USER:
            # 用户消息可以接在任意消息后面
            self._context.append(data)

        elif data.role == Role.ASSISTANT:
            # 助手消息只能接在 用户消息 后面
            if self._context:
                last_role = self._context[-1].role
                if last_role != Role.USER:
                    raise ValueError("助手消息只能接在用户消息后面")
            self._context.append(data)

        elif data.role == Role.TOOL:
            # 工具消息只能接在 助手消息 后面
            if self._context:
                last_role = self._context[-1].role
                if last_role != Role.ASSISTANT and last_role != Role.TOOL:
                    raise ValueError("工具消息只能接在助手消息/工具消息后面")
            self._context.append(data)

        else:
            raise ValueError(f"未知的消息角色: {data.role}")

    def clear_context_data(self) -> None:
        self._context = []
