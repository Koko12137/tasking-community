import asyncio
from typing import Any

from ..core.state_machine.task import ITask
from ..core.state_machine.const import StateT, EventT
from ..model import Message, IAsyncQueue


async def stream_output_hook(
    context: dict[str, Any],
    queue: IAsyncQueue[Message],
    stream_queue: IAsyncQueue[Message] | None,
    task: ITask[StateT, EventT],
) -> None:
    """流式输出思考内容的钩子方法

    参数:
        context (dict[str, Any]): 当前请求的上下文信息, 包含用户信息、请求元数据等
        queue (IQueue[Message]): 向人类发送消息的队列
        stream_queue (IQueue[Message] | None): 用于流式输出的消息队列
        task (ITask[StateT, EventT]): 当前任务实例
    """
    while True:
        # 检查 stream_queue 是否关闭
        if stream_queue is None or stream_queue.is_closed():
            break

        # 从 stream_queue 获取消息块
        try:
            chunk = await asyncio.wait_for(stream_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            continue

        # 将 chunk 内容发送到主消息队列
        await queue.put(chunk)
