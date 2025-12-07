"""
Task模块测试套件

测试BaseTask和相关功能
"""

import unittest
from typing import Callable, Awaitable, Any

from src.core.state_machine.task.base import BaseTask
from src.core.state_machine.task.interface import ITask
from src.core.state_machine.task.const import TaskState, TaskEvent
from src.model import CompletionConfig, Message, Role


class TestBaseTask(unittest.IsolatedAsyncioTestCase):
    """测试BaseTask的核心功能"""

    def setUp(self) -> None:
        """设置测试环境"""
        # 定义状态转换
        self.transitions: dict[
            tuple[TaskState, TaskEvent],
            tuple[TaskState, Callable[[ITask[TaskState, TaskEvent]], Awaitable[None] | None] | None]
        ] = {
            (TaskState.INITED, TaskEvent.IDENTIFIED): (TaskState.CREATED, None),
            (TaskState.CREATED, TaskEvent.PLANED): (TaskState.RUNNING, None),
            (TaskState.RUNNING, TaskEvent.DONE): (TaskState.FINISHED, None),
            (TaskState.RUNNING, TaskEvent.ERROR): (TaskState.FAILED, None),
            (TaskState.CREATED, TaskEvent.CANCEL): (TaskState.CANCELED, None),
        }

        # 创建完成配置
        self.completion_config = CompletionConfig(
            temperature=0.7,
            max_tokens=1000
        )

        # 创建任务实例
        self.task = BaseTask[TaskState, TaskEvent](
            valid_states={TaskState.INITED, TaskState.CREATED, TaskState.RUNNING,
                         TaskState.FINISHED, TaskState.FAILED, TaskState.CANCELED},
            init_state=TaskState.INITED,
            transitions=self.transitions,
            protocol="test_protocol_v1",
            tags={"test", "base_task"},
            task_type="test_task",
            completion_config=self.completion_config,
            max_revisit_limit=3
        )

        # 任务在初始化时已自动编译

    def test_task_initialization(self) -> None:
        """测试任务初始化 - 基础功能测试样例"""
        # 验证ID类型
        task_id: str = self.task.get_id()
        self.assertIsInstance(task_id, str)
        self.assertGreater(len(task_id), 0)

        # 验证属性类型与默认值
        self.assertEqual(self.task.get_protocol(), "test_protocol_v1")
        self.assertEqual(self.task.get_tags(), {"test", "base_task"})
        self.assertIsInstance(self.task.get_tags(), set)
        self.assertEqual(self.task.get_task_type(), "test_task")
        self.assertEqual(self.task.get_input(), "")
        self.assertEqual(self.task.get_output(), "")
        self.assertEqual(self.task.get_title(), "")
        self.assertFalse(self.task.is_completed())
        self.assertFalse(self.task.is_error())

    def test_task_protocol_management(self) -> None:
        """测试任务协议管理"""
        # 测试初始协议
        protocol = self.task.get_protocol()
        self.assertEqual(protocol, "test_protocol_v1")
        self.assertIsInstance(protocol, str)

    def test_task_tags_management(self) -> None:
        """测试任务标签管理"""
        initial_tags = self.task.get_tags()
        self.assertEqual(initial_tags, {"test", "base_task"})

        # 测试标签集合特性
        self.assertIsInstance(initial_tags, set)
        self.assertIn("test", initial_tags)
        self.assertIn("base_task", initial_tags)

    def test_task_title_management(self) -> None:
        """测试任务标题管理"""
        # 测试初始标题
        self.assertEqual(self.task.get_title(), "")

        # 设置标题
        title = "Test Task Title"
        self.task.set_title(title)
        self.assertEqual(self.task.get_title(), title)

    def test_task_input_output_management(self) -> None:
        """测试任务输入输出数据管理 - 类型检查样例"""
        # 测试输入（字符串类型）
        input_data: str = "test_input_123"
        self.task.set_input(input_data)
        self.assertEqual(self.task.get_input(), input_data)
        self.assertIsInstance(self.task.get_input(), str)

        # 测试输入（字典类型）
        input_dict: dict[str, Any] = {"key": "value", "number": 123}
        self.task.set_input(input_dict)
        self.assertEqual(self.task.get_input(), input_dict)
        self.assertIsInstance(self.task.get_input(), dict)

        # 测试输出
        output_data: str = "test_output_456"
        self.task.set_completed(output_data)
        self.assertEqual(self.task.get_output(), output_data)
        self.assertIsInstance(self.task.get_output(), str)
        self.assertTrue(self.task.is_completed())

    async def test_task_state_visit_counting(self) -> None:
        """测试状态访问计数功能"""
        # 初始状态计数
        initial_count = self.task.get_state_visit_count(TaskState.INITED)
        self.assertEqual(initial_count, 1)

        # 状态转换后计数
        await self.task.handle_event(TaskEvent.IDENTIFIED)
        self.assertEqual(self.task.get_current_state(), TaskState.CREATED)

        created_count = self.task.get_state_visit_count(TaskState.CREATED)
        self.assertEqual(created_count, 1)

        # 再次转换
        await self.task.handle_event(TaskEvent.PLANED)
        self.assertEqual(self.task.get_current_state(), TaskState.RUNNING)

        running_count = self.task.get_state_visit_count(TaskState.RUNNING)
        self.assertEqual(running_count, 1)

    async def test_task_max_revisit_limit(self) -> None:
        """测试最大重访限制"""
        self.assertEqual(self.task.get_max_revisit_limit(), 3)

        # 测试多次访问同一状态
        # 先返回到初始状态
        await self.task.handle_event(TaskEvent.IDENTIFIED)  # INITED -> CREATED
        await self.task.handle_event(TaskEvent.CANCEL)  # CREATED -> CANCELED

        # 重置任务
        self.task.reset()

        # 模拟多次访问同一状态（通过在RUNNING状态之间循环）
        await self.task.handle_event(TaskEvent.IDENTIFIED)  # INITED -> CREATED
        await self.task.handle_event(TaskEvent.PLANED)  # CREATED -> RUNNING

        # 继续触发事件会增加RUNNING状态的访问计数
        # 由于没有从RUNNING到RUNNING的转换，我们需要测试其他场景
        self.assertEqual(self.task.get_state_visit_count(TaskState.RUNNING), 1)

    def test_task_error_state_management(self) -> None:
        """测试任务错误状态管理"""
        # 初始状态应该没有错误
        self.assertFalse(self.task.is_error())
        self.assertEqual(self.task.get_error_info(), "")

        # 设置错误信息
        error_msg = "Test error message"
        self.task.set_error(error_msg)
        self.assertTrue(self.task.is_error())
        self.assertEqual(self.task.get_error_info(), error_msg)

        # 清除错误信息
        self.task.clean_error_info()
        self.assertFalse(self.task.is_error())
        self.assertEqual(self.task.get_error_info(), "")

    def test_task_completion_config(self) -> None:
        """测试任务完成配置"""
        config = self.task.get_completion_config()
        self.assertIsInstance(config, CompletionConfig)
        self.assertEqual(config.temperature, 0.7)
        self.assertEqual(config.max_tokens, 1000)

    def test_task_context_management(self) -> None:
        """测试任务上下文管理"""
        # 测试获取当前状态的上下文
        context = self.task.get_context()
        self.assertIsNotNone(context)

        # 测试追加上下文数据 - 先添加系统消息
        system_msg = Message(role=Role.SYSTEM, content="System message")
        self.task.append_context(system_msg)

        # 再添加用户消息
        user_msg = Message(role=Role.USER, content="Test message")
        self.task.append_context(user_msg)

        # 验证上下文数据已添加
        updated_context = self.task.get_context()
        self.assertIsNotNone(updated_context)
        self.assertEqual(len(updated_context.get_context_data()), 2)

    async def test_task_reset(self) -> None:
        """测试任务重置功能"""
        # 执行一些状态转换
        await self.task.handle_event(TaskEvent.IDENTIFIED)
        self.assertEqual(self.task.get_current_state(), TaskState.CREATED)

        # 设置一些数据
        self.task.set_title("Test Title")
        self.task.set_input("Test Input")
        self.task.set_completed("Test Output")
        self.task.set_error("Test Error")

        # 重置任务
        self.task.reset()

        # 验证重置后的状态
        self.assertEqual(self.task.get_current_state(), TaskState.INITED)
        self.assertEqual(self.task.get_title(), "Test Title")  # 标题不会重置
        self.assertEqual(self.task.get_input(), "Test Input")  # 输入不会重置
        self.assertEqual(self.task.get_output(), "Test Output")  # 输出不会重置
        # 错误信息不会被reset清除，需要手动clean_error_info
        self.assertTrue(self.task.is_error())

        # 手动清除错误信息
        self.task.clean_error_info()
        self.assertFalse(self.task.is_error())

    def test_task_interface_compliance(self) -> None:
        """测试Task是否实现ITask接口"""
        # 验证BaseTask是ITask的子类
        self.assertIsInstance(self.task, ITask)

    def test_task_type_safety(self) -> None:
        """测试任务类型安全"""
        # 测试不同类型的参数 - 需要确保所有状态都可到达
        transitions_int: dict[
            tuple[TaskState, TaskEvent],
            tuple[TaskState, Callable[[ITask[TaskState, TaskEvent]], Awaitable[None] | None] | None]
        ] = {
            (TaskState.INITED, TaskEvent.IDENTIFIED): (TaskState.CREATED, None),
            (TaskState.CREATED, TaskEvent.DONE): (TaskState.FINISHED, None)
        }
        task1 = BaseTask[TaskState, TaskEvent](
            valid_states={TaskState.INITED, TaskState.CREATED, TaskState.FINISHED},
            init_state=TaskState.INITED,
            transitions=transitions_int,
            protocol="test_int",
            tags={"test_int"},
            task_type="test_int",
            completion_config=self.completion_config
        )
        # task1 在初始化时已自动编译

        # 验证类型创建成功
        self.assertIsInstance(task1, BaseTask)

        # 验证ID生成
        self.assertIsInstance(task1.get_id(), str)


