from typing import Callable, Awaitable

from loguru import logger

from .const import TaskState, TaskEvent
from .interface import ITreeTaskNode
from .base import BaseTask
from .tree import BaseTreeTaskNode
from ....utils.io import read_document
from ....model.message import MultimodalContent, TextBlock


def get_base_states() -> set[TaskState]:
    """获取常用状态集合
    -  INIT, CREATED, RUNNING, FINISHED, ERROR, CANCELED

    Returns:
        常用状态集合
    """
    return {
        TaskState.INITED,
        TaskState.CREATED,
        TaskState.RUNNING,
        TaskState.FINISHED,
        TaskState.ERROR,
        TaskState.CANCELED,
    }


def get_base_transition() -> dict[
    tuple[TaskState, TaskEvent],
    tuple[TaskState, Callable[[ITreeTaskNode[TaskState, TaskEvent]], Awaitable[None] | None] | None]
]:
    """获取常用状态和转换规则
    - 状态： CREATED, RUNNING, FINISHED, ERROR, CANCELED
    - 事件： Identified, FinishPlan, Done, Error, Retry, Cancel
    - 转换规则：
        1. INIT -> CREATED（事件：IDENTIFIED）
        2. CREATED → RUNNING（事件：FinishPlan）
        3. RUNNING → FINISHED（事件：Done）
        4. RUNNING → ERROR（事件：Error）
        5. ERROR → RUNNING（事件：Retry）
        6. ERROR → CANCELED（事件：Cancel）

    Args:
        protocol: 任务协议定义
        tags: 任务标签集合
        data_type: 任务数据类型（默认：object）

    Returns:
        BaseTask实例
    """
    transitions: dict[
        tuple[TaskState, TaskEvent],
        tuple[TaskState, Callable[[ITreeTaskNode[TaskState, TaskEvent]], Awaitable[None] | None] | None]
    ] = {}

    # 1. INIT -> CREATED（事件：IDENTIFIED）
    def on_identified(sm: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(sm, BaseTask)
        logger.info(f"[{sm.get_id()}] 任务目标已确认，进入创建阶段")

    transitions[(TaskState.INITED, TaskEvent.IDENTIFIED)] = (
        TaskState.CREATED, on_identified
    )

    # 2. CREATED → RUNNING（事件：PLANED）
    def on_finish_plan(sm: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(sm, BaseTask)
        sm.clean_error_info()  # 清除错误信息
        logger.info(f"[{sm.get_id()}] 任务规划完成，进入执行阶段")

    transitions[(TaskState.CREATED, TaskEvent.PLANED)] = (
        TaskState.RUNNING, on_finish_plan
    )

    # 3. RUNNING → FINISHED（事件：Done）
    def on_done(sm: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(sm, BaseTask)
        logger.info(f"[{sm.get_id()}] 任务执行完成")

    transitions[(TaskState.RUNNING, TaskEvent.DONE)] = (
        TaskState.FINISHED, on_done
    )

    # 4. RUNNING → ERROR（事件：ERROR）
    def on_error(sm: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(sm, BaseTask)
        logger.info(f"[{sm.get_id()}] 任务执行出错")

    transitions[(TaskState.RUNNING, TaskEvent.ERROR)] = (
        TaskState.ERROR, on_error
    )

    # 5. RUNNING → INITED（事件：INIT）
    def on_init(sm: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(sm, BaseTask)
        sm.clean_error_info()  # 重置时清除错误信息
        logger.info(f"[{sm.get_id()}] 任务重置，返回初始状态")

    transitions[(TaskState.RUNNING, TaskEvent.INIT)] = (
        TaskState.INITED, on_init
    )

    # 6. ERROR → RUNNING（事件：RETRY）
    def on_retry(sm: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(sm, BaseTask)
        sm.clean_error_info()  # 重试时清除错误信息
        logger.info(f"[{sm.get_id()}] 任务重试，重新进入执行阶段")

    transitions[(TaskState.ERROR, TaskEvent.RETRY)] = (
        TaskState.RUNNING, on_retry
    )

    # 7. ERROR → CANCELED（事件：CANCEL）
    def on_cancel(sm: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(sm, BaseTask)
        logger.info(f"[{sm.get_id()}] 任务取消，终止执行")

    transitions[(TaskState.ERROR, TaskEvent.CANCEL)] = (
        TaskState.CANCELED, on_cancel
    )

    return transitions


class DefaultTreeNode(BaseTreeTaskNode[TaskState, TaskEvent]):
    """默认树形任务节点，通常用于初始任务节点"""
    _protocol: list[MultimodalContent] = [
        TextBlock(text=read_document("task/default.xml"))
    ]
    _task_type: str = "root_task"
    _tags: set[str] = set()
    
    def __init__(self, max_depth: int = 5) -> None:
        super().__init__(
            protocol=self._protocol,
            tags=self._tags,
            task_type=self._task_type,
            valid_states=get_base_states(),
            init_state=TaskState.INITED,
            max_depth=max_depth,
            transitions=get_base_transition(),
        )
