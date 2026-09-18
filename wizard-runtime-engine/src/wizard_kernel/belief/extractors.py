"""Extractor Framework — deterministic first, never cognitive for structured data.

Extractors convert Observations into typed Claim candidates.
They NEVER write to the Knowledge Graph directly (invariant 2).
They return ExtractResult or None. EvidenceEngine is called by the loop.

Registration is dynamic: extractors register themselves for specific obs_types.
New extractors need zero changes to core loop — just register.

Invariant 4: extractor failures are caught and logged — they never crash the loop.
Invariant 5: no technology names are hardcoded except as values inside extractor
            functions that specifically handle that file format.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from wizard_kernel.contracts.observation import Observation

log = logging.getLogger(__name__)

# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ExtractResult:
    claim_type: str
    key: str
    value: Any
    support_type: str = "support"   # "support" | "contradict"
    confidence: str = "high"        # "high" | "medium" | "low"


ExtractorFn = Callable[[Observation], list[ExtractResult]]

# Registry: obs_type -> list of extractor functions
_REGISTRY: dict[str, list[ExtractorFn]] = {}


def register(obs_type: str):
    """Decorator — register an extractor function for a specific obs_type."""
    def decorator(fn: ExtractorFn) -> ExtractorFn:
        _REGISTRY.setdefault(obs_type, []).append(fn)
        return fn
    return decorator


def extract(obs: Observation) -> list[ExtractResult]:
    """Run all registered extractors for this observation's type."""
    results: list[ExtractResult] = []
    for fn in _REGISTRY.get(obs.obs_type, []):
        try:
            results.extend(fn(obs) or [])
        except Exception:  # noqa: BLE001 — extractor failure is never a crash (invariant 4)
            log.debug("extractor %s failed on obs %s", fn.__name__, obs.id, exc_info=True)
    return results


# ── Built-in extractors ───────────────────────────────────────────────────────

@register("file_content")
def _extract_package_json(obs: Observation) -> list[ExtractResult]:
    path = obs.payload.get("data", {}).get("path", "") or obs.payload.get("path", "")
    parsed = obs.payload.get("data", {}).get("parsed") or obs.payload.get("parsed")
    if not (path.endswith("package.json") and isinstance(parsed, dict)):
        return []
    results = []
    if name := parsed.get("name"):
        results.append(ExtractResult("PACKAGE", "name", name))
    if version := parsed.get("version"):
        results.append(ExtractResult("PACKAGE", "version", version))
    if scripts := parsed.get("scripts"):
        results.append(ExtractResult("PACKAGE", "has_scripts", True))
        if "start" in scripts:
            results.append(ExtractResult("RUNTIME", "has_start_script", scripts["start"]))
        if "test" in scripts:
            results.append(ExtractResult("RUNTIME", "has_test_script", scripts["test"]))
    if deps := parsed.get("dependencies", {}):
        results.append(ExtractResult("PACKAGE", "dependency_count", len(deps)))
    if engines := parsed.get("engines", {}).get("node"):
        results.append(ExtractResult("RUNTIME", "node_version_required", engines))
    return results


@register("file_content")
def _extract_pyproject_toml(obs: Observation) -> list[ExtractResult]:
    path = obs.payload.get("data", {}).get("path", "") or obs.payload.get("path", "")
    content = obs.payload.get("data", {}).get("content", "") or obs.payload.get("content", "")
    log.debug("pyproject extractor: path=%r", path)
    if not path.endswith("pyproject.toml"):
        return []
    results = []
    if m := re.search(r'name\s*=\s*["\']([^"\']+)["\']', content):
        results.append(ExtractResult("PACKAGE", "name", m.group(1)))
    if m := re.search(r'version\s*=\s*["\']([^"\']+)["\']', content):
        results.append(ExtractResult("PACKAGE", "version", m.group(1)))
    if "requires-python" in content or 'python_requires' in content:
        results.append(ExtractResult("RUNTIME", "language", "Python"))
    if "dependencies = [" in content:
        deps_block = content.split("dependencies = [")[1].split("]")[0]
        count = len([l for l in deps_block.splitlines() if '"' in l or "'" in l])
        results.append(ExtractResult("PACKAGE", "dependency_count", count))
    if "[tool.pytest" in content:
        results.append(ExtractResult("TESTING", "has_pytest", True))
    return results


