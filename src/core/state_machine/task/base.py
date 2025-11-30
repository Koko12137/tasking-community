import json
import copy
from typing import Any, Callable, cast, Awaitable

from loguru import logger

from ..interface import IStateMachine
from ..const import StateT, EventT
from .interface import ITask, ITaskView
from ..base import BaseStateMachine
from ...context import IContext, BaseContext
from ....model import Message


class BaseTask(BaseStateMachine[StateT, EventT], ITask[StateT, EventT]):
    """任务状态机、任务属性管理"""
    # *** 状态机属性增强 ***
    _state_visit_counts: dict[StateT, int]
    _max_revisit_limit: int
    
    # *** 任务基本属性 ***
    _tags: set[str]
    _title: str
    _task_type: str
    
    # *** 任务输入输出 ***
    _protocol: str | dict[str, Any]
    _input_data: str | list[dict[str, Any]]
    _output_data: str
    _is_completed: bool
    
    # *** 错误信息 ***
    _is_error: bool
    _error_info: str
    
    # *** 上下文管理 ***
    _contexts: dict[StateT, IContext]
    _context_cls: type[IContext]

    def __init__(
        self,
        valid_states: set[StateT],
        init_state: StateT,
        transitions: dict[
            tuple[StateT, EventT],
            tuple[StateT, Callable[[ITask[StateT, EventT]], Awaitable[None] | None] | None]
        ],
        protocol: str,
        tags: set[str],
        task_type: str,
        context_cls: type[IContext] = BaseContext,
        **kwargs: Any,
    ) -> None:
        # 状态机属性增强
        self._state_visit_counts = dict()
        self._max_revisit_limit = 1     # 默认不允许重访
        
        # 任务预定义属性
        self._tags = tags.copy()        # 标签集合
        self._protocol = protocol       # 协议定义
        self._task_type = task_type     # 任务类型标识字符串

        # 任务输入输出
        self._title = ""                # 任务标题
        self._input_data = ""           # 输入数据
        self._output_data = ""          # 输出数据
        self._is_completed = False      # 是否完成

        # 错误信息
        self._is_error = False          # 是否错误
        self._error_info = ""           # 错误详情
        
        # 上下文初始化
        self._contexts = {}
        self._context_cls = context_cls
        
        # 需要转换 transitions 中的回调函数类型，从 ITask 转为 IStateMachine
        converted_transitions: dict[
            tuple[StateT, EventT],
            tuple[StateT, Callable[[IStateMachine[StateT, EventT]], Awaitable[None] | None] | None]
        ] = {}
        for (state, event), (next_state, callback) in transitions.items():
            converted_callback: Callable[[IStateMachine[StateT, EventT]], Awaitable[None] | None] | None = None
            if callback is not None:
                # ITask[...] 是 IStateMachine[...] 的子类型，可以直接转换
                converted_callback = cast(Callable[[IStateMachine[StateT, EventT]], Awaitable[None] | None], callback)
            converted_transitions[(state, event)] = (next_state, converted_callback)
        
        # 初始化父类状态机，并执行编译
        super().__init__(
            valid_states=valid_states,
            initial_state=init_state,
            transitions=converted_transitions,
            **kwargs,
        )

    def __repr__(self) -> str:
        return self.__str__()
    
    def __str__(self) -> str:
        return f"BaseTask(id={self._id}, tags={self._tags}, is_completed={self._is_completed})"

    # ********** 实现ITask接口：状态机属性增强 **********
    
    def get_state_visit_count(self, state: StateT) -> int:
        """获取指定状态的访问计数

        Args:
            state: 目标状态

        Returns:
            指定状态的访问次数
        """
        return self._state_visit_counts.get(state, 0)
    
    def set_max_revisit_count(self, count: int) -> None:
        self._max_revisit_limit = count
        
    def get_max_revisit_limit(self) -> int:
        """获取最大重访限制次数

        Returns:
            最大重访限制次数
        """
        return self._max_revisit_limit

    # ********** 实现ITask接口：任务基本属性 **********

    def get_tags(self) -> set[str]:
        """获取任务的标签集合"""
        return self._tags.copy()
    
    def get_task_type(self) -> str:
        """获取任务类型"""
        return self._task_type
    
    def get_title(self) -> str:
        """
        获取任务的标题
        
        Returns:
            任务标题字符串
        """
        return self._title
    
    def set_title(self, title: str) -> None:
        """
        设置任务的标题
        
        Args:
            title: 任务标题字符串
        """
        self._title = title

    # ********** 实现ITask接口：输入输出管理 **********
    
    def get_protocol(self) -> str | dict[str, Any]:
        """获取任务的协议定义，包括输入输出格式等信息"""
        return copy.deepcopy(self._protocol)

    def get_input(self) -> str | list[dict[str, Any]]:
        """获取任务的输入数据"""
        return copy.deepcopy(self._input_data)

    def set_input(self, input_data: str | list[dict[str, Any]]) -> None:
        """设置任务的输入数据"""
        self._input_data = input_data

    # ********** 实现ITask接口：完成状态管理 **********

    def get_output(self) -> str:
        """获取任务的输出数据"""
        return self._output_data

    def is_completed(self) -> bool:
        """检查任务是否已完成

        Returns:
            如果任务已完成则返回True，否则返回False
        """
        return self._is_completed

    def set_completed(self, output: str) -> None:
        """
        设置任务为已完成状态，并存储输出数据

        Args:
            output: 输出数据内容
        """
        self._output_data = output
        self._is_completed = True
        logger.info(f"[{self._id}] 任务已标记为完成")

    # ********** 实现ITask接口：错误状态管理 **********
    
    def is_error(self) -> bool:
        """错误状态包括FAILED和CANCELED"""
        return self._is_error

    def get_error_info(self) -> str:
        """
        获取任务的错误信息
        
        Returns:
            错误信息字符串，如果没有错误则返回空字符串
        """
        return self._error_info
    
    def set_error(self, error_info: str) -> None:
        """
        设置任务为错误状态，并添加错误信息
        
        Args:
            error_info: 错误信息字符串
        """
        self._error_info = error_info
        self._is_error = True  # 新增：设置错误状态为True
        logger.info(f"[{self._id}] 任务错误信息已更新")
    
    def clean_error_info(self) -> None:
        """清除任务的错误信息"""
        self._error_info = ""
        self._is_error = False
        logger.info(f"[{self._id}] 任务错误信息已清除")
    
    # ********** 上下文信息 **********

    def get_context(self) -> IContext:
        """获取指定状态的上下文信息

        Returns:
            IContextual: 状态的上下文信息
        """
        # 获取当前状态
        state = self._current_state
        return self._contexts[state]

    def get_contexts(self) -> dict[StateT, IContext]:
        """
        获取任务所有状态的上下文信息对象列表
        
        Returns:
            上下文信息对象字典，键是任务状态，值是上下文实例
        """
        return self._contexts

    def append_context(self, data: Message) -> None:
        """
        向当前状态的上下文信息中追加数据

        Args:
            data: 追加的数据
        """
        if not self._is_compiled:
            raise RuntimeError("Cannot append context before compilation")
        
        # 获取当前状态
        state = self._current_state
        # 追加数据到对应状态的上下文
        self._contexts[state].append_context_data(data)
        
    # ********** 重写编译方法，初始化上下文 **********
    
    def compile(self) -> None:
        """
        编译状态机，完成初始化及全状态可达性检查
        
        编译时必须满足以下所有条件：
        1. 已设置有效状态集合（非空）
        2. 已设置初始状态（且在有效状态集合中）
        3. 已设置至少一个转换规则
        4. 所有有效状态均可从初始状态出发到达（允许有环）
        
        Raises:
            ValueError: 若上述条件不满足则抛出对应异常
        """
        super().compile()
        
        # 初始化所有状态的访问计数
        self._state_visit_counts = {state: 0 for state in self._valid_states}
        # 初始状态访问计数设为1
        self._state_visit_counts[self._initial_state] = 1
        # 初始化所有状态的上下文
        for state in self._valid_states:
            self._contexts[state] = self._context_cls()
            
    # ********** 重写状态转换方法，增加访问计数 **********
    
    def handle_event(self, event: EventT) -> None:
        """处理事件并进行状态转换，增加状态访问计数管理

        Args:
            event: 触发的事件

        Raises:
            ValueError: 如果当前状态未设置或没有定义对应的转换规则则抛出该异常
            RuntimeError: 如果状态机重访次数达到限制
        """
        # 检查重访次数是否设置
        if self._max_revisit_limit <= 0:
            raise RuntimeError("Max revisit limit must be greater than 0")

        # 获取下一个状态以及对应的动作
        key = (self._current_state, event)
        if key not in self._transitions:
            raise ValueError(
                f"No transition defined for state {self._current_state} with event {event}"
            )
        next_state, action = self._transitions[key]
        # 增加新状态的访问计数
        self._state_visit_counts[next_state] += 1
        # 检查是否超过重访限制
        visit_count = self._state_visit_counts[next_state]
        if visit_count > self._max_revisit_limit:
            raise RuntimeError(
                f"State {next_state} has been revisited {visit_count} times, "
                f"reaching the limit of {self._max_revisit_limit}"
            )
        
        # 执行事件处理
        if action is not None:
            action(self)  # 执行状态转换前的动作
        # 切换到下一个状态
        self._current_state = next_state

    # ********** 重写重置方法，重置访问计数和上下文 **********
    
    def reset(self) -> None:
        super().reset()
        
        # 重置所有 context
        self._contexts = {}
        for state in self._valid_states:
            self._contexts[state] = BaseContext()
        # 重置访问计数
        self._state_visit_counts = {state: 0 for state in self._valid_states}
        # 初始状态访问计数设为1
        self._state_visit_counts[self._initial_state] = 1


