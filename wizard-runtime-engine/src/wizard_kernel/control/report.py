"""Report generator — Phase 5.

Spec (BUILD_PLAN.md Phase 5):
  1. Header — inv_id, date, duration, budget used, claims count
  2. Summary — the answer to the command that asked
  3. Detected Technologies table — from RUNTIME/FRAMEWORK claims
  4. Goals Summary table — goal name, state, brief
  5. Evidence Index — Claim | obs_id | source_tier | trust_score
  6. Contradictions — claims connected by CONTRADICTS edges in KG
  7. Unverified Areas — goals not yet satisfied

Rule: every paragraph that mentions a claim includes [evidence: obs_XXX].
      Claims with no observations are silently excluded from narrative.

**The report is written in the command's own terms.** `inv.intent` is the command
family and `inv.targets` are the words it was aimed at, and both are read here:
the title, the summary's heading, what the summary answers first, and which
claims lead it. A fixed template over four commands is how `verify runtime`,
`explain dependencies` and `report` came to print the same page — the run did
different work and the document said so nowhere.

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
        f"# {_FAMILY_TITLES.get(inv.intent, 'Report')}",
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
    # The heading is the command's own question, not a fixed label. Two runs that
    # were asked different things and print the same heading are two runs whose
    # reports cannot be told apart by reading them, which is exactly how four
    # commands came to have one summary between them.
    lines += [_summary_heading(inv), ""]
    if kg:
        high_trust = [c for c in kg.all_claims() if kg.trust_of(c.id) >= 0.6]
        # Which claim types the command's own target words name, in the shared
        # vocabulary. This is what makes `verify runtime` and `verify
        # dependencies` lead with different findings from the same repository:
        # the subject the user typed decides which claims are the answer.
        subject_types = _subject_types(inv.targets)
        lines += _lead(inv, kg, goals)
        lines.append("")
        # FILE_READ is excluded from the summary and only from the summary. That
        # a file was opened is a record of the Runtime's work, not something the
        # investigation found out — and the claims arrive in admission order, so
        # the reads (one per file, all at the same trust) took every one of the
        # five summary slots and the report led with a list of paths. The reader
        # asked what the project does; "we opened fourteen files" is not an
        # answer, and it buried the claims that were. The reads keep their place
        # in the Evidence Index below, where the audit belongs.
        exec_claims = _headline_claims(kg, high_trust, subject_types)
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
                lines.append(_findings_opener(kg, observations, subject_types))
                lines.append("")
                for p in summary_parts:
                    lines.append(f"- {p}")
            else:
                lines.append(
                    "Investigation completed. All claims lack execution-tier "
                    "evidence — manual review recommended."
                )
        else:
            # Two different situations used to share one message. A run that
            # read files and established nothing is not a run whose claims all
            # fell below the belief threshold — saying so would describe a
            # confidence problem where the real finding is that the
            # investigation never got past looking.
            if high_trust:
                lines.append(
                    f"Investigation of `{inv.repository_path}` read "
                    f"**{len(high_trust)} files** and established nothing beyond "
                    "them. No claim about how the project behaves reached "
                    "confidence — the run collected no evidence of that kind."
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
                "| Claim | Value | Contradicted By | Its Value | Belief | Disbelief |",
                "|---|---|---|---|---|---|",
            ]
            for rel in contradict_rels:
                c_from = kg.get(rel.from_id)
                c_to = kg.get(rel.to_id)
                if c_from and c_to:
                    from wizard_kernel.belief import trust as trust_engine
                    b = trust_engine.compute(kg.evidence_for(rel.from_id))
                    d = trust_engine.disbelief(kg.evidence_for(rel.from_id))
                    # The values are here because the keys cannot say which two
                    # claims these are. A key is a type and a subject, and two
                    # claims can share both while disagreeing — a `name` per
                    # package.json, a `current_url` per moment. Printed as keys
                    # alone those rows read as a claim contradicting itself,
                    # which is the one thing a contradiction cannot be; the
                    # values are what turn the row back into a statement about
                    # the project.
                    lines.append(
                        f"| `{c_from.claim_type}:{c_from.key}` "
                        f"| `{_claim_value(c_from)}` "
                        f"| `{c_to.claim_type}:{c_to.key}` "
                        f"| `{_claim_value(c_to)}` "
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
    # A report has no unverified areas — it verified nothing, by design, and a
    # list of goals under "not satisfied" would blame the repository for a
    # question the command never asked. The same goals are worth stating as
    # scope, which is what this heading says they are.
    reporting = inv.intent == "report"
    lines += ["## Not Checked" if reporting else "## Unverified Areas", ""]
    unverified = []
    if goals:
        unverified = [g for g in goals.all() if g.state != "satisfied"]
    if reporting:
        if unverified:
            lines.append(
                "A report runs nothing, so nothing below was established either "
                "way. These are the questions a `verify` on this repository would "
                "ask:"
            )
            lines.append("")
            for g in unverified:
                lines.append(f"- **{g.name}**")
        else:
            lines.append(
                "A report runs nothing. Every goal it tracked was answerable by "
                "reading, and each is listed as satisfied above."
            )
    elif unverified:
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

#: What the document calls itself, per command family.
#:
#: The title is the first thing a reader sees and it was the same four words for
#: four different commands: a `report`, which runs nothing at all, was headed
#: "Verification Report", and an `explain` answered under a heading that claimed
#: something had been verified. The family is a field the run already carries, so
#: this is a projection of the request and not a guess about its content.
_FAMILY_TITLES = {
    "verify": "Verification Report",
    "explain": "Explanation",
    "report": "Repository Report",
    "investigate": "Investigation Report",
}

#: The executive summary's heading, per command family — the question that
#: command asked. `verify` asks a question with a yes-or-no answer and `report`
#: asks a descriptive one that has no answer at all; a fixed heading over both
#: is a heading that describes neither.
_FAMILY_HEADINGS = {
    "verify": "Verdict",
    "explain": "Explanation",
    "report": "What This Repository Is",
    "investigate": "What Was Found",
}

#: The claim types the acted/read distinction is drawn from. A claim in one of
#: these exists only because the run *did* something — a command was executed, or
#: a control was pressed or typed into. Everything else in the graph is the run
#: reading what the system already says about itself.
_ACTED_CLAIM_TYPES = frozenset({"EXECUTION", "INTERACTION"})

_HEADLINE_COUNT = 5


def _subject_types(targets: list) -> set[str]:
    """The claim types the command's own target words name.

    Read from the shared goal vocabulary in `ports/goal_policy.py` rather than
    from a second list here, so `verify runtime` and `verify dependencies` cannot
    come to disagree with the planner about what "runtime" means — the plan and
    the summary are two readings of one table.

    Empty for a target the vocabulary does not know (`architecture` is a subject,
    not a probe), which is what makes the ordering fall back to the rules in
    `_headline_claims` rather than order by nothing.
    """
    from wizard_kernel.ports.goal_policy import goal_evidence_for, goals_named_by

    types: set[str] = set()
    for name in goals_named_by([str(t) for t in targets]):
        types.update(goal_evidence_for(name).required_claim_types)
    return types


def _named_by_subject(claim, subject_types: set[str]) -> bool:
    """Whether this claim is one of the ones the command asked for."""
    return bool(subject_types) and claim.claim_type in subject_types


def _summary_heading(inv) -> str:
    """`## Verdict — runtime`, in the command's own words.

    The target is appended rather than substituted: the family says what kind of
    answer the reader is looking at, and the target says what it is an answer
    about. `verify runtime` and `verify dependencies` print different headings
    for the same reason they plan different goals.
    """
    base = _FAMILY_HEADINGS.get(inv.intent, "What Was Found")
    subject = ", ".join(str(t) for t in (inv.targets or ()))
    return f"## {base} — {subject}" if subject else f"## {base}"


def _lead(inv, kg, goals) -> list[str]:
    """The paragraph that answers the command's own question.

    One template for four commands is what made every run's summary read the
    same. `verify runtime` and `report` are not asking the same thing, so the
    summary cannot open with the same sentence and still be a summary of either.
    Each branch below states the thing that command was run to establish before
    it lists anything, and every sentence in every branch is a projection of goal
    states and claim counts — there is no branch that can say more than the run
    supports.
    """
    claims = kg.all_claims() if kg else []
    tracked = goals.all() if goals else []
    family = inv.intent

    if family == "report":
        # The one thing a reader of a report must not be left to infer is that
        # nothing was run. Said first, because every "not established" further
        # down the page means "outside what a report does" and not "looked at and
        # found wanting".
        out = [
            f"This is a report on `{inv.repository_path}`: it describes what the "
            f"repository is and runs nothing. **{len(claims)} claims** were "
            "projected from it, all read from files or the repository's own "
            "declarations."
        ]
        acted = [c for c in claims if c.claim_type in _ACTED_CLAIM_TYPES]
        if acted:
            # Stated rather than asserted away. A report is not supposed to
            # execute anything, so if it did, that is the finding.
            out += ["", f"*{len(acted)} claim(s) came from something being run, "
                        "which a report does not ask for.*"]
        return out

    if family == "verify" and tracked:
        satisfied = [g for g in tracked if g.state == "satisfied"]
        settled = [g for g in tracked if g.state == "failed"]
        rest = [g for g in tracked if g.state not in ("satisfied", "failed")]
        if not satisfied and not rest:
            head = (f"**Not proved.** None of the {len(tracked)} goal(s) this "
                    "command set out to establish were satisfied, and each one "
                    "failed against evidence rather than going unanswered.")
        elif not rest and not settled:
            head = (f"**Proved.** All {len(tracked)} goal(s) this command set out "
                    "to establish are satisfied.")
        else:
            head = (f"**Partly proved.** {len(satisfied)} of {len(tracked)} "
                    "goal(s) satisfied.")
        out = [head, ""]
        for g in tracked:
            mark = {"satisfied": "✓", "failed": "✗"}.get(g.state, "·")
            out.append(f"- {mark} **{g.name}** — `{g.state}` ({g.progress:.0%})")
        return out

    if family == "explain":
        subject = ", ".join(str(t) for t in (inv.targets or ())) or "the repository"
        found = len(claims)
        if not found:
            return [
                f"Nothing was established about {subject}: the run collected no "
                "claims at all, so there is nothing to explain and this is not an "
                "explanation that came up empty."
            ]
        return [
            f"Asked what {subject} is, the run established **{found} claims** "
            f"about `{inv.repository_path}`. What it could not establish is listed "
            "under *Unverified Areas*."
        ]

    # investigate, and the default: the broad question, answered with what the
    # run went and got.
    acted = [c for c in claims if c.claim_type in _ACTED_CLAIM_TYPES]
    out = [f"Investigation of `{inv.repository_path}` produced **{len(claims)} "
           "claims**."]
    if acted:
        out.append("")
        out.append(f"{len(acted)} of them are the run's own actions against the "
                   "system rather than a reading of it, and those lead below.")
    return out


def _findings_opener(kg, observations, subject_types: set[str]) -> str:
    """The sentence introducing the headline list, in the command's own terms."""
    count = len(kg.all_claims())
    if subject_types:
        named = ", ".join(sorted(subject_types))
        return (f"Led by the findings that answer the target — claims of type "
                f"**{named}** — across **{count} claims** and "
                f"{len(observations)} observations:")
    return (f"**{count} claims** from {len(observations)} collected observations. "
            "High-confidence findings:")


