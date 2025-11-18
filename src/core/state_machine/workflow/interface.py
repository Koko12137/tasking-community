from abc import abstractmethod
from typing import Any, Generic, Awaitable, Callable

from fastmcp.tools import Tool as FastMcpTool
from mcp.types import CallToolResult

from src.core.state_machine.interface import IStateMachine
from src.core.state_machine.task.interface import ITask, StateT, EventT
from src.core.state_machine.workflow.const import WorkflowStageT, WorkflowEventT
from src.model import Message, IQueue, CompletionConfig


class IWorkflow(IStateMachine[WorkflowStageT, WorkflowEventT], Generic[WorkflowStageT, WorkflowEventT, StateT, EventT]):
    """工作流接口定义"""
        
    # ********** 基础属性信息 **********
    
    @abstractmethod
    def get_name(self) -> str:
        """获取工作流的名称"""
        pass
    
    @abstractmethod
    def get_completion_config(self) -> CompletionConfig:
        """
        获取工作流当前阶段的LLM推理配置信息
        
        Returns:
            LLM推理配置信息实例
        """
        pass
        
    # ********** 基础能力信息 **********
    
    @abstractmethod
    def has_stage(self, stage: WorkflowStageT) -> bool:
        """检查工作流是否包含指定阶段

        Args:
            stage (StageT): 目标阶段
            
        Returns:
            bool: 如果包含则返回 True，否则返回 False
        """
        pass

    @abstractmethod
    def get_event_chain(self) -> list[WorkflowEventT]:
        """获取工作流的事件链的副本，第一个为初始事件，最后一个为结束事件
        
        Returns:
            list[WorkflowEventT]: 工作流的事件链
        """
        pass

    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def get_prompts(self) -> dict[WorkflowStageT, str]:
        """获取工作流的所有阶段提示模板的副本

        Returns:
            dict[WorkflowStageT, str]: 工作流的所有阶段提示模板的副本
        """
        pass
    
    @abstractmethod
    def get_prompt(self) -> str:
        """获取工作流当前阶段的提示模板

        Returns:
            str: 当前阶段的提示模板
        """
        pass
    
    @abstractmethod
    def get_observe_funcs(self) -> dict[WorkflowStageT, Callable[[ITask[StateT, EventT], dict[str, Any]], Message]]:
        """获取工作流的所有阶段观察函数的副本

        Returns:
            dict[WorkflowStageT, Callable]: 工作流的所有阶段观察函数
        """
        pass
    
    @abstractmethod
    def get_observe_fn(self) -> Callable[[ITask[StateT, EventT], dict[str, Any]], Message]:
        """获取工作流当前阶段的观察函数

        Returns:
            Callable: 当前阶段用于从任务中提取观察信息的函数
        """
        pass
        
    # ********** 工作流工具与推理配置 **********
    
    @abstractmethod
    def add_tool(self, tool: Callable[..., Any], name: str, tags: set[str], dependencies: list[str]) -> None:
        """添加工具
        
        Args:
            tool (Callable): 工具函数，最后一个入参必须是 kwargs，用于接收注入参数
            name (str): 工具名称
            tags (set[str]): 工具标签
            dependencies (list[str]): 工具依赖的其他输入，这个对大模型不可见，可由 `call_tool` 注入
        """
        pass

    @abstractmethod
    def get_tool(self, name: str) -> tuple[FastMcpTool, set[str]] | None:
        """获取指定名称的工具

        Args:
            name (str): 工具名称

        Returns:
            tuple[FastMcpTool, set[str]] | None: 指定名称的工具和标签集合，如果未找到则返回None
        """
        pass
    
    @abstractmethod
    def get_tools(self) -> dict[str, tuple[FastMcpTool, set[str]]]:
        """获取工作流中所有注册的工具的副本

        Returns:
            dict[str, tuple[FastMcpTool, set[str]]]: 工作流中所有注册的工具，键为工具名称，值为工具和标签集合的元组
        """
        pass
    
    @abstractmethod
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
            kwargs (dict[str, Any]): 工具调用的参数

        Returns:
            CallToolResult: 工具调用结果

        Raises:
            ValueError: 如果工具名称未注册到工作流
        """
        pass
