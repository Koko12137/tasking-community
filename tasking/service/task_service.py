import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Generic, override

from json_repair import repair_json

from ..core.state_machine import StateT, EventT
from ..core.state_machine.task import ITask, ITreeTaskNode
from ..core.scheduler import IScheduler
from ..model.queue import AsyncQueue
from ..model.message import Message


class ITaskService(ABC, Generic[StateT, EventT]):
    """Interface for task management services, providing methods to create, list, retrieve,
    pause, resume, and cancel tasks, as well as access to the task scheduler.

    Recommended for the following usages:
    - Creating new tasks and managing their input/output protocol, task tags and lifecycle.
    - Managing task output post-processing and tree task context engineering.
    - Scheduling and executing tasks and processing the human interference when needed.
    """

    @abstractmethod
    def create_task(self, context: dict[str, Any], task_type: str, task_title: str, task_input: str) -> str:
        """Create a new task with the provided data.

        Args:
            context: The context of the request. Includes user info and other metadata.
            task_type: The type of the task to be created.
            task_title: The title of the task to be created.
            task_input: The input data for the task.
            parent: Optional; The ID of the parent task, if any.
            
        Returns:
            task_id:
                The ID of the created task.
        """
        pass

    @abstractmethod
    def list_tasks(self, context: dict[str, Any]) -> list[ITask[StateT, EventT]]:
        """List all tasks, optionally filtered by certain parameters.

        Args:
            context: The context of the request. Includes user info and other metadata.

        Returns:
            list:
                A list of tasks.
        """
        pass

    @abstractmethod
    def get_task(self, context: dict[str, Any], task_id: str) -> ITask[StateT, EventT]:
        """Retrieve a task by its ID.

        Args:
            context: The context of the request. Includes user info and other metadata.
            task_id: The ID of the task to be retrieved.

        Returns:
            task:
                The retrieved task.
                
        Raises:
            ValueError: If the task with the given ID does not exist.
        """
        pass

    @abstractmethod
    async def pause_task(self, context: dict[str, Any], task_id: str) -> None:
        """Pause a task by its ID.

        Args:
            context: The context of the request. Includes user info and other metadata.
            task_id: The ID of the task to be paused.
        """
        pass

    @abstractmethod
    async def resume_task(self, context: dict[str, Any], task_id: str) -> None:
        """Resume a task by its ID.

        Args:
            context: The context of the request. Includes user info and other metadata.
            task_id: The ID of the task to be resumed.
        """
        pass

    @abstractmethod
    async def cancel_task(self, context: dict[str, Any], task_id: str) -> None:
        """Cancel a task by its ID.
        
        Args:
            context: The context of the request. Includes user info and other metadata.
            task_id: The ID of the task to be canceled.
        """
        pass

    @abstractmethod
    def get_scheduler(self) -> IScheduler[StateT, EventT]:
        """Retrieve the task scheduler instance.
        
        Returns:
            scheduler:
                The task scheduler instance.
        """
        pass
    
    @abstractmethod
    async def run_task(self, context: dict[str, Any], task_id: str) -> None:
        """Run the task processing loop for a specific task.

        Args:
            context: The context of the request. Includes user info and other metadata.
            task_id: The ID of the task to be processed.
        """
        pass
    
    
