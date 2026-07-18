from pydantic import BaseModel
from wizard_kernel.contracts.node import InvestigationNode


class TechnologyEntry(BaseModel):
    name: str
    confidence: str
    signals: list[str]
    initial_goals: list[str]
    priority_files: list[str] = []


class TechnologyPlan(BaseModel):
    technologies: list[TechnologyEntry]
    seed_nodes: list[InvestigationNode] = []
