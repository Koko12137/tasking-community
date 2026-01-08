import datetime as dt
from typing import Any
from collections.abc import Callable, Awaitable

from ...core.state_machine import StateT, EventT
from ...core.state_machine.task import ITask
from ...model import IAsyncQueue, Message, Role, TextBlock
from ...model.memory import StateMemory
from ...database.interface import ISqlDatabase
from ...utils.io import read_markdown


class StateMemoryHooks:
    """状态记忆钩子实现类"""
    _db: ISqlDatabase[StateMemory]
    _state_extractor: Callable[[list[Message]], Awaitable[Message]]
    
    def __init__(
        self, 
        db: ISqlDatabase[StateMemory],
        state_extractor: Callable[[list[Message]], Awaitable[Message]],
    ) -> None:
        """初始化状态记忆钩子实例
        
        Args:
            db: 键值数据库实例
            state_extractor: 状态提取函数
        """
        self._db = db
        self._state_extractor = state_extractor

    async def pre_run_once_hook(
        self,
        context: dict[str, Any],
        queue: IAsyncQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        """在任务运行前的状态记忆钩子实现

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            queue: 消息队列
            task: 当前任务实例
        """
        if len(task.get_context().get_context_data()) == 0:
            role = Role.SYSTEM
        elif task.get_context().get_context_data()[-1].role == Role.SYSTEM:
            role = Role.SYSTEM
        else:
            role = Role.USER

        # 获取 TaskID
        task_id = task.get_id()
        
        # 从数据库中检索状态记忆，召回最新的一条状态记忆
        state_memory = await self._db.search(
            context=context,
            where=[f"task_id = '{task_id}'"],
            order_by="timestamp DESC",
            limit=1,
        )
        
        if not state_memory:
            # 无状态记忆，直接返回
            return
        state_memory = state_memory[0]
        # 将状态记忆内容添加到任务上下文中
        task.get_context().append_context_data(Message(
            role=role,
            content=state_memory.content
        ))

    async def post_run_once_hook(
        self,
        context: dict[str, Any],
        queue: IAsyncQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        """在任务运行后的状态记忆钩子实现（默认无操作）

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            queue: 消息队列
            task: 当前任务实例
        """
        task_id = task.get_id()

        # 获取任务上下文
        messages = task.get_context().get_context_data()
        # 添加任务输入到 messages 中
        messages.append(Message(
            role=Role.USER,
            content=task.get_input()
        ))
        # 拼接状态提取提示词
        prompt = read_markdown("memory/state_compress.md")
        messages.append(Message(
            role=Role.USER,
            content=[TextBlock(text=prompt)]
        ))
        # 提取状态记忆内容
        extracted = await self._state_extractor(messages)
        # 确保 extracted.content 只有一个元素且是 TextBlock 类型的内容
        if not len(extracted.content) == 1 or not isinstance(extracted.content[0], TextBlock):
            raise ValueError("Extracted content must contain exactly one TextBlock")

        # 创建状态记忆条目
        state_memory = StateMemory.from_dict(
            {
                "id": task_id,
                "task_id": task_id,
                "raw_data": [msg.model_dump() for msg in messages],
                "content": [block.model_dump() for block in extracted.content],
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        # 将状态记忆存储到数据库中
        await self._db.add(
            context=context,
            memory=state_memory,
        )