@register("file_content")
def _extract_dockerfile(obs: Observation) -> list[ExtractResult]:
    path = (obs.payload.get("data", {}).get("path", "") or obs.payload.get("path", "")).lower()
    content = obs.payload.get("data", {}).get("content", "") or obs.payload.get("content", "")
    if "dockerfile" not in path and path != "dockerfile":
        return []
    results = [ExtractResult("DEPLOYMENT", "has_dockerfile", True)]
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("FROM "):
            base = line[5:].strip()
            results.append(ExtractResult("DEPLOYMENT", "base_image", base))
        if line.upper().startswith("EXPOSE "):
            port = line[7:].strip()
            results.append(ExtractResult("DEPLOYMENT", "exposed_port", port))
        if "CMD" in line.upper() or "ENTRYPOINT" in line.upper():
            results.append(ExtractResult("DEPLOYMENT", "has_entrypoint", True))
    return results


_COMPOSE_NAMES = (
    "docker-compose.yml", "docker-compose.yaml",
    "compose.yml", "compose.yaml",
)


@register("file_content")
def _extract_compose(obs: Observation) -> list[ExtractResult]:
    """Containerisation declared by a compose file rather than a Dockerfile.

    Both are deployment artifacts and both are DEPLOYMENT evidence, and a repo
    routinely has one without the other. Only the Dockerfile used to be read,
    so a compose-only repository — which is most of them, including the sample
    project — produced no DEPLOYMENT claim at all, and "Verify Containerization"
    could not be satisfied however long the investigation ran. The goal then
    looked identical to a goal the run had failed to prove, which is worse than
    a wrong answer: it made a satisfiable question look unanswerable.
    """
    data = obs.payload.get("data", {}) or {}
    path = (data.get("path", "") or obs.payload.get("path", "")).replace("\\", "/")
    content = data.get("content", "") or obs.payload.get("content", "")
    if path.rsplit("/", 1)[-1].lower() not in _COMPOSE_NAMES:
        return []

    results = [ExtractResult("DEPLOYMENT", "has_compose_file", True)]
    for line in content.splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if stripped.startswith("image:"):
            results.append(ExtractResult("DEPLOYMENT", "compose_image",
                                         stripped[len("image:"):].strip()))
        elif stripped.startswith("build:"):
            results.append(ExtractResult("DEPLOYMENT", "has_build", True))
        elif re.fullmatch(r"['\"]?\d+:\d+['\"]?", stripped):
            # A `ports:` entry, `"5432:5432"`. The host half is what is reachable.
            results.append(ExtractResult("DEPLOYMENT", "published_port",
                                         stripped.strip("'\"").split(":")[0]))
    return results


@register("file_content")
def _extract_requirements_txt(obs: Observation) -> list[ExtractResult]:
    path = obs.payload.get("data", {}).get("path", "") or obs.payload.get("path", "")
    content = obs.payload.get("data", {}).get("content", "") or obs.payload.get("content", "")
    if not path.endswith("requirements.txt"):
        return []
    packages = [l.split("==")[0].split(">=")[0].strip()
                for l in content.splitlines()
                if l.strip() and not l.startswith("#")]
    return [
        ExtractResult("RUNTIME", "language", "Python"),
        ExtractResult("PACKAGE", "dependency_count", len(packages)),
        ExtractResult("PACKAGE", "requirements_packages", packages[:50]),  # cap at 50
    ]


@register("command_result")
def _extract_command_result(obs: Observation) -> list[ExtractResult]:
    exit_code = obs.payload.get("exit_code")
    stdout = obs.payload.get("stdout", "")
    stderr = obs.payload.get("stderr", "")
    tool = obs.source_tool
    if exit_code is None:
        return []

    results = [ExtractResult(
        "EXECUTION", f"{tool}_exit_code", exit_code,
        support_type="support" if exit_code == 0 else "contradict",
    )]

    # Language/runtime version detection from common CLI outputs
    for pattern, claim_type, key in [
        (r"node\s+v?([\d.]+)", "RUNTIME", "node_version"),
        (r"python\s+[\d.]+", "RUNTIME", "python_version"),
        (r"npm\s+([\d.]+)", "RUNTIME", "npm_version"),
        (r"added\s+(\d+)\s+packages", "PACKAGE", "npm_packages_installed"),
        (r"(\d+)\s+passed", "TESTING", "tests_passed"),
        (r"(\d+)\s+failed", "TESTING", "tests_failed"),
    ]:
        if m := re.search(pattern, stdout, re.IGNORECASE):
            results.append(ExtractResult(claim_type, key, m.group(1) if m.lastindex else True))

    return results


