"""The existing menu remains usable after the composer takes focus."""

from contextlib import contextmanager

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.formatted_text.utils import split_lines
from prompt_toolkit.input import DummyInput
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.output import DummyOutput

from wizard.cli.tui.app import INTENT, MENU, WORKING, WizardTUI


@contextmanager
def ui():
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        app = WizardTUI()
        app._geometry = lambda: (120, 44)
        yield app


def click(app, label, release=True):
    lines = list(split_lines(to_formatted_text(app._render_body())))
    row = next(i for i, line in enumerate(lines)
               if "".join(part[1] for part in line).strip(" │┃▸") == label)
    events = [MouseEventType.MOUSE_DOWN, MouseEventType.MOUSE_UP] if release else [MouseEventType.MOUSE_DOWN]
    for event in events:
        app.body.content.mouse_handler(MouseEvent(Point(8, row), event, MouseButton.LEFT, frozenset()))


@pytest.mark.parametrize("family", ["investigate", "verify", "report", "explain"])
def test_click_primary_command_after_input_focus_preserves_draft(family):
    with ui() as app:
        app.input.text = "my existing intent"
        app.app.layout.focus(app.input)
        app._status_input = True
        click(app, family)
        assert app.family == family
        if family != "report":
            assert app.state == MENU and app.menu_level == "target"
            assert app.app.layout.has_focus(app.body)
            app.app.layout.focus(app.input)
            click(app, app._targets()[0])
        assert app.state == INTENT and app.app.layout.has_focus(app.input)
        assert app.input.text == "my existing intent"
        assert not app._status_input


def test_mouse_down_returns_focus_for_existing_arrow_navigation():
    with ui() as app:
        app.input.text = "draft"
        app.app.layout.focus(app.input)
        click(app, "verify", release=False)
        assert app.state == MENU and app.selected == 1
        assert app.app.layout.has_focus(app.body)
        app._move(1)
        app._select()
        assert app.family == "report" and app.state == INTENT
        assert app.input.text == "draft"


def test_menu_mouse_handler_does_not_interfere_with_running_or_side_chat():
    with ui() as app:
        event = MouseEvent(Point(8, 4), MouseEventType.MOUSE_UP, MouseButton.LEFT, frozenset())
        app.state = WORKING
        assert not app._menu_mouse(event)
        app.state = MENU
        app.show_btw = True
        assert not app._menu_mouse(event)


def test_escape_returns_from_composer_to_existing_menu():
    with ui() as app:
        app.app.layout.focus(app.input)
        app._back()
        assert app.state == MENU and app.app.layout.has_focus(app.body)


def test_terminal_mouse_events_reach_menu_after_composer_focus():
    import asyncio

    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.input import create_pipe_input

    class Terminal(DummyOutput):
        def get_size(self):
            return Size(rows=44, columns=120)

    async def until(predicate):
        for _ in range(200):
            if predicate():
                return
            await asyncio.sleep(0.01)
        raise AssertionError("TUI did not update")

    async def run():
        with create_pipe_input() as keys, create_app_session(input=keys, output=Terminal()):
            app = WizardTUI()
            task = asyncio.create_task(app.app.run_async())
            try:
                await until(lambda: app.app.is_running and app.app.renderer._last_screen is not None)
                app.app.layout.focus(app.input)
                app.input.text = "keep my intent"
                app._status_input = True
                app.app.invalidate()
                await asyncio.sleep(0.1)
                screen = app.app.renderer._last_screen
                row, text = next((y, "".join(cells[x].char for x in range(120)))
                                 for y, cells in screen.data_buffer.items()
                                 if "".join(cells[x].char for x in range(120)).strip(" │┃▸") == "report")
                col = text.index("report")
                keys.send_text(f"\x1b[<0;{col + 1};{row + 1}M\x1b[<0;{col + 1};{row + 1}m")
                await until(lambda: app.state == INTENT)
                assert app.family == "report" and app.app.layout.has_focus(app.input)
                assert app.input.text == "keep my intent"
            finally:
                app.app.exit()
                await task
    asyncio.run(run())
