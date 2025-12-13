# Scheduler 模块文档

> Scheduler 模块负责任务调度和编排，监听任务状态变化并触发相应的业务逻辑。

## 核心概念

Scheduler 是一个**灵活的调度系统**，具有以下特点：

- **纯状态驱动**：只关心 Task 的状态机状态，根据状态变化触发相应的处理逻辑
- **状态管理职责**：Scheduler 负责 Task 的生命周期推进，根据状态进行任务调度
- **状态感知后处理**：在任务状态改变时执行相应的后处理操作
- **灵活调度策略**：可以根据任务的**状态/标签/类别/协议**等属性进行自定义调度
- **状态可达性保证**：Task 是一个必须能达到终点的图数据结构，Scheduler 确保状态可达性

## Scheduler vs Workflow 的区别

```mermaid
graph TB
    ScheduleStart[调度器入口]
    ScheduleStart --> ReadState[读取 Task 当前状态]
    ReadState -->|否| SelectHandler{根据状态选择调度函数}
    SelectHandler --> CallHandler[调度函数<br/>执行业务逻辑<br/>]
    HandlerReturn --> TaskHandle[将 Event 发送给 Task 执行处理]
    TaskHandle --> OnStateChanged[调度器后处理：on_state_changed]
    %% 后处理完成后回到“根据状态选择调度函数”进行最终判断
    OnStateChanged --> ReadState{是否为结束状态？}
    ReadState -->|是| END

    subgraph "Workflow - 自驱动事件链"
        W1[Agent 执行任务] --> W2[获取第一个工作流事件<br/>event_chain_0]
        W2 --> W3[执行工作流动作]
        W3 --> W4[触发下一个 工作流Event]
        W4 --> W5[event_chain_1]
        W5 --> W3
        W3 -->|到达终态| W6[Workflow 结束]
    end

    CallHandler --> W1
    W6 --> HandlerReturn[调度函数返回 Event 或 None]

    %% 说明与样式（便于阅读）
    style ScheduleStart fill:#e1f5fe,stroke:#90caf9
    style ReadState fill:#fff3e0
    style SelectHandler fill:#fff9c4
    style CallHandler fill:#f3e5f5
    style HandlerReturn fill:#fff8e1
    style TaskHandle fill:#e8f5e9
    style OnStateChanged fill:#fce4ec
```

**关键区别**：
- **Scheduler**：只关心 Task 的状态机状态，根据状态变化进行调度，并在状态改变时执行后处理
- **Workflow**：不关心 Task 的状态，只关心任务运行期间的推进情况，并依此驱动自身的状态变化
- **Agent**：不关心 Task 的状态，专注于任务内容的正确执行和推进

## 核心功能

### 调度器类型

#### build_base_scheduler

基础任务调度器，支持树形任务调度：

```python
from tasking.core.scheduler import build_base_scheduler
from tasking.core.agent import IAgent
from tasking.core.state_machine.task.const import TaskState, TaskEvent

# 需要先配置 executor Agent
executor: IAgent[...]  # 配置实际的执行器 Agent
orchestrator: IAgent[...] | None = None  # 可选的规划器 Agent

# 创建基础调度器
scheduler = build_base_scheduler(
    executor=executor,
    orchestrator=orchestrator,
    max_error_retry=3
)
```

**注意**：`build_base_scheduler` 已经内置了对树形任务的支持，包括：
- 自动调度子任务
- 处理子任务取消
- 递归执行父子任务关系

无需单独的 `create_tree_scheduler` 函数。

## 自定义调度策略

除了基于状态的标准调度，Scheduler 支持基于任务属性的自定义调度策略：

### 基于标签的调度

