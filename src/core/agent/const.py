from enum import Enum, auto


class DefaultAgent(Enum):
    """基础代理类型枚举"""
    SUPERVISOR = auto()  # 监督者代理
    PLANNER = auto()     # 规划者代理
    EXECUTOR = auto()    # 执行者代理
