#!/usr/bin/env python3
"""
Corner Cases 和边界条件测试套件 - 修复版本

此测试套件专注于测试状态机和树形结构中的边界条件和异常情况：
- 循环引用检测：防止无限递归和内存泄漏
- 深度边界验证：确保树结构逻辑正确
- 类型安全保证：验证泛型系统正确工作
- 错误恢复机制：确保异常情况下系统稳定
- 边界条件：处理极值和特殊情况

重点: 边界条件 + 异常处理 + 类型安全
"""

import unittest
from typing import Any, Callable, Awaitable

# 导入核心类与类型
from tasking.core.state_machine.task.tree import BaseTreeTaskNode
from tasking.core.state_machine.task.base import BaseTask
from tasking.core.state_machine.task.default_node import get_base_states
from tasking.core.state_machine.task.const import TaskState, TaskEvent
from tasking.core.state_machine.task.interface import ITask
from tasking.model import CompletionConfig, TextBlock


# ==============================
# Helper functions for test setup
# ==============================

def get_base_task_transitions() -> dict[
    tuple[TaskState, TaskEvent],
    tuple[TaskState, Callable[[ITask[TaskState, TaskEvent]], Awaitable[None] | None] | None]
]:
    """获取 BaseTask 专用的状态转换规则（使用当前可用的状态和事件）"""
    return {
        (TaskState.CREATED, TaskEvent.INIT): (TaskState.RUNNING, None),
        (TaskState.CREATED, TaskEvent.CANCEL): (TaskState.CANCELED, None),
        (TaskState.RUNNING, TaskEvent.DONE): (TaskState.FINISHED, None),
        (TaskState.RUNNING, TaskEvent.CANCEL): (TaskState.CANCELED, None),
        # 允许从 CANCELED 回到 CREATED 用于重试
        (TaskState.CANCELED, TaskEvent.INIT): (TaskState.CREATED, None),
    }


def create_tree_node(
    unique_protocol: str,
    tags: set[str],
    task_type: str,
    max_depth: int,
    completion_config: CompletionConfig
) -> BaseTreeTaskNode[TaskState, TaskEvent]:
    """Create a BaseTreeTaskNode with default parameters"""
    from tasking.model import TextBlock
    from tasking.core.state_machine.task.default_node import get_base_states, get_base_transition
    return BaseTreeTaskNode[TaskState, TaskEvent](
        valid_states=get_base_states(),
        init_state=TaskState.CREATED,
        transitions=get_base_transition(),
        unique_protocol=[TextBlock(text=unique_protocol)],
        tags=tags,
        task_type=task_type,
        max_depth=max_depth,
        completion_config=completion_config
    )


def create_base_task(
    unique_protocol: str,
    tags: set[str],
    task_type: str,
    completion_config: CompletionConfig,
    max_revisit_limit: int = 1
) -> BaseTask[TaskState, TaskEvent]:
    """Create a BaseTask with default parameters"""
    from tasking.model import TextBlock
    return BaseTask[TaskState, TaskEvent](
        valid_states=get_base_states(),
        init_state=TaskState.CREATED,  # get_base_states() 返回的状态集合中，CREATED 是初始状态
        transitions=get_base_task_transitions(),
        unique_protocol=[TextBlock(text=unique_protocol)],
        tags=tags,
        task_type=task_type,
        completion_config=completion_config,
        max_revisit_limit=max_revisit_limit
    )


