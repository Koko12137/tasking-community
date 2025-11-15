from abc import abstractmethod, ABC
from uuid import uuid4
from threading import Lock

from loguru import logger

from src.model import CompletionUsage


class IStepCounter(ABC):
    """步骤计数器的协议。限制可以是最大自动步骤或最大余额成本。最好为所有Agent使用相同的步骤计数器。
    """
    
    @abstractmethod
    def get_uid(self) -> str:
        """获取步骤计数器的唯一标识符
        
        返回:
            str: 步骤计数器的唯一标识符
        """
        pass
    
    @abstractmethod
    def get_limit(self) -> int:
        """获取步骤计数器的限制
        
        返回:
            int: 步骤计数器的限制
        """
        pass
    
    @abstractmethod
    async def update_limit(self, limit: int | float) -> None:
        """更新步骤计数器的限制
        
        参数:
            limit (Union[int, float]):
                步骤计数器的限制
        """
        pass
    
    @abstractmethod
    async def check_limit(self) -> bool:
        """检查步骤计数器的限制是否已达到
        
        返回:
            bool:
                步骤计数器的限制是否已达到
        
        异常:
            MaxStepsError:
                步骤计数器引发的最大步骤错误
        """
        pass
    
    @abstractmethod
    async def step(self, step: CompletionUsage) -> None:
        """增加步骤计数器的当前步骤
        
        参数:
            step (CompletionUsage):
                要增加的步骤
        
        返回:
            None 
        
        异常:
            MaxStepsError:
                步骤计数器引发的最大步骤错误
        """
        pass
    
    @abstractmethod
    async def recharge(self, limit: int | float) -> None:
        """为步骤计数器充值限制
        
        参数:
            limit (Union[int, float]):
                步骤计数器的限制
        """
        pass

    @abstractmethod
    async def reset(self) -> None:
        """重置步骤计数器的当前步骤
        
        返回:
            None
        """
        pass


class MaxStepsError(Exception):
    """MaxStepsError is the error raised when the max steps is reached.
    
    Attributes:
        current (int):
            The current step of the step counter.
        limit (int):
            The limit of the step counter.
    """
    current: int
    limit: int
    
    def __init__(self, current: int, limit: int) -> None:
        """Initialize the MaxStepsError.
        
        Args:
            current (int):
                The current step of the step counter.
            limit (int):
                The limit of the step counter.
        """
        self.current = current
        self.limit = limit
        
    def __str__(self) -> str:
        """Return the string representation of the MaxStepsError.
        
        Returns:
            str:
                The string representation of the MaxStepsError.
        """
        return f"Max auto steps reached. Current: {self.current}, Limit: {self.limit}"


class MaxStepCounter(IStepCounter):
    """MaxStepCounter allows the user to set the limit of the step counter, and the limit will **never** be reset. 
    
    Attributes:
        limit (int):
            The limit of the step counter. 
        current (int):
            The current step of the step counter. 
    """
    uid: str
    limit: int
    current: int
    lock: Lock
    
    def __init__(self, limit: int = 10) -> None:
        """Initialize the step counter.
        
        Args:
            limit (int, optional, defaults to 10):
                The limit of the step counter. 
        """
        self.uid = uuid4().hex
        self.limit = limit
        self.current = 0
        self.lock = Lock()
        
    async def check_limit(self) -> bool:
        """Check if the limit of the step counter is reached.
        
        Returns:
            bool:
                Whether the limit of the step counter is reached.
                
        Raises:
            MaxStepsError:
                The max steps error raised by the step counter. 
        """
        if self.current >= self.limit:
            e = MaxStepsError(self.current, self.limit)
            logger.error(e)
            raise e
        return False
        
    async def step(self, step: CompletionUsage) -> None:
        """Increment the current step of the step counter.
        
        Args:
            step (CompletionUsage):
                The step to increment. 
                
        Returns:
            None 
        
        Raises:
            MaxStepsError:
                The max steps error raised by the step counter. 
        """
        with self.lock:
            self.current += 1
            
        # Check if the current step is greater than the max auto steps
        if await self.check_limit():
            e = MaxStepsError(self.current, self.limit)
            # The max steps error is raised, then update the task status to cancelled
            logger.error(e)
            raise e
        
    async def reset(self) -> None:
        """Reset the current step of the step counter.
        
        Returns:
            None
        """
        raise NotImplementedError("Reset is not supported for the max step counter.")

    async def update_limit(self, limit: int | float) -> None:
        """Update the limit of the step counter.
        
        Args:
            limit (Union[int, float]):
                The limit of the step counter. 
        """
        raise NotImplementedError("Update limit is not supported for the max step counter.")

    async def recharge(self, limit: int | float) -> None:
        """Recharge the limit of the step counter.
        
        Args:
            limit (Union[int, float]):
                The limit of the step counter. 
        """
        raise NotImplementedError("Recharge is not supported for the max step counter.")


