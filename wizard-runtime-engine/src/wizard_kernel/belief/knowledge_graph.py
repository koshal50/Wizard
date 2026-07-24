"""Knowledge Graph — stores Claims (nodes) and typed Relationships (edges).
Claims enter only via EvidenceEngine. Kernel owns truth."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from wizard_kernel.contracts.claim import Claim
from wizard_kernel.contracts.evidence import Evidence
from wizard_kernel.storage import fs_store
from wizard_kernel.belief import trust as trust_engine

RelType = Literal["DEPENDS_ON", "USES", "CONTRADICTS", "PROVIDES", "RELATED"]


@dataclass
class Relationship:
    from_id: str
    to_id: str
    rel_type: RelType
    id: str = field(default_factory=lambda: f"rel_{uuid.uuid4().hex[:6]}")


class KnowledgeGraph:
    def __init__(self, inv_id: str) -> None:
        self._inv_id = inv_id
        self._claims: dict[str, Claim] = {}
        self._evidence: dict[str, list[Evidence]] = {}   # claim_id → evidences
        self._trust: dict[str, float] = {}               # claim_id → belief score
        self._rels: list[Relationship] = []

    # ── Claim management ──────────────────────────────────────────────────────

    def insert(self, claim: Claim, evidence: Evidence) -> None:
        """Insert a new Claim with its first Evidence. Only path claims enter."""
        self._claims[claim.id] = claim
        self._evidence.setdefault(claim.id, []).append(evidence)
        self._recompute_trust(claim.id)

    def add_evidence(self, claim_id: str, evidence: Evidence) -> float:
        """Add more evidence to an existing claim and recompute trust."""
        self._evidence.setdefault(claim_id, []).append(evidence)
        return self._recompute_trust(claim_id)

    def get(self, claim_id: str) -> Claim | None:
        return self._claims.get(claim_id)

    def find(self, claim_type: str, key: str) -> list[Claim]:
        return [c for c in self._claims.values()
                if c.claim_type == claim_type and c.key == key]

    def all_claims(self) -> list[Claim]:
        return list(self._claims.values())

    def trust_of(self, claim_id: str) -> float:
        return self._trust.get(claim_id, 0.0)

    def evidence_for(self, claim_id: str) -> list[Evidence]:
        return self._evidence.get(claim_id, [])

    def has_execution_evidence(self, claim_id: str) -> bool:
        return trust_engine.has_execution_evidence(self._evidence.get(claim_id, []))

    # ── Relationship management ───────────────────────────────────────────────

    def add_relationship(self, from_id: str, to_id: str, rel_type: RelType) -> None:
        if from_id in self._claims and to_id in self._claims:
            self._rels.append(Relationship(from_id=from_id, to_id=to_id, rel_type=rel_type))

    def relationships(self) -> list[Relationship]:
        return list(self._rels)

    # ── Persistence ───────────────────────────────────────────────────────────

    def persist(self) -> None:
        fs_store.write(self._inv_id, "knowledge_graph.json", {
            "claims": [c.model_dump() for c in self._claims.values()],
            "trust": self._trust,
            "evidence": {
                cid: [e.model_dump() for e in evs]
                for cid, evs in self._evidence.items()
            },
            "relationships": [
                {"id": r.id, "from": r.from_id, "to": r.to_id, "type": r.rel_type}
                for r in self._rels
            ],
        })

    def summary(self) -> dict[str, Any]:
        """Compact summary sent to Planner — never the full raw graph."""
        return {
            "claims_count": len(self._claims),
            "high_trust_claims": [
                {"type": c.claim_type, "key": c.key, "value": c.value,
                 "trust": self._trust.get(c.id, 0.0)}
                for c in self._claims.values()
                if self._trust.get(c.id, 0.0) >= 0.6
            ],
            "contradictions": [
                r.from_id for r in self._rels if r.rel_type == "CONTRADICTS"
            ],
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _recompute_trust(self, claim_id: str) -> float:
        evs = self._evidence.get(claim_id, [])
        score = trust_engine.compute(evs)
        self._trust[claim_id] = score
        return score
