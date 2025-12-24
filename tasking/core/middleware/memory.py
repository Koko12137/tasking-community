import datetime as dt
from abc import ABC, abstractmethod
from typing import Any, Generic, cast
from collections.abc import Callable, Awaitable

from fastmcp.client.transports import ClientTransportT

from ..agent import IAgent
from ..state_machine import StateT, EventT
from ..state_machine.task import ITask
from ..state_machine.workflow import WorkflowStageT, WorkflowEventT
from ...model import IAsyncQueue, Message, Role, TextBlock, ImageBlock, VideoBlock, MultimodalContent
from ...model.memory import MemoryT, EpisodeMemory, StateMemory
from ...database.interface import IVectorDatabase, IKVDatabase
from ...utils.io import read_markdown


class IMemoryHooks(ABC, Generic[MemoryT]):
    """记忆中间件钩子接口定义"""

    @abstractmethod
    async def pre_run_once_hook(
        self,
        context: dict[str, Any],
        queue: IAsyncQueue[Message],
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
        queue: IAsyncQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        """在记忆中间件运行后执行的钩子

        参数:
            context (dict): 当前请求的上下文信息
            queue (IQueue[Message]): 消息队列
            task (ITask[StateT, EventT]): 当前任务实例
        """
        pass


class StateMemoryHooks(IMemoryHooks[StateMemory]):
    """状态记忆钩子实现类"""
    _db: IKVDatabase[StateMemory]
    _state_extractor: Callable[[list[Message]], Awaitable[Message]]
    
    def __init__(
        self, 
        db: IKVDatabase[StateMemory],
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
        """在任务运行前的状态记忆钩子实现（默认无操作）
        
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

        # 获取 context 中的 UserID / ProjectID / TraceID / TaskID
        user_id = context.get("user_id")
        assert user_id, "User ID is required in context"
        project_id = context.get("project_id")
        assert project_id, "Project ID is required in context"
        trace_id = context.get("trace_id")
        assert trace_id, "Trace ID is required in context"
        task_id = task.get_id()
        
        # 拼接状态记忆检索唯一ID
        state_memory_key = f"{user_id}:{project_id}:{trace_id}:{task_id}"
        # 从数据库中检索状态记忆
        state_memory = await self._db.search(
            context=context,
            key=state_memory_key
        )
        
        if not state_memory:
            # 无状态记忆，直接返回
            return
        # 将状态记忆内容添加到任务上下文中
        task.get_context().append_context_data(Message(
            role=role,
            content=cast(list[TextBlock | ImageBlock | VideoBlock], state_memory.content)
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
        # 从 context 中获取 UserID / ProjectID / TraceID / TaskID
        user_id = context.get("user_id")
        assert user_id, "User ID is required in context"
        project_id = context.get("project_id")
        assert project_id, "Project ID is required in context"
        trace_id = context.get("trace_id")
        assert trace_id, "Trace ID is required in context"
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

        # 拼接状态记忆存储唯一ID
        state_memory_key = f"{user_id}:{project_id}:{trace_id}:{task_id}"
        # 创建状态记忆条目
        state_memory = StateMemory.from_dict(
            {
                "id": state_memory_key,
                "user_id": user_id,
                "project_id": project_id,
                "trace_id": trace_id,
                "task_id": task_id,
                "raw_data": [msg.model_dump() for msg in messages],
                "content": [block.model_dump() for block in extracted.content],
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        # 将状态记忆存储到数据库中
        await self._db.add(
            context=context,
            key=state_memory_key,
            value=state_memory,
        )


class EpisodeMemoryHooks(IMemoryHooks[EpisodeMemory]):
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
        results = await self._db.search(
            context=context,
            query=query,
            top_k=5,
            threshold=[0.8],
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
            user_id=user_id,
            project_id=project_id,
            trace_id=trace_id,
            task_id=task.get_id(),
            episode_id=str(len(existing_memories) + 1),
            raw_data=messages,
            content=cast(list[TextBlock], compressed.content),
            timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        # 将新的记忆条目存储到 Milvus 数据库中
        await self._db.add(
            context=context,
            memory=new_memory
        )


def register_memory_fold_hooks(
    agent: IAgent[WorkflowStageT, WorkflowEventT, StateT, EventT, ClientTransportT],
    state_kv_db: IKVDatabase[StateMemory],
    state_extractor: Callable[[list[Message]], Awaitable[Message]],
    episode_vector_db: IVectorDatabase[EpisodeMemory],
    memory_compressor: Callable[[list[Message]], Awaitable[Message]],
) -> None:
    """构建 Agent 状态记忆钩子实例。该函数会创建状态记忆钩子和情节记忆钩子，并注册到智能体中。
    策略如下：
    -  在智能体运行前的 pre_run_once_hook 中提取并状态记忆和情节记忆，加入到任务上下文中
    -  在智能体运行后的 post_run_once_hook 中将最新的状态记忆和情节记忆存储到数据库中
    -  在状态记忆后清理任务上下文中的状态内容，避免重复累积

    Args:
        agent: 智能体实例
        state_kv_db: 状态记忆键值数据库实例
        state_extractor: 用于提取状态记忆的函数
        episode_vector_db: 情节记忆向量数据库实例
        memory_compressor: 用于压缩情节记忆的函数
        
    Returns:
        None 
            Hooks 已注册到智能体
    """
    
    # 清空任务上下文的钩子
    async def clear_state_memory_hook(
        context: dict[str, Any],
        queue: IAsyncQueue[Message],
        task: ITask[StateT, EventT],
    ) -> None:
        """清理任务上下文中的状态记忆内容，避免重复累积
        
        Args:
            context: 上下文信息，用于配置或选择数据库实例
            queue: 消息队列
            task: 当前任务实例
        """
        # 调用任务上下文的清理方法
        task.get_context().clear_context_data()
    
    # 状态记忆钩子
    state_hooks = StateMemoryHooks(
        db=state_kv_db,
        state_extractor=state_extractor,
    )
    # 注册到智能体
    agent.add_pre_run_once_hook(state_hooks.pre_run_once_hook)
    agent.add_post_run_once_hook(state_hooks.post_run_once_hook)
    # 事件记忆钩子
    episode_hooks = EpisodeMemoryHooks(
        db=episode_vector_db,
        memory_compressor=memory_compressor,
    )
    # 注册到智能体
    agent.add_pre_observe_hook(episode_hooks.pre_run_once_hook)
    agent.add_post_run_once_hook(episode_hooks.post_run_once_hook)
    # 清理状态记忆钩子注册到智能体，避免重复累积，放在所有钩子最后执行
    agent.add_post_run_once_hook(clear_state_memory_hook)