```python
# 创建任务队列
from collections import defaultdict

# 示例框架 - 用户需要根据实际需求实现
class TagBasedScheduler:
    def __init__(self):
        self.task_queues = defaultdict(list)  # 按标签分组的任务队列
        self.executor_agents = {}  # 不同标签的执行器

    def register_agent_for_tag(self, tag: str, agent):
        """为特定标签注册执行器"""
        self.executor_agents[tag] = agent

    async def schedule_by_tag(self, scheduler, context, queue, task):
        """根据任务标签进行调度"""
        # 获取任务标签
        tags = task.get_tags()

        # 选择最匹配的执行器
        for tag in tags:
            if tag in self.executor_agents:
                executor = self.executor_agents[tag]

                # 使用对应的执行器处理任务
                result = await executor.run_task_stream(
                    context=context,
                    queue=queue,
                    task=task
                )
                return result

        # 没有匹配的执行器，使用默认处理
        print(f"未找到标签 {tags} 的专用执行器，使用默认处理")
        return TaskEvent.PLANED

# 使用示例
# tag_scheduler = TagBasedScheduler()
# tag_scheduler.register_agent_for_tag("data_processing", data_processing_agent)
# tag_scheduler.register_agent_for_tag("analysis", analysis_agent)
#
# # 注册调度回调
# scheduler.set_on_state_fn(TaskState.RUNNING, tag_scheduler.schedule_by_tag)
```

### 基于协议的调度

```python
# 示例框架 - 用户需要根据实际需求实现
class ProtocolBasedScheduler:
    def __init__(self):
        self.protocol_handlers = {}  # 协议处理器映射

    def register_protocol_handler(self, protocol: str, handler_func):
        """注册特定协议的处理器"""
        self.protocol_handlers[protocol] = handler_func

    async def schedule_by_protocol(self, scheduler, context, queue, task):
        """根据任务协议进行调度"""
        protocol = task.get_protocol()

        if protocol in self.protocol_handlers:
            handler = self.protocol_handlers[protocol]

            # 使用协议处理器处理任务
            await handler(scheduler, context, queue, task)
        else:
            # 通用协议处理
            await self.handle_generic_protocol(scheduler, context, queue, task)

        return TaskEvent.DONE

    async def handle_generic_protocol(self, scheduler, context, queue, task):
        """通用协议处理"""
        print(f"处理通用协议任务: {protocol}")
        # 执行通用逻辑
        pass

# 使用示例（注释掉的部分需要用户实现）
# protocol_scheduler = ProtocolBasedScheduler()
#
# # 注册文本分析协议处理器
# async def handle_text_analysis(scheduler, context, queue, task):
#     """文本分析协议处理"""
#     input_data = task.get_input()
#
#     # 验证输入是否符合协议
#     if "text" not in input_data:
#         task.set_error_info("缺少必需的 text 字段")
#         return TaskEvent.DONE  # 错误时返回DONE事件，让调度器处理错误状态
#
#     # 执行文本分析
#     # ...
#
#     return TaskEvent.DONE
#
# protocol_scheduler.register_protocol_handler(
#     "text_analysis_v1.0",
#     handle_text_analysis
# )
```

### 基于优先级的调度

```python
# 示例框架 - 用户需要根据实际需求实现
import heapq
from typing import NamedTuple

class PrioritizedTask(NamedTuple):
    priority: int
    order: int  # 相同优先级时的顺序
    task: object

class PriorityScheduler:
    def __init__(self):
        self.task_heap = []  # 优先级堆
        self.order_counter = 0

    def add_task(self, task, priority=0):
        """添加任务到优先级队列"""
        prioritized_task = PrioritizedTask(
            priority=priority,
            order=self.order_counter,
            task=task
        )
        heapq.heappush(self.task_heap, prioritized_task)
        self.order_counter += 1

    async def schedule_by_priority(self, scheduler, context, queue):
        """按优先级调度任务"""
        while self.task_heap:
            prioritized_task = heapq.heappop(self.task_heap)
            task = prioritized_task.task

            # 调度任务
            await scheduler.schedule(
                context=context,
                queue=queue,
                fsm=task
            )

# 使用示例（注释掉的部分需要用户实现）
# priority_scheduler = PriorityScheduler()
#
# async def on_task_created(scheduler, context, queue, task):
#     """任务创建时根据标签确定优先级"""
#     # 高优先级任务
#     if "urgent" in task.get_tags():
#         priority_scheduler.add_task(task, priority=10)
#     # 中等优先级任务
#     elif "normal" in task.get_tags():
#         priority_scheduler.add_task(task, priority=5)
#     # 低优先级任务
#     else:
#         priority_scheduler.add_task(task, priority=1)
#
#     return None  # 不立即执行，等待优先级调度
#
# scheduler.set_on_state_fn(TaskState.CREATED, on_task_created)
```