class TodoTaskView(ITaskView[StateT, EventT]):
    """将任务可视化为待办事项格式的字符串表示
    
    Example:
    ```markdown
    - [ ] 任务标题
    ```
    """
    _template: str = "- [{status}] {title}"
    
    def __call__(self, task: ITask[StateT, EventT], **kwargs: Any) -> str:
        """返回任务的待办事项字符串表示

        Args:
            task (ITask[StateT, EventT]): 任务实例
            **kwargs: 其他参数
        """
        status = "x" if task.is_completed() else " "
        return self._template.format(status=status, title=task.get_title())


class DocumentTaskView(ITaskView[StateT, EventT]):
    """将任务可视化为文档格式的字符串表示，格式化结果仅包含标题和输出内容
    
    Example:
    ```markdown
    # 任务标题
    任务输出内容
    ```
    """
    _template: str = "# {title}\n{output}"

    def __call__(self, task: ITask[StateT, EventT], **kwargs: Any) -> str:
        """返回任务的待办事项字符串表示

        Args:
            task (ITask[StateT, EventT]): 任务实例
            **kwargs: 其他参数
        """
        return self._template.format(
            title=task.get_title(),
            output=task.get_output()
        )
        
        
class ProtocolTaskView(ITaskView[StateT, EventT]):
    """将任务可视化为协议格式的字符串表示，格式化结果仅包含标题和协议内容
    
    Example:
    ```markdown
    # 任务类型
    任务协议内容
    ```
    """
    _template: str = "# {title}\n{protocol}"

    def __call__(self, task: ITask[StateT, EventT], **kwargs: Any) -> str:
        """返回任务的待办事项字符串表示

        Args:
            task (ITask[StateT, EventT]): 任务实例
            **kwargs: 其他参数
        """
        return self._template.format(
            title=task.get_task_type(),
            protocol=task.get_protocol()
        )


