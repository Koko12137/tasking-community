"""主程序入口，演示任务状态机与简单Agent的集成使用."""

import asyncio

from loguru import logger

from tasking.hook import stream_output_hook
from tasking.core.agent import build_react_agent
from tasking.core.scheduler import build_base_scheduler
from tasking.core.state_machine.task import DefaultTreeNode
from tasking.model import Message, IAsyncQueue, AsyncQueue, TextBlock


async def run() -> None:
    """入口函数，演示任务状态机与简单Agent的集成使用"""

    # 创建简单Agent
    agent = build_react_agent(name="executor")
    logger.info("react Agent created.")
    # 注册流式输出中间件
    agent.add_post_think_hook(stream_output_hook)

    # 创建默认的简单调度器
    scheduler = build_base_scheduler(agent)
    logger.info("base scheduler created.")

    # 创建默认的树形任务节点状态机实例
    task_node = DefaultTreeNode()
    logger.info(f"Created task node with type: {task_node.get_task_type()}")

    # 用户输入任务目标
    task_node.set_input([TextBlock(text="介绍一下人工智能技术")])
    # 设置任务标题
    task_node.set_title("ROOT Task Node")

    # 创建消息队列
    message_queue: IAsyncQueue[Message] = AsyncQueue()
    # 用于控制消息处理循环的标志
    should_process = True

    # 处理消息队列中的消息
    async def process_messages() -> None:
        """处理消息队列中的消息"""
        while should_process:
            try:
                # 使用队列的 get 方法，如果队列为空且已关闭会立即返回
                message = await message_queue.get()
                if len(message.content) != 0 and isinstance(message.content[0], TextBlock):
                    print(message.content[0].text, end="", flush=True)
            except asyncio.CancelledError:
                # 任务被取消，正常退出
                break
            except RuntimeError:
                # 队列已关闭，退出循环
                break
            except Exception:  # type: ignore[reportBroadException]
                # 其他未预期的异常，记录日志并退出
                logger.warning("Unexpected error in message processing, exiting loop")
                break

    # 启动消息处理任务
    process_task = asyncio.create_task(process_messages(), name="Process-Messages-Task")

    try:
        # 启动调度器任务
        schedule_task = asyncio.create_task(
            scheduler.schedule(dict[str, str](), message_queue, task_node),
            name="Scheduler-Task",
        )
        await schedule_task
    finally:
        # 确保在调度器完成后停止消息处理
        should_process = False
        # 关闭消息队列，这会导致 message_queue.get() 抛出异常或立即返回
        await message_queue.close()

        # 取消消息处理任务
        process_task.cancel()

        # 等待消息处理任务完成
        try:
            await process_task
        except asyncio.CancelledError:
            logger.debug("Message processing task cancelled successfully")

    # 获取任务的输出结果
    output = task_node.get_output()
    logger.info(f"Task Output: {output}")


if __name__ == "__main__":
    asyncio.run(run())
