"""Wizard interactive TUI — the full-screen front door for bare `wizard`.

A prompt_toolkit application (SPLASH → MENU → INTENT → WORKING → RESULT) that
reuses the existing CLI pipeline (build_intent → InvestigationRequest → the real
`stream_events` HTTP client). Rich builds the visuals; prompt_toolkit owns the
screen and keyboard.
"""

from __future__ import annotations

from wizard.cli.tui.app import run_tui

__all__ = ["run_tui"]
