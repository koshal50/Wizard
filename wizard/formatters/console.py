"""Shared Rich console instance, theme, and output helpers.

All terminal output flows through this module to ensure consistent
styling and color support detection.
"""

from __future__ import annotations

import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Ensure UTF-8 output on Windows
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    # Set console output encoding to UTF-8
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        # Enable UTF-8 mode on Windows console
        os.system("chcp 65001 >nul 2>&1")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Wizard Color Palette
# ---------------------------------------------------------------------------
WIZARD_THEME = Theme({
    # Brand
    "wizard.brand": "bold #8B5CF6",          # Violet / Purple
    "wizard.accent": "bold #6366F1",         # Indigo
    "wizard.subtle": "#A78BFA",              # Light purple

    # Status
    "wizard.success": "bold #10B981",        # Emerald green
    "wizard.warning": "bold #F59E0B",        # Amber
    "wizard.error": "bold #EF4444",          # Red
    "wizard.info": "bold #3B82F6",           # Blue

    # Structure
    "wizard.header": "bold #F8FAFC",         # Near-white
    "wizard.label": "bold #94A3B8",          # Slate gray
    "wizard.value": "#E2E8F0",              # Light slate
    "wizard.muted": "#64748B",              # Muted gray
    "wizard.dim": "dim #475569",            # Dark slate

    # Health
    "wizard.health.good": "bold #10B981",
    "wizard.health.ok": "bold #F59E0B",
    "wizard.health.poor": "bold #EF4444",

    # Misc
    "wizard.path": "underline #818CF8",      # Indigo underlined
    "wizard.number": "bold #60A5FA",         # Light blue
    "wizard.tag": "bold #34D399",            # Emerald tag
})

# ---------------------------------------------------------------------------
# Shared Console — force_terminal ensures color output even on legacy Windows
# ---------------------------------------------------------------------------
console = Console(theme=WIZARD_THEME, highlight=False)

# ---------------------------------------------------------------------------
# ASCII-safe Icons (no emoji — works on all terminals including Windows cmd)
# ---------------------------------------------------------------------------
ICON_CHECK = "[wizard.success]+[/]"
ICON_CROSS = "[wizard.error]x[/]"
ICON_WARN = "[wizard.warning]![/]"
ICON_INFO = "[wizard.info]*[/]"
ICON_BULLET = "[wizard.muted]-[/]"
ICON_STAR = "[wizard.brand]*[/]"
ICON_ARROW = "[wizard.accent]>[/]"

# Section title prefixes (ASCII-safe)
SEC_REPO = "[::] Repository Information"
SEC_LANG = "[::] Languages"
SEC_FRAMEWORK = "[::] Frameworks"
SEC_PKGMGR = "[::] Package Managers"
SEC_STRUCTURE = "[::] Project Structure"
SEC_CONFIG = "[::] Configuration Files"
SEC_HEALTH = "[::] Repository Health"
SEC_STATS = "[::] Statistics"
SEC_WARNINGS = "[::] Observations"
SEC_SUMMARY = "[::] Analysis Summary"
SEC_DEPS_OVERVIEW = "[::] Dependency Overview"
SEC_DEPS_LIST = "[::] Dependencies"
SEC_DEPS_DUP = "[::] Duplicate Dependencies"
SEC_DEPS_UNUSED = "[::] Potentially Unused"
SEC_DEPS_MISSING = "[::] Possibly Missing"
SEC_DEPS_ISSUES = "[::] Manifest Issues"
SEC_DEPS_TREE = "[::] Dependency Tree"
SEC_DEPS_SUMMARY = "[::] Dependency Insights Summary"

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
WIZARD_BANNER = r"""
 __        ___                  _
 \ \      / (_)______ _ _ __ __| |
  \ \ /\ / /| |_  / _` | '__/ _` |
   \ V  V / | |/ / (_| | | | (_| |
    \_/\_/  |_/___\__,_|_|  \__,_|
"""


def print_banner() -> None:
    """Print the Wizard ASCII art banner."""
    banner_text = Text(WIZARD_BANNER, style="wizard.brand")
    tagline = Text("  Repository Intelligence CLI", style="wizard.subtle")
    console.print(banner_text, end="")
    console.print(tagline)
    console.print()


# ---------------------------------------------------------------------------
# Section Helpers
# ---------------------------------------------------------------------------

def print_header(title: str, subtitle: str = "") -> None:
    """Print a styled section header."""
    if subtitle:
        header_str = f"  [wizard.header]{title}[/]  {subtitle}"
    else:
        header_str = f"  [wizard.header]{title}[/]"
    console.print()
    console.print(Panel.fit(
        header_str,
        border_style="wizard.accent",
        padding=(0, 1),
    ))


def print_section(title: str) -> None:
    """Print a subsection title."""
    console.print()
    console.print(f"  [wizard.accent]--[/] [wizard.label]{title}[/]")


def print_key_value(key: str, value: str, indent: int = 4) -> None:
    """Print a key-value pair."""
    padding = " " * indent
    console.print(f"{padding}[wizard.label]{key}:[/] [wizard.value]{value}[/]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"  {ICON_CHECK} {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"  {ICON_WARN} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"  {ICON_CROSS} {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"  {ICON_INFO} {message}")


def print_bullet(message: str, indent: int = 4) -> None:
    """Print a bulleted item."""
    padding = " " * indent
    console.print(f"{padding}{ICON_BULLET} {message}")