### 负载均衡调度

```python
# 示例框架 - 用户需要根据实际需求实现
class LoadBalancedScheduler:
    def __init__(self):
        self.executors = []
        self.current_executor = 0
        self.executor_loads = {}  # 跟踪每个执行器的负载

    def add_executor(self, executor):
        """添加执行器"""
        self.executors.append(executor)
        self.executor_loads[executor] = 0

    def get_least_loaded_executor(self):
        """获取负载最小的执行器"""
        if not self.executors:
            return None

        min_load = float('inf')
        selected_executor = None

        for executor in self.executors:
            load = self.executor_loads.get(executor, 0)
            if load < min_load:
                min_load = load
                selected_executor = executor

        return selected_executor

    async def schedule_with_balance(self, scheduler, context, queue, task):
        """负载均衡调度"""
        executor = self.get_least_loaded_executor()

        if executor:
            # 增加执行器负载计数
            self.executor_loads[executor] += 1

            try:
                # 执行任务
                result = await executor.run_task_stream(
                    context=context,
                    queue=queue,
                    task=task
                )
                return result
            finally:
                # 减少执行器负载计数
                self.executor_loads[executor] -= 1

        return TaskEvent.DONE

# 使用示例（注释掉的部分需要用户实现）
# load_balancer = LoadBalancedScheduler()
# load_balancer.add_executor(executor1)
# load_balancer.add_executor(executor2)
# load_balancer.add_executor(executor3)
#
# scheduler.set_on_state_fn(TaskState.RUNNING, load_balancer.schedule_with_balance)
```

## 状态回调机制

### on_state_fn：状态监听与任务调度

`on_state_fn` 是调度的核心机制，用于监听任务状态并执行相应的业务逻辑：

**关键特性**：
- **触发时机**：当任务进入特定状态时立即触发
- **返回要求**：必须返回一个 TaskEvent 来驱动任务状态变化
- **调度职责**：负责任务的具体执行和调度

```python
from queue import Queue
from tasking.model.message import Message, Role
from typing import Any

async def on_created_state(
    scheduler: BaseScheduler[TaskState, TaskEvent],
    context: dict[str, Any],
    queue: Queue[Message],
    task: ITask[TaskState, TaskEvent]
) -> TaskEvent:
    """进入 CREATED 状态的处理逻辑

    必须返回一个 TaskEvent 来驱动任务状态变化
    """
    print(f"任务 {task.get_id()[:8]} 已创建")

    # 设置任务属性
    task.set_title("已创建的任务")

    # 执行具体的业务逻辑（如调用 Agent 进行规划）
    # await orchestrator.run_task_stream(...)

    # 必须返回事件来驱动状态转换
    return TaskEvent.PLANED  # 驱动任务从 CREATED -> RUNNING

# 注册状态监听函数
scheduler.set_on_state_fn(TaskState.CREATED, on_created_state)
```

**重要**：`on_state_fn` 的返回值直接影响任务的状态转换，是驱动任务生命周期的核心。

### on_state_changed_fn：状态变化的后处理

`on_state_changed_fn` 用于处理任务状态变化后的清理和后处理工作：

**关键特性**：
- **触发时机**：在任务状态实际发生转换后触发
- **无返回值**：不返回任何值，不会驱动新的状态变化
- **后处理职责**：负责清理、记录、通知等后处理工作

