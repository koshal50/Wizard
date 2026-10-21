"""System clipboard access for explicit intent-box copy and paste actions."""

import subprocess

try:
    import pyperclip
except ImportError:
    pyperclip = None


class ClipboardError(Exception):
    pass


def write_text(text):
    if pyperclip is None:
        raise ClipboardError("System clipboard support is not installed. Use your terminal's copy shortcut.")
    try:
        pyperclip.copy(text)
    except (pyperclip.PyperclipException, OSError, subprocess.SubprocessError):
        raise ClipboardError(
            "Copy failed. The system clipboard is unavailable."
        ) from None


def read_text():
    if pyperclip is None:
        raise ClipboardError("System clipboard support is not installed. Use your terminal's paste shortcut.")
    try:
        return pyperclip.paste()
    except (pyperclip.PyperclipException, OSError, subprocess.SubprocessError):
        raise ClipboardError(
            "Paste failed. The system clipboard is unavailable. Try your terminal's paste shortcut."
        ) from None
