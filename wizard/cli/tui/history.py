"""Activity history — persists investigation runs for the "Recent activity" panel.

Stores a JSON-lines file at `output/wizard_history.json` inside the project.
Each line records one investigation launch with family, target, intent,
timestamp, and final status. The TUI reads the last 3 entries on startup
for the "Recent activity" section of the top panel.

Format (one JSON object per line):
    {"family": "investigate", "target": "architecture", "intent": "",
     "timestamp": "2026-09-13T14:03:00", "status": "completed"}
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# History file location — output/ in the project root (cwd at startup)
# ---------------------------------------------------------------------------
def _history_path() -> Path:
    """Return the path to the history file, creating output/ if needed."""
    output_dir = Path(os.getcwd()) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "wizard_history.json"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class HistoryEntry:
    """One past investigation run."""

    family: str                    # "investigate" | "verify" | "report" | "explain"
    target: str | None             # e.g. "architecture", None for report
    intent: str                    # free-text intent the user typed (may be empty)
    timestamp: str                 # ISO 8601
    status: str                    # "completed" | "failed" | "engine_unavailable" | "cancelled"

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "target": self.target,
            "intent": self.intent,
            "timestamp": self.timestamp,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> HistoryEntry:
        return cls(
            family=d.get("family", "?"),
            target=d.get("target"),
            intent=d.get("intent", ""),
            timestamp=d.get("timestamp", ""),
            status=d.get("status", "?"),
        )

    def display_line(self) -> str:
        """Build a human-readable one-line summary for the Recent activity panel.

        Examples:
            "investigate · architecture — Sep 13, 14:03"
            "verify · dependencies — Sep 12, 09:41"
            "report — Sep 11, 22:15"
        """
        # Parse timestamp for friendly display
        try:
            dt = datetime.fromisoformat(self.timestamp)
            date_str = dt.strftime("%b %d, %H:%M")
        except (ValueError, TypeError):
            date_str = self.timestamp[:16] if self.timestamp else "unknown"

        if self.target:
            label = f"{self.family} · {self.target}"
        else:
            label = self.family

        return f"{label} — {date_str}"


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------
def load_recent(count: int = 3) -> list[HistoryEntry]:
    """Load the most recent `count` history entries.

    Returns newest-first. If the file doesn't exist or is empty, returns [].
    Silently ignores malformed lines.
    """
    path = _history_path()
    if not path.exists():
        return []

    entries: list[HistoryEntry] = []
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                entries.append(HistoryEntry.from_dict(d))
            except (json.JSONDecodeError, KeyError):
                continue
    except OSError:
        return []

    # Return the last `count` entries, newest first
    return list(reversed(entries[-count:]))


def save_entry(entry: HistoryEntry) -> None:
    """Append one history entry to the log file."""
    path = _history_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")
    except OSError:
        pass  # silently fail — history is not critical


def record_run(
    family: str,
    target: str | None,
    intent: str = "",
    status: str = "completed",
) -> None:
    """Record a completed investigation run in the history file."""
    entry = HistoryEntry(
        family=family,
        target=target,
        intent=intent,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=status,
    )
    save_entry(entry)
