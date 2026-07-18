"""ObservationStore — append-only, immutable. Invariant 1 enforced here."""
import uuid
from datetime import datetime, timezone
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.storage import fs_store


class ObservationStore:
    def __init__(self, inv_id: str) -> None:
        self._inv_id = inv_id
        self._seq = 0
        self._cache: dict[str, Observation] = {}

    def append(self, *, node_id: str, source_tool: str, obs_type: str,
                payload: dict) -> Observation:
        """Create and persist an immutable Observation.
        Returns the frozen object — caller cannot mutate it."""
        obs = Observation(
            id=f"obs_{uuid.uuid4().hex[:8]}",
            investigation_id=self._inv_id,
            node_id=node_id,
            source_tool=source_tool,
            obs_type=obs_type,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
        self._seq += 1
        fs_store.write_observation(self._inv_id, self._seq, obs.model_dump())
        self._cache[obs.id] = obs
        return obs  # frozen — Pydantic ConfigDict(frozen=True)

    def get(self, obs_id: str) -> Observation | None:
        return self._cache.get(obs_id)

    def all(self) -> list[Observation]:
        return list(self._cache.values())

    def count(self) -> int:
        return len(self._cache)
