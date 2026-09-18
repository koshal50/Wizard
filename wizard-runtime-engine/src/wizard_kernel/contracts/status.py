from enum import Enum


class LifecycleState(str, Enum):
    created = "created"
    scanning = "scanning"
    planning = "planning"
    investigation_loop = "investigation_loop"
    reporting = "reporting"
    completed = "completed"
    # The investigation ended without satisfying every goal: the Planner had no
    # further steps to propose, or the budget ran out. Distinct from `failed`
    # (something broke) and from `completed` (the goals were met) because the
    # three read identically to a caller otherwise, and a run that gave up is
    # not a run that verified anything.
    incomplete = "incomplete"
    failed = "failed"
    cancelled = "cancelled"


# The states from which an investigation never moves again. A client waiting on
# a run is really asking this one question, and the answer belongs here rather
# than in each client: the CLI used to carry its own copy of the list and went on
# polling forever the moment `incomplete` was added to the enum, because its copy
# still named only the three states that existed when it was written.
TERMINAL_STATES: frozenset["LifecycleState"] = frozenset({
    LifecycleState.completed,
    LifecycleState.incomplete,
    LifecycleState.failed,
    LifecycleState.cancelled,
})


def is_terminal(state: "LifecycleState | str") -> bool:
    """Whether `state` is one the investigation has finished in.

    Accepts the raw string a client sends back, not just the enum: the API
    serialises the value, so that is the form a caller usually holds.
    """
    try:
        return LifecycleState(state) in TERMINAL_STATES
    except ValueError:
        # A state this kernel does not know is not one it can call finished.
        return False
