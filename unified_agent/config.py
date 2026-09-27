from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    default_max_steps: int = 50
    default_max_time_seconds: int = 900
    default_max_tool_calls: int = 100
    default_max_worker_calls: int = 20
    default_max_retries: int = 3