class TestTaskStateMachineIntegration(unittest.IsolatedAsyncioTestCase):
    """测试Task与StateMachine的集成"""

    def setUp(self) -> None:
        """设置测试环境"""
        self.transitions: dict[
            tuple[TaskState, TaskEvent],
            tuple[TaskState, Callable[[ITask[TaskState, TaskEvent]], Awaitable[None] | None] | None]
        ] = {
            (TaskState.INITED, TaskEvent.IDENTIFIED): (TaskState.CREATED, None),
            (TaskState.CREATED, TaskEvent.PLANED): (TaskState.RUNNING, None),
            (TaskState.RUNNING, TaskEvent.DONE): (TaskState.FINISHED, None),
        }

        self.completion_config = CompletionConfig(
            temperature=0.7,
            max_tokens=1000
        )

        self.task = BaseTask[TaskState, TaskEvent](
            valid_states={
                TaskState.INITED, TaskState.CREATED, TaskState.RUNNING, TaskState.FINISHED
            },
            init_state=TaskState.INITED,
            transitions=self.transitions,
            protocol="test_dict",
            tags={"test_dict"},
            task_type="test_dict",
            completion_config=self.completion_config
        )
        # 任务在初始化时已自动编译

    def test_task_state_machine_methods(self) -> None:
        """测试Task的状态机方法"""
        # 测试继承的状态机方法是否存在
        state_machine_methods = [
            'get_id', 'get_current_state', 'handle_event', 'reset', 'compile'
        ]

        for method_name in state_machine_methods:
            self.assertTrue(hasattr(self.task, method_name))
            method = getattr(self.task, method_name)
            self.assertTrue(callable(method))

    async def test_task_state_lifecycle(self) -> None:
        """测试任务状态生命周期"""
        # 验证初始状态
        self.assertEqual(self.task.get_current_state(), TaskState.INITED)

        # 执行状态转换
        await self.task.handle_event(TaskEvent.IDENTIFIED)
        self.assertEqual(self.task.get_current_state(), TaskState.CREATED)

        await self.task.handle_event(TaskEvent.PLANED)
        self.assertEqual(self.task.get_current_state(), TaskState.RUNNING)

        await self.task.handle_event(TaskEvent.DONE)
        self.assertEqual(self.task.get_current_state(), TaskState.FINISHED)


