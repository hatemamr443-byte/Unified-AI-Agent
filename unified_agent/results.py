from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    DENIED = "denied"


@dataclass
class ExecutionResult:
    task_id: str
    status: ExecutionStatus
    output: Any = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    confidence: float | None = None
    requires_human_review: bool = False
    attempts: int = 0
    retries: int = 0
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "evidence": self.evidence,
            "files_changed": self.files_changed,
            "tools_used": self.tools_used,
            "errors": self.errors,
            "confidence": self.confidence,
            "requires_human_review": self.requires_human_review,
            "attempts": self.attempts,
            "retries": self.retries,
            "elapsed_seconds": self.elapsed_seconds,
        }
