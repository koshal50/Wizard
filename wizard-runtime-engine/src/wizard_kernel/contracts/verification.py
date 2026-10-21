"""Canonical verification specification and tactical decisions for Runtime v2."""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel, create_model, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextPredicate(StrictModel):
    operator: Literal["equals", "contains", "not_contains"]
    expected: str = Field(min_length=1)
    target: str = ""
    after_submission: bool = False

    @model_validator(mode="after")
    def no_redaction_expectation(self):
        if isinstance(self.expected, str) and any(marker in self.expected for marker in ("[REDACTED]", "[EMAIL]")):
            raise ValueError("Redaction markers cannot be application expectations")
        return self


# Source/field/operator compatibility is encoded in the canonical typed variants,
# so constrained decoding sees the same rules as local validation.
_ASSERTION_FIELDS = {
    "content": "repository", "exists": "repository", "exit_code": "command",
    "is_running": "process", "active": "process", "status_code": "http",
    "body_preview": "http", "url": "browser", "title": "browser", "snapshot": "browser", "text": "browser",
}
_predicates = []
for _field, _source in _ASSERTION_FIELDS.items():
    _members = {"source": (Literal[_source], ...), "field": (Literal[_field], ...)}
    if _source != "browser":
        _members["after_submission"] = (Literal[False], False)
    if _field in {"exists", "is_running", "active"}:
        _members.update(operator=(Literal["equals"], "equals"), expected=(Literal["true", "false"], ...))
    elif _field in {"exit_code", "status_code"}:
        _members.update(operator=(Literal["equals"], "equals"),
                        expected=(int, Field(ge=100, le=599) if _field == "status_code" else ...))
    _predicates.append(create_model(_field + "_predicate", __base__=TextPredicate, **_members))


class Assertion(RootModel[Annotated[Union[tuple(_predicates)], Field(discriminator="field")]]):
    """Flat wire predicate, typed by field; preserves Runtime's public accessors."""
    @property
    def source(self): return self.root.source
    @property
    def field(self): return self.root.field
    @property
    def operator(self): return self.root.operator
    @property
    def expected(self): return str(self.root.expected)
    @property
    def target(self): return self.root.target
    @property
    def after_submission(self): return self.root.after_submission