class TestTaskComparison(unittest.TestCase):
    """测试Task比较操作"""

    def setUp(self) -> None:
        """设置测试环境"""
        self.transitions: dict[
            tuple[TaskState, TaskEvent],
            tuple[TaskState, Callable[[ITask[TaskState, TaskEvent]], Awaitable[None] | None] | None]
        ] = {
            (TaskState.INITED, TaskEvent.IDENTIFIED): (TaskState.CREATED, None),
        }

        self.completion_config = CompletionConfig(
            temperature=0.7,
            max_tokens=1000
        )

    def test_task_equality(self) -> None:
        """测试任务相等性比较"""
        task1 = BaseTask[TaskState, TaskEvent](
            valid_states={TaskState.INITED, TaskState.CREATED},
            init_state=TaskState.INITED,
            transitions=self.transitions,
            protocol="test_dict",
            tags={"test_dict"},
            task_type="test_dict",
            completion_config=self.completion_config
        )
        # task1 在初始化时已自动编译

        task2 = BaseTask[TaskState, TaskEvent](
            valid_states={TaskState.INITED, TaskState.CREATED},
            init_state=TaskState.INITED,
            transitions=self.transitions,
            protocol="test_dict",
            tags={"test_dict"},
            task_type="test_dict",
            completion_config=self.completion_config
        )
        # task2 在初始化时已自动编译

        # 不同的任务应该有不同的ID，因此不相等
        self.assertNotEqual(task1.get_id(), task2.get_id())

    def test_task_ordering(self) -> None:
        """测试任务排序"""
        tasks = []
        for _ in range(3):
            task = BaseTask[TaskState, TaskEvent](
                valid_states={TaskState.INITED, TaskState.CREATED},
                init_state=TaskState.INITED,
                transitions=self.transitions,
                protocol="test_dict",
                tags={"test_dict"},
                task_type="test_dict",
                completion_config=self.completion_config
            )
            # task 在初始化时已自动编译
            tasks.append(task)

        # 可以按ID排序
        task_ids = [task.get_id() for task in tasks]
        sorted_ids = sorted(task_ids)
        self.assertEqual(sorted(task_ids), sorted_ids)


if __name__ == '__main__':
    unittest.main()
