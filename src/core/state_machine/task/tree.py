import re
import json
from typing import Any, Awaitable, Callable, override, cast

from .interface import ITask, ITreeTaskNode, ITaskView
from .base import (
    BaseTask, 
    TodoTaskView, 
    DocumentTaskView, 
    RequirementTaskView, 
    JsonTaskView
)
from ..const import StateT, EventT
from ...context import IContext, BaseContext


class BaseTreeTaskNode(ITreeTaskNode[StateT, EventT], BaseTask[StateT, EventT]):
    """树形任务节点实现，支持父子节点管理"""
    # *** 树形结构属性 ***
    _is_root: bool
    _current_depth: int
    _max_depth: int

    # *** 父子节点管理 ***
    _parent: ITreeTaskNode[StateT, EventT] | None
    _sub_tasks: list[ITreeTaskNode[StateT, EventT]]
    
    def __init__(
        self,
        valid_states: set[StateT],
        init_state: StateT,
        transitions: dict[
            tuple[StateT, EventT],
            tuple[StateT, Callable[[ITreeTaskNode[StateT, EventT]], Awaitable[None] | None] | None],
        ],
        protocol: str,
        tags: set[str],
        task_type: str,
        max_depth: int,
        context_cls: type[IContext] = BaseContext,
        parent: ITreeTaskNode[StateT, EventT] | None = None,
        sub_tasks: list[ITreeTaskNode[StateT, EventT]] | None = None,
        **kwargs: Any,
    ) -> None:
        # 树形结构属性初始化
        self._parent = None  # 初始化为None，将通过set_parent设置
        self._sub_tasks = sub_tasks if sub_tasks else []

        # 初始化深度（延迟计算）
        self._current_depth = 0  # 将在父子关系建立后重新计算
        self._max_depth = max_depth
        
        # 需要转换 transitions 中的回调函数类型，从 ITreeTaskNode 转为 ITask
        converted_transitions: dict[
            tuple[StateT, EventT], 
            tuple[StateT, Callable[[ITask[StateT, EventT]], Awaitable[None] | None] | None]
        ] = {}
        for (state, event), (next_state, callback) in transitions.items():
            converted_callback: Callable[[ITask[StateT, EventT]], Awaitable[None] | None] | None = None
            if callback is not None:
                # ITreeTaskNode[...] 是 ITask[...] 的子类型，可以直接转换
                converted_callback = cast(Callable[[ITask[StateT, EventT]], Awaitable[None] | None], callback)
            converted_transitions[(state, event)] = (next_state, converted_callback)

        super().__init__(
            # IStateMachine参数
            valid_states=valid_states,
            init_state=init_state,
            transitions=converted_transitions,
            # ITask参数
            protocol=protocol,
            tags=tags,
            task_type=task_type,
            context_cls=context_cls,
            **kwargs,
        )

        # 建立父子关系
        if sub_tasks:
            # 为每个子任务设置父节点
            for child in sub_tasks:
                child.set_parent(self)

        if parent is not None:
            # 通知父节点添加这个子节点（避免循环调用）
            if self not in parent.get_sub_tasks():
                parent.add_sub_task(self)

    # ********** 基础信息 **********
    
    def is_leaf(self) -> bool:
        """
        检查当前节点是否为叶子节点（无子节点）

        Returns:
            如果是叶子节点则返回True，否则返回False
        """
        return len(self._sub_tasks) == 0
    
    def is_root(self) -> bool:
        """
        检查当前节点是否为根节点（无父节点），并且 current_depth 为 0

        Returns:
            如果是根节点则返回True，否则返回False
        """
        return self._parent is None and self._current_depth == 0
    
    def get_current_depth(self) -> int:
        """
        获取当前节点在树中的深度（根节点深度为0）
        
        Returns:
            当前节点的深度值
        """
        return self._current_depth
    
    def get_max_depth(self) -> int:
        """
        获取以当前节点为根节点的子树的最大深度
        
        Returns:
            子树的最大深度值
        """
        return self._max_depth

    # ********** 节点关系 **********

    def get_parent(self) -> ITreeTaskNode[StateT, EventT] | None:
        """
        获取父节点
        
        Returns:
            父节点对象
        """
        return self._parent
    
    def set_parent(self, parent: ITreeTaskNode[StateT, EventT]) -> None:
        """
        设置父节点

        Args:
            parent: 父节点对象

        Raises:
            RuntimeError: 如果设置后的深度会超过最大深度限制
        """
        if self._parent is not parent:
            # 计算新深度
            new_depth = 0
            if parent is not None: # pyright: ignore[reportUnnecessaryComparison]
                new_depth = parent.get_current_depth() + 1

            # 检查深度限制
            if new_depth > self._max_depth:
                raise RuntimeError(
                    f"Cannot set parent: depth {new_depth} exceeds max depth {self._max_depth}"
                )

            # 从原父节点移除（如果存在）
            if self._parent is not None:
                old_parent = self._parent
                if self in old_parent.get_sub_tasks():
                    old_parent.pop_sub_task(self)

            # 设置新父节点
            self._parent = parent

            # 添加到新父节点的子节点列表（避免循环调用）
            if parent is not None and self not in parent.get_sub_tasks(): # type: ignore
                parent.add_sub_task(self)

            # 设置新深度
            self._current_depth = new_depth
        
    def remove_parent(self) -> None:
        self._parent = None
        # 当前深度重置为0
        self._current_depth = 0
        
    def get_sub_tasks(self) -> list[ITreeTaskNode[StateT, EventT]]:
        """
        获取所有子任务节点
        
        Returns:
            子任务节点列表
        """
        return self._sub_tasks.copy()
    
    def add_sub_task(self, sub_task: ITreeTaskNode[StateT, EventT]) -> None:
        """
        添加子任务节点

        Args:
            sub_task: 子任务节点对象
        """
        # 避免重复添加
        if sub_task not in self._sub_tasks:
            self._sub_tasks.append(sub_task)

            # 设置子任务的父节点（避免循环调用）
            if sub_task.get_parent() is not self:
                sub_task.set_parent(self)

    def pop_sub_task(self, node: ITreeTaskNode[StateT, EventT]) -> ITreeTaskNode[StateT, EventT]:
        """
        移除并返回指定的子任务节点

        Args:
            node: 子任务节点对象

        Returns:
            被移除的子任务节点对象
        """
        try:
            self._sub_tasks.remove(node)
        except ValueError as e:
            # 重新抛出带有更清晰信息的错误
            raise ValueError(f"Sub task node not found in the list") from e

        # 清除被移除子节点的父节点引用
        node.remove_parent()

        return node


