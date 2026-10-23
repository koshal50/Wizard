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
    parent_id: Identifier | None = None
    level: Literal["subsystem", "module", "file"] = "module"


class Coverage(Strict):
    candidate_files: int = Field(ge=0)
    examined_files: list[str] = Field(max_length=500)
    context_files: list[str] = Field(default_factory=list, max_length=500)
    examined_areas: list[Label] = Field(default_factory=list, max_length=500)
    uninspected_file_count: int = Field(ge=0)
    uninspected_areas: list[Label] = Field(default_factory=list, max_length=500)
    unlisted_area_count: int = Field(default=0, ge=0)
    unassigned_files: list[str] = Field(default_factory=list, max_length=500)
    partial_files: list[str] = Field(default_factory=list, max_length=500)
    unmeasured_read_count: int = Field(default=0, ge=0)
    discovery_note: str = Field(max_length=1000)

    @field_validator("examined_files", "context_files", "unassigned_files", "partial_files")
    @classmethod
    def paths(cls, values):
        for value in values:
            Located(path=value)
        return values

    @model_validator(mode="after")
    def counts(self):
        examined, context = set(self.examined_files), set(self.context_files)
        if len(examined) != len(self.examined_files) or len(context) != len(self.context_files) or examined & context:
            raise ValueError("Coverage file lists must be distinct")
        if self.uninspected_file_count != self.candidate_files - len(examined):
            raise ValueError("Inconsistent measured coverage")
        if not set(self.unassigned_files) <= examined or not set(self.partial_files) <= examined | context:
            raise ValueError("Coverage refers to unexamined files")
        return self


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
    coverage: Coverage | None = None

    @model_validator(mode="after")
    def references(self):
        for rows in (self.nodes, self.relationships, self.evidence, self.groups):
            if len({r.id for r in rows}) != len(rows):
                raise ValueError("Duplicate identifiers")
        nodes, evidence = {n.id for n in self.nodes}, {e.id for e in self.evidence}
        by_id = {n.id: n for n in self.nodes}
        if any(n.parent_id is not None and n.parent_id not in nodes for n in self.nodes):
            raise ValueError("Unknown parent component")
        for node in self.nodes:
            ancestors, current = {node.id}, node.parent_id
            while current is not None:
                if current in ancestors or len(ancestors) > 8:
                    raise ValueError("Cyclic or excessively deep architecture hierarchy")
                ancestors.add(current)
                current = by_id[current].parent_id
            if node.level == "subsystem" and node.parent_id is not None:
                raise ValueError("Subsystems are overview roots")
            if node.parent_id and by_id[node.parent_id].level == "file":
                raise ValueError("Files cannot contain components")
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