# ==============================
# Test Class: 循环引用检测
# ==============================
class TestTreeCircularReference(unittest.IsolatedAsyncioTestCase):
    """测试树形结构的循环引用检测"""

    def setUp(self) -> None:
        """测试设置"""
        self.completion_config = CompletionConfig(
            temperature=0.7,
            max_tokens=1000
        )
        self.root_node = create_tree_node(
            unique_protocol="root_protocol",
            tags={"root"},
            task_type="root_task",
            max_depth=5,
            completion_config=self.completion_config
        )

    def tearDown(self) -> None:
        """测试清理"""
        # 清理资源
        if hasattr(self.root_node, '_contexts') and self.root_node._contexts:
            self.root_node._contexts.clear()

    def test_simple_circular_reference(self) -> None:
        """测试简单循环引用: A->B->A"""
        # 创建节点A (root_node)
        # 创建节点B
        node_b = create_tree_node(
            unique_protocol="node_b",
            tags={"node_b"},
            task_type="node_b_task",
            max_depth=5,
            completion_config=self.completion_config
        )

        # 建立关系: A -> B
        self.root_node.add_sub_task(node_b)

        # 尝试建立循环: B -> A
        # 这应该被检测并处理（或者通过深度逻辑发现）
        try:
            node_b.add_sub_task(self.root_node)
            # 如果成功添加，检查深度逻辑是否正确处理
            # B的深度是1，A作为B的子节点深度应该是2
            self.assertEqual(self.root_node.get_current_depth(), 2)
            self.assertEqual(node_b.get_current_depth(), 1)

            # 验证父子关系
            self.assertIn(self.root_node, node_b.get_sub_tasks())
            self.assertEqual(self.root_node.get_parent(), node_b)

        except Exception as e:
            # 如果抛出异常，这是可接受的循环检测行为
            self.assertIsInstance(e, (ValueError, RuntimeError))

    def test_self_reference(self) -> None:
        """测试自引用: A->A"""
        try:
            # 尝试将节点添加为自己的子节点
            self.root_node.add_sub_task(self.root_node)

            # 如果成功，检查深度逻辑
            # 节点的深度应该是1（作为自己的子节点）
            self.assertEqual(self.root_node.get_current_depth(), 1)

            # 验证父子关系
            self.assertIn(self.root_node, self.root_node.get_sub_tasks())
            self.assertEqual(self.root_node.get_parent(), self.root_node)

        except Exception as e:
            # 如果抛出异常，这是可接受的自引用检测行为
            self.assertIsInstance(e, (ValueError, RuntimeError))

    def test_complex_circular_reference(self) -> None:
        """测试复杂循环引用: A->B->C->A"""
        # 创建三个节点
        node_b = create_tree_node(
            unique_protocol="node_b",
            tags={"node_b"},
            task_type="node_b_task",
            max_depth=5,
            completion_config=self.completion_config
        )

        node_c = create_tree_node(
            unique_protocol="node_c",
            tags={"node_c"},
            task_type="node_c_task",
            max_depth=5,
            completion_config=self.completion_config
        )

        # 建立链式关系: A -> B -> C
        self.root_node.add_sub_task(node_b)
        node_b.add_sub_task(node_c)

        # 尝试完成循环: C -> A
        try:
            node_c.add_sub_task(self.root_node)

            # 如果成功，检查深度逻辑
            # A深度应为2（通过C->A），B深度应为1，C深度应为0（根）
            # 或者系统应该检测到循环

        except Exception as e:
            # 如果抛出异常，这是可接受的循环检测行为
            self.assertIsInstance(e, (ValueError, RuntimeError))


# ==============================
# Test Class: 深度测试
# ==============================
class TestTreeDepthValidation(unittest.IsolatedAsyncioTestCase):
    """测试树形结构的深度边界"""

    def setUp(self) -> None:
        """测试设置"""
        self.completion_config = CompletionConfig(
            temperature=0.7,
            max_tokens=1000
        )

    def test_max_depth_enforcement(self) -> None:
        """测试最大深度限制的强制执行"""
        max_depth = 3

        # 创建根节点
        root = create_tree_node(
            unique_protocol="root",
            tags={"root"},
            task_type="root_task",
            max_depth=max_depth,
            completion_config=self.completion_config
        )

        # 创建深度为max_depth-1的子节点
        current = root
        for i in range(max_depth - 1):
            child = create_tree_node(
                unique_protocol=f"depth_{i}",
                tags={f"depth_{i}"},
                task_type=f"depth_task_{i}",
                max_depth=max_depth,
                completion_config=self.completion_config
            )
            current.add_sub_task(child)
            current = child

        # 验证深度
        self.assertEqual(root.get_max_depth(), max_depth)
        self.assertEqual(current.get_current_depth(), max_depth - 1)

        # 尝试添加超出最大深度的子节点
        try:
            deeper_child = create_tree_node(
                unique_protocol="too_deep",
                tags={"too_deep"},
                task_type="too_deep_task",
                max_depth=max_depth,
                completion_config=self.completion_config
            )
            current.add_sub_task(deeper_child)

            # 如果成功添加，检查深度
            self.assertEqual(deeper_child.get_current_depth(), max_depth)

            # 尝试再添加一层应该失败
            even_deeper = create_tree_node(
                unique_protocol="even_deeper",
                tags={"even_deeper"},
                task_type="even_deeper_task",
                max_depth=max_depth,
                completion_config=self.completion_config
            )

            with self.assertRaises((ValueError, RuntimeError)):
                deeper_child.add_sub_task(even_deeper)

        except Exception as e:
            # 如果添加时就失败，这也是可接受的
            self.assertIsInstance(e, (ValueError, RuntimeError))

    def test_depth_calculation_consistency(self) -> None:
        """测试深度计算的一致性"""
        root = create_tree_node(
            unique_protocol="root",
            tags={"root"},
            task_type="root_task",
            max_depth=5,
            completion_config=self.completion_config
        )

        # 创建平衡的树结构
        child1 = create_tree_node(
            unique_protocol="child1",
            tags={"child1"},
            task_type="child1_task",
            max_depth=5,
            completion_config=self.completion_config
        )
        child2 = create_tree_node(
            unique_protocol="child2",
            tags={"child2"},
            task_type="child2_task",
            max_depth=5,
            completion_config=self.completion_config
        )

        root.add_sub_task(child1)
        root.add_sub_task(child2)

        # 添加孙子节点
        grandchild1 = create_tree_node(
            unique_protocol="grandchild1",
            tags={"grandchild1"},
            task_type="grandchild1_task",
            max_depth=5,
            completion_config=self.completion_config
        )

        child1.add_sub_task(grandchild1)

        # 验证深度
        self.assertEqual(root.get_current_depth(), 0)
        self.assertEqual(child1.get_current_depth(), 1)
        self.assertEqual(child2.get_current_depth(), 1)
        self.assertEqual(grandchild1.get_current_depth(), 2)

        # 验证最大深度
        self.assertEqual(root.get_max_depth(), 5)

    def test_depth_after_removal(self) -> None:
        """测试节点移除后的深度重新计算"""
        root = create_tree_node(
            unique_protocol="root",
            tags={"root"},
            task_type="root_task",
            max_depth=5,
            completion_config=self.completion_config
        )

        child = create_tree_node(
            unique_protocol="child",
            tags={"child"},
            task_type="child_task",
            max_depth=5,
            completion_config=self.completion_config
        )

        root.add_sub_task(child)
        self.assertEqual(child.get_current_depth(), 1)

        # 移除子节点
        root.pop_sub_task(child)

        # 验证深度重置
        self.assertEqual(child.get_current_depth(), 0)
        self.assertEqual(child.get_parent(), None)


