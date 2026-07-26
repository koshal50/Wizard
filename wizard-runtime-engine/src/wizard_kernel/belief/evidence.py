"""Evidence Engine — the only admission path for Claims into the Knowledge Graph.
Invariant 2: claims enter only through here. Never insert directly into the KG."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from wizard_kernel.contracts.claim import Claim
from wizard_kernel.contracts.evidence import Evidence, SupportType, SourceTier

if TYPE_CHECKING:
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph


class EvidenceEngine:
    def __init__(self, knowledge_graph: "KnowledgeGraph") -> None:
        self._kg = knowledge_graph
        # Track obs_ids already used — prevents double-counting (invariant 2)
        self._seen_obs: set[str] = set()

    def admit(
        self,
        *,
        inv_id: str,
        claim_type: str,
        key: str,
        value: Any,
        obs_id: str,
        support_type: SupportType,
        source_tier: SourceTier,
        node_id: str,
    ) -> tuple[Claim, Evidence] | None:
        """Create Claim + Evidence atomically and insert into the Knowledge Graph.
        Returns None if obs_id was already counted (dedup guard)."""
        # Track by obs_id + claim signature so one observation can produce multiple distinct claims
        sig = (obs_id, claim_type, key)
        if sig in self._seen_obs:
            return None
        self._seen_obs.add(sig)

        now = datetime.now(timezone.utc)
        
        # Check if claim already exists
        existing = self._kg.find(claim_type, key)
        if existing:
            # For simplicity, pick the first match. If value differs, it might be a contradiction.
            c = existing[0]
            if c.value != value:
                support_type = "contradict"
            ev = Evidence(
                id=f"ev_{uuid.uuid4().hex[:8]}",
                claim_id=c.id,
                observation_ids=[obs_id],
                support_type=support_type,
                source_tier=source_tier,
                created_at=now,
            )
            self._kg.add_evidence(c.id, ev)
            return c, ev

        claim = Claim(
            id=f"cl_{uuid.uuid4().hex[:8]}",
            investigation_id=inv_id,
            claim_type=claim_type,
            key=key,
            value=value,
            created_at=now,
        )
        evidence = Evidence(
            id=f"ev_{uuid.uuid4().hex[:8]}",
            claim_id=claim.id,
            observation_ids=[obs_id],
            support_type=support_type,
            source_tier=source_tier,
            created_at=now,
        )
        self._kg.insert(claim, evidence)
        return claim, evidence

    def add_supporting_evidence(
        self,
        claim_id: str,
        obs_id: str,
        source_tier: SourceTier,
    ) -> float | None:
        """Add more evidence to an existing claim. Returns new trust score."""
        claim = self._kg.get(claim_id)
        if not claim:
            return None
        sig = (obs_id, claim.claim_type, claim.key)
        if sig in self._seen_obs:
            return None
        self._seen_obs.add(sig)
        now = datetime.now(timezone.utc)
        ev = Evidence(
            id=f"ev_{uuid.uuid4().hex[:8]}",
            claim_id=claim_id,
            observation_ids=[obs_id],
            support_type="support",
            source_tier=source_tier,
            created_at=now,
        )
        return self._kg.add_evidence(claim_id, ev)
