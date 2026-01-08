import datetime as dt
from typing import Any
from collections.abc import Callable, Awaitable

from ...core.state_machine import StateT, EventT
from ...core.state_machine.task import ITask
from ...model import IAsyncQueue, Message, Role, TextBlock, MultimodalContent
from ...model.memory import EpisodeMemory
from ...database.interface import IVectorDatabase
from ...utils.io import read_markdown
from ...utils.string.message import extract_text_from_content


EPISODE = """
<episode>
<order>{i}</order>
<memory_id>{memory_id}</memory_id>
<timestamp>{timestamp}</timestamp>
<content>{content}</content>
</episode>
"""


class EpisodeMemoryHooks:
    """情节记忆钩子实现类"""
    _db: IVectorDatabase[EpisodeMemory]
    _memory_compressor: Callable[[list[Message]], Awaitable[Message]]

    def __init__(
        self,
        db: IVectorDatabase[EpisodeMemory],
        memory_compressor: Callable[[list[Message]], Awaitable[Message]],
    ) -> None:
        self._db = db
        self._memory_compressor = memory_compressor
        
    async def pre_run_once_hook(
        self,
        context: dict[str, Any],
        queue: IAsyncQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        """在任务运行前检索相关情节记忆并添加到上下文中
        
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

        # 获取任务上下文
        messages = task.get_context().get_context_data()
        # 添加任务输入到 messages 中
        messages.append(Message(
            role=Role.USER,
            content=task.get_input()
        ))
        # 拼接检索提示词
        prompt = read_markdown("memory/episode_search.md")
        messages.append(Message(
            role=role,
            content=[TextBlock(text=prompt)]
        ))
        # 从数据库中检索相关记忆
        query: list[MultimodalContent] = []
        for msg in messages:
            query.extend(msg.content)
        results = await self._db.search(
            context=context,
            query=query,
            top_k=5,
        )
        # 创建记忆摘要并添加到上下文中
        for i, (memory, _) in enumerate(results):
            summary_content = EPISODE.format(
                i=i,
                memory_id=memory.id,
                timestamp=memory.timestamp,
                content=extract_text_from_content(memory.content)
            )
            task.get_context().append_context_data(Message(
                role=role,
                content=[TextBlock(text=summary_content)]
            ))
        
    async def post_run_once_hook(
        self,
        context: dict[str, Any],
        queue: IAsyncQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        """在任务运行后压缩并存储情节记忆
        
        Args:
            context: 上下文信息，用于配置或选择数据库实例
            queue: 消息队列
            task: 当前任务实例
        """
        # 获取任务上下文
        messages = task.get_context().get_context_data()
        
        # 添加记忆压缩提示词到 messages 中
        compress_prompt = read_markdown("memory/episode_compress.md")
        messages.append(Message(
            role=Role.USER,
            content=[TextBlock(text=compress_prompt)]
        ))
        # 压缩记忆内容
        compressed = await self._memory_compressor(messages)
        # 确保 compressed.content 只有一个元素且是 TextBlock 类型的内容
        if not len(compressed.content) == 1 or not isinstance(compressed.content[0], TextBlock):
            raise ValueError("Compressed content must contain exactly one TextBlock")
        
        # 检索当前 Task ID 下的记忆条目数量
        filter_expr = f"task_id = '{task.get_id()}'"
        existing_memories = await self._db.query(
            context=context,
            filter_expr=filter_expr
        )
        
        # 创建新的情节记忆条目
        new_memory = EpisodeMemory(
            task_id=task.get_id(),
            episode_id=str(len(existing_memories) + 1),
            raw_data=messages,
            content=compressed.content,
            timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        # 将新的记忆条目存储到数据库中
        await self._db.add(
            context=context,
            memory=new_memory
        )