def _headline_claims(kg: "KnowledgeGraph", claims: list,
                     subject_types: "set[str] | None" = None) -> list:
    """The claims the Executive Summary leads with, in the order it should lead.

    Admission order was the only ordering here, and it is the one order that
    guarantees the summary is wrong. A run works through its plan in sequence —
    reads first, then the web, then commands — so the claims admitted first are
    always the manifest parses, and the five summary slots were always spent
    before the run had done anything. On an investigation asked to operate an
    application, the report opened with `PACKAGE name = taskboard` and the
    browser's own account of pressing the sign-in button arrived after the cut
    and never appeared at all. The one finding the run had gone and got was the
    one thing the summary did not mention.

    Four rules put it there, and none is a preference about subject matter:

    1. A claim the run had to *act* to obtain outranks one it read off. That is
       what the source tier already means — `EXECUTION` and `INTERACTION` claims
       cost an action against the real system, a `config_parse` claim cost a
       file read. The reader is owed the expensive ones first.
    2. One row per distinct claim. A finding re-observed is the same finding:
       eight `WEB current_url` rows are one fact about where the browser ended
       up, and listing them separately is how they took every slot between them
       and pushed the findings out. The Evidence Index below keeps every
       sighting, which is where an audit belongs.
    3. A claim that carries a value outranks one whose value is `True`. `True`
       is the value that says nothing the key has not already said: an
       `interacted:<control>` claim records that a control was touched and no
       more, while `effect:<control>` and `field_value:<control>` say what
       happened when it was. Ordering by arrival put the bookkeeping first and
       spent the summary's last slot on "we touched the password field" while
       the press of the submit button — the one claim that says whether any of
       it worked — fell off the end. The rule is type-agnostic on purpose; the
       report has no business knowing what a selector is, and does not need to.

    Ties keep admission order, so within a rank the summary still reads in the
    order things happened.

    `subject_types` is the rule the command supplies, and it is FIRST rather than
    last: among the claims the run has, one whose type the user's own target word
    named leads. A reader who typed `verify runtime` asked about the runtime, and
    a claim about the runtime answers that question while everything else the run
    did — however expensive it was to get — is context. Ranked *below* the acted
    rule instead, the subject claim landed in the same slot for `verify runtime`
    and `verify dependencies` and the two summaries came out identical but for
    one word; the subject is the question, so it leads.

    It is a *preference and never a filter*: a command whose target names nothing
    the vocabulary knows (`explain architecture`) gets the three rules below and
    no more, and a claim the subject named that the run never established cannot
    appear, because nothing in this function can admit a claim — it can only
    order the ones the run actually got.

    FILE_READ is dropped here rather than by the caller so the rules that decide
    what a headline is stay in one place — see the caller for why a read is a
    record of the Runtime's work rather than something it found out.
    """
    subject_types = subject_types or set()
    ranked = sorted(
        (c for c in claims if c.claim_type != "FILE_READ"),
        key=lambda c: (
            0 if _named_by_subject(c, subject_types) else 1,
            0 if c.claim_type in _ACTED_CLAIM_TYPES else 1,
            _TIER_RANK.get(_top_tier(kg.evidence_for(c.id)), len(_TIER_RANK)),
            1 if c.value is True else 0,
        ),
    )
    seen: set[tuple[str, str]] = set()
    headlines: list = []
    for claim in ranked:
        mark = (claim.claim_type, claim.key)
        if mark in seen:
            continue
        seen.add(mark)
        headlines.append(claim)
        if len(headlines) >= _HEADLINE_COUNT:
            break
    return headlines


#: Tier order for ranking, strongest evidence first. A tier absent from this map
#: sorts last rather than raising: an unrecognised tier is not a reason to fail
#: a report.
_TIER_RANK = {"execution": 0, "config_parse": 1, "documentation": 2}


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


def _claim_value(claim) -> str:
    """A claim's value as one table cell: short, and never empty.

    Long values are cut and lists are joined, because a cell that wraps to forty
    lines stops being a table. "(none)" rather than "" for a claim with no value:
    an empty cell reads as a rendering bug, and the absence is real information —
    a claim can assert that something exists without saying anything more.
    """
    value = getattr(claim, "value", None)
    if value is None:
        return "(none)"
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text[:80] + "…" if len(text) > 80 else text


def _disbelief_of(kg: "KnowledgeGraph", claim_id: str) -> float:
    from wizard_kernel.belief import trust as trust_engine
    return trust_engine.disbelief(kg.evidence_for(claim_id))


def _duration(start: datetime, end: datetime) -> str:
    delta = end - start
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m {secs % 60}s"