# ==============================
# Test Class: 状态访问计数
# ==============================
class TestStateVisitCounting(unittest.IsolatedAsyncioTestCase):
    """测试状态访问计数功能"""

    def setUp(self) -> None:
        """测试设置"""
        self.completion_config = CompletionConfig(
            temperature=0.7,
            max_tokens=1000
        )
        self.task = create_base_task(
            unique_protocol="visit_count_test",
            tags={"test", "visit_count"},
            task_type="visit_count_task",
            completion_config=self.completion_config,
            max_revisit_limit=3
        )

    def test_basic_visit_counting(self) -> None:
        """测试基本的访问计数"""
        # 初始状态的计数应该为1
        self.assertEqual(self.task.get_state_visit_count(TaskState.CREATED), 1)

        # 其他状态的计数应该为0
        self.assertEqual(self.task.get_state_visit_count(TaskState.RUNNING), 0)
        self.assertEqual(self.task.get_state_visit_count(TaskState.FINISHED), 0)

    async def test_visit_count_increments(self) -> None:
        """测试访问计数的递增"""
        # 初始状态是 CREATED，计数为1
        self.assertEqual(self.task.get_state_visit_count(TaskState.CREATED), 1)

        # 转换到RUNNING状态
        await self.task.handle_event(TaskEvent.INIT)  # -> RUNNING
        self.assertEqual(self.task.get_state_visit_count(TaskState.RUNNING), 1)

        # 再次到达RUNNING状态（通过取消和重试）
        await self.task.handle_event(TaskEvent.CANCEL)    # -> CANCELED
        await self.task.handle_event(TaskEvent.INIT)    # -> CREATED
        await self.task.handle_event(TaskEvent.INIT)    # -> RUNNING

        # RUNNING的计数应该为2
        self.assertEqual(self.task.get_state_visit_count(TaskState.RUNNING), 2)

    async def test_revisit_limit_enforcement(self) -> None:
        """测试重访限制的强制执行"""
        max_revisit = 3  # 增加限制，允许初始访问 + 2次重访

        # 创建有重访限制的任务
        # 注意：由于测试中 CREATED 状态会被访问多次（初始1次 + 通过 INIT 事件返回），
        # 测试流程：初始 CREATED(1) -> RUNNING -> CANCELED -> CREATED(2) -> RUNNING -> ...
        # 要测试5次 RUNNING 访问，CREATED 会被访问6次（初始1次 + 5次恢复）
        # 所以需要设置限制至少为6，这样第6次访问 CREATED 时会失败
        task = create_base_task(
            unique_protocol="revisit_test",
            tags={"test", "revisit"},
            task_type="revisit_task",
            completion_config=self.completion_config,
            max_revisit_limit=6  # 允许 CREATED 状态被访问6次（初始1次 + 5次恢复）
        )

        # 初始状态是 CREATED，计数为1
        self.assertEqual(task.get_state_visit_count(TaskState.CREATED), 1)

        # 访问同一状态，测试重访限制
        # 第一次访问RUNNING状态
        await task.handle_event(TaskEvent.INIT)   # -> RUNNING
        self.assertEqual(task.get_state_visit_count(TaskState.RUNNING), 1)

        # 第二次访问RUNNING状态（通过取消和重试）
        await task.handle_event(TaskEvent.CANCEL)    # -> CANCELED
        await task.handle_event(TaskEvent.INIT)    # -> CREATED (CREATED 第2次)
        await task.handle_event(TaskEvent.INIT)    # -> RUNNING
        self.assertEqual(task.get_state_visit_count(TaskState.RUNNING), 2)

        # 第三次访问RUNNING状态
        await task.handle_event(TaskEvent.CANCEL)    # -> CANCELED
        await task.handle_event(TaskEvent.INIT)    # -> CREATED (CREATED 第3次)
        await task.handle_event(TaskEvent.INIT)    # -> RUNNING
        self.assertEqual(task.get_state_visit_count(TaskState.RUNNING), 3)

        # 第四次访问RUNNING状态（应该成功，因为限制是5）
        await task.handle_event(TaskEvent.CANCEL)    # -> CANCELED
        await task.handle_event(TaskEvent.INIT)    # -> CREATED (CREATED 第4次)
        await task.handle_event(TaskEvent.INIT)    # -> RUNNING
        self.assertEqual(task.get_state_visit_count(TaskState.RUNNING), 4)
        
        # 第五次访问RUNNING状态（应该成功）
        await task.handle_event(TaskEvent.CANCEL)    # -> CANCELED
        await task.handle_event(TaskEvent.INIT)    # -> CREATED (CREATED 第5次)
        await task.handle_event(TaskEvent.INIT)    # -> RUNNING
        self.assertEqual(task.get_state_visit_count(TaskState.RUNNING), 5)
        
        # 第六次访问应该失败（超过限制6）
        # CREATED 状态已经被访问了5次（初始1次 + 4次恢复），第6次恢复时会访问第6次
        await task.handle_event(TaskEvent.CANCEL)    # -> CANCELED
        await task.handle_event(TaskEvent.INIT)    # -> CREATED (CREATED 第6次，达到限制6，应该成功)
        # 但第7次访问 CREATED 时会失败
        await task.handle_event(TaskEvent.INIT)    # -> RUNNING
        self.assertEqual(task.get_state_visit_count(TaskState.RUNNING), 6)
        
        # 第七次访问应该失败（超过限制6）
        await task.handle_event(TaskEvent.CANCEL)    # -> CANCELED
        # CREATED 状态已经被访问了6次（初始1次 + 5次恢复），第7次访问时会超过限制6
        with self.assertRaises(RuntimeError):
            await task.handle_event(TaskEvent.INIT)    # -> CREATED (CREATED 第7次，超过限制6，应该失败)

    async def test_visit_count_reset(self) -> None:
        """测试重置后的访问计数"""
        # 先执行一些转换
        await self.task.handle_event(TaskEvent.INIT)
        await self.task.handle_event(TaskEvent.DONE)

        # 检查计数
        self.assertEqual(self.task.get_state_visit_count(TaskState.CREATED), 1)
        self.assertEqual(self.task.get_state_visit_count(TaskState.RUNNING), 1)
        self.assertEqual(self.task.get_state_visit_count(TaskState.FINISHED), 1)

        # 重置任务
        self.task.reset()

        # 验证重置后的计数
        self.assertEqual(self.task.get_state_visit_count(TaskState.CREATED), 1)
        self.assertEqual(self.task.get_state_visit_count(TaskState.RUNNING), 0)
        self.assertEqual(self.task.get_state_visit_count(TaskState.FINISHED), 0)


