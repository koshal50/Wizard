from enum import Enum


class LifecycleState(str, Enum):
    created = "created"
    scanning = "scanning"
    planning = "planning"
    investigation_loop = "investigation_loop"
    reporting = "reporting"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
