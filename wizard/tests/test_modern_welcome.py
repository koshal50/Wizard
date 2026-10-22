"""Local presentation checks: no services or model calls."""
from io import StringIO

from rich.console import Console

from wizard.cli.tui.modern import header, intent, welcome


def render(content, width=80):
    output = StringIO()
    Console(file=output, width=width, color_system=None).print(content)
    return output.getvalue()


def test_welcome_has_plain_guidance_and_no_panel_borders():
    text = render(welcome("family", ["verify", "report"], 0, None, "my-project"))
    assert "Choose a command" in text
    assert "Check whether it works" in text
    assert "verify" in text and "report" in text
    assert "/login" in text
    assert not any(char in text for char in "╭╮╰╯│─")


def test_header_treats_external_text_as_text():
    text = render(header("[red]project", "name\x1b[2J"))
    assert "[red]project" in text
    assert "\x1b" not in text


def test_narrow_intent_preserves_selected_command():
    text = render(intent("verify", "runtime", "project"), width=32)
    assert "verify runtime" in text
    assert "Leave it empty" in text


def test_preview_contains_rendered_text(tmp_path):
    from wizard.cli.tui.modern import preview
    path = tmp_path / "preview.svg"
    preview(path)
    assert "investigate" in path.read_text(encoding="utf-8")


def test_modern_layout_focuses_input_without_periodic_refresh(monkeypatch):
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import DummyInput
    from prompt_toolkit.output import DummyOutput
    from wizard.cli.tui.app import WizardTUI, INTENT
    monkeypatch.setenv("WIZARD_UI", "modern")
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        app = WizardTUI("project")
        assert app.app.layout.has_focus(app.input)
        assert app.app.refresh_interval is None
        assert app.composer is not app.input_frame
        app.input.text = "Check the application"
        assert app._on_accept(app.input.buffer) is True
        assert app.state == INTENT
        assert app.session is None
        assert app.input.text == "Check the application"


def test_pixel_character_fits_reserved_terminal_area():
    from wizard.cli.tui.reaper import pixels, terminal_pose
    grid = pixels()
    assert len(grid) % 2 == 0
    assert max(map(len, grid)) <= 40
    assert len(terminal_pose().plain.splitlines()) + 5 <= 27


def test_workspace_design_exports_all_views_without_external_assets(tmp_path):
    from xml.etree import ElementTree as ET
    from wizard.cli.tui.workspace_preview import VIEWS, export_all
    export_all(tmp_path)
    for view in VIEWS:
        path = tmp_path / ("cli-workspace-" + view + ".svg")
        root = ET.parse(path).getroot()
        assert root.attrib["viewBox"] == "0 0 1600 1000"
        assert "SAMPLE DATA" in path.read_text(encoding="utf-8")
        assert "<image" not in path.read_text(encoding="utf-8")
    assert "cli-workspace-live.svg" in (tmp_path / "cli-workspace-preview.html").read_text(encoding="utf-8")
