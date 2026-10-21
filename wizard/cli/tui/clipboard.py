"""System clipboard access for explicit intent-box copy and paste actions."""

import subprocess

import pyperclip


class ClipboardError(Exception):
    pass


def write_text(text):
    try:
        pyperclip.copy(text)
    except (pyperclip.PyperclipException, OSError, subprocess.SubprocessError):
        raise ClipboardError(
            "Copy failed. The system clipboard is unavailable."
        ) from None


def read_text():
    try:
        return pyperclip.paste()
    except (pyperclip.PyperclipException, OSError, subprocess.SubprocessError):
        raise ClipboardError(
            "Paste failed. The system clipboard is unavailable. Try your terminal's paste shortcut."
        ) from None
