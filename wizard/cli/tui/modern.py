"""Borderless presentation for the staged UI refresh; no execution authority."""
from pathlib import Path

from rich.console import Group
from rich.padding import Padding
from rich.text import Text

from wizard.cli.tui.session import sanitize_terminal

INK = "#F3F1EC"
MUTED = "#7E7C88"
ACCENT = "#9B7EDE"
BACKGROUND = "#08080A"


def header(project: str, account: str):
    name = Path(project).name or project
    line = Text("wizard", style="bold " + INK)
    line.append(" · " + sanitize_terminal(name), style=MUTED)
    if account and account != "default user":
        line.append("    " + sanitize_terminal(account), style=MUTED)
    return Padding(line, (1, 3, 0, 3))


def welcome(level, options, selected, family, project):
    """Keep canonical command names selectable while explaining them plainly."""
    title = "Choose a command" if level == "family" else "Choose what to check"
    descriptions = {
        "investigate": "Explore how the project works",
        "verify": "Check whether it works",
        "report": "Open saved results",
        "explain": "Understand a part of the project",
    }
    parts = [Text(title, style=INK), Text("")]
    for index, option in enumerate(options):
        parts.append(Text(option, style=("bold " + ACCENT if index == selected else INK)))
        if level == "family":
            parts.append(Text("  " + descriptions.get(option, ""), style=MUTED))
    parts.extend([Text(""), Text("Choose above. Add details below.", style=MUTED),
                  Text("/login connects your account. / opens commands.", style=MUTED)])
    return Group(*parts)


def companion():
    from rich import box
    from rich.panel import Panel
    from wizard.cli.tui.reaper import terminal_pose
    return Group(Panel(Text("Welcome to Wizard.\nI check your project with real proof.\nType /login to connect your account.", style=INK),
                       box=box.ROUNDED, border_style=ACCENT, padding=(0, 1)),
                 terminal_pose())


def intent(family, target, project):
    label = " ".join(value for value in (family, target) if value)
    return Group(Text(""), Text("What should Wizard check?", style="bold " + INK),
                 Text(sanitize_terminal(label), style=ACCENT), Text(""),
                 Text("Project: " + sanitize_terminal(project), style=MUTED),
                 Text(""), Text("Describe the result you want to check, then submit.", style=INK),
                 Text("Leave it empty to use the selected check.", style=MUTED))


def surface(content):
    return Padding(content, (0, 2))


def preview(destination):
    """Export actual welcome components, without services, login or model calls."""
    from rich.console import Console
    from rich.terminal_theme import TerminalTheme
    from io import StringIO
    palette = [(8, 8, 10)] * 16
    theme = TerminalTheme((8, 8, 10), (243, 241, 236), palette[:8], palette[8:])
    console = Console(file=StringIO(), width=100, record=True, force_terminal=True)
    # The composer is represented here; live input is owned by Prompt Toolkit.
    console.print(header("~/my-project", "default user"))
    console.print(surface(welcome("family", ["investigate", "verify", "report", "explain"],
                                  1, None, "~/my-project")))
    from rich.align import Align
    from rich.console import Group
    console.print(Align.right(Group(companion()), width=40))
    console.print(Padding(Text("What should we check?", style=MUTED), (1, 3, 0, 3)))
    console.print(Padding(Text("Test sign up and log in", style=INK), (0, 3, 1, 3)))
    console.save_svg(str(destination), title="Wizard — welcome design, stage 1", theme=theme)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export the welcome design without starting Wizard")
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    preview(arguments.output)