```python
async def on_running_to_finished(
    scheduler: BaseScheduler[TaskState, TaskEvent],
    context: dict[str, Any],
    queue: Queue[Message],
    task: ITask[TaskState, TaskEvent]
) -> None:
    """任务从 RUNNING 变为 FINISHED 的后处理

    不返回任何值，仅执行后处理逻辑
    """
    print(f"任务 {task.get_id()} 已完成")

    # 清理错误信息
    task.clean_error_info()

    # 清理子任务（对于树形任务）
    if isinstance(task, ITreeTaskNode):
        # 移除已完成的子任务引用
        for sub_task in task.get_sub_tasks():
            if sub_task.get_current_state() == TaskState.FINISHED:
                sub_task.remove_parent()

    # 发送完成通知
    message = Message(
        role=Role.SYSTEM,
        content=[TextBlock(text=f"任务 {task.get_title()} 执行完成")]
    )
    await queue.put(message)

    # 注意：不返回任何值，不会触发新的状态转换

# 注册状态变化后处理函数
scheduler.set_on_state_changed_fn(
    (TaskState.RUNNING, TaskState.FINISHED),
    on_running_to_finished
)
```

**重要**：`on_state_changed_fn` 只负责后处理，不能驱动状态转换，避免无限循环。

### 两者的协作关系

```mermaid
sequenceDiagram
    participant Task as Task
    participant Scheduler as Scheduler
    participant on_state as on_state_fn
    participant on_changed as on_state_changed_fn

    Note over Scheduler: 监听任务状态
    Task->>Scheduler: 进入状态 S1

    Note over on_state: 执行调度逻辑
    Scheduler->>on_state: 调用 on_state_fn(S1)
    on_state->>Scheduler: 返回 TaskEvent
    Scheduler->>Task: handle_event(TaskEvent)
    Task->>Task: 状态转换 S1 -> S2

    Note over on_changed: 执行后处理
    Scheduler->>on_changed: 调用 on_state_changed_fn(S1->S2)
    on_changed->>Scheduler: 执行清理/通知等（无返回）

    Note over Scheduler: 继续监听新状态
    Scheduler->>Scheduler: 检查 S2 是否为结束状态
```

## 状态机特性

### 有限状态机保证

所有状态机（包括 Task 和 Workflow）都必须是能够到达终点的图数据结构：

1. **Task 状态机**：
   - 必须有明确的结束状态（FINISHED、CANCELED）
   - 每个状态都必须有到达终点的路径
   - 通过 `max_revisit_count` 防止无限循环

2. **Workflow 状态机**：
   - 通过 `event_chain` 定义执行序列，确保终态可达
   - 每个阶段转换都是确定性的
   - 终态（END）必须能够通过事件链到达

### 循环检测机制

```python
# Scheduler 循环检测和自动编译
# 调度器在初始化时自动设置 max_revisit_count 并编译
# max_revisit_count ≤ 0：无环模式，禁止状态重访
# max_revisit_count > 0：允许有限重访，超过次数则判定为非法循环

from tasking.core.scheduler import build_base_scheduler

scheduler = build_base_scheduler(
    executor=executor,
    max_error_retry=3
)

# 调度器已在初始化时自动编译，无需手动调用 compile()

# 捕获循环错误
try:
    await scheduler.schedule(context=context, queue=queue, fsm=task)
except RuntimeError as e:
    if "状态重访次数达到限制" in str(e):
        print("检测到循环，任务终止")
```

## 调度流程