class ITreeTaskService(ITaskService[StateT, EventT], ABC):
    
    @override
    @abstractmethod
    def create_task(self, context: dict[str, Any], task_type: str, task_title: str, task_input: str, parent: str | None = None) -> str:
        """Create a new task with the provided data, optionally specifying a parent task.

        Args:
            context: The context of the request. Includes user info and other metadata.
            task_type: The type of the task to be created.
            task_title: The title of the task to be created.
            task_input: The input data for the task.
            parent: Optional; The ID of the parent task, if any.
            
        Returns:
            task_id:
                The ID of the created task.
        """
        pass
    
    @abstractmethod
    def create_tasks_from_json(self, context: dict[str, Any], json_str: str, parent: str | None = None) -> list[str]:
        """Create multiple tasks in a batch operation.

        Args:
            context: The context of the request. Includes user info and other metadata.
            json_str: A JSON string representing a list of tasks to be created.
            parent: Optional; The ID of the parent task for all created tasks, if any.
            
        Returns:
            task_ids:
                A list of IDs of the created tasks.
                
        Raises:
            ValueError: If any task definition is invalid.
        """
        pass
    
    @override
    @abstractmethod
    def get_task(self, context: dict[str, Any], task_id: str) -> ITreeTaskNode[StateT, EventT]:
        """Retrieve a tree task node by its ID.

        Args:
            context: The context of the request. Includes user info and other metadata.
            task_id: The ID of the task to be retrieved.

        Returns:
            task:
                The retrieved tree task node.
                
        Raises:
            ValueError: If the task with the given ID does not exist.
        """
        pass


class BaseTaskService(ITaskService[StateT, EventT]):
    _scheduler: IScheduler[StateT, EventT]
    _tasks: dict[str, ITask[StateT, EventT]]
    _valid_task_types: set[type[ITask[StateT, EventT]]]
    _task_creators: dict[str, Callable[[str, str], ITask[StateT, EventT]]]
    _pause_events: dict[str, asyncio.Event]
    _cancel_events: dict[str, asyncio.Event]

    def __init__(
        self, 
        scheduler: IScheduler[StateT, EventT],
        valid_task_types: set[type[ITask[StateT, EventT]]],
        task_creators: dict[str, Callable[[str, str], ITask[StateT, EventT]]],
    ) -> None:
        self._scheduler = scheduler
        self._tasks = {}
        self._valid_task_types = valid_task_types
        self._task_creators = task_creators
        self._pause_events = {}
        self._cancel_events = {}

    def create_task(self, context: dict[str, Any], task_type: str, task_title: str, task_input: str) -> str:
        if task_type not in self._task_creators:
            raise ValueError(f"Unsupported task type: {task_type}")

        task = self._task_creators[task_type](task_title, task_input)
        # Get the task ID
        task_id = task.get_id()
        # Store the task
        self._tasks[task_id] = task
        #  Create pause and cancel events
        self._pause_events[task_id] = asyncio.Event()
        self._cancel_events[task_id] = asyncio.Event()

        return task_id
    
    def list_tasks(self, context: dict[str, Any]) -> list[ITask[StateT, EventT]]:
        return list(self._tasks.values())
    
    def get_task(self, context: dict[str, Any], task_id: str) -> ITask[StateT, EventT]:
        if task_id not in self._tasks:
            raise ValueError(f"Task with ID {task_id} not found.")
        return self._tasks[task_id]
    
    async def pause_task(self, context: dict[str, Any], task_id: str) -> None:
        if task_id not in self._tasks:
            raise ValueError(f"Task with ID {task_id} not found.")
        
        pause_event = self._pause_events[task_id]
        pause_event.set()
        
    async def resume_task(self, context: dict[str, Any], task_id: str) -> None:
        if task_id not in self._tasks:
            raise ValueError(f"Task with ID {task_id} not found.")
        
        pause_event = self._pause_events[task_id]
        pause_event.clear()
        
    async def cancel_task(self, context: dict[str, Any], task_id: str) -> None:
        if task_id not in self._tasks:
            raise ValueError(f"Task with ID {task_id} not found.")
        
        cancel_event = self._cancel_events[task_id]
        cancel_event.set()

    def get_scheduler(self) -> IScheduler[StateT, EventT]:
        return self._scheduler
    
    async def run_task(self, context: dict[str, Any], task_id: str) -> None:
        if task_id not in self._tasks:
            raise ValueError(f"Task with ID {task_id} not found.")
        
        pause_event = self._pause_events[task_id]
        cancel_event = self._cancel_events[task_id]
                
        # Update the cancel and pause events in the context
        context['pause_event'] = pause_event
        context['cancel_event'] = cancel_event
        
        # Get the scheduler
        scheduler = self.get_scheduler()
        # Get the task
        task = self._tasks[task_id]
        # Create a queue for the task
        queue = AsyncQueue[Message]()
        # Run the task using the scheduler
        await scheduler.schedule(context=context, queue=queue, task=task)


