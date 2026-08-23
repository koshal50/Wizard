"""Report generator — Phase 5.

Spec (BUILD_PLAN.md Phase 5):
  1. Header — inv_id, date, duration, budget used, claims count
  2. Executive Summary — 1 paragraph from verified goals
  3. Detected Technologies table — from RUNTIME/FRAMEWORK claims
  4. Goals Summary table — goal name, state, brief
  5. Evidence Index — Claim | obs_id | source_tier | trust_score
  6. Contradictions — claims connected by CONTRADICTS edges in KG
  7. Unverified Areas — goals not yet satisfied

Rule: every paragraph that mentions a claim includes [evidence: obs_XXX].
      Claims with no observations are silently excluded from narrative.

This module has ZERO LLM logic. Pure deterministic projection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wizard_kernel.control.investigation_graph import InvestigationGraph
    from wizard_kernel.control.goals import GoalEngine
    from wizard_kernel.contracts.observation import Observation
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
    from wizard_kernel.session.investigation import Investigation


def generate(
    inv: "Investigation",
    graph: "InvestigationGraph",
    observations: "list[Observation]",
    kg: "KnowledgeGraph | None" = None,
    goals: "GoalEngine | None" = None,
) -> str:
    """Project verified investigation state into markdown. No LLM."""
    now = datetime.now(timezone.utc)
    budget_used = inv.budget_total - inv.budget_remaining
    duration_str = _duration(inv.created_at, now)

    # Build obs lookup for evidence citation
    obs_by_id: dict[str, "Observation"] = {o.id: o for o in observations}

    lines: list[str] = []

    # ─── 1. Header ────────────────────────────────────────────────────────────
    lines += [
        "# Verification Report",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| **Investigation ID** | `{inv.id}` |",
        f"| **Repository** | `{inv.repository_path}` |",
        f"| **Intent** | {inv.intent} |",
        f"| **Targets** | {', '.join(inv.targets) or '*(all)*'} |",
        f"| **Generated** | {now.strftime('%Y-%m-%d %H:%M UTC')} |",
        f"| **Duration** | {duration_str} |",
        f"| **Budget used** | {budget_used} / {inv.budget_total} nodes |",
        f"| **Observations** | {len(observations)} |",
        f"| **Claims verified** | {kg.summary()['claims_count'] if kg else 0} |",
        "",
        "---",
        "",
    ]

    # ─── 2. Executive Summary ─────────────────────────────────────────────────
    lines += ["## Executive Summary", ""]
    if kg:
        high_trust = [c for c in kg.all_claims() if kg.trust_of(c.id) >= 0.6]
        exec_claims = high_trust[:5]
        if exec_claims:
            summary_parts = []
            for c in exec_claims:
                evs = kg.evidence_for(c.id)
                obs_refs = _obs_refs(evs, obs_by_id)
                if obs_refs:
                    summary_parts.append(
                        f"**{c.claim_type}** `{c.key}` = `{c.value}` "
                        f"(trust {kg.trust_of(c.id):.2f}) {obs_refs}"
                    )
            if summary_parts:
                lines.append(
                    f"Investigation of `{inv.repository_path}` produced "
                    f"**{len(kg.all_claims())} verified claims** "
                    f"with {len(observations)} collected observations. "
                    f"High-confidence findings:"
                )
                lines.append("")
                for p in summary_parts:
                    lines.append(f"- {p}")
            else:
                lines.append(
                    "Investigation completed. All claims lack execution-tier "
                    "evidence — manual review recommended."
                )
        else:
            lines.append(
                "No claims reached the 0.6 belief threshold. "
                "Budget may have been insufficient or the repository structure "
                "was unrecognised."
            )
    else:
        lines.append("No knowledge graph available.")
    lines.append("")
    lines += ["---", ""]

    # ─── 3. Detected Technologies ─────────────────────────────────────────────
    lines += ["## Detected Technologies", ""]
    if kg:
        tech_claims = [
            c for c in kg.all_claims()
            if c.claim_type in ("RUNTIME", "FRAMEWORK", "PACKAGE", "DEPLOYMENT")
               and kg.trust_of(c.id) >= 0.5
        ]
        if tech_claims:
            lines += [
                "| Technology | Property | Value | Trust |",
                "|---|---|---|---|",
            ]
            for c in sorted(tech_claims, key=lambda x: kg.trust_of(x.id), reverse=True):
                evs = kg.evidence_for(c.id)
                obs_refs = _obs_refs(evs, obs_by_id)
                tier = _top_tier(evs)
                lines.append(
                    f"| `{c.claim_type}` | `{c.key}` | `{c.value}` "
                    f"| {_trust_bar(kg.trust_of(c.id))} {kg.trust_of(c.id):.2f} "
                    f"{obs_refs} |"
                )
        else:
            lines.append("*No technology claims reached confidence threshold.*")
    lines += ["", "---", ""]

    # ─── 4. Goals Summary ─────────────────────────────────────────────────────
    lines += ["## Goals Summary", ""]
    if goals:
        goal_list = goals.all()
        if goal_list:
            lines += [
                "| Goal | State | Progress |",
                "|---|---|---|",
            ]
            for g in goal_list:
                icon = "✅" if g.state == "satisfied" else ("❌" if g.state == "failed" else "⏳")
                lines.append(f"| {g.name} | {icon} {g.state} | {g.progress:.0%} |")
        else:
            lines.append("*No goals were tracked for this investigation.*")
    else:
        lines.append("*Goal engine not available.*")
    lines += ["", "---", ""]

    # ─── 5. Evidence Index ────────────────────────────────────────────────────
    lines += ["## Evidence Index", ""]
    if kg:
        all_claims = kg.all_claims()
        if all_claims:
            lines += [
                "| Claim | Key | Value | obs_id | source_tier | trust |",
                "|---|---|---|---|---|---|",
            ]
            for c in sorted(all_claims, key=lambda x: kg.trust_of(x.id), reverse=True):
                evs = kg.evidence_for(c.id)
                if not evs:
                    continue  # rule: claims with no observations excluded
                for ev in evs:
                    for oid in ev.observation_ids:
                        if oid in obs_by_id:
                            lines.append(
                                f"| `{c.claim_type}` | `{c.key}` | `{c.value}` "
                                f"| `{oid}` | {ev.source_tier} "
                                f"| {_trust_bar(kg.trust_of(c.id))} {kg.trust_of(c.id):.2f} |"
                            )
        else:
            lines.append("*No claims were produced.*")
    lines += ["", "---", ""]

    # ─── 6. Contradictions ────────────────────────────────────────────────────
    lines += ["## Contradictions", ""]
    contradictions_found = False
    if kg:
        contradict_rels = [r for r in kg.relationships() if r.rel_type == "CONTRADICTS"]
        if contradict_rels:
            contradictions_found = True
            lines += [
                "| Claim | Contradicted By | Belief | Disbelief |",
                "|---|---|---|---|",
            ]
            for rel in contradict_rels:
                c_from = kg.get(rel.from_id)
                c_to = kg.get(rel.to_id)
                if c_from and c_to:
                    from wizard_kernel.belief import trust as trust_engine
                    b = trust_engine.compute(kg.evidence_for(rel.from_id))
                    d = trust_engine.disbelief(kg.evidence_for(rel.from_id))
                    lines.append(
                        f"| `{c_from.claim_type}:{c_from.key}` "
                        f"| `{c_to.claim_type}:{c_to.key}` "
                        f"| {b:.2f} | {d:.2f} |"
                    )
        # Also catch claims with high disbelief even without explicit edges
        high_disbelief = [
            c for c in kg.all_claims()
            if _disbelief_of(kg, c.id) > 0.3
        ]
        if high_disbelief and not contradictions_found:
            contradictions_found = True
            lines += [
                "The following claims have significant contradicting evidence:",
                "",
                "| Claim | Key | Belief | Disbelief |",
                "|---|---|---|---|",
            ]
            for c in high_disbelief:
                b = kg.trust_of(c.id)
                d = _disbelief_of(kg, c.id)
                lines.append(f"| `{c.claim_type}` | `{c.key}` | {b:.2f} | {d:.2f} |")

    if not contradictions_found:
        lines.append("*No contradictions detected.*")
    lines += ["", "---", ""]

    # ─── 7. Unverified Areas ──────────────────────────────────────────────────
    lines += ["## Unverified Areas", ""]
    unverified = []
    if goals:
        unverified = [g for g in goals.all() if g.state != "satisfied"]
    if unverified:
        lines.append("The following investigation goals were not satisfied:")
        lines.append("")
        for g in unverified:
            lines.append(f"- **{g.name}** — state: `{g.state}` (progress: {g.progress:.0%})")
    elif kg and kg.all_claims():
        lines.append("*All tracked goals satisfied.*")
    else:
        lines.append("*Insufficient data — run with a higher budget or more specific targets.*")
    lines += ["", "---", ""]

    # ─── Investigation Graph ──────────────────────────────────────────────────
    lines += ["## Investigation Graph", ""]
    nodes = graph.all_nodes()
    if nodes:
        lines += [
            "| Node | Type | State |",
            "|---|---|---|",
        ]
        for n in nodes:
            lines.append(f"| `{n.id}` | {n.type} | {n.state} |")
    else:
        lines.append("*No nodes in investigation graph.*")

    lines += [
        "",
        "---",
        "",
        "*Generated by Wizard Investigation Kernel v0.1.0*",
    ]
    return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trust_bar(score: float) -> str:
    filled = round(score * 5)
    return "█" * filled + "░" * (5 - filled)


def _obs_refs(evidences: list, obs_by_id: dict) -> str:
    """Build [evidence: obs_XXX] citation string from evidences."""
    refs = []
    for ev in evidences:
        for oid in ev.observation_ids:
            if oid in obs_by_id:
                refs.append(f"[evidence: {oid}]")
    return " ".join(refs[:3])  # cap at 3 citations per claim


def _top_tier(evidences: list) -> str:
    """Return highest source_tier in evidences."""
    tiers = {e.source_tier for e in evidences}
    for t in ("execution", "config_parse", "documentation"):
        if t in tiers:
            return t
    return "unknown"


def _disbelief_of(kg: "KnowledgeGraph", claim_id: str) -> float:
    from wizard_kernel.belief import trust as trust_engine
    return trust_engine.disbelief(kg.evidence_for(claim_id))


def _duration(start: datetime, end: datetime) -> str:
    delta = end - start
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m {secs % 60}s"
