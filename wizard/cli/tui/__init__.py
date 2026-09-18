"""Wizard interactive TUI — the full-screen front door for bare `wizard`.

A prompt_toolkit application (MENU → INTENT → WORKING → RESULT) that reuses the
existing CLI pipeline (build_intent → InvestigationRequest → the real
`stream_events` HTTP client). Rich builds the visuals; prompt_toolkit owns the
screen and keyboard.

There is no splash: the identity panel at the top of the first frame *is* the
welcome, and the command menu is already open under it, so the first keystroke
is a choice rather than a way past a title card.
"""

from __future__ import annotations

from wizard.cli.tui.app import run_tui

__all__ = ["run_tui"]