class TreeTaskService(BaseTaskService[StateT, EventT], ITreeTaskService[StateT, EventT]):
    _root_task_type: type[ITreeTaskNode[StateT, EventT]]
    
    def __init__(
        self,
        scheduler: IScheduler[StateT, EventT],
        valid_task_types: set[type[ITask[StateT, EventT]]],
        task_creators: dict[str, Callable[[str, str], ITask[StateT, EventT]]],
        root_task_type: type[ITreeTaskNode[StateT, EventT]],
    ) -> None:
        super().__init__(scheduler, valid_task_types, task_creators)
        self._root_task_type = root_task_type
    
    @override
    def create_task(self, context: dict[str, Any], task_type: str, task_title: str, task_input: str, parent: str | None = None) -> str:
        # Create the task using the base implementation
        task_id = super().create_task(context, task_type, task_title, task_input)
        # Get the new task
        new_task = self.get_task(context, task_id)
        # If a parent is specified, link the task to its parent
        if parent:
            parent_task = self.get_task(context, parent)
            parent_task.add_sub_task(new_task)
            # Set the parent in the new task
            new_task.set_parent(parent_task)

        return task_id
            
    @override
    def get_task(self, context: dict[str, Any], task_id: str) -> ITreeTaskNode[StateT, EventT]:
        task = super().get_task(context, task_id)
        if not isinstance(task, ITreeTaskNode):
            raise ValueError(f"Task with ID {task_id} is not a tree task node.")
        return task
    
    @override
    def create_tasks_from_json(self, context: dict[str, Any], json_str: str, parent: str | None = None) -> list[str]:
        # Repair the JSON string if it's malformed
        repaired_json_str = repair_json(json_str)
        try:
            # Parse the JSON string into a list of task definitions
            sub_tasks_data: dict[str, dict[str, Any]] = json.loads(repaired_json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")

        # Validate if parent is not provided, all tasks must be of root type
        if parent is None:
            for task_def in sub_tasks_data.values():
                task_type = task_def['任务类型']
                if task_type != self._root_task_type.__name__:
                    raise ValueError(f"All tasks must be of root type {self._root_task_type.__name__} when no parent is specified.")

        # List to hold created task IDs
        task_ids: list[str] = []

        # Create tasks based on the definitions
        for title, sub_task_data in sub_tasks_data.items():
            # Normalize the task definition
            sub_task_data = self._normalize_task_definition(sub_task_data)
            # Create each sub-task
            sub_task = self.create_task(
                context,
                sub_task_data["task_type"],
                title,
                sub_task_data["task_input"],
                parent,
            )
            # Append the created task ID to the list
            task_ids.append(sub_task)

        return task_ids

    def _normalize_task_definition(self, task_def: dict[str, Any]) -> dict[str, Any]:
        """Helper method to ensure task definition has required fields and translate them to standard keys.
        
        Args:
            task_def: The task definition dictionary.
        
        Returns:
            normalized_def:
                The normalized task definition with standard keys.
        """
        # Ensure any of '任务类型' / 'task_type' field exists
        if "任务类型" not in task_def and "task_type" not in task_def:
            raise ValueError("Task definition must include '任务类型' or 'task_type' field.")
        
        # Ensure any of '任务输入' / 'task_input' field exists
        if "任务输入" not in task_def and "task_input" not in task_def:
            raise ValueError("Task definition must include '任务输入' or 'task_input' field.")

        # Translate fields to standard keys
        normalized_def = {
            "task_type": task_def.get("任务类型", task_def.get("task_type")),
            "task_input": task_def.get("任务输入", task_def.get("task_input")),
        }
        return normalized_def