```mermaid
stateDiagram-v2
    [*] --> Ready: 调度器准备就绪
    Ready --> CheckEnd: 任务初始化完成

    CheckEnd --> |已在结束状态| [*]: 无需调度
    CheckEnd --> |未结束| OnState: 进入当前状态回调

    OnState --> TaskExecution: on_state 执行
    TaskExecution --> EventReturn: 返回事件
    
    EventReturn --> StateChange: 状态转换
    StateChange --> OnStateChanged: on_state_changed 回调
    
    OnStateChanged --> CheckEnd: 检查是否到达结束状态

    style Ready fill:#e8f5e9
    style OnState fill:#fff3e0
    style TaskExecution fill:#e3f2fd
    style StateChange fill:#fff3e0
    style OnStateChanged fill:#e8f5e9
    style CheckEnd fill:#fce4ec
```

**流程说明**:

1. **OnState**: 当任务进入某个状态时执行 on_state 回调，执行对应的业务逻辑
2. **任务执行**: on_state 中执行具体的任务逻辑（如调用 Agent 执行）
3. **事件返回**: 任务执行完后返回一个事件（如 TaskEvent.DONE）
4. **状态转换**: 根据返回的事件驱动状态机进行状态转换
5. **OnStateChanged**: 状态转换后执行 on_state_changed 回调
6. **检查终态**: 检查当前状态是否为结束状态，如果是则调度完成，否则继续调度循环

## 循环检测与错误处理

### 设置循环限制

调度器在创建时可以通过参数设置最大状态重访次数（max_revisit_count），并在初始化时自动进行编译检查。

示例（通过 build_base_scheduler 创建调度器时传入 max_error_retry）：

```python
# 通过 build_base_scheduler 创建调度器时，内部会处理错误重试
scheduler = build_base_scheduler(
    executor=executor,
    orchestrator=orchestrator,
    max_error_retry=3  # 内部转换为 max_revisit_count
)

# 直接调度任务时，如果检测到状态重访次数超过允许值，调度器会抛出 RuntimeError
try:
    await scheduler.schedule(context=context, queue=queue, fsm=task)
except RuntimeError as e:
    if "状态重访次数达到限制" in str(e):
        print("检测到循环，任务终止")
```

### 错误重试机制

```python
# build_base_scheduler 自动支持错误重试
# max_error_retry 控制重试次数
scheduler = build_base_scheduler(
    executor=executor,
    orchestrator=orchestrator,
    max_error_retry=3  # 最多重试3次
)
```

## 使用示例

### 完整的调度流程配置

```python
import asyncio
from queue import Queue
from tasking.core.scheduler import build_base_scheduler
from tasking.core.state_machine.task import build_base_tree_node
from tasking.core.state_machine.task.const import TaskState, TaskEvent
from tasking.core.agent import IAgent
from tasking.model.llm import CompletionConfig
from tasking.model.message import Message, Role, TextBlock

async def main():
    # 1. 创建任务
    task = build_base_tree_node(
        protocol="example_v1.0",
        tags={"example"},
        task_type="demo_task",
        max_depth=3,
        completion_config=CompletionConfig(),
    )
    task.compile(max_revisit_count=3)
    task.set_title("示例任务")

    # 2. 创建 Executor Agent（需要实现 IAgent 接口）
    executor: IAgent[...]  # 配置实际的执行器 Agent
    orchestrator: IAgent[...] | None = None  # 可选的规划器 Agent

    # 3. 创建调度器
    # 注意：build_base_scheduler 已经内置了状态处理函数
    # on_state_fn 和 on_state_changed_fn 可以通过 scheduler.set_on_state_fn
    # 和 scheduler.set_on_state_changed_fn 单独设置
    scheduler = build_base_scheduler(
        executor=executor,
        orchestrator=orchestrator,
        max_error_retry=3
    )

    # 4. 自定义状态处理（可选，覆盖默认行为）
    async def custom_on_created(
        scheduler,
        context,
        queue,
        task
    ) -> TaskEvent:
        """自定义 CREATED 状态处理"""
        print(f"任务创建: {task.get_title()}")

        # 执行自定义逻辑
        # ...

        # 必须返回事件驱动状态转换
        return TaskEvent.PLANED

    # 覆盖默认的状态处理函数
    scheduler.set_on_state_fn(TaskState.CREATED, custom_on_created)

    # 5. 配置自定义状态变化后处理（可选）
    async def custom_on_finished(
        scheduler,
        context,
        queue,
        task
    ) -> None:
        """自定义任务完成后的处理"""
        print(f"任务完成: {task.get_title()}")

        # 清理错误信息
        task.clean_error_info()

        # 发送完成通知
        message = Message(
            role=Role.SYSTEM,
            content=[TextBlock(text=f"任务 '{task.get_title()}' 已完成")]
        )
        await queue.put(message)

    # 注册状态变化后处理函数
    scheduler.set_on_state_changed_fn(
        (TaskState.RUNNING, TaskState.FINISHED),
        custom_on_finished
    )

    # 6. 执行调度
    context = {"user_id": "user123", "session_id": "abc"}
    queue = Queue[Message]()

    await scheduler.schedule(context=context, queue=queue, fsm=task)

    # 7. 处理队列消息
    while not queue.empty():
        message = queue.get()
        print(f"收到消息: {message.content}")

    print("调度完成")

if __name__ == "__main__":
    asyncio.run(main())
```

