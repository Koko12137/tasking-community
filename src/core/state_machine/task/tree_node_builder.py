from typing import Callable, Awaitable

from loguru import logger

from src.core.state_machine.task.const import TaskState, TaskEvent
from src.core.state_machine.task.interface import ITreeTaskNode
from src.core.state_machine.task.base import BaseTask
from src.core.state_machine.task.tree import BaseTreeTaskNode
from src.model import CompletionConfig
from src.utils.io import read_document
    

def get_base_states() -> set[TaskState]:
    """获取常用状态集合
    -  INIT, CREATED, RUNNING, FINISHED, FAILED, CANCELED
    
    Returns:
        常用状态集合
    """
    return {
        TaskState.INITED,
        TaskState.CREATED,
        TaskState.RUNNING,
        TaskState.FINISHED,
        TaskState.FAILED,
        TaskState.CANCELED,
    }


def get_base_transition() -> dict[
    tuple[TaskState, TaskEvent], 
    tuple[TaskState, Callable[[ITreeTaskNode[TaskState, TaskEvent]], Awaitable[None] | None] | None]
]:
    """获取常用状态和转换规则
    - 状态： CREATED, RUNNING, FINISHED, FAILED, CANCELED
    - 事件： Identified, FinishPlan, Done, Error, Retry, Cancel
    - 转换规则：
        1. INIT -> CREATED（事件：IDENTIFIED）
        2. CREATED → RUNNING（事件：FinishPlan）
        3. RUNNING → FINISHED（事件：Done）
        4. RUNNING → FAILED（事件：Error）
        5. FAILED → RUNNING（事件：Retry）
        6. FAILED → CANCELED（事件：Cancel）

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

    # 4. RUNNING → FAILED（事件：Error）
    def on_error(sm: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(sm, BaseTask)
        logger.info(f"[{sm.get_id()}] 任务执行出错")

    transitions[(TaskState.RUNNING, TaskEvent.ERROR)] = (
        TaskState.FAILED, on_error
    )

    # 5. RUNNING → INITED（事件：INIT）
    def on_init(sm: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(sm, BaseTask)
        sm.clean_error_info()  # 重置时清除错误信息
        logger.info(f"[{sm.get_id()}] 任务重置，返回初始状态")
        
    transitions[(TaskState.RUNNING, TaskEvent.INIT)] = (
        TaskState.INITED, on_init
    )

    # 6. FAILED → RUNNING（事件：Retry）
    def on_retry(sm: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(sm, BaseTask)
        sm.clean_error_info()  # 重试时清除错误信息
        logger.info(f"[{sm.get_id()}] 任务重试，重新进入执行阶段")

    transitions[(TaskState.FAILED, TaskEvent.RETRY)] = (
        TaskState.RUNNING, on_retry
    )

    # 7. FAILED → CANCELED（事件：Cancel）
    def on_cancel(sm: ITreeTaskNode[TaskState, TaskEvent]):
        assert isinstance(sm, BaseTask)
        logger.info(f"[{sm.get_id()}] 任务取消，终止执行")
    
    transitions[(TaskState.FAILED, TaskEvent.CANCEL)] = (
        TaskState.CANCELED, on_cancel
    )

    return transitions


def build_base_tree_node(
    protocol: str,
    tags: set[str],
    task_type: str,
    max_depth: int,
    completion_config: CompletionConfig,
) -> BaseTreeTaskNode[TaskState, TaskEvent]:
    """构建基础树形任务节点状态机实例

    Args:
        protocol: 任务协议定义
        tags: 任务标签集合
        task_type: 任务类型
        max_depth: 任务最大深度

    Returns:
        BaseTreeTaskNode实例
    """
    valid_states = get_base_states()
    transitions = get_base_transition()
    node = BaseTreeTaskNode[TaskState, TaskEvent](
        protocol=protocol,
        tags=tags,
        task_type=task_type,
        valid_states=valid_states,
        init_state=TaskState.INITED,
        max_depth=max_depth,
        transitions=transitions,
        completion_config=completion_config,
    )
    assert isinstance(node, BaseTreeTaskNode)
    return node


def build_default_tree_node() -> BaseTreeTaskNode[TaskState, TaskEvent]:
    """构建默认的树形任务节点状态机实例

    Returns:
        BaseTreeTaskNode实例
    """
    return build_base_tree_node(
        protocol=read_document("prompt/task/default.xml"),
        tags=set[str](),
        task_type="default_tree_task",
        max_depth=5,
        completion_config=CompletionConfig(),
    )


if __name__ == "__main__":
    # 简单测试
    valid_states = get_base_states()
    transitions = get_base_transition()

    task = BaseTreeTaskNode[TaskState, TaskEvent](
        protocol="example_protocol_v1.0",
        tags={"example", "test"},
        task_type="example_task",
        valid_states=valid_states,
        init_state=TaskState.INITED,
        max_depth=3,
        transitions=transitions,
        completion_config=CompletionConfig(),
    )
    assert isinstance(task, BaseTreeTaskNode)
    state = task.get_current_state()
    assert isinstance(state, TaskState)
    logger.info(f"创建任务，ID：{task.get_id()[:8]}, 初始状态：{state.name}")

    # 树形任务节点测试（使用已定义的构建函数）
    root_node = build_base_tree_node(
        protocol="tree_protocol_v1.0",
        tags={"tree", "root"},
        task_type="tree_task",
        max_depth=3,
        completion_config=CompletionConfig(),
    )
    child_node1 = build_base_tree_node(
        protocol="tree_protocol_v1.0",
        tags={"tree", "child1"},
        task_type="tree_task",
        max_depth=3,
        completion_config=CompletionConfig(),
    )
    child_node2 = build_base_tree_node(
        protocol="tree_protocol_v1.0",
        tags={"tree", "child2"},
        task_type="tree_task",
        max_depth=3,
        completion_config=CompletionConfig(),
    )
    root_node.add_sub_task(child_node1)
    root_node.add_sub_task(child_node2)
    logger.info(f"根节点ID：{root_node.get_id()[:8]}, 子节点数量：{len(root_node.get_sub_tasks())}")
