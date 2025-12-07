import datetime as dt
from abc import ABC, abstractmethod
from typing import Any, Generic

from ..state_machine import StateT, EventT
from ..state_machine.task import ITask
from ...llm import ILLM
from ...model import IQueue, Message, Role, TextBlock, MultimodalContent
from ...model.llm import CompletionConfig
from ...model.memory import MemoryT, EpisodeMemory
from ...database.interface import IVectorDBManager
from ...utils.io import read_markdown


class IMemoryHooks(ABC, Generic[MemoryT]):
    """记忆中间件钩子接口定义"""

    @abstractmethod
    async def pre_run_once_hook(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        """在记忆中间件运行前执行的钩子

        参数:
            context (dict): 当前请求的上下文信息
            queue (IQueue[Message]): 消息队列
            task (ITask[StateT, EventT]): 当前任务实例
        """
        pass

    @abstractmethod
    async def post_run_once_hook(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        """在记忆中间件运行后执行的钩子

        参数:
            context (dict): 当前请求的上下文信息
            queue (IQueue[Message]): 消息队列
            task (ITask[StateT, EventT]): 当前任务实例
        """
        pass


class EpisodeMemoryHooks(IMemoryHooks[EpisodeMemory]):
    """情节记忆钩子实现类"""
    _db_manager: IVectorDBManager[EpisodeMemory]
    _memory_compress_llm: ILLM
    _compress_config: CompletionConfig
    
    def __init__(
        self,
        db_manager: IVectorDBManager[EpisodeMemory],
        memory_compress_llm: ILLM,
        compress_config: CompletionConfig,
    ) -> None:
        self._db_manager = db_manager
        self._memory_compress_llm = memory_compress_llm
        self._compress_config = compress_config
        
    async def pre_run_once_hook(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        # 从 Database 管理器中获取向量数据库
        db = self._db_manager.get_vector_database(context)
        
        # 获取任务上下文
        messages = task.get_context().get_context_data()
        # 添加任务输入到 messages 中
        messages.append(Message(
            role=Role.USER,
            content=task.get_input()
        ))
        # 拼接检索提示词
        prompt = read_markdown("memory/episode.md")
        messages.append(Message(
            role=Role.USER,
            content=[TextBlock(text=prompt)]
        ))
        # 根据 task id 构建过滤条件
        filter_expr = f"task_id = '{task.get_id()}'"
        # 从 Milvus 数据库中检索相关记忆
        query: list[MultimodalContent] = []
        for msg in messages:
            query.extend(msg.content)
        results = await db.search(
            query=query,
            top_k=5,
            threshold=0.8,
            filter_expr=filter_expr
        )
        # 创建记忆摘要并添加到上下文中
        for i, (memory, _) in enumerate(results):
            summary_content = f"""### 相关记忆片段 {i+1}
            - 事件时间: {memory.timestamp}
            - 记忆内容:
            {memory.content}
            """
            task.get_context().append_context_data(Message(
                role=Role.USER,
                content=[TextBlock(text=summary_content)]
            ))
        
    async def post_run_once_hook(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        # 从 Database 管理器中获取向量数据库
        db = self._db_manager.get_vector_database(context)

        # 获取任务上下文
        messages = task.get_context().get_context_data()
        # 添加任务输入和输出到 messages 中
        messages.append(Message(
            role=Role.USER,
            content=task.get_input()
        ))
        messages.append(Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text=task.get_output())]
        ))
        
        # 从 context 中获取 UserID / ProjectID / TraceID
        user_id = context.get("user_id")
        assert user_id, "User ID is required in context"
        project_id = context.get("project_id")
        assert project_id, "Project ID is required in context"
        trace_id = context.get("trace_id")
        assert trace_id, "Trace ID is required in context"
        
        # 添加记忆压缩提示词到 messages 中
        compress_prompt = read_markdown("memory/episode_compress.md")
        messages.append(Message(
            role=Role.USER,
            content=[TextBlock(text=compress_prompt)]
        ))
        # 压缩记忆内容
        compressed = await self._memory_compress_llm.completion(
            messages=messages,
            completion_config=self._compress_config,
        )
        # 确保 compressed.content 只有一个元素且是 TextBlock 类型的内容
        if not len(compressed.content) == 1 or not isinstance(compressed.content[0], TextBlock):
            raise ValueError("Compressed content must contain exactly one TextBlock")
        
        # 检索当前 Task ID 下的记忆条目数量
        filter_expr = f"task_id = '{task.get_id()}'"
        existing_memories = await db.query(
            filter_expr=filter_expr
        )
        
        # 创建新的情节记忆条目
        new_memory = EpisodeMemory(
            user_id=user_id,
            project_id=project_id,
            trace_id=trace_id,
            task_id=task.get_id(),
            episode_id=str(len(existing_memories) + 1),
            raw_data=messages,
            content=compressed.content,
            timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        # 将新的记忆条目存储到 Milvus 数据库中
        await db.add(new_memory)
