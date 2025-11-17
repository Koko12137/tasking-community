import asyncio

from loguru import logger

from src.core.agent import build_react_agent
from src.core.scheduler import build_base_scheduler
from src.core.state_machine.task import build_default_tree_node
from src.model import Message, IQueue
from server.utils.queue import AQueue


async def run() -> None:
    """入口函数，演示任务状态机与简单Agent的集成使用"""

    # 创建简单Agent
    agent = build_react_agent(name="demo")
    logger.info("react Agent created.")

    # 创建默认的简单调度器
    scheduler = build_base_scheduler(agent)
    logger.info("base scheduler created.")
    
    # 创建默认的树形任务节点状态机实例
    task_node = build_default_tree_node()
    logger.info(f"Created task node with type: {task_node.get_task_type()}")
    
    # 用户输入任务目标
    task_node.set_input("介绍一下人工智能技术")

    # 创建消息队列
    message_queue: IQueue[Message] = AQueue()
    
    # 启动调度器
    await scheduler.schedule(dict[str, str](), message_queue, task_node)

    # 获取任务的输出结果
    output = task_node.get_output()
    logger.info(f"Task Output: {output}")


if __name__ == "__main__":
    asyncio.run(run())
