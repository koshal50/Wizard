"""Filesystem store — writes investigation state under .wizard/investigations/{id}/."""
import json
from pathlib import Path


def _inv_dir(inv_id: str) -> Path:
    return Path(".wizard") / "investigations" / inv_id


def ensure(inv_id: str) -> Path:
    d = _inv_dir(inv_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "observations").mkdir(exist_ok=True)
    return d


def write(inv_id: str, filename: str, data: dict | list) -> Path:
    p = ensure(inv_id) / filename
    p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return p


def read(inv_id: str, filename: str) -> dict | list | None:
    p = _inv_dir(inv_id) / filename
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def write_observation(inv_id: str, seq: int, data: dict) -> Path:
    p = ensure(inv_id) / "observations" / f"o_{seq:04d}.json"
    p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return p
