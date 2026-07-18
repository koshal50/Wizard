"""Architectural invariant: Observations are immutable after creation."""
import pytest
from datetime import datetime, timezone
from wizard_kernel.contracts.observation import Observation


def _obs(**kw) -> Observation:
    defaults = dict(
        id="obs_001", investigation_id="inv_001", node_id="node_001",
        source_tool="read_file", obs_type="file_content",
        payload={"content": "data"}, created_at=datetime.now(timezone.utc),
    )
    return Observation(**{**defaults, **kw})


def test_observation_immutable_id():
    obs = _obs()
    with pytest.raises(Exception):
        obs.id = "mutated"  # frozen=True must raise


def test_observation_immutable_payload():
    obs = _obs()
    with pytest.raises(Exception):
        obs.payload = {"injected": True}


def test_observation_fields_correct():
    obs = _obs(id="obs_xyz", obs_type="command_result")
    assert obs.id == "obs_xyz"
    assert obs.obs_type == "command_result"
