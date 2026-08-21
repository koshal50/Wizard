"""Stage 7a — Context Cache (architecture §12).

Avoids rebuilding identical context when the same agent is called for the same
node and state has not changed. The cache key embeds a state_version that is
bumped (and the whole cache cleared) on every state mutation, so a stale
projection can never be served after the knowledge graph, goals, or budget move.
"""
from __future__ import annotations

from wizard_kernel.context.sections import ContextSection


class ContextCache:
    def __init__(self, max_size: int = 32) -> None:
        self._cache: dict[str, list[ContextSection]] = {}
        self._max_size = max_size
        self.state_version = 0

    def _key(self, agent_type: str, node_id: str) -> str:
        return f"{agent_type}:{node_id}:{self.state_version}"

    def get(self, agent_type: str, node_id: str) -> list[ContextSection] | None:
        return self._cache.get(self._key(agent_type, node_id))

    def set(self, agent_type: str, node_id: str, sections: list[ContextSection]) -> None:
        self._cache[self._key(agent_type, node_id)] = sections
        self._evict()

    def invalidate(self) -> None:
        """Called on every state mutation: bump version and drop all entries."""
        self.state_version += 1
        self._cache.clear()

    def _evict(self) -> None:
        # Bounded cache — drop oldest insertions first (dicts keep insertion order,
        # a native language guarantee since 3.7; no LRU library needed).
        while len(self._cache) > self._max_size:
            self._cache.pop(next(iter(self._cache)))
