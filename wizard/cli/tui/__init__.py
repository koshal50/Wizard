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

def run_tui(repo_path=None):
    """Choose a terminal owner before importing either UI framework."""
    import os
    if os.environ.get("WIZARD_UI", "textual") == "textual":
        try:
            from wizard.cli.tui.textual_app import run_native
        except ModuleNotFoundError as exc:
            if exc.name != "textual":
                raise
            print('Wizard needs its updated UI dependencies: pip install -e ".[tui]"')
            return
        run_native(project=repo_path)
    else:
        from wizard.cli.tui.app import run_tui as legacy
        legacy(repo_path)

__all__ = ["run_tui"]
