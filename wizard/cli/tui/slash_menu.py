"""Registry-backed slash completion at the composer's command position only."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout.containers import ConditionalContainer, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType


def slash_prefix(document: Document) -> str | None:
    """A single command token, with the cursor at its end; never a path or prose.

    Leading horizontal whitespace is allowed. Arguments and slashes elsewhere
    are intentionally left to the ordinary input/submission path.
    """
    if document.cursor_position != len(document.text):
        return None
    match = re.fullmatch(r"[ \t]*(/[a-zA-Z-]*)", document.text)
    return match.group(1) if match else None


class SlashCompleter(Completer):
    def __init__(self, commands: Mapping[str, str]):
        self.commands = commands

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        prefix = slash_prefix(document)
        if prefix is not None:
            for name, description in self.commands.items():
                if name.startswith(prefix):
                    yield Completion(
                        name, start_position=-len(prefix), display_meta=description
                    )


class _MenuControl(FormattedTextControl):
    def __init__(self, menu):
        self.menu = menu
        super().__init__(
            menu.fragments,
            get_cursor_position=lambda: Point(x=0, y=menu.selected),
            show_cursor=False,
        )

    def mouse_handler(self, mouse_event: MouseEvent):
        # Move the selected row too, so Window's cursor-based scrolling does not
        # snap a wheel scroll back to the old highlight on the next repaint.
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            self.menu.move(-1)
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self.menu.move(1)
            return None
        return NotImplemented


class SlashMenu:
    """A scrolling popup whose selection does not rewrite the user's draft.

    prompt_toolkit owns painting, scrollbar, clipping, and cursor-relative float
    placement. The composer owns selection and command submission.
    """

    def __init__(
        self,
        buffer: Buffer,
        completer: SlashCompleter,
        focused: Callable[[], bool],
        size: Callable[[], tuple[int, int]],
    ):
        self.buffer = buffer
        self.completer = completer
        self.focused = focused
        self.size = size
        self.entries: list[Completion] = []
        self.selected = 0
        self.dismissed = False
        self.control = _MenuControl(self)
        self.window = Window(
            content=self.control,
            height=self.height,
            wrap_lines=False,
            always_hide_cursor=True,
            right_margins=[ScrollbarMargin(display_arrows=True)],
            style="class:slash-menu",
        )
        self.container = ConditionalContainer(
            self.window, Condition(lambda: self.visible)
        )
        buffer.on_text_changed += self._changed
        buffer.on_cursor_position_changed += self._changed

    @property
    def visible(self) -> bool:
        return bool(self.entries) and not self.dismissed and self.focused()

    def height(self) -> int:
        return min(len(self.entries), max(1, min(8, self.size()[1] // 3)))

    def _changed(self, buffer: Buffer):
        self.entries = list(
            self.completer.get_completions(buffer.document, CompleteEvent())
        )
        self.selected = 0
        self.dismissed = False
        self.window.vertical_scroll = 0

    def open(self):
        self._changed(self.buffer)

    def dismiss(self):
        self.dismissed = True

    def move(self, delta: int):
        if self.entries:
            self.selected = (self.selected + delta) % len(self.entries)

    def apply(self):
        if self.visible:
            completion = self.entries[self.selected]
            self.buffer.apply_completion(completion)
            self.dismiss()

    def fragments(self):
        result = []
        name_width = max((len(entry.text) for entry in self.entries), default=0)
        for index, entry in enumerate(self.entries):
            style = (
                "class:slash-menu.selected"
                if index == self.selected
                else "class:slash-menu"
            )
            result.append(
                (
                    style,
                    " "
                    + entry.text.ljust(name_width)
                    + "  "
                    + entry.display_meta_text
                    + " ",
                )
            )
            if index + 1 < len(self.entries):
                result.append(("", "\n"))
        return result
