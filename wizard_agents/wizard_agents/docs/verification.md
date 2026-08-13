# Verification Agent

## Purpose

Verification is a critical reviewer. Given claims and their supporting /
contradicting evidence from the Claims Graph, it decides which claims are
well-supported, which are weak, which are contradicted, and which are
missing evidence entirely — then writes a structured Markdown assessment.
It never investigates, executes, or changes system state.

## Contract

See `app/contracts/verification.py` for the full Pydantic schemas.

### `VerificationInput`

| Field | Type | Notes |
|---|---|---|
| `investigation_id` | str | |
| `claims` | `list[ClaimInput]` | at least one required |
| `contradictory_evidence` | `list[EvidenceInput]` | evidence not tied to one claim_id |
| `relevant_goals` | `list[str]` | |
| `context` | str \| None | |
| `trust_information` | str \| None | optional, Runtime-supplied, read-only |

`ClaimInput` carries `claim_id`, `statement`, optional `node_id`, a list
of `EvidenceInput` (each tagged `supports_claim: bool` and a `source`:
`execution`, `documentation`, `static_analysis`, `configuration`, `other`),
and an optional read-only `trust_score`.

### `VerificationOutput`

| Field | Type | Notes |
|---|---|---|
| `investigation_id` | str | must match input |
| `overall_assessment` | str | |
| `reviewed_claims` | `list[str]` | every claim_id supplied must appear here |
| `supported_claims` | `list[str]` | |
| `weak_claims` | `list[VerificationFinding]` | claim_id + finding + severity + rationale |
| `contradictions` | `list[VerificationFinding]` | |
| `missing_evidence` | `list[str]` | free-text descriptions of gaps |
| `unresolved_claims` | `list[str]` | claim_ids left undecided |
| `recommended_additional_investigations` | `list[str]` | |
| `reasoning` | str | |
| `report_markdown` | str | the artifact Runtime writes to `verification_report.md` |

## Review heuristics

Both the mock provider and the prompt given to a real LLM apply the same
priorities:

- A claim with **contradicting evidence** → flagged as a `contradiction`
  and added to `unresolved_claims` (never `supported_claims`).
- A claim with **no evidence at all** → flagged in `missing_evidence` and
  added to `unresolved_claims`.
- A claim with only **non-execution** evidence (documentation, static
  analysis, configuration) → flagged as a `weak_claims` finding
  ("claims lacking execution evidence" / "claims based only on
  documentation").
- Everything else → `supported_claims`.

## What Verification must never do

- Execute commands
- Access repository files
- Modify the Claims Graph
- Modify trust
- Mark goals complete
- Invent evidence or claims not supplied in the input

## Validation pipeline

1. **Pydantic parsing** — LLM JSON must parse into `VerificationOutput`.
2. **Semantic validation** (`validate_verification_output`) —
   - `investigation_id` matches
   - every claim_id referenced anywhere in the output (`reviewed_claims`,
     `supported_claims`, `unresolved_claims`, `weak_claims`,
     `contradictions`) must exist in the input's `claims` — anything else
     is treated as a **hallucinated claim** and rejected
   - a claim cannot be both `supported` and `unresolved`, or both
     `supported` and `contradicted`
   - every claim supplied in the input must appear in `reviewed_claims`
     (nothing silently dropped)
   - `report_markdown` must start with a Markdown heading

Any failure raises `VerificationAgentError` (surfaced as HTTP 422 by the API).
