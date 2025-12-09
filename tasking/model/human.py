from pydantic import BaseModel


class HumanResponse(BaseModel):
    """HumanResponse 模型，表示人类用户的响应"""

    message: str
    """人类用户的响应消息内容"""

    def is_approved(self) -> bool:
        """检查人类用户是否批准了响应

        Returns:
            bool: 如果人类用户批准了响应则返回 True，否则返回 False
        """
        approved_keywords = ["yes", "approve", "confirm", "agree", "ok"]
        return any(keyword in self.message.lower() for keyword in approved_keywords)


class HumanInterfere(Exception):
    """HumanInterfere 异常，表示人类用户介入了流程"""

    def __init__(self, message: str = "Human user rejected the request"):
        super().__init__(message)
