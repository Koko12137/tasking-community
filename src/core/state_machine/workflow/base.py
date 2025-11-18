from typing import Any, Callable, Awaitable, cast

from fastmcp.tools import Tool as FastMcpTool
from mcp.types import CallToolResult, TextContent

from src.core.state_machine.interface import IStateMachine
from src.core.state_machine.base import BaseStateMachine
from src.core.state_machine.task.interface import ITask, StateT, EventT
from src.core.state_machine.workflow.interface import IWorkflow
from src.core.state_machine.workflow.const import WorkflowStageT, WorkflowEventT
from src.model import Message, IQueue, CompletionConfig


class BaseWorkflow(IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT], BaseStateMachine[WorkflowStageT, WorkflowEventT]):
    """基础工作流实现类"""
    _name: str
    _completion_configs: dict[WorkflowStageT, CompletionConfig]
    # 基础能力
    _actions: dict[WorkflowStageT, Callable[
        [
            "IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]",  # workflow
            dict[str, Any],  # context
            IQueue[Message],  # queue
            ITask[StateT, EventT],  # task
        ],
        Awaitable[WorkflowEventT]
    ]]
    _prompts: dict[WorkflowStageT, str]
    _observe_funcs: dict[WorkflowStageT, Callable[[ITask[StateT, EventT], dict[str, Any]], Message]]
    _event_chain: list[WorkflowEventT]
    # 工具集合
    _tools: dict[str, tuple[FastMcpTool, set[str]]]

    def __init__(
        self,
        # 状态机基础能力
        valid_states: set[WorkflowStageT],
        init_state: WorkflowStageT,
        transitions: dict[
            tuple[WorkflowStageT, WorkflowEventT], 
            tuple[WorkflowStageT, Callable[[IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]], Awaitable[None] | None] | None]
        ],
        # Workflow 基本属性
        name: str,
        completion_configs: dict[WorkflowStageT, CompletionConfig],
        actions: dict[
            WorkflowStageT, 
            Callable[
                [
                    IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT], 
                    dict[str, Any], 
                    IQueue[Message], 
                    ITask[StateT, EventT]
                ], 
                Awaitable[WorkflowEventT]
            ]
        ],
        prompts: dict[WorkflowStageT, str],
        observe_funcs: dict[WorkflowStageT, Callable[[ITask[StateT, EventT], dict[str, Any]], Message]],
        event_chain: list[WorkflowEventT],
        tools: dict[str, tuple[FastMcpTool, set[str]]] | None = None,
        **kwargs: Any
    ) -> None:
        """构建基础工作流实例

        Args:
            valid_states: 工作流合法状态集合
            init_state: 工作流初始状态
            transitions: 工作流转换规则
            name: 工作流名称
            labels: 工作流标签字典
            actions: 工作流动作定义
            prompts: 工作流提示词定义
            observe_funcs: 工作流观察格式定义
            event_chain: 工作流事件链
            end_workflow: 结束工作流工具
            tools: 工作流工具集合（可选）
            **kwargs: 其他关键字参数
        """
        # 初始化基本属性
        self._name = name
        self._completion_configs = completion_configs
        # 初始化基础能力
        self._actions = actions
        self._prompts = prompts
        self._observe_funcs = observe_funcs
        self._event_chain = event_chain
        # 工具集合，默认包括结束工作流工具
        self._tools = tools if tools is not None else {}

        # 需要转换 transitions 中的回调函数类型，从 IWorkflow 转为 IStateMachine
        converted_transitions: dict[
            tuple[WorkflowStageT, WorkflowEventT], 
            tuple[WorkflowStageT, Callable[[IStateMachine[WorkflowStageT, WorkflowEventT]], Awaitable[None] | None] | None]
        ] = {}
        for (state, event), (next_state, callback) in transitions.items():
            converted_callback: Callable[[IStateMachine[WorkflowStageT, WorkflowEventT]], Awaitable[None] | None] | None = None
            if callback is not None:
                # IWorkflow[...] 是 IStateMachine[...] 的子类型，可以直接转换
                converted_callback = cast(Callable[[IStateMachine[WorkflowStageT, WorkflowEventT]], Awaitable[None] | None], callback)
            converted_transitions[(state, event)] = (next_state, converted_callback)

        # 初始化状态机，并且执行编译
        super().__init__(
            valid_states,
            init_state,
            converted_transitions,
            **kwargs
        )

    # ********** 基础属性信息 **********
    
    def get_name(self) -> str:
        """获取工作流的名称"""
        return self._name

    def get_completion_config(self) -> CompletionConfig:
        """
        获取工作流当前阶段的LLM推理配置信息
        
        Returns:
            LLM推理配置信息实例
        """
        # 获取当前状态
        stage = self.get_current_state()
        return self._completion_configs[stage]

    # ********** 基础能力信息 **********

    def has_stage(self, stage: WorkflowStageT) -> bool:
        """检查工作流是否包含指定阶段

        Args:
            stage (StageT): 目标阶段

        Returns:
            bool: 如果包含则返回 True，否则返回 False
        """
        return stage in self._valid_states if self._valid_states else False
    
    def get_event_chain(self) -> list[WorkflowEventT]:
        """获取工作流的事件链的副本，第一个为初始事件，最后一个为结束事件
        
        Returns:
            list[WorkflowEventT]: 工作流的事件链的副本
        """
        return self._event_chain.copy()

    def get_actions(self) -> dict[WorkflowStageT, Callable[
        [
            "IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]",  # workflow
            dict[str, Any],  # context
            IQueue[Message],  # queue
            ITask[StateT, EventT],  # task
        ], 
        Awaitable[WorkflowEventT]
    ]]:
        """获取工作流的所有动作的副本
        
        Returns:
            dict[WorkflowStageT, Callable[workflow, context, queue, task]]: 工作流的所有动作函数。签名：
                - workflow (IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]): 工作流实例
                - context (dict[str, Any]): 上下文字典,用于传递用户ID/AccessToken/TraceID等信息
                - queue (IQueue[Message]): 数据队列,用于输出数据
                - task (ITask[StateT, EventT]): 任务实例
        """
        return self._actions.copy()

    def get_action(self) -> Callable[
        [
            "IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]",  # workflow
            dict[str, Any],  # context
            IQueue[Message],  # queue
            ITask[StateT, EventT],  # task
        ], 
        Awaitable[WorkflowEventT]
    ]:
        """获取工作流当前阶段的动作
    
        Returns:
            指定阶段的动作动作函数。签名：
                - workflow (IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]): 工作流实例
                - context (dict[str, Any]): 上下文字典,用于传递用户ID/AccessToken/TraceID等信息
                - queue (IQueue[Message]): 数据队列,用于输出数据
                - task (ITask[StateT, EventT]): 任务实例
        """
        # 获取当前状态
        stage = self.get_current_state()
        return self._actions[stage]
    
    def get_prompts(self) -> dict[WorkflowStageT, str]:
        """获取工作流的所有阶段提示模板

        Returns:
            dict[WorkflowStageT, str]: 工作流的所有阶段提示模板
        """
        return self._prompts.copy()
    
    def get_prompt(self) -> str:
        """获取工作流当前阶段的提示模板

        Returns:
            str: 指定阶段的提示模板
        """
        # 获取当前状态
        stage = self.get_current_state()
        return self._prompts[stage]

    def get_observe_funcs(self) -> dict[WorkflowStageT, Callable[[ITask[StateT, EventT], dict[str, Any]], Message]]:
        """获取工作流的所有阶段观察格式

        Returns:
            dict[WorkflowStageT, Callable]: 工作流的所有阶段观察函数
        """
        return self._observe_funcs

    def get_observe_fn(self) -> Callable[[ITask[StateT, EventT], dict[str, Any]], Message]:
        """获取工作流当前阶段的观察格式

        Returns:
            Callable: 指定阶段用于从任务中提取观察信息的函数
        """
        # 获取当前状态
        stage = self.get_current_state()
        return self._observe_funcs[stage]
        
    # ********** 工作流工具与推理配置 **********

    def add_tool(self, tool: Callable[..., Any], name: str, tags: set[str], dependencies: list[str]) -> None:
        """添加工具
        
        Args:
            tool (Callable): 工具函数，必须接受关键字参数 kwargs（用于注入依赖）
            name (str): 工具名称
            tags (set[str]): 工具标签
            dependencies (list[str]): 工具依赖的其他输入，这个对大模型不可见，可由 `call_tool` 注入
        """
        # 转为 FastMcpTool 并添加到工具集合
        fastmcp_tool = FastMcpTool.from_function(
            fn=tool, 
            name=name, 
            tags=tags,
            exclude_args=["task", "workflow", *dependencies],  # 排除 task/workflow 参数以及其他依赖注入参数
        )
        # 添加到 Dict 中
        self._tools[name] = (fastmcp_tool, tags)

    def get_tool(self, name: str) -> tuple[FastMcpTool, set[str]] | None:
        """获取指定名称的工具

        Args:
            name (str): 工具名称

        Returns:
            tuple[FastMcpTool, set[str]] | None: 指定名称的工具和标签集合，如果未找到则返回None
        """
        return self._tools[name] if name in self._tools else None
    
    def get_tools(self) -> dict[str, tuple[FastMcpTool, set[str]]]:
        """获取工作流的所有工具的副本

        Returns:
            dict[str, tuple[FastMcpTool, set[str]]]: 工作流的所有工具，键为工具名称，值为工具和标签集合的元组
        """
        return self._tools.copy()

    async def call_tool(
        self, 
        name: str, 
        task: ITask[StateT, EventT], 
        inject: dict[str, Any], 
        kwargs: dict[str, Any]
    ) -> CallToolResult:
        """调用指定名称的工具

        Args:
            name (str): 工具名称
            task (ITask[StateT, EventT]): 任务实例
            inject (dict[str, Any]): 注入工具的额外依赖参数
            kwargs (dict[str, Any]): 工具调用参数

        Returns:
            CallToolResult: 工具调用结果

        Raises:
            ValueError: 如果工具名称未注册到工作流
        """
        tool_entry = self.get_tool(name)
        if tool_entry is None:
            raise ValueError(f"Tool '{name}' is not registered in the workflow")
        
        tool, _ = tool_entry
        # 更新 kwargs，注入 workflow 实例和 task 实例，以及其他依赖参数
        kwargs.update({"kwargs": {"workflow": self, "task": task, **inject}})
        # 调用工具
        try:
            tool_call_result = await tool.run(kwargs)
            result = CallToolResult(
                content=tool_call_result.content,
                structuredContent=tool_call_result.structured_content,
                isError=False,
            )
        except RuntimeError as e:
            # 运行时错误直接抛出
            raise e
        except Exception as e:
            result = CallToolResult(content=[TextContent(type="text", text=str(e))], isError=True)

        return result

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
        
        # 检查 event chain 是否设置
        if self._event_chain == []:
            self._is_compiled = False  # 回滚编译状态
            raise ValueError("Event chain must be set before compilation")

        # 检查 actions 是否为空
        if self._actions == {}:
            self._is_compiled = False  # 回滚编译状态
            raise ValueError("Actions must be set before compilation")

        # 检查 prompts 是否为空
        if self._prompts == {}:
            self._is_compiled = False  # 回滚编译状态
            raise ValueError("Prompts must be set before compilation")

        # 检查 observe_funcs 是否为空
        if self._observe_funcs == {}:
            self._is_compiled = False  # 回滚编译状态
            raise ValueError("Observe functions must be set before compilation")