@register("path_check")
def _extract_path_check(obs: Observation) -> list[ExtractResult]:
    # path_exists tool puts path in payload["data"]["path"] and exists in payload["exists"]
    path = obs.payload.get("data", {}).get("path", "") or obs.payload.get("path", "")
    exists = obs.payload.get("data", {}).get("exists", False) or obs.payload.get("exists", False)
    return [ExtractResult("FILESYSTEM", f"exists:{path}", exists,
                          support_type="support" if exists else "contradict")]


# ── Cognitive extractor stub (Phase 6) ───────────────────────────────────────
# When deterministic extractors produce no results for an observation,
# the loop can call planner.interpret(node, obs) to get suggested new nodes.
# That is handled in loop.py, not here — keeping extractors deterministic-only.
# This stub is the hook point for future cognitive extraction registration.
_COGNITIVE_REGISTRY: dict[str, list[ExtractorFn]] = {}


def register_cognitive(obs_type: str):
    """Register an extractor that may call an external service (Phase 6 only)."""
    def decorator(fn: ExtractorFn) -> ExtractorFn:
        _COGNITIVE_REGISTRY.setdefault(obs_type, []).append(fn)
        return fn
    return decorator


@register("port_check")
def _extract_port_check(obs: Observation) -> list[ExtractResult]:
    port = obs.payload.get("data", {}).get("port")
    active = obs.payload.get("data", {}).get("active", False)
    if port is None:
        return []
    return [ExtractResult(
        "RUNTIME", f"port:{port}:active", active,
        support_type="support" if active else "contradict",
        confidence="high",  # execution-tier check
    )]


@register("filesystem")
def _extract_tree(obs: Observation) -> list[ExtractResult]:
    tree = obs.payload.get("data", {}).get("tree", [])
    count = obs.payload.get("data", {}).get("count", 0)
    return [ExtractResult("FILESYSTEM", "total_visible_files", count)]


# ── Agentic browser extractors ────────────────────────────────────────────────
# Browser observations carry the tool envelope's `data` dict (url/title/status,
# plus snapshot/text/links). Reaching a page yields "WEB" claims; *acting* on one
# yields "INTERACTION" — two types because they are two findings, and a goal that
# asks for the second must not be closable by the first. Browser evidence is
# execution-tier (see trust.source_tier_for_tool), so both can carry verify goals.

@register("browser_action")
def _extract_browser_action(obs: Observation) -> list[ExtractResult]:
    """Claims from a browser action — navigation and *interaction* are not the same.

    This extractor used to treat all three of navigate / click / fill identically,
    so a click produced current_url and page_title and nothing else: the exact
    claim set a navigate produces. Two runs — one that walked the page and one
    that pressed its buttons — were indistinguishable in the Knowledge Graph, so
    no goal could ever depend on the difference and the browser could only ever
    be a reader.

    Typing those claims "WEB" still would not fix that. The kernel's goal engine
    counts claim *types* and cannot tell two keys of one type apart, so a goal
    requiring "WEB" closes on a navigate's current_url whether or not the page was
    ever touched — which is precisely what happened: a run that was asked to log
    in reached the login page, satisfied "Verify Web Surface", and stopped with
    the form untouched. The difference between reaching a page and operating one
    therefore has to live in the type:

        WEB          current_url, http_status:<url>, page_title — the page exists
        INTERACTION  interacted:<selector>, effect:<selector>,
                     field_value:<selector>                        — it was operated

    A navigate produces no INTERACTION claim, so a goal routed to that type is
    one only an action can close, and "it reached the page" can no longer be
    reported as "it did what it was asked".

    `interacted:<selector>` carries the value `True` — the claim is that this
    control was acted on. It deliberately does NOT carry which action: a control
    that is typed into and then pressed is one control acted on twice, and a
    value of "type" followed by "click" is the EvidenceEngine's signal for two
    conflicting findings about one key. It would file a CONTRADICTS edge between
    a field and itself, which the report prints as an accusation about the app
    built entirely out of the wizard's own bookkeeping. Which action happened is
    already recorded, by the claims that actually differ between them —
    `effect:<selector>` for a press, `field_value:` / `field_effect:` for a type.

    `effect` is deliberately a *supporting* claim whose **value** carries the
    finding, not a contradicting claim. "This button changed nothing" is an
    observation about the page, and it is true whatever the page is supposed to
    do; calling it a contradiction would assert the app is broken, which is a
    stronger claim than the evidence supports and one this extractor is not
    entitled to make. The reader of the report decides what an inert control
    means — the browser's job is to say plainly that it was inert.
    """
    data = obs.payload.get("data", {}) or {}
    url = data.get("url")
    if not url:
        return []
    results = [ExtractResult("WEB", "current_url", url)]
    status = data.get("status")
    if status is not None:
        results.append(ExtractResult(
            "WEB", f"http_status:{url}", status,
            support_type="support" if 200 <= int(status) < 400 else "contradict",
        ))
    if title := data.get("title"):
        results.append(ExtractResult("WEB", "page_title", title))

    selector = data.get("selector") or ""
    if data.get("clicked") and selector:
        results.append(ExtractResult("INTERACTION", f"interacted:{selector}", True))
        if effect := data.get("effect"):
            results.append(ExtractResult("INTERACTION", f"effect:{selector}", effect))
    if data.get("typed") and selector:
        results.append(ExtractResult("INTERACTION", f"interacted:{selector}", True))
        # The field's own value after the type. A controlled input that rejects a
        # keystroke raises nothing, so "the type succeeded" is not evidence the
        # value landed — reading the element back is.
        if (value := data.get("value")) is not None:
            results.append(ExtractResult("INTERACTION", f"field_value:{selector}", value))
        # Typing's own effect, under its own key. NOT `effect:<selector>`, which
        # is what pressing the control did: a type and a click on one selector
        # are two different actions, and a form that re-renders when you fill a
        # field but not when you press its submit would otherwise file a
        # contradiction between them — an accusation about the app built out of
        # the wizard comparing two things that were never the same question.
        if effect := data.get("effect"):
            results.append(ExtractResult("INTERACTION", f"field_effect:{selector}", effect))

    return results