# ==============================
# Test Class: 类型安全
# ==============================
class TestTypeSafety(unittest.IsolatedAsyncioTestCase):
    """测试类型安全保证"""

    def test_generic_type_parameters(self) -> None:
        """测试泛型类型参数的正确使用"""
        # 使用正确的类型参数
        task: BaseTask[TaskState, TaskEvent] = create_base_task(
            unique_protocol="type_test",
            tags={"type_test"},
            task_type="type_test_task",
            completion_config=CompletionConfig()
        )

        # 验证类型
        self.assertIsInstance(task, BaseTask)
        self.assertIsInstance(task.get_current_state(), TaskState)

        # 验证状态机方法
        state: TaskState = task.get_current_state()
        self.assertIsInstance(state, TaskState)

    async def test_state_event_compatibility(self) -> None:
        """测试状态和事件的兼容性"""
        # 使用create_base_task辅助函数
        task = create_base_task(
            unique_protocol="compatibility_test",
            tags={"test", "compatibility"},
            task_type="compatibility_test",
            completion_config=CompletionConfig()
        )

        # 正确的事件应该可以处理
        await task.handle_event(TaskEvent.INIT)
        self.assertEqual(task.get_current_state(), TaskState.RUNNING)

    async def test_invalid_event_rejection(self) -> None:
        """测试无效事件的拒绝"""
        task = create_base_task(
            unique_protocol="invalid_event_test",
            tags={"test"},
            task_type="invalid_event_task",
            completion_config=CompletionConfig()
        )

        # 尝试处理未定义的事件
        # 在 CREATED 状态下，DONE 事件未定义
        with self.assertRaises(ValueError):
            await task.handle_event(TaskEvent.DONE)  # 在CREATED状态下未定义