class RequirementTaskView(ITaskView[StateT, EventT]):
    """将任务可视化为需求格式的字符串表示，格式化内容可用于任务需求描述
    
    Example:
    ```markdown
    # 任务标题: 示例任务
    - 类型: 示例类型
    - 标签: 标签1, 标签2
    - 完成: False
    
    ## 任务执行协议
    示例协议内容
    
    ## 任务输入
    示例输入内容
    ```
    """
    _template: str = "# 任务标题: {title}\n- 类型: {task_type}\n- 标签: {tags}\n- 完成: {is_completed}\n## 任务执行协议\n{protocol}\n## 任务输入\n{input_data}"

    def __call__(self, task: ITask[StateT, EventT], **kwargs: Any) -> str:
        """返回任务的待办事项字符串表示

        Args:
            task (ITask[StateT, EventT]): 任务实例
            **kwargs: 其他参数
        """
        return self._template.format(
            title=task.get_title(),
            task_type=task.get_task_type(),
            tags=task.get_tags(),
            is_completed=task.is_completed(),
            protocol=task.get_protocol(),
            input_data=task.get_input()
        )


class JsonTaskView(ITaskView[StateT, EventT]):
    """将任务可视化为JSON格式的字符串表示，格式化结果可用于结构化检查
    
    Example:
    ```json
    {
        "title": "示例任务",
        "task_type": "示例类型",
        "tags": ["标签1", "标签2"]
    }
    ```
    """

    def __call__(self, task: ITask[StateT, EventT], **kwargs: Any) -> str:
        """返回任务的待办事项字符串表示

        Args:
            task (ITask[StateT, EventT]): 任务实例
            **kwargs: 其他参数
        """
        task_info: dict[str, Any] = {
            "title": task.get_title(),
            "task_type": task.get_task_type(),
            "tags": list(task.get_tags())
        }
        return json.dumps(task_info, ensure_ascii=False, indent=4)
