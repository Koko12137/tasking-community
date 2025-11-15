from enum import Enum, auto


class TaskState(Enum):
    """任务的合法状态枚举"""
    INITED = auto()     # 初始化
    CREATED = auto()    # 创建
    RUNNING = auto()    # 执行中
    FINISHED = auto()   # 完成
    FAILED = auto()     # 失败
    CANCELED = auto()   # 取消


class TaskEvent(Enum):
    """任务的合法事件枚举"""
    INIT = auto()           # 初始化
    IDENTIFIED = auto()     # 目标已确认
    PLANED = auto()         # 完成规划
    DONE = auto()           # 执行完成
    ERROR = auto()          # 执行错误
    RETRY = auto()          # 重试
    CANCEL = auto()         # 取消


if __name__ == "__main__":
    # 测试枚举定义
    for state in TaskState:
        print(f"TaskState: {state.name} = {state.value}")
    
    for event in TaskEvent:
        print(f"TaskEvent: {event.name} = {event.value}")
