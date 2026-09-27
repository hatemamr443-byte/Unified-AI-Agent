from enum import Enum

from .models import RiskLevel, Task


class Decision(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


class PolicyEngine:
    def evaluate(self, task: Task, requires_confirmation: bool = False) -> Decision:
        if task.risk_level == RiskLevel.HIGH:
            return Decision.CONFIRM
        if requires_confirmation:
            return Decision.CONFIRM
        return Decision.ALLOW