### 最佳实践

#### 1. on_state_fn 最佳实践

```python
async def best_practice_on_state(
    scheduler,
    context,
    queue,
    task
) -> TaskEvent:
    """on_state_fn 的最佳实践示例"""

    # ✅ DO: 记录状态进入
    logger.info(f"Task {task.get_id()} entered {task.get_current_state()}")

    # ✅ DO: 执行业务逻辑
    try:
        # 执行具体逻辑
        if task.get_current_state() == TaskState.CREATED:
            # 规划阶段
            result = await plan_task(task, context)
            return TaskEvent.PLANED

        elif task.get_current_state() == TaskState.RUNNING:
            # 执行阶段
            result = await execute_task(task, context)
            if result.success:
                return TaskEvent.DONE
            else:
                task.set_error_info(result.error)
                return TaskEvent.PLANED  # 重试

    except Exception as e:
        # ❌ DON'T: 不返回事件
        # ✅ DO: 异常时也要返回事件
        task.set_error_info(str(e))
        return TaskEvent.PLANED  # 返回重试事件

    # ❌ NEVER: 不要返回 None
```

#### 2. on_state_changed_fn 最佳实践

```python
async def best_practice_on_state_changed(
    scheduler,
    context,
    queue,
    task
) -> None:
    """on_state_changed_fn 的最佳实践示例"""

    # ✅ DO: 执行清理工作
    if task.get_current_state() == TaskState.FINISHED:
        task.clean_error_info()

        # 清理子任务引用（如果是树形任务）
        if isinstance(task, ITreeTaskNode):
            for sub_task in task.get_sub_tasks():
                if sub_task.get_current_state() == TaskState.FINISHED:
                    sub_task.remove_parent()

    # ✅ DO: 发送通知和日志
    message = Message(
        role=Role.SYSTEM,
        content=[TextBlock(text=f"Task {task.get_title()} is now {task.get_current_state()}")]
    )
    await queue.put(message)

    # ❌ NEVER: 不要返回任何值
    # ❌ NEVER: 不要试图驱动状态转换
    # return TaskEvent.SOME_EVENT  # 错误！
```

#### 3. 错误处理模式

```python
# ✅ 正确的错误处理：在 on_state_fn 中处理
async def robust_on_state(
    scheduler,
    context,
    queue,
    task
) -> TaskEvent:
    try:
        # 执行业务逻辑
        await do_work(task)
        return TaskEvent.DONE
    except TemporaryError as e:
        # 临时错误，可以重试
        task.set_error_info(str(e))
        return TaskEvent.PLANED  # 触发重试
    except FatalError as e:
        # 致命错误，取消任务
        task.set_error_info(str(e))
        return TaskEvent.CANCEL

# ✅ 在 on_state_changed_fn 中只做日志记录
async def log_error(
    scheduler,
    context,
    queue,
    task
) -> None:
    if task.is_error():
        logger.error(f"Task {task.get_id()} failed: {task.get_error_info()}")
        # 只记录，不处理
```

