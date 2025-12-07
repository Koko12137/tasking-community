from typing import Any, Callable, Awaitable, TypeVar

from loguru import logger
from fastmcp.client.transports import ClientTransportT

from .interface import IScheduler
from .base import BaseScheduler
from ..state_machine.task import ITask, ITreeTaskNode, TaskState, TaskEvent
from ..state_machine.workflow.const import WorkflowStageProtocol, WorkflowEventProtocol
from ..agent import IAgent
from ...model import Message, IQueue


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
        supervisor: 监督者代理实例，可选，如果未提供则跳过监督阶段

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

    # 1. INIT -> CREATED
    async def init_to_created_task(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> TaskEvent:
        """INIT -> CREATED 任务调度函数"""
        # 强制转换为 ITreeTaskNode 以使用树形特定方法
        assert isinstance(fsm, ITreeTaskNode)

        # 重置状态机
        fsm.reset()
        fsm.clean_error_info()
        # 取消所有未完成的子任务
        sub_tasks = fsm.get_sub_tasks()
        for sub_task in sub_tasks:
            if sub_task.get_current_state() != TaskState.FINISHED:
                await sub_task.handle_event(TaskEvent.CANCEL)

        # 返回 IDENTIFIED 事件，驱动状态机转换状态
        return TaskEvent.IDENTIFIED

    on_state_fn[TaskState.INITED] = init_to_created_task

    # 2. CREATED -> RUNNING
    async def created_to_running_task(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> TaskEvent:
        """CREATED -> RUNNING 任务调度函数"""
        # 强制转换为 ITreeTaskNode 以使用树形特定方法
        assert isinstance(fsm, ITreeTaskNode)

        if orchestrator is not None:
            # 调用 orchestrator 进行任务规划
            await orchestrator.run_task_stream(context=context, queue=queue, task=fsm)

        # 返回 PLANED 事件，驱动状态机转换状态
        return TaskEvent.PLANED

    on_state_fn[TaskState.CREATED] = created_to_running_task

    # 3. RUNNING -> FINISHED / ERROR / INITED
    async def running_to_finished_task(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> TaskEvent:
        """RUNNING -> FINISHED / ERROR / INITED 任务调度函数。
        该任务会先调度其子任务，等待子任务完成后再执行当前任务。该任务执行后可能会进入三种状态：
        - FINISHED: 任务正常完成
        - ERROR: 子任务正常完成，但该任务执行过程中出错
        - INITED: 子任务中有被取消的任务，当前任务进入初始状态，等待重新规划执行
        """
        # 强制转换为 ITreeTaskNode 以使用树形特定方法
        assert isinstance(fsm, ITreeTaskNode)
        # 先执行其子任务
        sub_tasks = fsm.get_sub_tasks()
        for sub_task in sub_tasks:
            await scheduler.schedule(context, queue, sub_task)

        # 检查任务状态，如果任一子任务被取消，则当前任务进入初始状态，等待重新执行
        if any(sub_task.get_current_state() == TaskState.CANCELED for sub_task in sub_tasks):
            # 有子任务被取消，返回重置当前任务状态
            return TaskEvent.INIT

        # 调用 Executor 进行任务执行
        await executor.run_task_stream(context=context, queue=queue, task=fsm)
        if fsm.is_error():
            # 任务执行出错，返回 ERROR 事件，驱动状态机转换状态
            return TaskEvent.ERROR

        # 返回 DONE 事件，驱动状态机转换状态
        return TaskEvent.DONE

    on_state_fn[TaskState.RUNNING] = running_to_finished_task

    # 4. ERROR -> RETRY / CANCELED
    async def error_to_retry_task(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> TaskEvent:
        """ERROR -> RETRY / CANCELED 任务调度函数"""
        # 强制转换为 ITreeTaskNode 以使用树形特定方法
        assert isinstance(fsm, ITreeTaskNode)

        if (
            fsm.get_state_visit_count(TaskState.ERROR) >= scheduler.get_max_revisit_count()
            and scheduler.get_max_revisit_count() > 0
        ):
            # 达到最大重试次数，返回 CANCEL 事件，驱动状态机转换状态
            return TaskEvent.CANCEL

        # 返回 RETRY 事件，驱动状态机转换状态
        return TaskEvent.RETRY

    on_state_fn[TaskState.ERROR] = error_to_retry_task

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
        supervisor: 监督者代理实例，可选，如果未提供则跳过监督阶段

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
    
    # 1. TaskState.INITED -> TaskState.CREATED
    async def on_inited_to_created(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 INITED 变更到 CREATED 时的调度函数"""
        logger.info(f"Task {fsm.get_id()} state changed from INITED to CREATED.")
    on_state_changed_fn[(TaskState.INITED, TaskState.CREATED)] = on_inited_to_created
    
    # 2. TaskState.CREATED -> TaskState.RUNNING
    async def on_created_to_running(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 CREATED 变更到 RUNNING 时的调度函数"""
        logger.info(f"Task {fsm.get_id()} state changed from CREATED to RUNNING.")
    on_state_changed_fn[(TaskState.CREATED, TaskState.RUNNING)] = on_created_to_running
    
    # 3. TaskState.RUNNING -> TaskState.FINISHED
    async def on_running_to_finished(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 RUNNING 变更到 FINISHED 时的调度函数"""
        logger.info(f"Task {fsm.get_id()} state changed from RUNNING to FINISHED.")
    on_state_changed_fn[(TaskState.RUNNING, TaskState.FINISHED)] = on_running_to_finished
    
    # 4. TaskState.RUNNING -> TaskState.ERROR
    async def on_running_to_error(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 RUNNING 变更到 ERROR 时的调度函数"""
        logger.error(f"Task {fsm.get_id()} state changed from RUNNING to ERROR. Error info: {fsm.get_error_info()}")
    on_state_changed_fn[(TaskState.RUNNING, TaskState.ERROR)] = on_running_to_error
    
    # 5. TaskState.ERROR -> TaskState.INITED
    async def on_error_to_inited(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 ERROR 变更到 INITED 时的调度函数"""
        logger.info(f"Task {fsm.get_id()} state changed from ERROR to INITED for retry.")
    on_state_changed_fn[(TaskState.ERROR, TaskState.INITED)] = on_error_to_inited
    
    # 6. TaskState.ERROR -> TaskState.RUNNING
    async def on_error_to_running(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 ERROR 变更到 RUNNING 时的调度函数"""
        logger.info(f"Task {fsm.get_id()} state changed from ERROR to RUNNING for retry.")
    on_state_changed_fn[(TaskState.ERROR, TaskState.RUNNING)] = on_error_to_running
    
    # 7. TaskState.ERROR -> TaskState.CANCELED
    async def on_error_to_canceled(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> None:
        """任务状态从 ERROR 变更到 CANCELED 时的调度函数"""
        logger.error(f"Task {fsm.get_id()} state changed from ERROR to CANCELED after reaching max retry limit.")
    on_state_changed_fn[(TaskState.ERROR, TaskState.CANCELED)] = on_error_to_canceled
    
    return on_state_changed_fn


def build_base_scheduler(
    executor: IAgent[ExecStage, ExecEvent, TaskState, TaskEvent, ClientTransportT],
    orchestrator: IAgent[OrchStage, OrchEvent, TaskState, TaskEvent, ClientTransportT] | None = None,
    max_error_retry: int = 3,
) -> IScheduler[TaskState, TaskEvent]:
    """创建基础任务调度器实例，简单任务的调度器，意图澄清/拆解规划阶段会被跳过，直接进入执行阶段。

    Args:
        executor: 执行者代理实例
        orchestrator: 编排者代理实例，可选，如果未提供则跳过编排阶段
        supervisor: 监督者代理实例，可选，如果未提供则跳过监督阶段
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