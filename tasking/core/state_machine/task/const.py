from enum import Enum, auto


class TaskState(Enum):
    """任务的合法状态枚举"""
    CREATED = auto()    # 创建
    RUNNING = auto()    # 执行中
    FINISHED = auto()   # 完成
    CANCELED = auto()   # 取消


class TaskEvent(Enum):
    """任务的合法事件枚举"""
    INIT = auto()           # 初始化
    PLANED = auto()         # 完成规划
    DONE = auto()           # 执行完成
    CANCEL = auto()         # 取消
