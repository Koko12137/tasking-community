from collections.abc import Callable, Awaitable

from loguru import logger

from .const import TaskState, TaskEvent
from .interface import ITreeTaskNode
from .base import BaseTask
from .tree import BaseTreeTaskNode
from ....utils.io import read_document
from ....model.message import MultimodalContent, TextBlock


def get_base_states() -> set[TaskState]:
    """获取常用状态集合
    -  CREATED, RUNNING, FINISHED, CANCELED

    Returns:
        常用状态集合
    """
    return {
        TaskState.CREATED,
        TaskState.RUNNING,
        TaskState.FINISHED,
        TaskState.CANCELED,
    }


def get_base_transition() -> dict[
    tuple[TaskState, TaskEvent],
    tuple[TaskState, Callable[[ITreeTaskNode[TaskState, TaskEvent]], Awaitable[None] | None] | None]
]:
    """获取常用状态和转换规则
    - 状态： CREATED, RUNNING, FINISHED, CANCELED
    - 事件： INIT, PLANED, DONE, CANCEL
    - 转换规则：
        1. CREATED → CREATED（事件：INIT）
        2. CREATED → RUNNING（事件：PLANED）
        3. RUNNING → FINISHED（事件：DONE）
        4. RUNNING → RUNNING（事件：PLANED，错误重试）
        5. RUNNING → CREATED（事件：INIT，子任务取消重置）
        6. RUNNING → CANCELED（事件：CANCEL）

    Args:
        protocol: 任务协议定义
        tags: 任务标签集合
        data_type: 任务数据类型（默认：object）

    Returns:
        转换规则字典
    """
    transitions: dict[
        tuple[TaskState, TaskEvent],
        tuple[TaskState, Callable[[ITreeTaskNode[TaskState, TaskEvent]], Awaitable[None] | None] | None]
    ] = {}

    # 1. CREATED → CREATED（事件：INIT）
    def on_created_init(task: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(task, BaseTask)
        logger.info(f"[{task.get_title()}] 任务初始化完成，进入创建状态")
    transitions[(TaskState.CREATED, TaskEvent.INIT)] = (TaskState.CREATED, on_created_init)

    # 2. CREATED → RUNNING（事件：PLANED）
    def on_created_planed(task: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(task, BaseTask)
        logger.info(f"[{task.get_title()}] 任务规划完成，进入执行阶段")
    transitions[(TaskState.CREATED, TaskEvent.PLANED)] = (TaskState.RUNNING, on_created_planed)

    # 3. RUNNING → FINISHED（事件：DONE）
    def on_running_done(task: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(task, BaseTask)
        logger.info(f"[{task.get_title()}] 任务执行完成")
    transitions[(TaskState.RUNNING, TaskEvent.DONE)] = (TaskState.FINISHED, on_running_done)

    # 4. RUNNING → RUNNING（事件：PLANED，错误重试）
    def on_running_planed(task: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(task, BaseTask)
        logger.info(f"[{task.get_title()}] 任务执行出错，准备重试")
    transitions[(TaskState.RUNNING, TaskEvent.PLANED)] = (TaskState.RUNNING, on_running_planed)

    # 5. RUNNING → CREATED（事件：INIT，子任务取消重置）
    def on_running_init(task: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(task, BaseTask)
        logger.info(f"[{task.get_title()}] 子任务被取消，重置任务状态")
    transitions[(TaskState.RUNNING, TaskEvent.INIT)] = (TaskState.CREATED, on_running_init)

    # 6. RUNNING → CANCELED（事件：CANCEL）
    def on_running_cancel(task: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(task, BaseTask)
        logger.info(f"[{task.get_title()}] 任务被取消")
    transitions[(TaskState.RUNNING, TaskEvent.CANCEL)] = (TaskState.CANCELED, on_running_cancel)
    return transitions


class DefaultTreeNode(BaseTreeTaskNode[TaskState, TaskEvent]):
    """默认树形任务节点，通常用于初始任务节点"""
    _protocol: list[MultimodalContent] = [
        TextBlock(text=read_document("task/default.md"))
    ]
    _task_type: str = "root_task"
    _tags: set[str] = set()
    
    def __init__(self, max_depth: int = 5) -> None:
        super().__init__(
            unique_protocol=self._protocol,
            tags=self._tags,
            task_type=self._task_type,
            valid_states=get_base_states(),
            init_state=TaskState.CREATED,
            max_depth=max_depth,
            transitions=get_base_transition(),
        )
