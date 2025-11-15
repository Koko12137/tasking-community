from typing import Any, Callable, Awaitable

from src.core.scheduler.interface import IScheduler
from src.core.scheduler.base import BaseScheduler
from src.core.state_machine.task import ITask, TaskState, TaskEvent
from src.core.state_machine.workflow import SimpleStage, SimpleEvent
from src.core.agent import IAgent
from src.model import Message, IQueue


def create_simple_scheduler(
    executor: IAgent[SimpleStage, SimpleEvent, TaskState, TaskEvent],
    max_error_retry: int = 3,
) -> IScheduler[TaskState, TaskEvent]:
    """创建基础任务调度器实例，简单任务的调度器，意图澄清/拆解规划阶段会被跳过，直接进入执行阶段。

    Args:
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
        # 确保为 ITask 实例
        assert isinstance(fsm, ITask)
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
        # 确保为 ITask 实例
        assert isinstance(fsm, ITask)
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
        """RUNNING -> FINISHED / FAILED 任务调度函数。该任务执行后可能会进入两种状态：
        - FINISHED: 任务正常完成
        - FAILED: 该任务执行过程中出错
        """
        # 确保为 ITask 实例
        assert isinstance(fsm, ITask)
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
        # 确保为 ITask 实例
        assert isinstance(fsm, ITask)

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