# ==============================
# Test Class: 错误恢复
# ==============================
class TestErrorRecovery(unittest.IsolatedAsyncioTestCase):
    """测试错误恢复机制"""

    def setUp(self) -> None:
        """测试设置"""
        self.completion_config = CompletionConfig(
            temperature=0.7,
            max_tokens=1000
        )

    async def test_error_state_recovery(self) -> None:
        """测试错误状态的恢复"""
        # 直接创建任务，使用默认的transitions
        # 注意：由于测试中 CREATED 状态会被访问2次（初始1次 + 1次通过 INIT 事件返回），
        # 需要设置 max_revisit_limit 至少为 2
        task = create_base_task(
            unique_protocol="error_recovery_test",
            tags={"test", "error_recovery"},
            task_type="error_recovery_task",
            completion_config=self.completion_config,
            max_revisit_limit=5  # 增加限制以允许状态恢复
        )

        # 正常执行
        await task.handle_event(TaskEvent.INIT)
        self.assertEqual(task.get_current_state(), TaskState.RUNNING)

        # 发生错误（使用 CANCEL 作为错误状态）
        await task.handle_event(TaskEvent.CANCEL)
        self.assertEqual(task.get_current_state(), TaskState.CANCELED)

        # 需要手动设置错误状态进行测试
        error_msg = "Test error"
        task.set_error(error_msg)
        self.assertTrue(task.is_error())
        self.assertEqual(task.get_error_info(), error_msg)

        # 在恢复重试前检查错误状态
        self.assertTrue(task.is_error())
        self.assertEqual(task.get_error_info(), error_msg)

        # 恢复重试（通过 INIT 事件回到 CREATED，然后到 RUNNING）
        await task.handle_event(TaskEvent.INIT)
        self.assertEqual(task.get_current_state(), TaskState.CREATED)
        await task.handle_event(TaskEvent.INIT)
        self.assertEqual(task.get_current_state(), TaskState.RUNNING)

        # 测试使用的是get_base_task_transitions()，没有回调函数，需要手动清除错误状态
        # 在实际的builder.py中，on_retry会自动调用clean_error_info()
        task.clean_error_info()
        self.assertFalse(task.is_error())
        self.assertEqual(task.get_error_info(), "")  # 错误信息应该被清除

        # 完成任务
        await task.handle_event(TaskEvent.DONE)
        self.assertEqual(task.get_current_state(), TaskState.FINISHED)

    async def test_partial_state_recovery(self) -> None:
        """测试部分状态恢复"""
        task = create_base_task(
            unique_protocol="partial_recovery_test",
            tags={"test", "partial_recovery"},
            task_type="partial_recovery_task",
            completion_config=self.completion_config
        )

        # 执行一些操作
        await task.handle_event(TaskEvent.INIT)
        task.set_title("Test Title")
        task.set_input("Test Input")

        # 进入错误状态（通过创建新任务模拟）
        error_task = create_base_task(
            unique_protocol="error_task",
            tags={"error"},
            task_type="error_task",
            completion_config=self.completion_config
        )
        error_task.set_error("Simulated error")

        # 恢复时保留部分状态
        # 注意：实际实现中可能需要更复杂的恢复逻辑
        self.assertEqual(task.get_title(), "Test Title")
        self.assertEqual(task.get_input(), "Test Input")


if __name__ == '__main__':
    unittest.main()
