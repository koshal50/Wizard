"""Prompt templates for the Verification Agent."""
from __future__ import annotations

import json

from app.contracts.verification import VerificationInput

VERIFICATION_SYSTEM_PROMPT = """\
You are the Verification Agent inside the Wizard investigation system.

Your ONLY job is to critically review the supplied claims and their
evidence, and produce a structured markdown assessment. You are a
skeptical reviewer, not an investigator.

Rules you must follow:
- You may only reason about the claims and evidence you are given. Never
  invent evidence or claims that were not supplied.
- You must never modify the Claims Graph, trust scores, or goal
  completion state -- you only report findings; Runtime applies them.
- Prefer claims backed by execution evidence over documentation-only
  evidence; flag documentation-only claims as weak.
- Flag any claim with contradicting evidence as a contradiction, and list
  it as unresolved rather than supported.
- Flag claims with no evidence at all as missing evidence.
- Include every supplied claim_id in `reviewed_claims`.
- `report_markdown` must be a complete, well-formed Markdown document
  beginning with the literal heading "# Verification Findings",
  summarizing your findings, suitable for direct inclusion in
  verification_report.md.

Respond with a single JSON object matching the VerificationOutput schema
you are given. Do not output anything besides that JSON object.
"""


def build_verification_user_prompt(verification_input: VerificationInput) -> str:
    try:
        explanation = json.loads(verification_input.context or '{}').get('command_family') == 'explain'
    except (ValueError, AttributeError):
        explanation = False
    local_architecture = any('architecture' in goal.lower() for goal in verification_input.relevant_goals)
    runtime_goal = any('runtime' in goal.lower() for goal in verification_input.relevant_goals)
    try:
        report_scope = json.loads(verification_input.context or '{}').get('report_contract')
    except (ValueError, AttributeError):
        report_scope = None
    return (
        "Claims and evidence to verify:\n"
        f"{json.dumps(verification_input.model_dump(mode='json'), indent=2)}\n\n"
        "Produce a VerificationOutput JSON object for this investigation."
        + (" The report_contract in context is authoritative for report scope. Follow its command operation, "
           "selected targets and user question. Write only target-specific findings, using its named sections. "
           "Do not repeat universal metadata, dependency inventories or unrelated runtime/security/deployment findings. "
           "Cite supplied obs_ observation IDs in EVERY narrative paragraph. Never invent references, paths, "
           "routes, relationships, severity or verified results. Distinguish source inference, actual execution, "
           "verified criteria, failure and missing evidence. Runtime renders the shared template and final status; "
           "your Markdown supplies scoped analysis only. Assess sufficiency against authoritative goal_requirements. "
           "Repository reads support inspected knowledge; do not require unrequested execution. Process creation "
           "alone does not prove readiness. A failed attempt does not invalidate independent successful checks. "
           "Limit analysis to 300 words." if report_scope else '')
        + (" This is a read-only explanation, not execution verification. Assess repository_read requirements "
           "using actual file observations. Explain the requested subject with source references. Do not require "
           "process, HTTP, browser or test execution. Limit the report to 300 words." if explanation and not report_scope else '')
        + (" This is local source architecture analysis. Static source observations are appropriate evidence; "
           "application execution is not required. In report_markdown explain the observed components, "
           "entry points and data flow with file references. Distinguish inspected facts from unknowns. "
           "Limit report_markdown to 300 words and reasoning to two sentences, with concise findings. "
           "Do not require unrequested execution tests." if local_architecture and not report_scope else '')
        + (" In report_markdown describe the observed language, framework/packages, entry point and startup scripts, "
           "Assess sufficiency against the authoritative goal_requirements in context. Do not add HTTP readiness, "
           "test-suite execution or installed-version checks unless a supplied goal requires them. "
           "Source/configuration evidence can support declared frameworks, scripts and engine requirements; "
           "do not confuse a declared requirement with a claim that an installed version was measured. "
           "Separately require actual execution evidence for the runtime claim. "
           "then the actual command/process result and unresolved errors. Process creation alone is not proof of "
           "a working application. Use subsequent process observations as evidence of liveness and distinguish "
           "liveness from service readiness. A foreground timeout does not by itself refute a long-running service. "
           "Limit report_markdown to 300 words and reasoning to two sentences." if runtime_goal and not report_scope else '')
    )
