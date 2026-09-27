from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Budget:
    max_steps: int = 50
    max_time_seconds: int = 900
    max_tool_calls: int = 100
    max_worker_calls: int = 20
    max_retries: int = 3


@dataclass
class Task:
    task_id: str
    goal: str
    parent_task_id: str | None = None
    constraints: dict[str, Any] = field(default_factory=dict)
    requested_capabilities: list[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    budget: Budget = field(default_factory=Budget)
    state: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
