"""Plan contracts — what the Planner returns.

GoalDefinition carries ALL goal satisfaction criteria: required claim types,
belief threshold, and whether execution evidence is mandatory.
The kernel NEVER infers these from goal names — the Planner drives it.

Invariant 5: no technology-specific knowledge lives in the kernel core.
"""
from pydantic import BaseModel
from wizard_kernel.contracts.node import InvestigationNode


class GoalDefinition(BaseModel):
    """A single investigation goal, fully specified by the Planner.

    The kernel uses `required_claim_types` and `belief_threshold` directly —
    it never interprets the `name` string to decide what evidence is needed.
    """
    name: str
    required_claim_types: list[str] = []
    belief_threshold: float = 0.6
    requires_execution_evidence: bool = False


class TechnologyEntry(BaseModel):
    name: str
    confidence: str
    signals: list[str]
    initial_goals: list[GoalDefinition] = []
    priority_files: list[str] = []


class TechnologyPlan(BaseModel):
    technologies: list[TechnologyEntry]
    seed_nodes: list[InvestigationNode] = []
