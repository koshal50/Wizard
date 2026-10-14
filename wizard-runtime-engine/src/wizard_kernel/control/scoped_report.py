"""Evidence projection -> subject builders -> template-shaped Markdown.

No tools, repository reads, agent calls, goal mutations or state transitions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath

from wizard_kernel.contracts.actions import failure_reason, safe_parameters
from wizard_kernel.control.report_scope import CLAIM_TYPES, TARGET_SECTIONS, report_contract
from wizard_kernel.control.runtime_checks import runtime_levels


def text(value):
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(value))
    value = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", value)
    value = re.sub(
        r"(?i)(password|secret|api[_ -]?key|token)(\s*[:=]\s*)[^\s,;]+", r"\1\2[REDACTED]", value
    )
    return value.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")[:1200]


def table(headers, rows):
    if not rows:
        return ["Not established from the collected evidence."]
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *["| " + " | ".join(text(cell) for cell in row) + " |" for row in rows],
    ]


def details(label, body):
    return [f"<details>\n<summary>{label}</summary>", "", *body, "", "</details>"]


@dataclass
class ReportContext:
    inv: object
    observations: list
    goals: list
    goal_engine: object
    graph: object
    kg: object
    sources: list
    claims: list
    targets: list
    status: str

    @classmethod
    def extract(cls, inv, graph, observations, kg=None, goals=None):
        owned = {o.id: o for o in observations if o.investigation_id == inv.id}
        observations = list(owned.values())
        sources = []
        for obs in observations:
            if obs.success and obs.source_tool == "read_file":
                data = obs.payload.get("data") or {}
                params = (obs.payload.get("action") or {}).get("params") or {}
                path = str(
                    data.get("path")
                    or params.get("path")
                    or (obs.payload.get("meta") or {}).get("path")
                    or ""
                ).replace("\\", "/")
                if path:
                    sources.append(
                        (path, str(data.get("content") or obs.payload.get("content") or ""), obs)
                    )
        claims = [c for c in kg.all_claims() if c.investigation_id == inv.id] if kg else []
        state = getattr(inv.state, "value", inv.state)
        status = {
            "completed": "VERIFIED" if inv.intent == "verify" else "COMPLETED",
            "failed": "FAILED",
            "timed_out": "TIMED OUT",
            "cancelled": "CANCELLED",
        }.get(state, "INCOMPLETE")
        goal_list = goals.all() if goals else []
        # Partial success never conceals an incomplete orchestration state.
        if state == "incomplete" and (
            any(g.state == "satisfied" for g in goal_list)
            or any(runtime_levels(observations).values())
        ):
            status = "PARTIALLY VERIFIED (INCOMPLETE)"
        targets = report_contract(inv)["targets"]
        return cls(inv, observations, goal_list, goals, graph, kg, sources, claims, targets, status)

    def refs(self, obs):
        return f"`{obs.id}`"

    def selected_claims(self, target):
        return [c for c in self.claims if c.claim_type in CLAIM_TYPES.get(target, set())]

    def claim_rows(self, claims):
        valid_ids = {o.id for o in self.observations}
        rows = []
        for claim in claims:
            evidence = [
                e
                for e in self.kg.evidence_for(claim.id)
                if valid_ids.intersection(e.observation_ids)
            ]
            for ev in evidence:
                refs = ", ".join(f"`{oid}`" for oid in ev.observation_ids if oid in valid_ids)
                rows.append(
                    (
                        f"{claim.claim_type}: {claim.key} (`{claim.id}`)",
                        claim.value,
                        self.kg.trust_of(claim.id),
                        refs,
                        ev.source_tier,
                        ev.support_type,
                    )
                )
        return rows


def packages(ctx):
    result = []
    for path, content, obs in ctx.sources:
        if PurePosixPath(path).name != "package.json":
            continue
        try:
            package = json.loads(content)
        except (ValueError, TypeError):
            continue
        if isinstance(package, dict):
            result.append((path, package, obs))
    return result


def source_rows(ctx, pattern, match_path=True):
    rows = []
    for path, content, obs in ctx.sources:
        for number, line in enumerate(content.splitlines(), 1):
            if not line.strip() or line.lstrip().startswith(("//", "#")):
                continue
            if re.search(pattern, (path + " " if match_path else "") + line, re.IGNORECASE):
                # Bound excerpts, not a dump of source files or entire logs.
                rows.append(
                    (f"{path}:{number}", line.strip()[:200], "Inferred from source", obs.id)
                )
                if len(rows) >= 24:
                    return rows
    return rows


def execution_rows(ctx, pattern=None, tools=None):
    rows = []
    for obs in ctx.observations:
        if obs.source_tool in {
            "read_file",
            "search_files",
            "path_exists",
            "list_tree",
            "explorer",
            "verifier",
        }:
            continue
        action = obs.payload.get("action") or {}
        params = safe_parameters(action.get("params") or obs.payload.get("meta") or {})
        if obs.source_tool == "browser_type":
            params.pop("text", None)
        if tools and obs.source_tool not in tools:
            continue
        if pattern and not re.search(pattern, str(params), re.IGNORECASE):
            continue
        data = obs.payload.get("data") or {}
        outcome = (
            f"Executed; HTTP {data['status_code']}"
            if "status_code" in data
            else f"Executed; exit {obs.payload.get('exit_code', data.get('exit_code', 'not reported'))}"
        )
        if not obs.success:
            outcome = "Failed: " + failure_reason(obs.payload)
        rows.append((obs.source_tool, params, outcome, obs.id))
    return rows


def scripts(ctx, pattern):
    return [
        (path, name, command, "Declared; execution must be established separately", obs.id)
        for path, package, obs in packages(ctx)
        for name, command in (package.get("scripts") or {}).items()
        if re.search(pattern, name, re.IGNORECASE)
    ]


def route_body(block):
    """Keep contract hints inside a literal inline handler, not nearby helpers."""
    if named := re.search(r"^([ \t]*)(?:async\s+)?def\s+\w+\s*\(", block, re.MULTILINE):
        indent = len(named.group(1))
        lines = block[named.start() :].splitlines()
        end = len(lines)
        for i, line in enumerate(lines[1:], 1):
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                end = i
                break
        return "\n".join(lines[:end])
    callback = re.search(r"(?:=>\s*|function(?:\s+\w+)?\s*\([^)]*\)\s*)\{", block)
    if not callback or re.search(r"\)\s*;", block[: callback.start()]):
        return block.split("\n", 1)[0]
    scrubbed = re.sub(
        r"([\"\'`])(?:\\.|(?!\1).)*?\1|//[^\n]*|/\*.*?\*/",
        lambda m: " " * len(m.group()),
        block,
        flags=re.DOTALL,
    )
    depth = 0
    for i in range(callback.end() - 1, len(scrubbed)):
        if scrubbed[i] == "{":
            depth += 1
        elif scrubbed[i] == "}":
            depth -= 1
            if depth == 0:
                return block[: i + 1]
    return block[: callback.start()]


def routes(ctx):
    found = []
    pattern = r"^[ \t]*@?(?P<owner>\w+)\.(?P<method>get|post|put|patch|delete|options|head)\(\s*[\"\'](?P<path>/[^\"\']*)[\"\']"
    for source, content, obs in ctx.sources:
        symbols = {"app", "router"}
        symbols.update(
            re.findall(
                r"\b(\w+)\s*=\s*(?:express\.Router|Router|APIRouter|FastAPI|Flask|express)\s*\(",
                content,
            )
        )
        matches = [
            m
            for m in re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
            if m.group("owner") in symbols
        ]
        for i, match in enumerate(matches):
            line = content.count("\n", 0, match.start()) + 1
            block = route_body(
                content[
                    match.end() : matches[i + 1].start() if i + 1 < len(matches) else len(content)
                ][:5000]
            )
            handler = (
                block.split("\n")[0].strip().lstrip(",").strip()[:140]
                or "Inline handler; see source"
            )
            if named := re.search(r"\b(?:async\s+)?def\s+(\w+)\s*\(", block):
                handler = named.group(1)
            path = match.group("path")
            actual = [
                o
                for o in ctx.observations
                if o.source_tool == "http_request"
                and (o.payload.get("data") or {}).get("url", "").split("?", 1)[0].endswith(path)
                and (o.payload.get("data") or {}).get("method", "GET").upper()
                == match.group("method").upper()
            ]
            # A response is not automatically proof that this source handler ran.
            tested = "Source-discovered; not verified"
            if actual:
                tested = "HTTP attempted: " + ", ".join(
                    f"{o.id}: {(o.payload.get('data') or {}).get('status_code', 'no response')}"
                    for o in actual
                )
            found.append(
                {
                    "method": match.group("method").upper(),
                    "path": path,
                    "owner": match.group("owner"),
                    "source": f"{source}:{line}",
                    "handler": handler,
                    "obs": obs.id,
                    "block": block,
                    "execution": tested,
                }
            )
    return found


def architecture(ctx):
    stack = [
        (c.claim_type, f"{c.key}: {c.value}", "Inferred; see provenance below")
        for c in ctx.selected_claims("architecture")
        if c.claim_type != "FILESYSTEM" and ctx.claim_rows([c])
    ]
    for path, package, obs in packages(ctx):
        stack.append(("Runtime requirement", package.get("engines", "Not declared"), obs.id))
        for dep in ("express", "react", "vite", "next", "fastify", "webpack", "typescript"):
            deps = {**(package.get("dependencies") or {}), **(package.get("devDependencies") or {})}
            if dep in deps:
                stack.append(("Declared framework/build dependency", f"{dep}: {deps[dep]}", obs.id))
    for path, content, obs in ctx.sources:
        language = {
            ".py": "Python",
            ".js": "JavaScript",
            ".jsx": "JavaScript / JSX",
            ".ts": "TypeScript",
            ".tsx": "TypeScript / JSX",
            ".java": "Java",
            ".go": "Go",
            ".rs": "Rust",
        }.get(PurePosixPath(path).suffix)
        if language:
            stack.append(("Source language (inferred from extension)", language, obs.id))
        for module in re.findall(r"(?:require\(\s*|\bfrom\s+)[\"\']([^\"\']+)[\"\']", content):
            if module.split("/")[0] in {
                "express",
                "react",
                "react-dom",
                "vite",
                "next",
                "fastify",
                "webpack",
                "typescript",
            }:
                stack.append(("Referenced framework/build module", module, obs.id))
    components = []
    for path, content, obs in ctx.sources:
        signals = []
        for label, pattern in [
            ("HTTP route definitions", r"\.(?:get|post|put|delete)\("),
            ("Application initialization", r"\blisten\(|createApp\(|createRoot\("),
            ("Exported functions/classes", r"\b(?:class|function|def)\s+\w+|module\.exports"),
            ("Dependency/build manifest", r'"(?:scripts|dependencies)"'),
        ]:
            if re.search(pattern, content):
                signals.append(label)
        if signals:
            components.append((path, "; ".join(signals), "Inferred", obs.id))
    relationships = []
    external = []
    for path, content, obs in ctx.sources:
        for imported in re.findall(r"(?:require\(\s*|\bfrom\s+)[\"\'](\.[^\"\']+)[\"\']", content)[
            :8
        ]:
            relationships.append(
                (
                    path,
                    imported,
                    "Observed source import; communication protocol not established",
                    obs.id,
                )
            )
        for imported in re.findall(
            r"(?:require\(\s*|\bfrom\s+)[\"\']((?!\.)[^\"\']+)[\"\']", content
        )[:8]:
            external.append(
                (
                    imported,
                    path,
                    "Referenced external module; service availability not established",
                    obs.id,
                )
            )
    return {
        "Application stack": table(["Area", "Value", "Evidence"], stack),
        "Major components and responsibilities": table(
            ["Source", "Responsibility signals", "State", "Evidence"], components
        ),
        "Established relationships": table(
            ["Source", "Imported module", "Relationship", "Evidence"], relationships
        ),
        "Relevant repository structure": table(
            ["Directory", "Inspected path", "Responsibility signals", "Observation"],
            [
                (
                    str(PurePosixPath(p).parent),
                    p,
                    next(
                        (row[1] for row in components if row[0] == p),
                        "Inspected configuration/source; responsibility not established",
                    ),
                    o.id,
                )
                for p, _, o in ctx.sources
            ],
        ),
        "External dependencies and services": table(
            ["Dependency", "Source", "State", "Evidence"], external
        ),
        "Architecture gaps": [
            "Only inspected sources are represented. Runtime health, deployment success, and unobserved communication paths are not established by architecture inspection."
        ],
    }


def api(ctx):
    discovered = routes(ctx)
    route_rows = [
        (r["owner"], r["method"], r["path"], r["handler"], r["source"], r["obs"], r["execution"])
        for r in discovered
    ]
    contracts = []
    auth = []
    for route in discovered:
        block = route["block"]
        params = re.findall(r":(\w+)|\{(\w+)\}", route["path"])
        query = sorted(set(re.findall(r"\breq\.query\.(\w+)", block)))
        body = sorted(set(re.findall(r"\breq\.body\.(\w+)", block)))
        for destructured in re.findall(r"\{([^{}]+)\}\s*=\s*req\.body", block):
            body.extend(re.findall(r"(?:^|,)\s*(\w+)", destructured))
        body = sorted(set(body))
        statuses = sorted(set(re.findall(r"\b(?:res\.status\(|status_code\s*=)\s*(\d{3})", block)))
        contracts.append(
            (
                f"{route['method']} {route['path']}",
                ", ".join(a or b for a, b in params) or "None in literal path",
                ", ".join(query) or "Not established",
                ", ".join(body) or "Schema not established",
                ", ".join(statuses) or "Not established",
                route["obs"],
            )
        )
        auth.append(
            (
                f"{route['method']} {route['path']}",
                route["handler"],
                "Middleware references only; authorization contract requires tracing definitions",
                route["obs"],
            )
        )
    frameworks = [
        (p, name, deps[name], o.id)
        for p, pkg, o in packages(ctx)
        for deps in [{**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}]
        for name in ("express", "fastify", "koa", "@nestjs/core")
        if name in deps
    ]
    frameworks.extend(
        (path, module, "Source import; version not established", obs.id)
        for path, content, obs in ctx.sources
        for module in re.findall(r"(?:require\(\s*|\bfrom\s+)[\"\']([^\"\']+)[\"\']", content)
        if module in {"express", "fastify", "koa", "@nestjs/core", "fastapi", "flask"}
    )
    return {
        "API overview": [
            f"{len(discovered)} literal route declarations were discovered in inspected source. Source discovery and HTTP attempts are shown separately. Router mount prefixes and handler execution are not inferred from file proximity."
        ]
        + [""]
        + table(["Manifest", "Declared API framework", "Constraint", "Evidence"], frameworks),
        "Routes and handlers": table(
            [
                "Router",
                "Method",
                "Declared path",
                "Handler/reference",
                "Source",
                "Evidence",
                "Execution",
            ],
            route_rows,
        ),
        "Request and response contracts": table(
            [
                "Route",
                "Path parameters",
                "Query fields",
                "Body fields",
                "Declared statuses",
                "Evidence",
            ],
            contracts,
        ),
        "Authentication and validation": table(
            ["Route", "Observed handler/middleware arguments", "Limit", "Evidence"], auth
        ),
        "API gaps": [
            "Dynamic routes, mounted prefixes, full schemas, authorization semantics and uninspected handler dependencies remain unestablished unless linked evidence below proves them."
        ],
    }


def runtime(ctx):
    levels = []
    for label, ids in runtime_levels(ctx.observations).items():
        failures = [
            o for o in ctx.observations if not o.success and o.payload.get("readiness_check")
        ]
        value = (
            "verified at observation time"
            if ids
            else "failed: " + failure_reason(failures[-1].payload)
            if label == "HTTP readiness" and failures
            else "not verified"
        )
        levels.append(
            f"- {label}: {text(value)}"
            + (" — " + ", ".join(f"`{id}`" for id in ids) if ids else "")
        )
    entry = [
        (p, package.get("main", "Not declared"), "Declared entry point", obs.id)
        for p, package, obs in packages(ctx)
    ]
    startup = scripts(ctx, r"^(start|dev|serve)(:|$)")
    return {
        "Runtime verification levels": levels,
        "Entry points and startup commands": table(
            ["Manifest", "Entry point", "State", "Evidence"], entry
        )
        + [""]
        + table(["Manifest", "Script", "Command", "State", "Evidence"], startup),
        "Configuration and initialization": table(
            ["Source", "Observed declaration", "State", "Evidence"],
            source_rows(
                ctx,
                r"\blisten\(|createApp\(|process\.env|os\.environ|dotenv|initialize|config\.",
                match_path=False,
            ),
        ),
        "Runtime dependencies": table(
            ["Manifest", "Declared engine requirements", "Evidence"],
            [(p, v.get("engines", "Not declared"), o.id) for p, v, o in packages(ctx)],
        ),
    }


def subject(ctx, target):
    if target == "architecture":
        return architecture(ctx)
    if target == "api":
        return api(ctx)
    if target == "runtime":
        return runtime(ctx)
    if target == "dependencies":
        rows = [
            (p, name, version, "Declared; installation not proven", o.id)
            for p, pkg, o in packages(ctx)
            for name, version in {
                **(pkg.get("dependencies") or {}),
                **(pkg.get("devDependencies") or {}),
            }.items()
        ]
        return {
            "Declared dependencies": table(
                ["Manifest", "Dependency", "Constraint", "State", "Evidence"], rows
            ),
            "Availability and resolution checks": table(
                ["Tool", "Check", "Outcome", "Evidence"],
                execution_rows(ctx, r"install|\bls\b|resolve|dependency|dependencies|pip.*check"),
            ),
            "Dependency gaps": [
                "Declared constraints do not prove installed versions or successful resolution."
            ],
        }
    patterns = {
        "deployment": r"docker|compose|kubernetes|helm|terraform|deploy|image:|ports:|environment:",
        "containers": r"docker|compose|FROM\s|EXPOSE\s|image:|container",
        "ci": r"\.github/workflows|\.gitlab-ci|Jenkinsfile|runs-on|steps:|workflow|pipeline",
        "build": r"vite\.config|webpack|tsconfig|build|compile|bundle|dist|outDir",
        "authentication": r"authenticate|authorize|requireAuth|jwt|session|token|password|protected|roles?",
        "security": r"validate|sanitize|helmet|cors|permission|csrf|security|vulnerab|authorization",
    }
    declarations = table(
        ["Source", "Observed declaration", "State", "Evidence"], source_rows(ctx, patterns[target])
    )
    checks = table(["Tool", "Check", "Outcome", "Evidence"], execution_rows(ctx, patterns[target]))
    names = TARGET_SECTIONS[target]
    result = {name: ["Not established from the collected evidence."] for name in names}
    result[names[0]] = declarations
    if target == "build":
        result[names[0]] = table(
            ["Manifest", "Script", "Command", "State", "Evidence"],
            scripts(ctx, r"build|compile|bundle"),
        )
        result[names[1]] = declarations
        result[names[2]] = checks
    elif target in {"deployment", "containers", "ci"}:
        result[next(name for name in names if "execution" in name.lower())] = checks
        if target == "deployment":
            result[names[1]] = declarations
    elif target == "security":
        result[names[0]] = [
            "Source indicators are not confirmed vulnerabilities. Severity is not invented."
        ] + declarations
        result[names[1]] = checks
    elif target == "authentication":
        result[names[1]] = declarations
        result[names[2]] = table(
            ["Method", "Path", "Handler/middleware", "Source", "Evidence"],
            [
                (r["method"], r["path"], r["handler"], r["source"], r["obs"])
                for r in routes(ctx)
                if re.search(patterns[target], r["block"], re.IGNORECASE)
            ],
        )
    if "gap" in names[-1].lower() or "risks" in names[-1].lower():
        result[names[-1]] = [
            "Uninspected configuration and unperformed checks remain not verified. No success or vulnerability is inferred from declarations alone."
        ]
    return result


def target_executions(ctx, target):
    patterns = {
        "dependencies": r"install|\bls\b|resolve|dependency|dependencies|pip.*check",
        "containers": r"docker|compose|container",
        "deployment": r"docker|compose|kubectl|helm|deploy|terraform|cloud",
        "ci": r"workflow|pipeline|ci|lint|test",
        "build": r"build|compile|bundle",
        "security": r"audit|security|vulnerab|scan|lint",
        "api": r"http|curl|requests|api|endpoint|supertest",
    }
    if target == "runtime":
        return execution_rows(
            ctx,
            tools={
                "start_process",
                "read_process",
                "check_port",
                "http_request",
                "execute_command",
            },
        )
    return execution_rows(ctx, patterns.get(target))


def validated_model_findings(ctx, markdown):
    """Admit scoped, cited analysis; never let model Markdown own report status."""
    if not markdown or len(markdown) > 16000 or "{{" in markdown or "<" in markdown:
        return []
    known = {o.id for o in ctx.observations}
    allowed = {"verification findings", "main conclusions", "findings", "executive summary"}
    allowed.update(name.lower() for t in ctx.targets for name in TARGET_SECTIONS[t])
    body = []
    for line in markdown.splitlines():
        if line.startswith("#"):
            if line.lstrip("# ").strip().lower() not in allowed:
                return []
        else:
            body.append(line)
    paragraphs = re.split(r"\n\s*\n", "\n".join(body).strip())
    accepted = []
    for paragraph in paragraphs:
        refs = set(re.findall(r"\bobs_[a-zA-Z0-9_]+\b", paragraph))
        if not refs or not refs <= known:
            return []
        if ctx.status != "VERIFIED" and re.search(
            r"\b(?:fully verified|all goals verified|verification succeeded)\b",
            paragraph,
            re.IGNORECASE,
        ):
            return []
        claims = set(re.findall(r"\bcl_[a-zA-Z0-9_]+\b", paragraph))
        if not claims <= {c.id for c in ctx.claims}:
            return []
        paths = re.findall(r"`([^`]+\.(?:py|[cm]?js|jsx|tsx?|json|ya?ml|toml))`", paragraph)
        if any(path.replace("\\", "/") not in {p for p, _, _ in ctx.sources} for path in paths):
            return []
        accepted.append(text(paragraph))
    return accepted


def executive_findings(ctx):
    findings = []
    for target in ctx.targets:
        if target == "architecture":
            for path, content, obs in ctx.sources:
                roles = [
                    label
                    for label, pattern in [
                        ("HTTP route declarations", r"\b(?:app|router)\.(?:get|post|put|delete)\("),
                        ("application initialization", r"\blisten\(|createApp\(|createRoot\("),
                    ]
                    if re.search(pattern, content)
                ]
                if roles:
                    findings.append(
                        f"- **Inferred:** `{text(path)}` contains {', '.join(roles)} (`{obs.id}`)."
                    )
        elif target == "api":
            for route in routes(ctx)[:4]:
                findings.append(
                    f"- **Observed source:** `{route['method']} {text(route['path'])}` in `{route['source']}` (`{route['obs']}`); {text(route['execution'])}."
                )
        elif target == "runtime":
            for label, ids in runtime_levels(ctx.observations).items():
                if ids:
                    findings.append(
                        f"- **Observed:** {label.lower()} supported at observation time ({', '.join(f'`{oid}`' for oid in ids)})."
                    )
        elif target == "dependencies":
            for path, pkg, obs in packages(ctx):
                count = len(
                    {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
                )
                findings.append(
                    f"- **Inferred:** `{text(path)}` declares {count} dependencies; installation is not inferred (`{obs.id}`)."
                )
        elif target == "build":
            findings.extend(
                f"- **Declared:** `{text(command)}` in `{path}` (`{oid}`); execution is assessed separately."
                for path, _, command, _, oid in scripts(ctx, r"build|compile|bundle")[:3]
            )
        else:
            findings.extend(
                f"- **Evidence-backed claim:** `{text(c.key)}` = `{text(c.value)}` (`{c.id}`); see provenance and contradictions below."
                for c in ctx.selected_claims(target)[:3]
                if ctx.claim_rows([c])
            )
    return findings[:6]


def render(inv, graph, observations, kg=None, goals=None):
    from wizard_kernel.storage import fs_store

    ctx = ReportContext.extract(inv, graph, observations, kg, goals)
    contract = report_contract(inv)
    targets = ctx.targets
    title = {
        "verify": "Verification Report",
        "investigate": "Investigation Report",
        "explain": "Explanation Report",
        "report": "Knowledge Report",
    }.get(inv.intent, "Investigation Report")
    title += " — " + (
        ", ".join("API" if t == "api" else "CI" if t == "ci" else t.title() for t in targets)
        or "Existing investigation state"
    )
    reason = inv.error or inv.last_event or "No final reason recorded"
    missing = [
        (g, goals.evidence_status(g.id, ctx.observations)["missing"])
        for g in ctx.goals
        if g.state != "satisfied"
    ]
    failures = [o for o in ctx.observations if not o.success]
    summary = f"{contract['operation']}. Requested subject: {text(inv.question or ', '.join(targets) or 'existing investigation state')}. "
    summary += f"The final investigation state is **{text(getattr(inv.state, 'value', inv.state))}**; report outcome: **{ctx.status}**."
    top = executive_findings(ctx) + (
        [
            f"- {g.name}: {'Verified according to Runtime criteria' if g.state == 'satisfied' else 'Not verified'}."
            for g in ctx.goals
        ]
        if inv.intent in {"verify", "report"}
        else []
    )
    if not top:
        top = ["- No goal result was established in the supplied investigation state."]
    next_step = (
        "Review the missing evidence and failed actions below before choosing the next check."
        if missing or failures
        else "Review the findings within the inspected scope; no additional check is implied by this report."
    )
    lines = [
        f"# {title}",
        "",
        f"> **Command:** `{text(inv.intent)}` · **Intent:** `{text(inv.question or ', '.join(targets) or 'existing state')}` · **Status:** `{ctx.status}` · **Investigation:** `{inv.id}`",
        "",
        "## Executive Summary",
        "",
        summary,
        "",
        "### Main conclusions",
        "",
        *top,
        "",
        "### Important gaps or failures",
        "",
        *(
            [
                f"- {text(g.name)}: missing {', '.join(req) or 'usable evidence'}."
                for g, req in missing
            ]
            + [f"- {text(failure_reason(o.payload))} (`{o.id}`)." for o in failures[-4:]]
            or ["- None recorded within the collected evidence."]
        ),
        "",
        "### Recommended next step",
        "",
        next_step,
        "",
        "## Investigation Overview",
        "",
    ]
    now = datetime.now(UTC)
    duration = max(0, int(((inv.finished_at or now) - inv.started_at).total_seconds()))
    lines += table(
        ["Field", "Value"],
        [
            ("Command", inv.intent),
            ("Intent", inv.question or ", ".join(targets) or "Existing state"),
            ("Repository", inv.repository_path),
            ("Investigation ID", inv.id),
            ("Started / generated", f"{inv.started_at} / {now}"),
            ("Duration", f"{duration // 60}m {duration % 60}s"),
            ("Final state / reason", f"{getattr(inv.state, 'value', inv.state)} — {reason}"),
            (
                "Goals verified",
                f"{sum(g.state == 'satisfied' for g in ctx.goals)} / {len(ctx.goals)}",
            ),
            ("Observations collected", len(ctx.observations)),
            (
                "Claims supported",
                sum(ctx.kg.trust_of(c.id) >= 0.6 for c in ctx.claims) if kg else 0,
            ),
            ("Budget used", f"{inv.budget_total - inv.budget_remaining} / {inv.budget_total}"),
        ],
    )
    for target in targets:
        lines += [
            "",
            f"## {'API' if target == 'api' else 'CI' if target == 'ci' else target.title()} — {'Verification' if inv.intent == 'verify' else 'Findings'}",
            "",
        ]
        sections = subject(ctx, target)
        for heading in TARGET_SECTIONS[target]:
            lines += [f"### {heading}", "", *sections[heading], ""]
        if inv.intent == "verify":
            lines += [
                "### Checks executed",
                "",
                *table(["Tool", "Target", "Outcome", "Evidence"], target_executions(ctx, target)),
                "",
            ]
    if not targets:
        lines += [
            "",
            "## Existing Investigation State",
            "",
            "Only supplied knowledge is rendered; this report performs no new investigation.",
            "",
            *table(["Goal", "State"], [(g.name, g.state) for g in ctx.goals]),
        ]
        if inv.targets:
            lines.append(
                "Targets without a registered subject renderer: "
                + text(", ".join(inv.targets))
                + ". No architecture fallback was applied."
            )
    lines += [
        "",
        "## Goal Verification",
        "",
        *table(
            ["Goal", "Required claims / evidence", "Result", "Reason"],
            [
                (
                    g.name,
                    ", ".join([*g.required_claim_types, *g.required_evidence]),
                    "Verified"
                    if g.state == "satisfied"
                    else "Failed"
                    if g.state == "failed"
                    else "Not verified",
                    ", ".join(goals.evidence_status(g.id, ctx.observations)["missing"])
                    or "Runtime goal state: " + g.state,
                )
                for g in ctx.goals
            ],
        ),
    ]
    for heading, state in [
        ("Verified", "satisfied"),
        ("Failed", "failed"),
        ("Not verified", "open"),
    ]:
        lines += [
            "",
            f"### {heading}",
            "",
            *(
                [f"- {text(g.name)} (`{g.id}`)." for g in ctx.goals if g.state == state]
                or ["- None recorded."]
            ),
        ]
    lines += ["", "## Findings", ""]
    selected = list({c.id: c for target in targets for c in ctx.selected_claims(target)}.values())
    if inv.intent == "report" and not targets:
        selected = [c for c in ctx.claims if c.claim_type != "FILE_READ"]
    findings = ctx.claim_rows(selected)
    lines += table(
        ["Finding / claim", "Value", "Trust", "Evidence", "Source", "Assessment"], findings[:12]
    )
    model = validated_model_findings(ctx, fs_store.read_text(inv.id, "model_report.md"))
    if model:
        lines += [
            "",
            "### Evidence-backed model analysis",
            "",
            "Model interpretation (inferred); Runtime criteria and final state above remain authoritative.",
            "",
            *model,
        ]
    lines += [
        "",
        "## Evidence and Provenance",
        "",
        "References retain their original investigation ownership. Repeated references are not independent evidence.",
        "",
    ]
    lines += table(
        ["Source / method", "Observation ID", "Outcome"],
        [
            (
                o.source_tool,
                o.id,
                "Observed source result"
                if o.success
                and o.source_tool in {"read_file", "search_files", "list_tree", "path_exists"}
                else "Observed execution result"
                if o.success
                else "Failed; not successful evidence",
            )
            for o in ctx.observations[:8]
        ],
    )
    lines += [
        "",
        *details(
            "Show complete evidence index",
            table(
                ["Observation ID", "Tool", "Source path", "Outcome"],
                [
                    (
                        o.id,
                        o.source_tool,
                        (o.payload.get("data") or {}).get("path", ""),
                        "Observed" if o.success else "Failed",
                    )
                    for o in ctx.observations
                ],
            )
            + [""]
            + table(
                [
                    "Claim / finding",
                    "Value",
                    "Trust",
                    "Observation ID",
                    "Source tier",
                    "Assessment",
                ],
                ctx.claim_rows(ctx.claims),
            ),
        ),
        "",
        "### Evidence quality",
        "",
        f"- Directly observed: {len(ctx.observations)} collected observations; successful and failed outcomes are distinguished.",
        "- Inferred: source and configuration declarations are not successful execution.",
        "- Missing evidence: "
        + (
            text(
                "; ".join(f"{g.name}: {', '.join(req) or 'usable evidence'}" for g, req in missing)
            )
            or "None recorded by the supplied goal engine."
        ),
        "",
        "## Contradictions and Uncertainty",
        "",
    ]
    owned_claims = {c.id for c in ctx.claims}
    contradictions = (
        [
            (r.from_id, r.to_id, "Unresolved")
            for r in kg.relationships()
            if r.rel_type == "CONTRADICTS" and r.from_id in owned_claims and r.to_id in owned_claims
        ]
        if kg
        else []
    )
    contradictory_evidence = (
        [
            (
                c.id,
                e.id,
                ", ".join(
                    oid for oid in e.observation_ids if oid in {o.id for o in ctx.observations}
                ),
            )
            for c in ctx.claims
            for e in kg.evidence_for(c.id)
            if e.support_type == "contradict"
            and any(o.id in e.observation_ids for o in ctx.observations)
        ]
        if kg
        else []
    )
    lines += (
        table(["Claim", "Contradictory claim", "Status"], contradictions)
        if contradictions
        else ["No contradiction relationships recorded within this investigation."]
    )
    if contradictory_evidence:
        lines += [
            "",
            *table(["Claim", "Contradicting evidence", "Observations"], contradictory_evidence),
        ]
    lines += [
        "",
        "## Runtime Activity",
        "",
        *details(
            "Show executed actions, failures and cleanup",
            table(["Tool", "Target / parameters", "Outcome", "Observation ID"], execution_rows(ctx))
            + ["", "### Failed actions", ""]
            + table(
                ["Action", "Goal", "Error / exit code", "Observation"],
                [
                    (o.source_tool, o.goal_id or "Unassigned", failure_reason(o.payload), o.id)
                    for o in failures
                ],
            )
            + [
                "",
                "### Cleanup",
                "",
                "Cleanup below is Runtime-reported, not an independent external check.",
            ]
            + [
                f"- {text(k.replace('_', ' '))}: {'not used' if v is None else 'confirmed by Runtime' if v is True else 'not confirmed' if v is False else text(v)}"
                for k, v in inv.cleanup.items()
            ],
        ),
        "",
        "## Limitations and Next Steps",
        "",
        "Scope is limited to observations collected for this investigation. Uninspected information and unperformed requested checks remain unverified.",
        "",
        next_step,
        "",
        "## Investigation Graph",
        "",
        *details(
            "Show investigation graph",
            table(
                ["Node ID", "Action type", "State", "Observation IDs"],
                [
                    (
                        n.id,
                        n.type,
                        n.state,
                        ", ".join(
                            id for id in n.observation_ids if id in {o.id for o in ctx.observations}
                        ),
                    )
                    for n in graph.all_nodes()
                ]
                if graph
                else [],
            ),
        ),
        "",
        "<sub>Generated by Wizard Investigation Kernel · Report schema 2</sub>",
        "",
    ]
    return "\n".join(lines)