class RequirementTreeTaskView(ITaskView[StateT, EventT]):
    """将树形任务可视化为需求格式的字符串表示，格式化内容可用于任务需求描述，递归包含所有子任务。
    由于父任务需在子任务全部完成后才执行，因此该视图的子任务直接输出结果。
    
    Example:
    ```markdown
    
    ## 子任务1标题
    子任务1输出内容

    ## 子任务2标题
    子任务2输出内容
    
    # 任务标题: 主任务
    - 类型: 主任务类型
    - 标签: 标签1, 标签2

    ## 任务执行协议
    主任务协议内容
    
    ## 任务输入
    主任务输入内容
    ```
    """

    @override
    def __call__(self, task: ITask[StateT, EventT], **kwargs: Any) -> str:
        """返回任务的需求事项字符串表示

        Args:
            task (ITask[StateT, EventT]): 任务实例
            **kwargs: 其他参数
        """
        assert isinstance(task, ITreeTaskNode), "RequirementTreeTaskView 只能用于 ITreeTaskNode 实例"
        
        # 格式化当前任务信息
        task_view: str = RequirementTaskView()(task, **kwargs)

        # 格式化子任务，没有递归，不关心子任务的子任务的结果
        sub_tasks_views: list[str] = []
        for sub_task in task.get_sub_tasks():
            # 获取子任务的文档视图
            sub_task_view = DocumentTaskView()(sub_task, **kwargs)
            # 降级子任务标题：通过在每个 markdown 标题前增加一个 "#"，实现子任务标题的视觉嵌套（heading demotion）
            sub_task_view = re.sub(r'(?m)(#+)(\s)', lambda m: '#' * (len(m.group(1)) + 1) + m.group(2), sub_task_view)
            sub_tasks_views.append(sub_task_view)

        return task_view + "\n\n" + "\n\n".join(sub_tasks_views)