class CheckSpec(StrictModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    workflow: Literal["general", "registration", "login", "form_submission"] = "general"
    assertions: list[Assertion] = Field(default_factory=list)
    unresolved_reason: str = ""
    capabilities: list[Literal["repository", "process", "http", "browser"]] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def expectation_or_reason(self):
        if not self.assertions and not self.unresolved_reason:
            raise ValueError("Check requires explicit expectations or a reason discovery is needed")
        return self


class VerificationSpec(StrictModel):
    checks: list[CheckSpec] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def dependencies(self):
        ids = [c.id for c in self.checks]
        if len(set(ids)) != len(ids):
            raise ValueError("check IDs must be unique")
        by_id = {c.id: c for c in self.checks}
        def visit(check_id, ancestors):
            if check_id not in by_id or check_id in ancestors:
                raise ValueError("unknown or cyclic check dependency")
            for dependency in by_id[check_id].depends_on:
                visit(dependency, ancestors | {check_id})
        for check in self.checks:
            visit(check.id, set())
        return self


def planning_model(commands: list[str], *, read_only: bool = False):
    """Constrain executable identities using repository discovery, not labels."""
    targets = Literal[tuple(dict.fromkeys(["", *commands]))]
    predicates = tuple(create_model(p.__name__ + "_declared", __base__=p, target=(targets, ""))
                       if p.model_fields["source"].annotation == Literal["process"] else p for p in _predicates)
    if read_only:
        predicates = tuple(p for p in predicates if p.model_fields['source'].annotation == Literal['repository'])
    predicate = RootModel[Annotated[Union[predicates], Field(discriminator="field")]]
    check = create_model("PlannedCheck", __base__=CheckSpec, assertions=(list[predicate], Field(default_factory=list)))
    if read_only:
        check = create_model('ReadOnlyCheck', __base__=check,
            capabilities=(list[Literal['repository']], Field(default_factory=list)))
    return create_model("GroundedVerificationSpec", __base__=VerificationSpec,
                        checks=(list[check], Field(min_length=1, max_length=8)))


class FormField(StrictModel):
    selector: str
    value_ref: str  # Only Runtime resolves authorized values; the model never generates them.


class CheckRefinement(StrictModel):
    assertions: list[Assertion] = Field(min_length=1)
    observation_ids: list[str] = Field(min_length=1)


# One source for parameter names/types. The strict provider schema is derived
# from these models and the executor receives their validated model_dump().
_PARAMETERS = {
    "list_tree": {"max_depth": (int, 3)},
    "read_file": {"path": (str, ...), "max_bytes": (int, 8000)},
    "search_files": {"pattern": (str, ...), "glob": (str, "**/*")},
    "path_exists": {"path": (str, ...)},
    "execute_command": {"command": (str, ...), "cwd": (str, ".")},
    "start_process": {"command": (str, ...), "cwd": (str, ".")},
    "read_process": {"handle_id": (str, ...)},
    "kill_process": {"handle_id": (str, ...)},
    "list_processes": {},
    "check_port": {"port": (int, ...), "host": (str, "localhost")},
    "http_request": {"url": (str, ...), "method": (Literal["GET", "HEAD", "POST"], "GET"), "body": (str, ""), "require_ready": (bool, True)},
    "browser_navigate": {"url": (str, ...)},
    "browser_assertion": {"field": (Literal["url", "title", "snapshot", "text"], ...),
                          "operator": (Literal["equals", "contains", "not_contains"], ...), "expected": (str, ...)},
    "browser_snapshot": {}, "browser_extract": {}, "browser_back": {},
    "browser_click": {"selector": (str, ...)},
    "browser_type": {"selector": (str, ...), "value_ref": (str, ...)},
    "browser_fill_form": {"fields": (list[FormField], ...)},
}
TOOL_ACTIONS = {}
for _tool, _fields in _PARAMETERS.items():
    _params = create_model(f"{_tool}_parameters", __base__=StrictModel, **_fields)
    TOOL_ACTIONS[_tool] = create_model(
        f"{_tool}_action", __base__=StrictModel,
        tool=(Literal[_tool], ...), parameters=(_params, ...),
    )


class DecisionEnvelope(StrictModel):
    """The wire object wraps a typed union; Runtime consumes its typed decision.

    A root object is required by Cerebras. The nested union enforces conditional
    fields in the provider schema rather than only after generation in Python.
    """
    @property
    def kind(self): return self.decision.kind
    @property
    def action(self): return self.decision.action
    @property
    def refinement(self): return self.decision.refinement
    @property
    def reason(self): return self.decision.reason


def decision_model(available_tools: list[str], *, allow_evaluate: bool = True, value_refs: list[str] | None = None,
                   allow_refine: bool = True, browser_refinement: bool = False, allow_blocked: bool = True,
                   browser_targets: list[str] | None = None, require_submission: bool | None = None,
                   process_targets: list[str] | None = None):
    """Only advertise allowed tools, with structurally exclusive decision kinds."""
    registered = dict(TOOL_ACTIONS)
    if value_refs:
        ref_type = Literal[tuple(value_refs)]
        observed_field = create_model("AuthorizedFormField", __base__=FormField, value_ref=(ref_type, ...))
        for name in ("browser_type", "browser_fill_form"):
            base = registered[name].model_fields["parameters"].annotation
            binding = {"value_ref": (ref_type, ...)} if name == "browser_type" else {"fields": (list[observed_field], ...)}
            params = create_model(name + "_authorized_parameters", __base__=base, **binding)
            registered[name] = create_model(name + "_authorized_action", __base__=registered[name], parameters=(params, ...))
    actions = tuple(registered[t] for t in available_tools)
    if not actions:
        raise ValueError("no tools available")
    action_type = actions[0] if len(actions) == 1 else Annotated[Union[actions], Field(discriminator="tool")]
    tool = create_model("ToolDecision", __base__=StrictModel,
        kind=(Literal["tool"], ...), action=(action_type, ...),
        refinement=(None, None), reason=(str, ...))
    refinement_type = CheckRefinement
    if browser_refinement:
        targets = Literal[tuple(dict.fromkeys(["", *(t for t in (browser_targets or []) if isinstance(t, str) and t)]))]
        bindings = {"target": (targets, "")}
        if require_submission is not None:
            bindings["after_submission"] = (Literal[require_submission], require_submission)
        browser_predicates = tuple(create_model(p.__name__ + "_observed", __base__=p, **bindings)
                                   for p in _predicates if p.model_fields["source"].annotation == Literal["browser"])
        browser_assertion = RootModel[Annotated[Union[browser_predicates], Field(discriminator="field")]]
        refinement_type = create_model("BrowserRefinement", __base__=CheckRefinement,
                                      assertions=(list[browser_assertion], Field(min_length=1)))
    elif process_targets is not None:
        targets = Literal[tuple(dict.fromkeys(process_targets or [""]))]
        predicates = tuple(create_model(p.__name__ + "_observed", __base__=p, target=(targets, ""))
                           for p in _predicates if p.model_fields["source"].annotation == Literal["process"])
        predicate = RootModel[Annotated[Union[predicates], Field(discriminator="field")]]
        refinement_type = create_model("ProcessRefinement", __base__=CheckRefinement,
                                      assertions=(list[predicate], Field(min_length=1)))
    refine = create_model("RefineDecision", __base__=StrictModel,
        kind=(Literal["refine"], ...), action=(None, None),
        refinement=(refinement_type, ...), reason=(str, ...))
    blocked = create_model("BlockedDecision", __base__=StrictModel,
        kind=(Literal["blocked"], ...), action=(None, None),
        refinement=(None, None), reason=(str, ...))
    variants = (tool,) + ((blocked,) if allow_blocked else ()) + ((refine,) if allow_refine else ())
    if allow_evaluate:
        evaluate = create_model("EvaluateDecision", __base__=StrictModel,
            kind=(Literal["evaluate"], ...), action=(None, None),
            refinement=(None, None), reason=(str, ...))
        variants += (evaluate,)
    decision_type = variants[0] if len(variants) == 1 else Annotated[Union[variants], Field(discriminator="kind")]
    return create_model("TacticalDecision", __base__=DecisionEnvelope, decision=(decision_type, ...))
