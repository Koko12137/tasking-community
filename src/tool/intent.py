from typing import Any

from ..core.state_machine.task import ITask


def intent_identify(intent: int, kwargs: dict[str, Any] = {}) -> None:
    """意图识别工具。这个是提供给大模型用的意图识别工具，开发者需要重新实现这个函数的文档，然后用 FastMCP 的 Tool 功能包装起来供大模型调用。
    
    Example:
        ```python
        from fastmcp.tools import Tool
        from tasking.tool.intent import intent_identify
        
        DOCS = ""\"意图识别工具。根据任务的输入内容，识别出用户的意图编号。
        1. 用户的意图是询问天气
        2. 用户的意图是预订餐厅
        3. 用户的意图是查询航班信息
        
        Args:
            intent: 识别出的意图编号，必须是整数
        ""\"
        
        intent_tool = Tool.from_function(
            fn=intent_identify,
            name="intent_identify",
            description=DOCS,
            exclude_args=["kwargs"],    # 排除掉 kwargs 参数，这个由框架自动注入
        )
        ```
    """
    # 从 kwargs 中获取当前任务对象
    task = kwargs.get("task")
    if task is None:
        raise ValueError("Task object is required in kwargs")
    if not isinstance(task, ITask):
        raise TypeError("Invalid task object in kwargs")
    
    task_input = task.get_input()
    # 添加意图识别结果到任务输入的最后
    if isinstance(task_input, list):
        task_input.append({"type": "text", "text": f"<intent>{intent}</intent>"})
        task.set_input(task_input)
    elif isinstance(task_input, str): # pyright: ignore[reportUnnecessaryIsInstance]
        task.set_input(f"{task_input}\n<intent>{intent}</intent>")
    else:
        raise TypeError("Unsupported input type for intent identification")
