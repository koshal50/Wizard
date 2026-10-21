"""Versioned, bounded diagram contract shared by local export and backend."""
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")]
Label = Annotated[str, StringConstraints(min_length=1, max_length=240)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Located(Strict):
    path: str | None = Field(default=None, max_length=512)

    @field_validator("path")
    @classmethod
    def relative_path(cls, value):
        if value is not None and (not value or "\\" in value or ":" in value or
                                  PurePosixPath(value).is_absolute() or
                                  any(p in {"", ".", ".."} for p in value.split("/"))):
            raise ValueError("Only repository-relative paths are allowed")
        return value


class Evidence(Located):
    id: Identifier
    description: str = Field(min_length=1, max_length=2000)
    classification: Literal["observed", "inferred"]
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def lines(self):
        if self.line_end is not None and (self.line_start is None or self.line_end < self.line_start):
            raise ValueError("Invalid line range")
        if self.line_start is not None and self.path is None:
            raise ValueError("Line ranges require a path")
        return self


class Node(Located):
    id: Identifier
    label: Label
    type: Label
    description: str = Field(default="", max_length=2000)
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    group_id: Identifier | None = None


class Group(Located):
    id: Identifier
    label: Label
    description: str = Field(default="", max_length=2000)
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=100)


class Relationship(Strict):
    id: Identifier
    source: Identifier
    target: Identifier
    type: Label
    label: str = Field(default="", max_length=240)
    description: str = Field(default="", max_length=2000)
    classification: Literal["observed", "inferred"]
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=100)


class ArchitectureGraph(Strict):
    schema_version: Literal[1] = 1
    title: Label
    repository_name: Label
    status: Literal["completed", "incomplete"]
    nodes: list[Node] = Field(max_length=500)
    relationships: list[Relationship] = Field(max_length=2000)
    evidence: list[Evidence] = Field(max_length=3000)
    groups: list[Group] = Field(default_factory=list, max_length=100)
    limitations: list[Annotated[str, StringConstraints(min_length=1, max_length=1000)]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def references(self):
        for rows in (self.nodes, self.relationships, self.evidence, self.groups):
            if len({r.id for r in rows}) != len(rows):
                raise ValueError("Duplicate identifiers")
        nodes, evidence = {n.id for n in self.nodes}, {e.id for e in self.evidence}
        groups = {g.id for g in self.groups}
        if groups & nodes:
            raise ValueError("Group and node identifiers must be distinct")
        for node in self.nodes:
            if (groups and node.group_id not in groups) or (node.group_id is not None and node.group_id not in groups):
                raise ValueError("Unknown architectural group")
        for row in [*self.nodes, *self.relationships, *self.groups]:
            if not set(row.evidence_ids) <= evidence:
                raise ValueError("Unknown evidence reference")
        relationships = set()
        for edge in self.relationships:
            key = (edge.source, edge.target, edge.type.casefold())
            if key in relationships or edge.source == edge.target:
                raise ValueError("Duplicate or self relationship")
            relationships.add(key)
            if edge.source not in nodes or edge.target not in nodes:
                raise ValueError("Unknown relationship endpoint")
            if edge.classification == "observed" and (not edge.evidence_ids or any(
                e.classification != "observed" for e in self.evidence if e.id in edge.evidence_ids
            )):
                raise ValueError("Observed relationships require observed evidence")
        return self
