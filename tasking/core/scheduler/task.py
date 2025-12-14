from typing import Any, Callable, Awaitable, TypeVar

from loguru import logger
from fastmcp.client.transports import ClientTransportT

from .interface import IScheduler
from .base import BaseScheduler
from ..agent import IAgent
from ..state_machine.task import ITask, ITreeTaskNode, TaskState, TaskEvent
from ..state_machine.workflow.const import WorkflowStageProtocol, WorkflowEventProtocol
from ...model import Message, IQueue, TextBlock, Role


ExecStage = TypeVar("ExecStage", bound=WorkflowStageProtocol)
ExecEvent = TypeVar("ExecEvent", bound=WorkflowEventProtocol)
OrchStage = TypeVar("OrchStage", bound=WorkflowStageProtocol)
OrchEvent = TypeVar("OrchEvent", bound=WorkflowEventProtocol)


def get_tree_on_state_fn(
    executor: IAgent[ExecStage, ExecEvent, TaskState, TaskEvent, ClientTransportT],
    orchestrator: IAgent[OrchStage, OrchEvent, TaskState, TaskEvent, ClientTransportT] | None = None,
) -> dict[TaskState, Callable[
    [
        IScheduler[TaskState, TaskEvent],
        dict[str, Any],
        IQueue[Message],
        ITask[TaskState, TaskEvent]
    ],
    Awaitable[TaskEvent]
]]:
    """获取树状任务调度器的状态调度函数映射表

    Args:
        executor: 执行者代理实例
        orchestrator: 规划者代理实例，可选，如果未提供则跳过规划阶段

    Returns:
        dict: 状态调度函数映射表
    """

    on_state_fn: dict[TaskState, Callable[
        [
            IScheduler[TaskState, TaskEvent],
            dict[str, Any],
            IQueue[Message],
            ITask[TaskState, TaskEvent]
        ],
        Awaitable[TaskEvent]
    ]] = {}

    # 1. CREATED -> RUNNING
    async def created_to_running_task(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> TaskEvent:
        """CREATED -> RUNNING 任务调度函数"""
        # 强制转换为 ITreeTaskNode 以使用树形特定方法
        assert isinstance(task, ITreeTaskNode)

        if orchestrator is not None:
            # 调用 orchestrator 进行任务规划
            await orchestrator.run_task_stream(context=context, queue=queue, task=task)

        # 返回 PLANED 事件，驱动状态机转换状态
        return TaskEvent.PLANED

    # 注册状态调度函数
    on_state_fn[TaskState.CREATED] = created_to_running_task

    # 2. RUNNING -> RUNNING / FINISHED / INITED / CANCELED
    async def running_to_finished_task(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> TaskEvent:
        """RUNNING -> RUNNING / FINISHED / INITED / CANCELED 任务调度函数。
        该任务会先调度其子任务，等待子任务完成后再执行当前任务。该任务执行后可能会进入三种状态：
        - RUNNING: 任务执行出错，状态机重试执行
        - FINISHED: 任务正常完成
        - INITED: 子任务中有被取消的任务，当前任务进入初始状态，等待重新规划执行
        """
        # 强制转换为 ITreeTaskNode 以使用树形特定方法
        assert isinstance(task, ITreeTaskNode)
        # 先执行其子任务
        sub_tasks = task.get_sub_tasks()
        for sub_task in sub_tasks:
            await scheduler.schedule(context, queue, sub_task)

        # 检查任务状态，如果任一子任务被取消，则当前任务进入初始状态，等待重新执行
        if any(sub_task.get_current_state() == TaskState.CANCELED for sub_task in sub_tasks):
            # 有子任务被取消，返回重置当前任务状态
            return TaskEvent.INIT

        # 调用 Executor 进行任务执行
        await executor.run_task_stream(context=context, queue=queue, task=task)
        if task.is_error():
            if task.get_state_visit_count(TaskState.RUNNING) >= scheduler.get_max_revisit_count():
                # 达到最大重试次数，取消任务
                return TaskEvent.CANCEL
            else:
                # 任务执行出错，返回 PLANED 事件，状态机重试执行
                return TaskEvent.PLANED

        # 返回 DONE 事件，驱动状态机转换状态
        return TaskEvent.DONE

    # 注册状态调度函数
    on_state_fn[TaskState.RUNNING] = running_to_finished_task

    return on_state_fn


def get_tree_on_state_changed_fn(
    executor: IAgent[ExecStage, ExecEvent, TaskState, TaskEvent, ClientTransportT],
    orchestrator: IAgent[OrchStage, OrchEvent, TaskState, TaskEvent, ClientTransportT] | None = None,
) -> dict[tuple[TaskState, TaskState], Callable[
    [
        IScheduler[TaskState, TaskEvent],
        dict[str, Any],
        IQueue[Message],
        ITask[TaskState, TaskEvent]
    ],
    Awaitable[None]
]]:
    """获取树状任务调度器的状态变更调度函数映射表

    Args:
        executor: 执行者代理实例
        orchestrator: 编排者代理实例，可选，如果未提供则跳过编排阶段

    Returns:
        dict: 状态变更调度函数映射表
    """
    on_state_changed_fn: dict[tuple[TaskState, TaskState], Callable[
        [
            IScheduler[TaskState, TaskEvent],
            dict[str, Any],
            IQueue[Message],
            ITask[TaskState, TaskEvent]
        ],
        Awaitable[None]
    ]] = {}
    
    # 1. TaskState.CREATED -> TaskState.RUNNING
    async def on_created_to_running(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 CREATED 变更到 RUNNING 时的调度函数"""
        logger.info(f"Task {task.get_title()} state changed from CREATED to RUNNING.")
    on_state_changed_fn[(TaskState.CREATED, TaskState.RUNNING)] = on_created_to_running
    
    # 2. TaskState.RUNNING -> TaskState.FINISHED
    async def on_running_to_finished(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 RUNNING 变更到 FINISHED 时的调度函数"""
        logger.info(f"Task {task.get_title()} state changed from RUNNING to FINISHED.")

    # 注册状态变更调度函数
    on_state_changed_fn[(TaskState.RUNNING, TaskState.FINISHED)] = on_running_to_finished
    
    # 3. TaskState.RUNNING -> TaskState.RUNNING (RETRY)
    async def on_running_to_running(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 RUNNING 变更到 RUNNING 时的调度函数"""
        logger.error(f"Task {task.get_title()} state changed from RUNNING to RUNNING. Error info: {task.get_error_info()}")
        # 获取错误信息
        error_info = task.get_error_info()
        # 新建 Message 记录错误日志
        error_message = Message(
            role=Role.SYSTEM,
            content=[
                TextBlock(text="任务在上一轮执行过程中出错，错误信息如下："),
                TextBlock(text=error_info)
            ],
        )
        # 将错误日志消息加入队列
        await queue.put(error_message)
        # 将错误信息放入任务上下文中
        task.append_context(error_message)
        # 清空错误信息
        task.clean_error_info()

    # 注册状态变更调度函数
    on_state_changed_fn[(TaskState.RUNNING, TaskState.RUNNING)] = on_running_to_running
    
    # 4. TaskState.RUNNING -> TaskState.CREATED
    async def on_running_to_created(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 RUNNING 变更到 CREATED 时的调度函数"""
        logger.info(f"Task {task.get_title()} state changed from RUNNING to CREATED for retry.")
        # 强制转换为 ITreeTaskNode 以使用树形特定方法
        assert isinstance(task, ITreeTaskNode)
        
        # 获取子任务
        sub_tasks = task.get_sub_tasks()
        # 获取被取消的子任务
        canceled_sub_tasks: list[ITreeTaskNode[TaskState, TaskEvent]] = []
        for sub_task in sub_tasks:
            if sub_task.get_current_state() == TaskState.CANCELED:
                canceled_sub_tasks.append(sub_task)
        # 将被取消的子任务信息加入到父任务的上下文中
        for canceled_sub_task in canceled_sub_tasks:
            cancel_message = Message(
                role=Role.SYSTEM,
                content=[
                    TextBlock(
                        text=f"子任务 {canceled_sub_task.get_title()} 被取消。错误信息：{canceled_sub_task.get_error_info()}"
                    )
                ],
            )
            task.append_context(cancel_message)

        # 取消所有未完成的子任务
        for sub_task in sub_tasks:
            if sub_task.get_current_state() != TaskState.FINISHED:
                await sub_task.handle_event(TaskEvent.CANCEL)

        # 重置状态机
        task.reset()
        task.clean_error_info()

    # 注册状态变更调度函数
    on_state_changed_fn[(TaskState.RUNNING, TaskState.CREATED)] = on_running_to_created
    
    # 5. TaskState.RUNNING -> TaskState.CANCELED
    async def on_running_to_canceled(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 RUNNING 变更到 CANCELED 时的调度函数"""
        logger.info(f"Task {task.get_title()} state changed from RUNNING to CANCELED.")

    # 注册状态变更调度函数
    on_state_changed_fn[(TaskState.RUNNING, TaskState.CANCELED)] = on_running_to_canceled

    return on_state_changed_fn


def build_base_scheduler(
    executor: IAgent[ExecStage, ExecEvent, TaskState, TaskEvent, ClientTransportT],
    orchestrator: IAgent[OrchStage, OrchEvent, TaskState, TaskEvent, ClientTransportT] | None = None,
    max_error_retry: int = 3,
) -> IScheduler[TaskState, TaskEvent]:
    """创建基础任务调度器实例。

    Args:
        executor: 执行者代理实例
        orchestrator: 编排者代理实例，可选，如果未提供则跳过编排阶段
        max_error_retry: 最大错误重试次数，默认值为3

    Returns:
        BaseScheduler[TaskState, TaskEvent]实例
    """
    # 构建任务调度规则映射表
    on_state_fn = get_tree_on_state_fn(
        executor=executor,
        orchestrator=orchestrator,
    )
    # 构建任务回调调度规则映射表
    on_state_changed_fn = get_tree_on_state_changed_fn(
        executor=executor,
        orchestrator=orchestrator,
    )

    # 设置结束状态
    end_states = {TaskState.FINISHED, TaskState.CANCELED}

    # 构建调度器实例
    return BaseScheduler[TaskState, TaskEvent](
        end_states=end_states,
        on_state_fn=on_state_fn,
        on_state_changed_fn=on_state_changed_fn,
        max_revisit_count=max_error_retry,
    )