class BaseStepCounter(MaxStepCounter):
    """BaseStepCounter count only the action steps, without any concern of the token usage. The step counter could be 
    reset by the user. 
    
    Attributes:
        uid (str):
            The unique identifier of the step counter. 
        limit (int):
            The limit of the step counter. 
        current (int):
            The current step of the step counter. 
    """
    uid: str
    limit: int
    current: int
    
    def __init__(self, limit: int = 10) -> None:
        """Initialize the step counter.
        
        Args:
            limit (int, optional, defaults to 10):
                The limit of the step counter. 
        """
        super().__init__(limit)
        
    async def step(self, step: CompletionUsage) -> None:
        """Increment the current step of the step counter.
        
        Args:
            step (CompletionUsage):
                The step to increment. 
                
        Returns:
            None 
        
        Raises:
            MaxStepsError:
                The max steps error raised by the step counter. 
        """
        with self.lock:
            self.current += 1
            # Log the current step
            logger.warning(f"The current step is {self.current}, the limit is {self.limit}.")
            
        # Check if the current step is greater than the max auto steps
        if await self.check_limit():
            # Request the user to reset the step counter
            reset = input(f"The limit of auto steps is reached. Do you want to reset the step counter with limit {self.limit} steps? (y/n)")
            
            if reset == "y":
                # Reset the step counter and continue the loop
                await self.reset()
            else:
                e = MaxStepsError(self.current, self.limit)
                # The max steps error is raised, then update the task status to cancelled
                logger.error(e)
                raise e
        
    async def reset(self) -> None:
        """Reset the current step of the step counter.
        
        Returns:
            None
        """
        with self.lock:
            self.current = 0

    async def update_limit(self, limit: int | float) -> None:
        """Update the limit of the step counter.
        
        Args:
            limit (int):
                The limit of the step counter. 
        """
        with self.lock:
            self.limit = int(limit)

    async def recharge(self, limit: int | float) -> None:
        """Recharge the limit of the step counter.
        
        Args:
            limit (Union[int, float]):
                The limit of the step counter. 
        """
        with self.lock:
            self.limit += int(limit)


class TokenStepCounter(BaseStepCounter):
    """TokenStepCounter counts the token usage of the LLM. The step counter will ask for reset when the token usage is greater than the limit. 
    
    Attributes:
        uid (str):
            The unique identifier of the step counter. 
        limit (int):
            The limit of the step counter. 
        current (int):
            The current step of the step counter. 
    """
    uid: str
    limit: int
    current: int
    
    def __init__(self, limit: int = 10000) -> None:
        """Initialize the step counter.
        
        Args:
            limit (int, optional, defaults to 10000):
                The limit of the step counter. Default to 10 thousand. 
        """
        super().__init__(limit)
    
    async def step(self, step: CompletionUsage) -> None:
        """Increment the current step of the step counter.
        
        Args:
            step (CompletionUsage):
                The step to increment. 
        """
        with self.lock:
            self.current += step.total_tokens
            logger.warning(f"The current Token Usage is {self.current}, the Limit is {self.limit}.")
            
        # Check if the current step is greater than the max auto steps
        if await self.check_limit():
            # Request the user to reset the step counter
            reset = input(f"The limit of auto steps is reached. Do you want to reset the step counter with limit {self.limit} steps? (y/n)")
            
            if reset == "y":
                # Reset the step counter and continue the loop  
                await self.reset()
            else:
                e = MaxStepsError(self.current, self.limit)
                # The max steps error is raised, then update the task status to cancelled
                logger.error(e)
                raise e
            
    async def reset(self) -> None:
        """Reset is not supported for the token step counter.
        """
        raise NotImplementedError("Reset is not supported for the token step counter. Please use `recharge` to update the limit.")
