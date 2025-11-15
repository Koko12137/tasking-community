from typing import Any, Callable, Awaitable

from src.core.scheduler.interface import IScheduler
from src.core.scheduler.base import BaseScheduler
from src.core.state_machine.task import ITask, ITreeTaskNode, TaskState, TaskEvent
from src.core.state_machine.workflow import ReActStage, ReActEvent
from src.core.agent import IAgent
from src.model import Message, IQueue


def create_tree_scheduler(
    supervisor: IAgent[ReActStage, ReActEvent, TaskState, TaskEvent],
    planner: IAgent[ReActStage, ReActEvent, TaskState, TaskEvent],
    executor: IAgent[ReActStage, ReActEvent, TaskState, TaskEvent],
    max_error_retry: int = 3,
) -> IScheduler[TaskState, TaskEvent]:
    """创建基础树状任务调度器实例，会遵循标准的任务生命周期，包括意图澄清、任务规划和任务执行阶段。

    Args:
        supervisor: 监督者代理实例
        planner: 规划者代理实例
        executor: 执行者代理实例
        max_error_retry: 最大错误重试次数，默认值为3

    Returns:
        BaseScheduler[TaskState, TaskEvent]实例
    """
    # 构建任务调度规则映射表
    on_state_fn: dict[TaskState, Callable[
        [
            IScheduler[TaskState, TaskEvent],
            dict[str, Any],
            IQueue[Message],
            ITask[TaskState, TaskEvent]
        ],
        Awaitable[TaskEvent]
    ]] = {}
    # 构建任务回调调度规则映射表
    on_state_changed_fn: dict[tuple[TaskState, TaskState], Callable[
        [
            IScheduler[TaskState, TaskEvent],
            dict[str, Any],
            IQueue[Message],
            ITask[TaskState, TaskEvent]
        ],
        Awaitable[TaskEvent]
    ]] = {}

    # ********** 调度器规则 **********

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
        # 调用 Supervisor 进行任务意图澄清
        await supervisor.run_task_stream(context=context, queue=queue, task=fsm)
        # 重置状态机
        fsm.reset()
        fsm.clean_error_info()
        # 取消所有未完成的子任务
        sub_tasks = fsm.get_sub_tasks()
        for sub_task in sub_tasks:
            if sub_task.get_current_state() != TaskState.FINISHED:
                sub_task.handle_event(TaskEvent.CANCEL)
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
        # 调用 Planner 进行任务规划
        await planner.run_task_stream(context=context, queue=queue, task=fsm)
        # 返回 PLANED 事件，驱动状态机转换状态
        return TaskEvent.PLANED

    on_state_fn[TaskState.CREATED] = created_to_running_task

    # 3. RUNNING -> FINISHED / FAILED / INITED
    async def running_to_finished_task(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> TaskEvent:
        """RUNNING -> FINISHED / FAILED / INITED 任务调度函数。
        该任务会先调度其子任务，等待子任务完成后再执行当前任务。该任务执行后可能会进入三种状态：
        - FINISHED: 任务正常完成
        - FAILED: 子任务正常完成，但该任务执行过程中出错
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

    # 4. FAILED -> RUNNING / CANCELED
    async def failed_to_running_task(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> TaskEvent:
        """FAILED -> RUNNING / CANCELED 任务调度函数。
        根据当前任务的失败重试次数决定是重试执行任务还是取消任务。
        """
        failed_count = fsm.get_state_visit_count(TaskState.FAILED)
        if failed_count >= scheduler.get_max_revisit_count():
            # 达到最大重试次数，返回 CANCEL
            return TaskEvent.CANCEL

        # 返回 RETRY 事件，驱动状态机转换状态
        return TaskEvent.RETRY

    on_state_changed_fn[(TaskState.RUNNING, TaskState.FAILED)] = failed_to_running_task

    # 添加从各状态到CANCELED的转换规则，确保所有结束状态都参与转换
    async def to_canceled_task(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> TaskEvent:
        """各状态 -> CANCELED 任务调度函数"""
        return TaskEvent.CANCEL

    # 添加到CANCELED的转换规则
    on_state_changed_fn[(TaskState.FAILED, TaskState.CANCELED)] = to_canceled_task

    # 添加到FINISHED的转换规则
    async def to_finished_task(
        scheduler: IScheduler[TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[TaskState, TaskEvent],
    ) -> TaskEvent:
        """各状态 -> FINISHED 任务调度函数"""
        return TaskEvent.DONE

    on_state_changed_fn[(TaskState.RUNNING, TaskState.FINISHED)] = to_finished_task

    # 设置结束状态
    end_states = {TaskState.FINISHED, TaskState.FAILED, TaskState.CANCELED}

    # 构建调度器实例
    return BaseScheduler[TaskState, TaskEvent](
        end_states=end_states,
        on_state_fn=on_state_fn,
        on_state_changed_fn=on_state_changed_fn,
        max_revisit_count=max_error_retry,
    )