@register("page_content")
def _extract_page_content(obs: Observation) -> list[ExtractResult]:
    data = obs.payload.get("data", {}) or {}
    url = data.get("url")
    if not url:
        return []
    results = [ExtractResult("WEB", "current_url", url)]
    if title := data.get("title"):
        results.append(ExtractResult("WEB", "page_title", title))
    if (node_count := data.get("node_count")) is not None:
        results.append(ExtractResult("WEB", "a11y_node_count", node_count))
    if (links := data.get("links")) is not None:
        results.append(ExtractResult("WEB", "link_count", len(links)))
    if (controls := data.get("controls")) is not None:
        # How much there is to operate, as opposed to how much there is to read.
        # A page with links and no controls is a page the run can only walk.
        results.append(ExtractResult("WEB", "control_count", len(controls)))
    if data.get("text"):
        results.append(ExtractResult("WEB", "has_text_content", True))
    return results


# ── Cognitive extraction (Phase 6) ────────────────────────────────────────────

def extract_cognitive(obs: Observation, planner_interpret_fn=None) -> list[ExtractResult]:
    """Run cognitive extractors for ambiguous observations.

    Cognitive extractors can call external services (e.g. the Planner LLM).
    They are completely separate from deterministic extractors and ONLY run when:
    1. The deterministic extract() produced zero results, AND
    2. A planner_interpret_fn is provided by the loop.

    The results are still routed through EvidenceEngine — cognitive extractors
    cannot insert into the KG directly (invariant 2).

    Args:
        obs: the observation to interpret
        planner_interpret_fn: callable(obs) -> list[ExtractResult] | None
                              provided by the loop if the Planner supports interpretation.
    """
    results: list[ExtractResult] = []

    # Run any registered cognitive extractors for this obs_type
    for fn in _COGNITIVE_REGISTRY.get(obs.obs_type, []):
        try:
            results.extend(fn(obs) or [])
        except Exception:  # noqa: BLE001
            log.debug("cognitive extractor %s failed on obs %s", fn.__name__, obs.id,
                      exc_info=True)

    # If still no results and we have a Planner interpret function, call it
    if not results and planner_interpret_fn is not None:
        try:
            # The Planner returns new InvestigationNodes, not ExtractResults.
            # Cognitive extraction from Planner is handled in the loop itself
            # via planner.interpret(node, obs) — this hook is for future plugins
            # that convert planner output directly into ExtractResults.
            pass
        except Exception:  # noqa: BLE001
            log.debug("planner interpret fallback failed for obs %s", obs.id, exc_info=True)

    return results