class DocumentTreeTaskView(ITaskView[StateT, EventT]):
    """将任务可视化为文档格式的字符串表示，格式化结果仅包含标题和输出内容
    
    Example:
    ```markdown
    # 主任务标题
    任务输出内容
    
    ## 子任务1标题
    子任务1输出内容

    ## 子任务2标题
    子任务2输出内容
    """
    
    @override
    def __call__(self, task: ITask[StateT, EventT], **kwargs: Any) -> str:
        """返回任务的需求事项字符串表示

        Args:
            task (ITask[StateT, EventT]): 任务实例
            **kwargs: 其他参数
        """
        assert isinstance(task, ITreeTaskNode), "DocumentTreeTaskView 只能用于 ITreeTaskNode 实例"
        
        # 获取递归限制（-1表示无限制，0表示不递归，正数表示递归层数）
        recursive_limit: int = kwargs.get("recursive_limit", -1)
        # 格式化当前任务信息
        task_view: str = DocumentTaskView()(task, **kwargs)
        # 如果递归限制为0，则不处理子任务
        if recursive_limit == 0:
            return task_view
        # 更新下一层的递归限制
        if recursive_limit > 0:
            kwargs["recursive_limit"] = recursive_limit - 1
        
        # 递归格式化子任务
        sub_tasks_views: list[str] = []
        for sub_task in task.get_sub_tasks():
            # 获取子任务的文档视图
            sub_task_view = DocumentTreeTaskView()(sub_task, **kwargs)
            # 降级子任务标题：将任意连续的 '#' 增加一个
            sub_task_view = re.sub(r'(?m)(#+)(\s)', lambda m: '#' * (len(m.group(1)) + 1) + m.group(2), sub_task_view)
            sub_tasks_views.append(sub_task_view)
            
        return task_view + "\n\n" + "\n\n".join(sub_tasks_views)


class TodoTreeTaskView(ITaskView[StateT, EventT]):
    """将树形任务可视化为待办事项格式的字符串表示

    Example:
    ```markdown
    - [ ] 任务标题
        - [ ] 子任务1标题
        - [ ] 子任务2标题
    ```
    """
    
    @override
    def __call__(self, task: ITask[StateT, EventT], **kwargs: Any) -> str:
        """返回任务的需求事项字符串表示

        Args:
            task (ITask[StateT, EventT]): 任务实例
            **kwargs: 其他参数
        """
        assert isinstance(task, ITreeTaskNode), "TodoTreeTaskView 只能用于 ITreeTaskNode 实例"
        
        # 获取递归限制（-1表示无限制，0表示不递归，正数表示递归层数）
        recursive_limit: int = kwargs.get("recursive_limit", -1)
        # 格式化当前任务信息
        task_view: str = TodoTaskView()(task, **kwargs)
        # 如果递归限制为0，则不处理子任务
        if recursive_limit == 0:
            return task_view
        # 更新下一层的递归限制
        if recursive_limit > 0:
            kwargs["recursive_limit"] = recursive_limit - 1

        # 递归格式化子任务
        sub_tasks_views: list[str] = []
        for sub_task in task.get_sub_tasks():
            # 获取子任务的待办事项视图
            sub_task_view = TodoTaskView()(sub_task, **kwargs)
            # 增加子任务缩进
            sub_task_view = re.sub(r'(?m)^', '\t', sub_task_view)
            sub_tasks_views.append(sub_task_view)
            
        return task_view + "\n" + "\n".join(sub_tasks_views)


class JsonTreeTaskView(ITaskView[StateT, EventT]):
    """将任务可视化为JSON格式的字符串表示，格式化结果可用于结构化检查
    
    Example:
    ```json
    {
        "title": "示例任务",
        "task_type": "示例类型",
        "tags": ["标签1", "标签2"],
        "sub_tasks": [
            {
                "title": "子任务1",
                "task_type": "子任务类型1",
                "tags": ["子任务标签1"],
                "sub_tasks": []
            },
            {
                "title": "子任务2",
                "task_type": "子任务类型2",
                "tags": ["子任务标签2"],
                "sub_tasks": []
            }
        ]
    }
    ```
    """
    @override
    def __call__(self, task: ITask[StateT, EventT], **kwargs: Any) -> str:
        """返回任务的需求事项字符串表示

        Args:
            task (ITask[StateT, EventT]): 任务实例
            **kwargs: 其他参数
        """
        assert isinstance(task, ITreeTaskNode), "JsonTreeTaskView 只能用于 ITreeTaskNode 实例"
        
        # 获取递归限制（-1表示无限制，0表示不递归，正数表示递归层数）
        recursive_limit: int = kwargs.get("recursive_limit", -1)
        # 格式化当前任务信息
        task_view: dict[str, Any] = json.loads(JsonTaskView()(task, **kwargs))
        # 增加子任务标签
        task_view["sub_tasks"] = []
        # 如果递归限制为0，则不处理子任务
        if recursive_limit == 0:
            return json.dumps(task_view, ensure_ascii=False, indent=4)
        # 更新下一层的递归限制
        if recursive_limit > 0:
            kwargs["recursive_limit"] = recursive_limit - 1

        # 递归格式化子任务
        sub_tasks_views: list[dict[str, Any]] = []
        for sub_task in task.get_sub_tasks():
            # 获取子任务的JSON视图并解析为字典
            sub_task_view = JsonTaskView()(sub_task, **kwargs)
            sub_tasks_views.append(json.loads(sub_task_view))

        task_view["sub_tasks"] = sub_tasks_views
        return json.dumps(task_view, ensure_ascii=False, indent=4)
