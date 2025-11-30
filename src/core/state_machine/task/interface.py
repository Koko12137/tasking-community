from abc import abstractmethod, ABC
from typing import Any, Generic

from ..interface import IStateMachine
from ..const import StateT, EventT
from ...context import IContext
from ....model import Message


class ITask(IStateMachine[StateT, EventT]):

    # ********** 状态机属性增强 **********
    
    @abstractmethod
    def get_state_visit_count(self, state: StateT) -> int:
        """获取指定状态的访问计数

        Args:
            state: 目标状态

        Returns:
            指定状态的访问次数
        """
        pass
    
    @abstractmethod
    def set_max_revisit_count(self, count: int) -> None:
        """设置最大重访限制次数

        Args:
            count: 最大重访限制次数
        """
        pass
    
    @abstractmethod
    def get_max_revisit_limit(self) -> int:
        """获取最大重访限制次数

        Returns:
            最大重访限制次数
        """
        pass

    # ********** 任务基本属性 **********
    
    @abstractmethod
    def get_tags(self) -> set[str]:
        """
        获取任务标签集合，用于标识任务的特性或分类
        
        Returns:
            任务标签的集合
        """
        pass

    @abstractmethod
    def get_task_type(self) -> str:
        """
        获取任务的类型标识字符串
        
        Returns:
            任务类型标识字符串
        """
        pass

    @abstractmethod
    def get_title(self) -> str:
        """
        获取任务的标题
        
        Returns:
            任务标题字符串
        """
        pass
    
    @abstractmethod
    def set_title(self, title: str) -> None:
        """
        设置任务的标题
        
        Args:
            title: 任务标题字符串
        """
        pass

    # ********** 任务输入输出协议/案例/输入数据 **********

    @abstractmethod
    def get_protocol(self) -> str | dict[str, Any]:
        """
        获取任务的输入输出协议定义
        
        Returns:
            协议定义内容
        """
        pass
    
    @abstractmethod
    def get_input(self) -> str | list[dict[str, Any]]:
        """
        获取任务的输入数据
        
        Returns:
            输入数据内容，可以是字符串或字典列表
        """
        pass
    
    @abstractmethod
    def set_input(self, input_data: str | list[dict[str, Any]]) -> None:
        """
        设置任务的输入数据
        
        Args:
            input_data: 输入数据内容，可以是字符串或字典列表
        """
        pass
    
    # ********** 完成状态与信息 **********
    
    @abstractmethod
    def get_output(self) -> str:
        """
        获取任务的输出数据
        
        Returns:
            输出数据内容
        """
        pass
    
    @abstractmethod
    def set_completed(self, output: str) -> None:
        """
        设置任务为已完成状态，并存储输出数据
        
        Args:
            output: 输出数据内容
        """
        pass
    
    @abstractmethod
    def is_completed(self) -> bool:
        """
        检查任务是否已完成
        
        Returns:
            如果任务已完成则返回True，否则返回False
        """
        pass
    
    # ********** 错误状态与信息 **********
    
    @abstractmethod
    def is_error(self) -> bool:
        """
        检查任务是否错误
        
        Returns:
            如果错误则返回True，否则返回False
        """
        pass
    
    @abstractmethod
    def get_error_info(self) -> str:
        """
        获取任务的错误信息
        
        Returns:
            错误信息字符串，如果没有错误则返回空字符串
        """
        pass
    
    @abstractmethod
    def set_error(self, error_info: str) -> None:
        """
        设置任务为错误状态，并添加错误信息
        
        Args:
            error_info: 错误信息字符串
        """
        pass
    
    @abstractmethod
    def clean_error_info(self) -> None:
        """清除任务的错误信息"""
        pass

    # ********** 上下文信息 **********
    
    @abstractmethod
    def get_contexts(self) -> dict[StateT, IContext]:
        """
        获取任务所有状态的上下文信息对象字典
        
        Returns:
            上下文信息对象字典，键是任务状态，值是上下文实例
        """
        pass

    @abstractmethod
    def get_context(self) -> IContext:
        """
        获取任务当前状态的上下文信息对象
        
        Returns:
            上下文信息对象
        """
        pass

    @abstractmethod
    def append_context(self, data: Message) -> None:
        """
        向当前状态的上下文信息中追加数据
        
        Args:
            data: 追加的数据
        """
        pass
            
    # ********** 重写状态转换方法，增加访问计数 **********
    
    @abstractmethod
    def handle_event(self, event: EventT) -> None:
        """处理事件并进行状态转换，增加状态访问计数管理

        Args:
            event: 触发的事件

        Raises:
            ValueError: 如果当前状态未设置或没有定义对应的转换规则则抛出该异常
            RuntimeError: 如果状态机状态重访次数达到限制
        """


class ITaskView(ABC, Generic[StateT, EventT]):
    """将任务可视化为字符串表示的接口"""
    
    @abstractmethod
    def __call__(self, task: ITask[StateT, EventT], **kwargs: Any) -> str:
        """返回任务的字符串表示
        
        Args:
            task: 任务对象
            **kwargs: 其他参数
        """
        pass


class ITreeTaskNode(ITask[StateT, EventT]):
    """树形任务任务接口，支持父子关系管理"""

    # ********** 基础信息 **********
    
    @abstractmethod
    def is_leaf(self) -> bool:
        """
        检查当前任务是否为叶子任务（无子任务）
        
        Returns:
            如果是叶子任务则返回True，否则返回False
        """
        pass
    
    @abstractmethod
    def is_root(self) -> bool:
        """
        检查当前任务是否为根任务（无父任务）
        
        Returns:
            如果是根任务则返回True，否则返回False
        """
        pass
    
    @abstractmethod
    def get_current_depth(self) -> int:
        """
        获取当前任务在树中的深度（根任务深度为0）
        
        Returns:
            当前任务的深度值
        """
        pass
    
    @abstractmethod
    def get_max_depth(self) -> int:
        """
        获取以当前任务为根任务的子树的最大深度
        
        Returns:
            子树的最大深度值
        """
        pass

    # ********** 任务关系 **********
    
    @abstractmethod
    def get_parent(self) -> "ITreeTaskNode[StateT, EventT] | None":
        """
        获取父任务
        
        Returns:
            父任务对象
        """
        pass
    
    @abstractmethod
    def set_parent(self, parent: "ITreeTaskNode[StateT, EventT]") -> None:
        """
        设置父任务
        
        Args:
            parent: 父任务对象

        Raises:
            RuntimeError: 如果设置后的深度会超过最大深度限制
        """
        pass
    
    @abstractmethod
    def remove_parent(self) -> None:
        """
        移除当前任务的父任务关系
        """
        pass
    
    @abstractmethod
    def get_sub_tasks(self) -> list["ITreeTaskNode[StateT, EventT]"]:
        """
        获取所有子任务任务
        
        Returns:
            子任务任务列表
        """
        pass
    
    @abstractmethod
    def add_sub_task(self, sub_task: "ITreeTaskNode[StateT, EventT]") -> None:
        """
        添加子任务任务
        
        Args:
            sub_task: 子任务任务对象
        """
        pass
    
    @abstractmethod
    def pop_sub_task(
        self, 
        node: "ITreeTaskNode[StateT, EventT]",
    ) -> "ITreeTaskNode[StateT, EventT]":
        """
        移除并返回指定的子任务任务

        Args:
            node: 子任务任务对象
            
        Returns:
            被移除的子任务任务对象
        """
        pass
