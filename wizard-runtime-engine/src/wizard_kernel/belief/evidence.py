"""Evidence Engine — the only admission path for Claims into the Knowledge Graph.

Invariant 2: claims enter only through here. Never insert directly into the KG.

Key behaviour:
- One (obs_id, claim_type, key) triple can only be counted once — prevents double-counting trust.
- One obs_id CAN produce multiple DISTINCT claims (different claim_type or key).
- When a claim with the same (claim_type, key) already exists but with a DIFFERENT value,
  a new contradicting claim is created and a CONTRADICTS relationship is added to the KG.
- When the same (claim_type, key) AND same value already exists, the new observation
  is added as additional supporting evidence to the existing claim.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from wizard_kernel.contracts.claim import Claim
from wizard_kernel.contracts.evidence import Evidence, SupportType, SourceTier

if TYPE_CHECKING:
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph

log = logging.getLogger(__name__)


class EvidenceEngine:
    def __init__(self, knowledge_graph: "KnowledgeGraph") -> None:
        self._kg = knowledge_graph
        # Track (obs_id, claim_type, key) triples to prevent double-counting
        self._seen: set[tuple[str, str, str]] = set()

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
        """Create or reinforce a Claim atomically.

        Returns None if this exact (obs_id, claim_type, key) was already counted.
        Returns (Claim, Evidence) on success — caller uses this to count admitted claims.
        """
        sig = (obs_id, claim_type, key)
        if sig in self._seen:
            return None
        self._seen.add(sig)

        now = datetime.now(timezone.utc)
        existing = self._kg.find(claim_type, key)

        if existing:
            c = existing[0]
            if c.value != value:
                # Conflicting value — create a distinct contradicting claim
                # and link both with a CONTRADICTS edge so the report can surface it.
                log.debug(
                    "contradiction detected: %s:%s old=%r new=%r",
                    claim_type, key, c.value, value,
                )
                new_claim = Claim(
                    id=f"cl_{uuid.uuid4().hex[:8]}",
                    investigation_id=inv_id,
                    claim_type=claim_type,
                    key=key,
                    value=value,
                    created_at=now,
                )
                contra_ev = Evidence(
                    id=f"ev_{uuid.uuid4().hex[:8]}",
                    claim_id=new_claim.id,
                    observation_ids=[obs_id],
                    support_type="contradict",
                    source_tier=source_tier,
                    created_at=now,
                )
                self._kg.insert(new_claim, contra_ev)
                self._kg.add_relationship(new_claim.id, c.id, "CONTRADICTS")
                return new_claim, contra_ev
            else:
                # Same value — reinforce with additional supporting evidence
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

        # New claim — no prior claim with this (claim_type, key)
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
        # Invariant 2: only path into KG
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
        if sig in self._seen:
            return None
        self._seen.add(sig)
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