### 递归调度树形任务

```python
async def handle_root_task(
    scheduler: BaseScheduler[TaskState, TaskEvent],
    context: dict[str, Any],
    queue: Queue[Message],
    root_task: ITreeTaskNode[TaskState, TaskEvent]
) -> TaskEvent:
    """处理根任务，递归调度子任务"""
    
    # 定义一个快捷的函数用于读取你的提示词
    from your.read.util import read_prompt

    # 创建子任务
    subtasks = []
    for i in range(3):
        subtask = build_base_tree_node(
            protocol=read_prompt(f"subtask_{i}_v1.0"),  # 该任务遵循 subtask_{i}_v1.0 定义的任务执行规范
            tags={"subtask"},
            task_type="subtask",
            max_depth=3,
            completion_config=CompletionConfig(),
        )
        subtasks.append(subtask)

        # 添加到根任务
        root_task.add_sub_task(subtask)

    # 递归调度所有子任务
    for subtask in subtasks:
        await scheduler.schedule(
            context=context,
            queue=queue,
            fsm=subtask
        )

    # 所有子任务完成后继续
    return TaskEvent.DONE

# 注册回调
scheduler.set_on_state_fn(TaskState.CREATED, handle_root_task)
```

## 调度器配置

### 结束状态设置

调度器的结束状态在初始化时通过 builder 函数自动设置：

```python
# 调度器通过 build_base_scheduler 创建时自动配置结束状态
scheduler = build_base_scheduler(
    executor=executor,
    orchestrator=orchestrator,
    max_error_retry=3
    # 结束状态 (FINISHED, CANCELED) 已在函数内部预配置
)

# 获取结束状态
end_states = scheduler.get_end_states()
print(f"结束状态: {end_states}")
```

### 自动编译

调度器在初始化时自动编译，无需手动调用 compile()：

```python
# 创建调度器时自动编译
scheduler = build_base_scheduler(
    executor=executor,
    orchestrator=orchestrator,
    max_error_retry=3
)

# 调度器已在初始化时自动编译，可以直接使用
# 检查是否已编译
if scheduler.is_compiled():
    print("调度器已编译，可以使用")

# 现在可以直接调度任务
await scheduler.schedule(context=context, queue=queue, fsm=task)
```

## 核心原则总结

### on_state_fn vs on_state_changed_fn 的关键区别

| 特性 | on_state_fn | on_state_changed_fn |
|------|------------|-------------------|
| **触发时机** | 进入状态时 | 状态变化后 |
| **返回值** | 必须 TaskEvent | 必须无返回 |
| **作用** | 驱动状态转换 | 执行后处理 |
| **副作用** | 会触发新状态 | 不会触发新状态 |
| **用途** | 业务执行逻辑 | 清理/通知/日志 |

**记忆口诀**：
- `on_state_fn`：**驱动者** - 返回事件推动任务前进
- `on_state_changed_fn`：**清理者** - 无返值善后不留痕迹

## 最佳实践

1. **合理设置重试次数**：避免无限重试消耗资源，max_error_retry 通过 builder 函数传入
2. **职责分离**：
   - 在 `on_state_fn` 中执行业务逻辑，返回事件
   - 在 `on_state_changed_fn` 中执行清理，不返回值
3. **错误处理**：
   - 业务逻辑错误在 `on_state_fn` 中处理并返回相应事件
   - `on_state_changed_fn` 只做日志记录，不处理错误
4. **监控队列消息**：及时处理调度过程中的消息
5. **理解循环检测**：调度器自动检测非法循环，通过 max_revisit_count 控制（在初始化时设置）
6. **选择合适的调度器类型**：简单任务用 create_simple_scheduler，复杂工作流用 create_tree_scheduler

**最后更新**: 2025-11-11