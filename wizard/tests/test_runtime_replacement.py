"""Service updates never require provider calls."""
from unittest.mock import Mock, patch

from wizard.cli.tui import services
from wizard.cli.display.usage import counter


def test_idle_old_runtime_is_replaced(tmp_path):
    spec = services.ServiceSpec("kernel", "Runtime", 8080, "/health", str(tmp_path),
        ("python",), env={"WIZARD_BUILD_ID": "new"})
    with patch.object(services, "healthy", side_effect=[True, False, True]), \
         patch.object(services, "service_build_id", return_value="old"), \
         patch.object(services, "_retire_idle_runtime", return_value=(True, "")) as retire, \
         patch.object(services, "port_open", return_value=False), \
         patch.object(services, "_spawn", return_value=Mock()) as spawn:
        assert services.ensure_service(spec, tmp_path).status == "started"
        retire.assert_called_once()
        spawn.assert_called_once()


def test_busy_old_runtime_is_not_replaced(tmp_path):
    spec = services.ServiceSpec("kernel", "Runtime", 8080, "/health", str(tmp_path),
        ("python",), env={"WIZARD_BUILD_ID": "new"})
    with patch.object(services, "healthy", return_value=True), \
         patch.object(services, "service_build_id", return_value="old"), \
         patch.object(services, "_retire_idle_runtime", return_value=(False, "Investigation running")), \
         patch.object(services, "_spawn") as spawn:
        assert services.ensure_service(spec, tmp_path).detail == "Investigation running"
        spawn.assert_not_called()


def test_usage_shows_both_provider_counts():
    text = counter({"total_tokens": 1500, "input_tokens": 1200, "output_tokens": 300}, compact=True)
    assert "↑ 1.20k / ↓ 300" in text
