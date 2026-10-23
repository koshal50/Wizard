"""Native Textual shell for Wizard's existing Runtime and account clients.

Account login and explicitly started investigations reuse the existing workers.
Opening the shell or reviewing a selection never starts services or model calls.
"""
from pathlib import Path
import threading
import time

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Resize, Paste
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, LoadingIndicator, Markdown, Static

from wizard.cli.parser.command_parser import BTW_COMMANDS, COMMAND_TARGETS, SLASH_COMMANDS
from wizard.cli.parser.intent_builder import build_intent
from wizard.cli.parser.intent_parser import parse_intent
from wizard.cli.tui.reaper_widget import ReaperGuide
from wizard.cli.tui.account_panel import AccountPanel
from wizard.cli.tui.live_run import LiveRun
from wizard.cli.tui.preferences import PREFERENCES, load_preferences, save_preferences
from wizard.cli.tui.session import sanitize_terminal


class ReportScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Close report")]
    DEFAULT_CSS = """
    ReportScreen { background: ansi_default; padding: 1 2; }
    ReportScreen VerticalScroll { height: 1fr; }
    ReportScreen Markdown { background: transparent; }
    """

    def __init__(self, report):
        super().__init__()
        self.report = report

    def compose(self):
        yield Button("Back to execution", id="close-report")
        with VerticalScroll():
            yield Markdown(self.report, open_links=False)

    @on(Button.Pressed, "#close-report")
    def close_report(self):
        self.dismiss()


DESCRIPTIONS = {
    "investigate": "Explore the project",
    "verify": "Check that it works",
    "report": "View saved results",
    "explain": "Understand a part",
}

TARGET_HELP = {
    "architecture": "I'll trace the main parts and how they connect.",
    "runtime": "I'll check how the app starts and whether it runs.",
    "deployment": "I'll inspect how this project is deployed.",
    "authentication": "I'll check the sign-in and account flow.",
    "api": "I'll check the project's API behavior.",
    "security": "I'll look for security problems in this project.",
    "build": "I'll check how the project builds.",
    "dependencies": "I'll check the project's dependencies.",
    "containers": "I'll check the container setup.",
    "ci": "I'll check the automated build and check setup.",
}

UI_COMMANDS = {**SLASH_COMMANDS, **BTW_COMMANDS, "/cancel": "Cancel the current check",
               "/help": "Show how Wizard works", "/guide": "Show or hide the reaper"}


class EmberMark(Static):
    """Small animated colour pixels, not an ASCII spinner or loading claim."""
    def on_mount(self):
        self.frame = 0
        self.timer = self.set_interval(.18, self.tick)
        self.tick()

    def tick(self):
        if self.app.screen.has_class("short"):
            return
        colours = ("#35262A", "#754336", "#BE6E45", "#E7A168", "#B6DDE5", "#628A9B", "#28313C")
        out = Text()
        for i in range(12):
            out.append(" ", style="on " + colours[(i+self.frame) % len(colours)])
        self.update(out)
        self.frame += 1

    def on_unmount(self):
        self.timer.stop()


class WizardApp(App):
    """A single terminal owner projecting existing account and Runtime workers."""

    TITLE = "Wizard"
    ENABLE_COMMAND_PALETTE = False

    class RunChanged(Message):
        def can_replace(self, message):
            return isinstance(message, WizardApp.RunChanged)

    class ChatChanged(Message):
        def can_replace(self, message):
            return isinstance(message, WizardApp.ChatChanged)
    BINDINGS = [("ctrl+q", "quit", "Quit"), ("escape", "back", "Back"),
                Binding("ctrl+c", "copy_or_cancel", show=False, priority=True),
                Binding("ctrl+v", "paste_input", show=False, priority=True),
                Binding("ctrl+shift+c", "copy_or_cancel", show=False, priority=True),
                Binding("ctrl+shift+v", "paste_input", show=False, priority=True),
                Binding("ctrl+a", "select_input", show=False, priority=True),
                Binding("ctrl+t", "toggle_process_output", show=False, priority=True),
                Binding("up", "navigate_up", show=False, priority=True),
                Binding("down", "navigate_down", show=False, priority=True),
                Binding("tab", "slash_apply", show=False, priority=True),
                Binding("pageup", "page_up", show=False, priority=True),
                Binding("pagedown", "page_down", show=False, priority=True),
                Binding("ctrl+home", "content_home", show=False, priority=True),
                Binding("ctrl+end", "content_end", show=False, priority=True)]
    CSS = """
    Screen { background: ansi_default; color: #F3F1EC; }
    #identity { height: 3; padding: 1 3 0 3; color: #DDEEF3; }
    #brand-motion { height: 1; padding: 0 3; margin-bottom: 1; }
    #workspace { height: 1fr; padding: 0 2; }
    #primary { width: 1fr; height: 1fr; min-height: 0; }
    #content { height: 1fr; min-height: 0; overflow-y: auto; scrollbar-size: 1 1; padding: 0; }
    .account-mode #content { align: center middle; }
    .startup-mode #content { align: center middle; }
    #startup-panel { height: auto; width: 100%; padding: 1 2; }
    #startup-title { height: 2; text-align: center; color: #DDEEF3; }
    #startup-animation { height: 2; color: #E7A168; }
    #startup-detail { height: auto; text-align: center; color: #8CBFCF; }
    #heading { height: 2; color: #8CBFCF; }
    #families { height: auto; }
    #recent { height: auto; margin-top: 1; color: #7E7C88; }
    Button { min-width: 0; height: 3; border: none; background: transparent;
        color: #A29CAB; padding: 0 1; text-align: left; content-align: left middle; }
    Button:hover { background: #19191E; color: #E7A168; }
    Button:focus { text-style: none; background: #1E2229; color: #DDEEF3; }
    Button.-active { background: #1B2127; color: #E7A168; }
    #families Button { width: 100%; height: 2; }
    #targets { height: auto; }
    #targets Button { width: 100%; height: 2; }
    #help { height: auto; margin-top: 1; color: #A29CAB; }
    #review { height: auto; margin-top: 1; color: #F3F1EC; }
    #onboarding { height: auto; }
    #welcome-copy { height: auto; margin-bottom: 1; color: #DDEEF3; }
    #onboarding Button { width: 100%; height: 2; }
    .guide-hidden #companion { display: none; }
    #utility { height: auto; }
    #utility-body { height: auto; background: transparent; }
    #utility-note { height: auto; color: #8CBFCF; }
    #companion { width: 32; height: 100%; align: right bottom; padding: 0 2 1 1; }
    #bottom-row { dock: bottom; height: 17; max-height: 60%; align-vertical: bottom; }
    .short #bottom-row { height: 10; }
    #bottom-row #speech { height: 1fr; min-height: 0; max-height: 7; overflow-y: auto; scrollbar-size: 1 1; }
    #bottom-row #render-note, #bottom-row #art-credit { display: none; }
    #bottom-row ReaperGuide { width: 100%; height: 100%; }
    #bottom-row ReaperGuide #real-reaper { width: auto; height: 8; max-height: 8; }
    .short #bottom-row ReaperGuide #real-reaper { height: 3; max-height: 3; }
    .short #bottom-row #speech { max-height: 4; }
    #composer { width: 1fr; height: 100%; align-vertical: bottom; padding: 0; }
    #context-strip { height: 1; color: #8CBFCF; }
    #selection { height: 1; color: #A29CAB; }
    #usage-footer { height: 1; color: #b8b1c5; text-wrap: nowrap; overflow-x: hidden; }
    #input-row { height: 3; border-top: solid #8CBFCF; border-bottom: solid #E7A168; }
    #prompt { width: 2; height: 1; color: #E7A168; }
    #intent { height: 1; border: none; padding: 0; background: transparent;
        color: #F3F1EC; width: 1fr; }
    #intent:focus { border: none; background: transparent; }
    #notice { height: auto; max-height: 4; color: #E7A168; }
    #slash-options { height: auto; max-height: 8; background: #141A20; }
    #slash-options Button { width: 100%; height: 1; color: #B6DDE5; }
    #actions { height: 2; layout: grid; grid-size: 4; grid-rows: 2; }
    #actions Button { height: 2; width: 1fr; }
    #stage { display: none; }
    .compact #companion { width: 22; }
    .compact ReaperGuide { width: 20; }
    .compact ReaperGuide #speech { max-height: 5; }
    .compact ReaperGuide #art-credit { display: none; }
    .narrow #companion { width: 14; padding-left: 1; }
    .narrow ReaperGuide { width: 13; }
    .narrow ReaperGuide #real-reaper { width: 12; max-height: 8; }
    .tiny #companion { width: 10; padding-left: 0; }
    .tiny ReaperGuide { width: 10; }
    .tiny ReaperGuide #real-reaper { width: 9; max-height: 6; }
    .short #heading { height: 1; }
    .short #brand-motion { display: none; }
    .short #identity { height: 2; padding-top: 0; }
    .short #families Button { height: 2; }
    """

    def __init__(self, project=None, *, preferences_path=PREFERENCES):
        # Keep ANSI default colours as terminal defaults instead of translating
        # them through Textual's dark theme (which turns the background black).
        super().__init__(ansi_color=True)
        self.project = Path(project or Path.cwd()).expanduser().resolve()
        self.family = None
        self.target = None
        self.prepared_intent = None
        self._preferences_path = preferences_path
        self._preferences = load_preferences(preferences_path)
        self.motion_enabled = self._preferences.get("motion", True)
        self._guide_visible = self._preferences.get("guide", True)
        self._tour_open = False
        self._tour_step = 0
        self._slash_index = 0
        self._slash_suppressed = None
        self._account_login = None
        self._account_revision = 0
        self._session_account_revision = 0
        self._account_operation = None
        self._ui_closing = False
        self.session = None
        self._recorded_session = None
        self._supervisor = None
        self._startup_thread = None
        self._services_ready = False
        self._service_stop = threading.Event()
        self._starting = False
        self._cleanup_lock = threading.Lock()
        self._services_stopped = False
        self._last_narration = None
        self._utility_view = None
        self._utility_visibility = {}
        self._status_request = None
        self._logout_pending = False
        self.side_chat = None
        self._chat_connecting = False
        self._chat_draft = ""
        self._main_draft = ""
        self._diagram = None
        self._diagram_request = None

    def compose(self) -> ComposeResult:
        identity = Text("Run. Observe. Verify.", style="bold #DDEEF3")
        identity.append("  /  " + sanitize_terminal(self.project.name), style="#8CBFCF")
        yield Static(identity, id="identity")
        yield EmberMark(id="brand-motion")
        with Horizontal(id="workspace"):
            with Vertical(id="primary"):
                with VerticalScroll(id="content"):
                    with Vertical(id="startup-panel"):
                        yield Static("Getting your workspace ready", id="startup-title")
                        yield LoadingIndicator(id="startup-animation")
                        yield Static("Starting local services", id="startup-detail", markup=False)
                    yield Static("Choose a command", id="heading")
                    with Vertical(id="onboarding"):
                        yield Static("", id="welcome-copy", markup=False)
                        yield Button("Show me", id="tour-next")
                        yield Button("Continue locally", id="tour-skip")
                        yield Button("Log in", id="tour-login")
                    yield AccountPanel(id="account-panel")
                    with Vertical(id="families"):
                        for family in COMMAND_TARGETS:
                            label = Text(family.ljust(15), style="#E7A168")
                            label.append(DESCRIPTIONS.get(family, ""), style="#A1B8C1")
                            yield Button(label, id="family-" + family)
                        yield Static("", id="recent", markup=False)
                    yield Vertical(id="targets")
                    yield Static("Choose a command, then add details below.", id="help", markup=False)
                    yield Static("", id="review", markup=False)
                    yield LiveRun(id="live-run")
                    with Vertical(id="utility"):
                        yield Markdown("", id="utility-body", open_links=False)
                        yield Static("", id="utility-note", markup=False)
                        yield Button("Upload connections", id="diagram-upload")
                        yield Button("Keep local", id="diagram-local")
                with Horizontal(id="bottom-row"):
                    with Vertical(id="composer"):
                        yield VerticalScroll(id="slash-options")
                        yield Static("", id="notice", markup=False)
                        yield Static("Arrows choose · Enter selects · Tab moves", id="context-strip", markup=False)
                        yield Static("No command selected", id="selection", markup=False)
                        with Horizontal(id="actions"):
                            yield Button("Commands", id="commands-action")
                            yield Button("Clear", id="clear-action")
                            yield Button("Motion off", id="motion-action")
                            yield Button("Quit", id="quit-action")
                        yield Static("", id="usage-footer", markup=False)
                        with Horizontal(id="input-row"):
                            yield Static(">", id="prompt")
                            yield Input(placeholder="Add an intent, or type / for commands", id="intent")
                        yield Static("Enter runs your check · Ctrl+C cancels · /login links your account", id="stage")
                    with Vertical(id="companion"):
                        yield ReaperGuide(id="guide")

    def on_mount(self):
        self.query_one("#startup-panel").display = False
        self.query_one("#onboarding").display = False
        self.query_one("#account-panel").display = False
        self.query_one("#utility").display = False
        self.query_one("#diagram-upload").display = False
        self.query_one("#diagram-local").display = False
        self.query_one("#live-run").display = False
        self._size_layout(self.size.width, self.size.height)
        self.query_one("#targets").display = False
        self.query_one("#slash-options").display = False
        self.query_one("#family-" + next(iter(COMMAND_TARGETS)), Button).focus()
        self._refresh_recent()
        self.refresh_usage_footer()
        self.screen.set_class(not self._guide_visible, "guide-hidden")
        if not self.motion_enabled:
            self.query_one("#brand-motion", EmberMark).timer.pause()
            self.query_one("#motion-action", Button).label = "Motion on"
        if not self._preferences.get("intro_seen"):
            self._show_intro()
        from wizard.cli.tui.services import build_specs
        if not self.is_headless and any(spec.key == "account" for spec in build_specs()):
            self._show_startup("Starting local services")
            self.query_one("#notice", Static).update("Starting local services...")
            self.call_after_refresh(self._connect_services, self._startup_services_ready)

    def _show_startup(self, detail):
        self._startup_visibility = {selector: self.query_one(selector).display for selector in
            ("#heading", "#onboarding", "#families", "#targets", "#help", "#review", "#live-run", "#utility")}
        for selector in self._startup_visibility:
            self.query_one(selector).display = False
        self.query_one("#startup-panel").display = True
        self.query_one("#startup-detail", Static).update(detail)
        self.query_one("#startup-animation").display = self.motion_enabled
        self.screen.add_class("startup-mode")
        self.query_one("#guide", ReaperGuide).explain("Getting your workspace ready. I'm starting the local services. Your project hasn't been run.")

    def _startup_services_ready(self, error):
        if self._ui_closing:
            return
        self.query_one("#startup-panel").display = False
        self.screen.remove_class("startup-mode")
        for selector, visible in getattr(self, "_startup_visibility", {}).items():
            self.query_one(selector).display = visible
        report = self._supervisor.report if self._supervisor else None
        failures = [state.spec.label + ": " + state.detail for state in report.states if not state.ok] if report else []
        message = error or "\n".join(failures) or "Local services are ready. Wizard will stop the services it started when you exit."
        self.query_one("#notice", Static).update(sanitize_terminal(message))
        self.query_one("#guide", ReaperGuide).explain("Services are ready. Choose what you want to check." if not error and not failures else sanitize_terminal(message))

    def _startup_progress(self, message):
        if not self._ui_closing:
            self.query_one("#startup-detail", Static).update(message)

    def on_resize(self, event: Resize):
        self._size_layout(event.size.width, event.size.height)

    def _size_layout(self, width, height):
        self.screen.set_class(width < 90 or height < 28, "compact")
        self.screen.set_class(width < 60, "narrow")
        self.screen.set_class(width < 44, "tiny")
        self.screen.set_class(height < 26, "short")
        if self.is_mounted:
            self.query_one("#guide", ReaperGuide).set_motion(self.motion_enabled and self._guide_visible and height >= 20)

    def _show_intro(self):
        if self._run_active():
            self._show_utility("help", "How to use Wizard")
            self.query_one("#utility-body", Markdown).update(
                "Choose a command and a check, add optional details, then **Enter**.\n\n"
                "Watch real activity and expand the observed page or report. **Ctrl+C** cancels the check.\n\n"
                "`/status` shows usage. `/btw` opens a side conversation. `/login` links your account. "
                "**Esc** returns without interrupting work.")
            return
        if self._utility_view:
            self._close_utility()
        if not self._tour_open:
            self._tour_saved = {selector: self.query_one(selector).display
                                for selector in ("#families", "#targets", "#help", "#review", "#live-run")}
        self._tour_open = True
        self._tour_step = 0
        for selector in self._tour_saved:
            self.query_one(selector).display = False
        self.query_one("#onboarding").display = True
        self._paint_intro()
        self.query_one("#tour-next", Button).focus()

    def _paint_intro(self):
        slides = (
            ("Welcome to Wizard", "Check your project with real results.\n\nWizard can read files, start your app and test it in a browser.\nYou choose what to check; the report shows what was actually verified."),
            ("Choose what to check", "Pick a command, then a check.\n\nAdd a goal below, or leave it empty. Press Enter to begin.\nChecks may use model credits and start project processes."),
            ("Stay in control", "Watch the activity as it arrives. Expand a page or report for details.\n\nCtrl+C cancels. /btw opens a side conversation. /status shows usage.\nLogin is optional for local checks. Type /login when you want to link an account."),
        )
        title, body = slides[self._tour_step]
        self.query_one("#heading", Static).update(title)
        self.query_one("#welcome-copy", Static).update(body)
        self.query_one("#tour-next", Button).label = "Open workspace" if self._tour_step == 2 else "Next"
        self.query_one("#guide", ReaperGuide).explain(("Hi. I'll help you check what works. You can take a quick tour or continue locally.",
                                                       "Choose a check, add any details, then press Enter. Nothing runs until you submit.",
                                                       "I'll show the real status here. You can stop a check whenever you need.")[self._tour_step])

    def _finish_intro(self):
        if not self._tour_open:
            return
        self._tour_open = False
        self.query_one("#onboarding").display = False
        for selector, visible in self._tour_saved.items():
            self.query_one(selector).display = visible
        self._preferences["intro_seen"] = True
        save_preferences(self._preferences, self._preferences_path)
        self.query_one("#heading", Static).update(" / ".join(part for part in (self.family, self.target) if part) or "Choose a command")
        self.query_one("#guide", ReaperGuide).explain("Choose what to check. An intent is optional. /login connects your account.")
        self.query_one("#intent", Input).focus() if self.family else self.query_one("#family-" + next(iter(COMMAND_TARGETS)), Button).focus()

    async def _choose_family(self, family):
        if self._run_active():
            return
        if family not in COMMAND_TARGETS:
            return
        self._finish_intro()
        self.family, self.target, self.prepared_intent = family, None, None
        targets = self.query_one("#targets", Vertical)
        await targets.remove_children()
        for button in self.query("#families Button"):
            button.set_class(button.id == "family-" + family, "-active")
        if COMMAND_TARGETS[family]:
            await targets.mount(*(Button(value, id="target-" + value) for value in COMMAND_TARGETS[family]))
        self.query_one("#families").display = False
        targets.display = bool(COMMAND_TARGETS[family])
        self.query_one("#heading", Static).update(family + " / choose what to check" if COMMAND_TARGETS[family] else "report")
        if self.motion_enabled:
            self.query_one("#content").styles.opacity = .35
            self.query_one("#content").styles.animate("opacity", 1, duration=.18)
        self.query_one("#review", Static).update("")
        self.query_one("#help", Static).update(
            "Choose what to check. Your intent below is optional."
            if COMMAND_TARGETS[family] else "Report uses saved results. No subcommand is needed.")
        self.query_one("#guide", ReaperGuide).explain(DESCRIPTIONS.get(family, "Choose what to check."))
        self._selection()
        if COMMAND_TARGETS[family]:
            self.query_one("#target-" + COMMAND_TARGETS[family][0], Button).focus()
        else:
            self.query_one("#intent", Input).focus()

    def _selection(self):
        self.query_one("#selection", Static).update(" ".join(x for x in (self.family, self.target) if x))
        self.query_one("#context-strip", Static).update(
            "Enter runs this check · an intent is optional" if self.target or self.family == "report"
            else "Choose what to check. Enter selects.")
        self.query_one("#notice", Static).update("")

    @on(Button.Pressed)
    async def pressed(self, event: Button.Pressed):
        identity = event.button.id or ""
        if identity == "tour-next":
            self._tour_step += 1
            if self._tour_step >= 3:
                self._finish_intro()
            else:
                self._paint_intro()
        elif identity == "tour-skip":
            self._finish_intro()
        elif identity == "tour-login":
            self._start_login()
        elif identity == "diagram-upload":
            self._upload_diagram()
        elif identity == "diagram-local":
            self._diagram = None
            self.query_one("#diagram-upload").display = False
            self.query_one("#diagram-local").display = False
            self.query_one("#utility-note", Static).update("Connections kept locally. Nothing was uploaded.")
        elif identity.startswith("family-"):
            await self._choose_family(identity.removeprefix("family-"))
        elif identity.startswith("target-"):
            target = identity.removeprefix("target-")
            if target not in COMMAND_TARGETS.get(self.family, []):
                return
            self.target, self.prepared_intent = target, None
            for button in self.query("#targets Button"):
                button.set_class(button is event.button, "-active")
            self.query_one("#review", Static).update("")
            self.query_one("#guide", ReaperGuide).explain(TARGET_HELP.get(target, "Add an intent, or leave it empty."))
            self.query_one("#targets").display = False
            self.query_one("#heading", Static).update(self.family + " / " + target)
            self.query_one("#help", Static).update("Add details below, or leave the intent empty.")
            self._selection()
            self.query_one("#intent", Input).focus()
        elif identity == "clear-action":
            self.prepared_intent = None
            self.query_one("#intent", Input).value = ""
            self.query_one("#review", Static).update("")
            self.query_one("#notice", Static).update("")
            self.query_one("#intent", Input).focus()
        elif identity == "quit-action":
            self.exit()
        elif identity == "commands-action":
            self.action_back()
        elif identity == "motion-action":
            self.motion_enabled = not self.motion_enabled
            self.query_one("#brand-motion", EmberMark).timer.resume() if self.motion_enabled else self.query_one("#brand-motion", EmberMark).timer.pause()
            self._size_layout(self.size.width, self.size.height)
            event.button.label = "Motion off" if self.motion_enabled else "Motion on"
            self._preferences["motion"] = self.motion_enabled
            save_preferences(self._preferences, self._preferences_path)
        elif identity.startswith("slash-"):
            command = event.button.name
            if command in UI_COMMANDS:
                self._slash_suppressed = command
                field = self.query_one("#intent", Input)
                field.value = command
                field.cursor_position = len(command)
                field.focus()
                self.query_one("#slash-options").display = False

    @on(Input.Changed, "#intent")
    async def changed(self, event: Input.Changed):
        self.prepared_intent = None
        self.query_one("#review", Static).update("")
        import re
        drawer = self.query_one("#slash-options", VerticalScroll)
        await drawer.remove_children()
        prefix = event.value.lstrip(" \t")
        if event.value == self._slash_suppressed:
            drawer.display = False
            return
        if re.fullmatch(r"/[a-zA-Z-]*(?: [a-zA-Z-]*){0,2}", prefix) and event.input.cursor_position == len(event.value):
            matches = [(key, value) for key, value in UI_COMMANDS.items() if key.startswith(prefix)]
            if matches:
                await drawer.mount(*(Button(key.ljust(17) + value, id="slash-" + str(index), name=key) for index, (key, value) in enumerate(matches)))
                self._slash_index = 0
                self._highlight_slash()
            drawer.display = bool(matches)
        else:
            drawer.display = False

    @on(Input.Submitted, "#intent")
    def submitted(self):
        if self.query_one("#slash-options").display:
            if self.query_one("#intent", Input).value.strip() not in UI_COMMANDS:
                self.action_slash_apply()
                return
            self.query_one("#slash-options").display = False
        if self._review():
            self._start_run()

    def check_action(self, action, parameters):
        if action in {"navigate_up", "navigate_down"}:
            if not self.is_mounted:
                return False
            field = self.query_one("#intent", Input)
            if self.query_one("#slash-options").display and field.has_focus:
                return True
            return (bool(self._menu_buttons()) and (not field.has_focus or not field.value)) or self.query_one("#live-run").display
        if action in {"slash_up", "slash_down", "slash_apply"}:
            if not self.is_mounted:
                return False
            return self.query_one("#slash-options").display and self.query_one("#intent", Input).has_focus
        return True

    def _menu_buttons(self):
        for container in ("#onboarding", "#families", "#targets"):
            if self.query_one(container).display:
                return list(self.query(container + " Button"))
        return []

    def _navigate(self, delta):
        if self.query_one("#slash-options").display and self.query_one("#intent", Input).has_focus:
            self._move_slash(delta)
            return
        buttons = self._menu_buttons()
        if buttons:
            current = buttons.index(self.focused) if self.focused in buttons else (-1 if delta > 0 else 0)
            button = buttons[(current + delta) % len(buttons)]
            button.focus()
            button.scroll_visible(animate=False)
        else:
            self.query_one("#content", VerticalScroll).scroll_relative(y=delta * 3, animate=False)

    def action_navigate_up(self):
        self._follow_execution = False
        self._navigate(-1)

    def action_navigate_down(self):
        self._navigate(1)

    def action_page_up(self):
        self._follow_execution = False
        self.query_one("#content", VerticalScroll).scroll_page_up(animate=False)

    def action_page_down(self):
        self.query_one("#content", VerticalScroll).scroll_page_down(animate=False)

    def action_content_home(self):
        self._follow_execution = False
        self.query_one("#content", VerticalScroll).scroll_home(animate=False)

    def action_content_end(self):
        self._follow_execution = True
        self.query_one("#content", VerticalScroll).scroll_end(animate=False)

    def on_mouse_scroll_up(self, event):
        self._follow_execution = False

    def on_mouse_scroll_down(self, event):
        self.call_after_refresh(self._resume_follow_at_bottom)

    def _resume_follow_at_bottom(self):
        content = self.query_one("#content", VerticalScroll)
        if content.scroll_y >= content.max_scroll_y - 1:
            self._follow_execution = True

    def _highlight_slash(self):
        for i, button in enumerate(self.query("#slash-options Button")):
            button.set_class(i == self._slash_index, "-active")
            if i == self._slash_index:
                button.scroll_visible(animate=False)

    def _move_slash(self, delta):
        buttons = list(self.query("#slash-options Button"))
        if buttons:
            self._slash_index = (self._slash_index + delta) % len(buttons)
            self._highlight_slash()

    def action_slash_up(self):
        self._move_slash(-1)

    def action_slash_down(self):
        self._move_slash(1)

    def action_slash_apply(self):
        buttons = list(self.query("#slash-options Button"))
        if not buttons:
            return
        command = buttons[self._slash_index].name
        self._slash_suppressed = command
        field = self.query_one("#intent", Input)
        field.value = command
        field.cursor_position = len(command)
        self.query_one("#slash-options").display = False
        field.focus()

    def _review(self):
        text = self.query_one("#intent", Input).value.strip()
        notice = self.query_one("#notice", Static)
        if text == "/help":
            self._show_intro()
            return
        if text == "/guide":
            self._guide_visible = not self._guide_visible
            self.screen.set_class(not self._guide_visible, "guide-hidden")
            self._preferences["guide"] = self._guide_visible
            save_preferences(self._preferences, self._preferences_path)
            self._size_layout(self.size.width, self.size.height)
            notice.update("Guide shown." if self._guide_visible else "Guide hidden. Type /guide to bring it back.")
            self.query_one("#intent", Input).value = ""
            return
        if text == "/exit":
            self.exit()
            return
        if text == "/login":
            self._start_login()
            return
        if text == "/cancel-login":
            self._cancel_login()
            return
        if text == "/cancel":
            self.action_cancel_current()
            return
        if text == "/logout":
            self._logout()
            return
        if text == "/status":
            self._show_status()
            return
        if text.startswith("/btw"):
            self._btw_command(text)
            return
        if self._utility_view == "btw" and not text.startswith("/"):
            self._submit_side(text)
            return
        if self._utility_view:
            self._close_utility()
        self._finish_intro()
        if self._run_active():
            notice.update("A check is active. Ctrl+C cancels it. Your next draft is kept.")
            return
        if text.startswith("/"):
            notice.update("This command is not connected in the UI preview. Your current Wizard settings are unchanged."
                          if text in UI_COMMANDS else "Unknown command. Type / to see commands.")
            return
        if not self.family:
            notice.update("Choose a command first.")
            return
        if COMMAND_TARGETS[self.family] and not self.target:
            notice.update("Choose a subcommand first.")
            return
        parsed = parse_intent(text, self.family, menu_target=self.target)
        self.prepared_intent = build_intent(self.family, target=self.target,
                                           targets=parsed.targets, urls=parsed.urls, question=text)
        return True

    def action_back(self):
        if self._tour_open:
            self._finish_intro()
            return
        if self.query_one("#slash-options").display:
            self._slash_suppressed = self.query_one("#intent", Input).value
            self.query_one("#slash-options").display = False
            return
        if self._utility_view:
            self._close_utility()
            return
        if self._run_active():
            self.query_one("#notice", Static).update("Your check is still active. Ctrl+C cancels it.")
            return
        if self.query_one("#account-panel").display:
            self._cancel_login()
            return
        if self.query_one("#slash-options").display:
            self._slash_suppressed = self.query_one("#intent", Input).value
            self.query_one("#slash-options").display = False
            return
        self.family, self.target, self.prepared_intent = None, None, None
        self.query_one("#help").display = True
        self.query_one("#families").display = True
        self.query_one("#targets").display = False
        self.query_one("#heading", Static).update("Choose a command")
        self.query_one("#selection", Static).update("No command selected")
        self.query_one("#context-strip", Static).update("Arrows choose · Enter selects · Tab moves")
        self.query_one("#guide", ReaperGuide).explain("Choose a command. I'll explain what it does.")
        self.query_one("#review", Static).update("")
        self.query_one("#notice", Static).update("")
        self.query_one("#family-" + next(iter(COMMAND_TARGETS)), Button).focus()

    def _start_login(self, *, services_ready=False):
        if not services_ready:
            from wizard.cli.tui.services import build_specs
            if any(spec.key == "account" for spec in build_specs()):
                self.query_one("#notice", Static).update("Starting account services before login...")
                def connected(error):
                    report = self._supervisor.report if self._supervisor else None
                    failures = [s.spec.label + ": " + s.detail for s in report.states if s.spec.key in {"account", "website"} and not s.ok] if report else []
                    if error or failures:
                        self.query_one("#notice", Static).update(sanitize_terminal(error or "\n".join(failures)))
                    else:
                        self._start_login(services_ready=True)
                self._connect_services(connected)
                return
        if self._logout_pending:
            self.query_one("#notice", Static).update("Logout is still finishing. Please wait.")
            return
        if self._run_active():
            self.query_one("#notice", Static).update("Finish or cancel the active check before linking an account.")
            return
        if self._utility_view:
            self._close_utility()
        self._finish_intro()
        from wizard.cli.account_login import LoginWorker
        if self._account_login and self._account_login.running:
            if self.query_one("#account-panel").display:
                self.query_one("#account-code", Input).focus()
            else:
                self.query_one("#notice", Static).update("The previous login is closing. Try /login again in a moment.")
            return
        operation = self._account_operation = object()
        def deliver(callback, *args):
            if self._ui_closing:
                return
            try:
                self.call_from_thread(callback, operation, *args)
            except RuntimeError:
                pass  # The terminal may have closed while HTTP was finishing.
        worker = self._account_login = LoginWorker(lambda message: deliver(self._login_message, message))
        worker.on_authenticated = lambda account: deliver(self._login_complete)
        panel = self.query_one("#account-panel", AccountPanel)
        self._login_visibility = {selector: self.query_one(selector).display for selector in
                                  ("#families", "#targets", "#help", "#review", "#live-run", "#utility")}
        for selector in self._login_visibility:
            self.query_one(selector).display = False
        self.screen.add_class("account-mode")
        panel.display = True
        panel.message("Opening the website. Sign in, approve access, then enter its code.")
        panel.set_busy(True)
        for selector in ("#families", "#targets", "#help", "#review", "#composer"):
            self.query_one(selector).display = False
        self.query_one("#heading", Static).update("Connect your account")
        self.query_one("#intent", Input).value = ""
        self.query_one("#guide", ReaperGuide).explain("Approve access on the website, then enter the code here. You can cancel any time.")
        self.query_one("#account-code", Input).focus()
        worker.start()

    def _login_message(self, operation, message):
        if operation is not self._account_operation:
            return
        # The worker's manual browser URL contains a one-use authorization ticket.
        # Keep it out of the UI transcript, companion and exported screenshots.
        if "Open this URL manually:" in message:
            message = ("Website opened. Sign in and approve, then enter the code here."
                       if "Browser opened." in message else
                       "The browser could not open. Cancel, check your default browser, then try /login again.")
        panel = self.query_one("#account-panel", AccountPanel)
        panel.message(sanitize_terminal(message))
        panel.set_busy(False)

    @on(AccountPanel.Submit)
    def _submit_login(self, event):
        if not self._account_login or not self._account_login.running:
            self.query_one("#account-panel", AccountPanel).message("This login has ended. Cancel, then type /login again.")
            return
        self.query_one("#account-panel", AccountPanel).set_busy(True)
        self.query_one("#account-panel", AccountPanel).message("Checking your code…")
        self.query_one("#guide", ReaperGuide).explain("Checking your code with the account service. Your project is not being started.")
        self._account_login.submit(event.code)

    @on(AccountPanel.Cancel)
    def _cancel_login(self):
        self._account_operation = None
        if self._account_login:
            self._account_login.cancel()
        self._leave_login("Login cancelled. You can keep using local checks.")

    def _login_complete(self, operation):
        if operation is not self._account_operation:
            return
        self._account_operation = None
        self._account_revision += 1
        self.refresh_usage_footer()
        self._status_request = None
        self._chat_connecting = False
        self._chat_draft = ""
        if self.side_chat:
            self.side_chat.close()
            self.side_chat = None
        self._leave_login("Account connected. Choose what to check.")

    def _leave_login(self, message):
        self.query_one("#account-code", Input).value = ""
        self.query_one("#account-panel", AccountPanel).set_busy(False)
        self.screen.remove_class("account-mode")
        self.query_one("#account-panel").display = False
        self.query_one("#composer").display = True
        self.query_one("#help").display = True
        self.query_one("#review").display = True
        for selector, visible in getattr(self, "_login_visibility", {}).items():
            self.query_one(selector).display = visible
        self.action_back()
        self.query_one("#notice", Static).update(message)
        self.query_one("#guide", ReaperGuide).explain(message)

    @on(AccountPanel.Retry)
    def _retry_login(self):
        if self._account_login and self._account_login.running:
            self._account_operation = None
            self._account_login.cancel()
            self.query_one("#account-panel", AccountPanel).message("Closing the previous request. Choose Try again once it has finished.")
            return
        self._leave_login("Starting a new login request…")
        self._start_login()

    @on(AccountPanel.Quit)
    def _quit_login(self):
        self.exit()

    def on_unmount(self):
        self._ui_closing = True
        self._account_operation = None
        if self._account_login:
            self._account_login.cancel()
        if self.side_chat:
            self.side_chat.close()

    def _background(self, action, completed):
        def run():
            try:
                result, error = action(), None
            except Exception as exc:
                result, error = None, sanitize_terminal(str(exc)) or "Request failed."
            if not self._ui_closing:
                try:
                    self.call_from_thread(completed, result, error)
                except RuntimeError:
                    pass
        threading.Thread(target=run, name="wizard-ui-request", daemon=True).start()

    def _show_utility(self, view, title):
        self._finish_intro()
        if self._utility_view is None:
            value = self.query_one("#intent", Input).value
            self._main_draft = "" if value.strip().startswith("/") else value
            self._utility_visibility = {selector: self.query_one(selector).display
                                        for selector in ("#families", "#targets", "#help", "#review", "#live-run")}
        self._utility_view = view
        self.query_one("#diagram-upload").display = False
        self.query_one("#diagram-local").display = False
        for selector in self._utility_visibility:
            self.query_one(selector).display = False
        self.query_one("#utility").display = True
        self.query_one("#heading", Static).update(title)
        self.query_one("#utility-note", Static).update("Esc returns to your check")
        self.query_one("#notice", Static).update("")

    def _close_utility(self):
        if self._utility_view == "btw":
            value = self.query_one("#intent", Input).value
            self._chat_draft = "" if value.strip().startswith("/") else value
        self.query_one("#intent", Input).value = self._main_draft
        self._utility_view = None
        self._status_request = None
        self._diagram_request = None
        self._diagram = None
        self.query_one("#utility").display = False
        for selector, visible in self._utility_visibility.items():
            self.query_one(selector).display = visible
        self.query_one("#heading", Static).update("Checking your project" if self._run_active()
                                                   else " / ".join(part for part in (self.family, self.target) if part) or "Choose a command")
        self.query_one("#context-strip", Static).update("Enter runs your check · / opens commands")
        self.query_one("#intent", Input).placeholder = "Add an intent, or type / for commands"
        if self.session:
            self._last_narration = None
            self._refresh_run()
        self.query_one("#intent", Input).focus()

    def _show_status(self):
        from wizard.cli.runtime_client.usage import status
        from wizard.cli.display.usage import format_status
        if self._utility_view == "btw":
            self._close_utility()
        self._show_utility("status", "Token usage")
        token = self._status_request = object()
        self.query_one("#utility-body", Markdown).update("Loading saved usage…")
        self.query_one("#intent", Input).value = ""
        snapshot = self.session.snapshot() if self.session else {}
        run_id = snapshot.get("investigation_id")
        pending_run = self._starting or (snapshot.get("running") and not run_id)
        def completed(result, error):
            if self._status_request is token and self._utility_view == "status":
                text = error or result
                self.query_one("#utility-body", Markdown).update("```text\n" + sanitize_terminal(text).replace("```", "~~~") + "\n```")
        def load():
            result = status(run_id=run_id)
            if pending_run:
                result = {**result, "current_run": None, "current_run_pending": True}
            return format_status(result)
        self._background(load, completed)

    def _logout(self):
        if self._run_active():
            self.query_one("#notice", Static).update("Finish or cancel the active check before changing accounts.")
            return
        if self._logout_pending:
            return
        if self._utility_view:
            self._close_utility()
        from wizard.cli.account_logout import logout
        self._logout_pending = True
        self._account_revision += 1
        self.refresh_usage_footer()
        self._chat_connecting = False
        self._chat_draft = ""
        self._account_operation = None
        self._status_request = None
        if self._account_login:
            self._account_login.cancel()
        if self.side_chat:
            self.side_chat.close()
            self.side_chat = None
        self.query_one("#notice", Static).update("Logging out…")
        self.query_one("#intent", Input).value = ""
        def completed(result, error):
            self._logout_pending = False
            self.query_one("#notice", Static).update(error or sanitize_terminal(result))
            self.query_one("#guide", ReaperGuide).explain(error or sanitize_terminal(result), immediate=True)
        self._background(logout, completed)

    def _btw_command(self, command):
        from wizard.cli.tui.side_chat import SideChat
        if command == "/btw main":
            if self._utility_view:
                self._close_utility()
            return
        if command in {"/btw copy", "/btw copy all"}:
            messages = self.side_chat.snapshot()["messages"] if self.side_chat else []
            text = ("\n\n".join(m["role"] + ":\n" + m["content"] for m in messages)
                    if command.endswith(" all") else next((m["content"] for m in reversed(messages) if m["role"] == "assistant"), ""))
            if not text:
                self.query_one("#notice", Static).update("No answer to copy yet.")
                return
            from wizard.cli.tui.clipboard import write_text
            self._background(lambda: write_text(text), lambda _, error: self.query_one("#notice", Static).update(error or "Copied."))
            return
        if command not in {"/btw", "/btw new"}:
            self.query_one("#notice", Static).update("Use /btw, /btw main, /btw new, or /btw copy.")
            return
        if command == "/btw new" and self.side_chat:
            self.side_chat.close()
            self.side_chat = None
            self._chat_connecting = False
            self._chat_draft = ""
        if self.side_chat is None:
            self.side_chat = SideChat(lambda: self.post_message(self.ChatChanged()))
        field = self.query_one("#intent", Input)
        entering = self._utility_view != "btw"
        self._show_utility("btw", "Side conversation")
        if entering:
            field.value = self._chat_draft
        elif command == "/btw new":
            field.value = ""
        field.placeholder = "Ask a question · Esc returns to your check"
        self.query_one("#guide", ReaperGuide).explain("Ask me about your project or this check. Your investigation keeps running. Questions use model credits.")
        self.query_one("#context-strip", Static).update("Enter sends a question · your investigation keeps running")
        self._refresh_chat()
        field.focus()

    def _submit_side(self, text):
        if not text:
            return
        if self._logout_pending:
            self.query_one("#notice", Static).update("Logout is still finishing. Your question is kept.")
            return
        if self._chat_connecting or self.side_chat.snapshot()["pending"]:
            self.query_one("#notice", Static).update("A reply is pending. Your draft is kept.")
            return
        chat = self.side_chat
        self._chat_connecting = True
        self.query_one("#utility-note", Static).update("Connecting to the conversation service…")
        def connected(error):
            self._chat_connecting = False
            if self.side_chat is not chat or chat.closed:
                return
            if error:
                self.query_one("#notice", Static).update(error)
                if self._utility_view == "btw":
                    self.query_one("#utility-note", Static).update("Not connected. Your question was not sent.")
                return
            if chat.submit(text) and self._utility_view == "btw":
                field = self.query_one("#intent", Input)
                if field.value.strip() == text:
                    field.value = ""
        self._connect_services(connected)

    @on(ChatChanged)
    def _refresh_chat(self):
        if self._utility_view != "btw" or not self.side_chat or self._ui_closing:
            return
        state = self.side_chat.snapshot()
        answer = next((m["content"] for m in reversed(state["messages"]) if m["role"] == "assistant"), "")
        if state["error"]:
            guidance = sanitize_terminal(state["error"])
        elif state["pending"]:
            guidance = "I'm checking your question. Your investigation keeps running."
        else:
            guidance = sanitize_terminal(answer)[:420] if answer else "Ask me about your project or the current check."
        self.query_one("#guide", ReaperGuide).explain(guidance)
        parts = [("**You**" if message["role"] == "user" else "**Wizard**") + "\n\n" + sanitize_terminal(message["content"])
                 for message in state["messages"][-40:]]
        self.query_one("#utility-body", Markdown).update("\n\n---\n\n".join(parts) or "Ask about your project or the current check. Questions may use model credits.")
        self.query_one("#utility-note", Static).update(state["error"] or ("Waiting for a reply…" if state["pending"] else "Esc returns · /btw new starts fresh · /btw copy copies the answer"))

    def _run_active(self):
        return self._starting or bool(self.session and not self.session.snapshot()["finished"])

    def _start_run(self):
        if self._logout_pending:
            self.query_one("#notice", Static).update("Logout is still finishing. Your request is kept.")
            return
        if self._run_active() or self.prepared_intent is None:
            return
        if self._startup_thread and self._startup_thread.is_alive():
            self.query_one("#notice", Static).update("The service connection is still finishing. Please wait before starting another check.")
            return
        if not self.project.is_dir():
            self.query_one("#notice", Static).update("The selected project folder does not exist.")
            return
        # Freeze the reviewed request. Later draft edits cannot change this run.
        request = (self.family, self.target, self.prepared_intent.question)
        self._starting = True
        self.query_one("#live-run").display = True
        self.query_one("#live-run", LiveRun).show_request(*request)
        self.query_one("#live-run", LiveRun).connecting()
        self.query_one("#families").display = False
        self.query_one("#targets").display = False
        self.query_one("#review", Static).update("")
        self.query_one("#help").display = False
        self.query_one("#context-strip", Static).update("Running · you can edit your next request below")
        self.query_one("#heading", Static).update("Checking " + sanitize_terminal(self.project.name))
        self.query_one("#notice", Static).update("Connecting to the local services…")
        self.query_one("#guide", ReaperGuide).explain("Connecting. No project action runs until the Runtime accepts your check.")
        if self._services_ready:
            self._begin_session(request)
            return
        self._connect_services(lambda error: self._connected(request, error))

    def _connect_services(self, continuation):
        if self._services_ready:
            continuation(None)
            return
        if self._startup_thread and self._startup_thread.is_alive():
            if not hasattr(self, "_service_waiters"):
                self._service_waiters = []
            self._service_waiters.append(continuation)
            return
        from wizard.cli.tui.services import ServiceSupervisor
        self._supervisor = self._supervisor or ServiceSupervisor(log_dir=self.project / ".wizard" / "logs")
        self._service_stop.clear()
        self._services_stopped = False
        def connect():
            try:
                def progress(message):
                    if not self._ui_closing:
                        self.call_from_thread(self._startup_progress, message)
                report = self._supervisor.ensure_all(cancel_event=self._service_stop, on_progress=progress)
                error = None
                if not report.investigation_stack_ok:
                    failures = [state for state in report.states if state.spec.key == "kernel" and not state.ok]
                    error = "\n".join(sanitize_terminal(state.spec.label + ": " + state.detail) for state in failures)
                    error = error or "Local services could not start. See .wizard/logs for details."
                if error:
                    self._stop_owned_services()
                if error is None and not self._ui_closing:
                    self._supervisor.apply_env()
                if not self._ui_closing:
                    self.call_from_thread(self._services_connected, continuation, error)
            except Exception as exc:
                if not self._ui_closing:
                    try:
                        self.call_from_thread(self._services_connected, continuation, sanitize_terminal(str(exc)))
                    except RuntimeError:
                        pass
            finally:
                if self._ui_closing:
                    self._stop_owned_services()
        self._startup_thread = threading.Thread(target=connect, name="wizard-ui-connect", daemon=False)
        self._startup_thread.start()

    def _services_connected(self, continuation, error):
        if not self._ui_closing:
            self._services_ready = error is None and bool(self._supervisor and self._supervisor.report and all(s.ok for s in self._supervisor.report.states))
            waiting = getattr(self, "_service_waiters", [])
            self._service_waiters = []
            continuation(error)
            for callback in waiting:
                callback(error)

    def _connected(self, request, error):
        if self._ui_closing or not self._starting:
            return
        self._services_ready = error is None
        if error:
            self._starting = False
            self.query_one("#live-run", LiveRun).stop_activity("Could not connect")
            self.query_one("#notice", Static).update(error)
            self.query_one("#guide", ReaperGuide).explain(sanitize_terminal(error)[:350] + "\nYour check has not been submitted.", immediate=True)
        elif self._starting:
            self._begin_session(request)

    def _begin_session(self, request):
        from wizard.cli.tui.session import TuiSession
        if self._ui_closing or not self._starting:
            return
        self._starting = False
        self._follow_execution = True
        self._session_account_revision = self._account_revision
        self.session = TuiSession(family=request[0], target=request[1], intent_text=request[2],
                                  repo_path=str(self.project), on_change=lambda: self.post_message(self.RunChanged()))
        if self.query_one("#intent", Input).value.strip() == request[2]:
            self.query_one("#intent", Input).value = ""
        # A new widget gives each run its own bounded transcript and scroll state.
        self.call_later(self._mount_session_view)

    async def _mount_session_view(self):
        await self.query_one("#live-run", LiveRun).remove()
        await self.query_one("#content", VerticalScroll).mount(LiveRun(id="live-run"))
        if self._ui_closing:
            return
        self.query_one("#heading", Static).update("Checking your project")
        self.query_one("#live-run", LiveRun).show_request(self.session.family, self.session.target, self.session.intent_text)
        self.query_one("#notice", Static).update("")
        self.session.start()
        self.post_message(self.RunChanged())

    @on(RunChanged)
    def _refresh_run(self):
        if not self.session or self._ui_closing or not self.is_running:
            return
        views = list(self.query(LiveRun))
        if not views or not self.query("#heading"):
            return  # A new run is replacing the previous view asynchronously.
        state = views[0].display_session(self.session)
        if state.get("finished") and self._recorded_session is not self.session:
            self._recorded_session = session = self.session
            from wizard.cli.tui.history import record_run
            self._background(lambda: record_run(session.family, session.target, session.intent_text,
                                               state["status"], repo_path=self.project),
                             lambda _, error: self._refresh_recent())
        narration = state.get("now")
        if state.get("finished") and not self._utility_view:
            narration = "Check finished: " + state["status"] + "."
            self.query_one("#heading", Static).update(narration)
            self.query_one("#context-strip", Static).update("Enter runs another check · Commands changes what to check")
            report = state.get("report_path")
            self.query_one("#notice", Static).update("Report saved: " + sanitize_terminal(report) if report else "No saved report path was returned. Open output details for the final status.")
        if narration and narration != self._last_narration and not self._utility_view:
            self._last_narration = narration
            self.query_one("#guide", ReaperGuide).explain(sanitize_terminal(narration), immediate=bool(state.get("finished")))

    def _refresh_recent(self):
        from wizard.cli.tui.history import load_recent
        entries = load_recent(3, repo_path=self.project)
        text = "Recent checks\n" + "\n".join(sanitize_terminal(entry.display_line() + " · " + str(entry.status)) for entry in entries) if entries else "Your completed checks will appear here."
        self.query_one("#recent", Static).update(text)

    def refresh_usage_footer(self):
        from wizard.cli.display.usage import counter
        if not self.is_mounted:
            return
        if self.session and self._session_account_revision != self._account_revision:
            text = "Previous account run. /status shows current account usage."
        else:
            state = self.session.snapshot() if self.session else {}
            elapsed = (state.get("ended_at") or time.monotonic()) - state.get("started_at", time.monotonic())
            text = counter(state.get("usage"), elapsed, compact=True)
        self.query_one("#usage-footer", Static).update(text)

    @on(LiveRun.Action)
    def _result_action(self, event):
        if not self.session or not self.session.snapshot().get("finished"):
            return
        state = self.session.snapshot()
        if event.action == "rerun":
            previous = self.session
            self.family, self.target = previous.family, previous.target
            self.prepared_intent = build_intent(previous.family, target=previous.target, question=previous.intent_text)
            self._start_run()
        elif event.action == "open":
            if state.get("report_markdown"):
                self.push_screen(ReportScreen(sanitize_terminal(state["report_markdown"])))
                return
            inv_id = str(state.get("investigation_id") or "")
            html = self.project / "output" / (inv_id + ".runbook.html")
            report = Path(state.get("report_path") or "")
            if not report.is_absolute():
                report = self.project / report
            self._open_report_path(html if inv_id and Path(inv_id).name == inv_id and html.is_file() else report)
        elif event.action == "copy":
            steps = (state.get("runbook") or {}).get("steps") or []
            commands = [str((step.get("parameters") or {}).get("command") or "") for step in steps
                        if step.get("tool") in {"start_process", "execute_command"}]
            commands = [command for command in commands if command]
            if not commands:
                self.query_one("#notice", Static).update("No startup command was recorded.")
                return
            from wizard.cli.tui.clipboard import write_text
            self._background(lambda: write_text("\n".join(commands)),
                             lambda _, error: self.query_one("#notice", Static).update(error or "Recorded commands copied. Review their folders and redacted values before running."))
        elif event.action == "diagram":
            self._show_diagram()

    def _open_report_path(self, path):
        path = path.resolve()
        if not path.is_relative_to((self.project / "output").resolve()) or not path.is_file():
            self.query_one("#notice", Static).update("No saved report was found inside this project's output folder.")
            return
        import webbrowser
        self._background(lambda: webbrowser.open(path.as_uri()),
                         lambda opened, error: self.query_one("#notice", Static).update(error or ("Report opened." if opened else "Could not open the report. File: " + sanitize_terminal(str(path)))))

    @on(Markdown.LinkClicked)
    def _report_link(self, event):
        from urllib.parse import urlsplit
        event.stop()
        if event.href.startswith("#"):
            event.markdown.goto_anchor(event.href[1:])
            return
        try:
            url = urlsplit(event.href)
            if url.scheme in {"http", "https"} and url.hostname and not url.username and not url.password:
                import webbrowser
                self._background(lambda: webbrowser.open(event.href),
                                 lambda _, error: self.query_one("#notice", Static).update(error or "Opened link."))
            elif not url.scheme and not url.netloc:
                self._open_report_path(self.project / "output" / url.path)
            else:
                self.query_one("#notice", Static).update("This link cannot be opened here. No command was executed.")
        except ValueError:
            self.query_one("#notice", Static).update("This link is not valid.")

    def _show_diagram(self):
        if not self.session:
            return
        from wizard.cli.runtime_client.architecture import prepare
        inv_id = self.session.snapshot().get("investigation_id")
        self._show_utility("diagram", "Project connections")
        token = self._diagram_request = object()
        self.query_one("#utility-body", Markdown).update("Loading connections from saved evidence…")
        def prepared(graph, error):
            if self._utility_view != "diagram" or self._diagram_request is not token:
                return
            if error:
                self.query_one("#utility-body", Markdown).update(sanitize_terminal(error))
                return
            from wizard.cli.account_login import account_origin, LoginError
            try:
                destination = account_origin()
            except LoginError:
                destination = None
            self._diagram = (graph, destination)
            nodes = graph.get("nodes") or []
            edges = graph.get("relationships") or []
            labels = {node["id"]: node["label"] for node in nodes}
            lines = ["## " + str(graph.get("title") or "Project connections"), "Status: " + str(graph.get("status")),
                     f"{len(nodes)} parts · {len(edges)} connections · {len(graph.get('evidence') or [])} evidence records", "### Parts"]
            lines.extend("- " + str(node["label"]) + " · " + str(node.get("type", "")) for node in nodes[:50])
            lines.append("### Connections")
            lines.extend("- " + str(labels.get(edge["source"], edge["source"])) + " → " + str(labels.get(edge["target"], edge["target"]))
                         + " · " + str(edge.get("label") or edge.get("type")) + " (" + str(edge.get("classification")) + ")" for edge in edges[:80])
            self.query_one("#utility-body", Markdown).update(sanitize_terminal("\n\n".join(lines)))
            note = ("Upload to " + destination + "? Includes labels, descriptions, relative paths and evidence references; no full source files. Choose Upload only to consent."
                    if destination else "Connections are local. Configure an account website and /login to upload them.")
            self.query_one("#utility-note", Static).update(note)
            self.query_one("#diagram-upload").display = destination is not None
            self.query_one("#diagram-local").display = True
        self._background(lambda: prepare(inv_id), prepared)

    def _upload_diagram(self):
        if not self._diagram or self._utility_view != "diagram":
            return
        graph, destination = self._diagram
        if not destination:
            return
        token = self._diagram_request
        self._diagram = None
        self.query_one("#diagram-upload").display = False
        self.query_one("#diagram-local").display = False
        self.query_one("#utility-note", Static).update("Uploading the connections you approved…")
        def send():
            from wizard.cli.runtime_client.architecture import upload
            from wizard.cli.account_login import account_origin
            if account_origin() != destination:
                raise ValueError("The account website changed. Review the destination again before uploading.")
            return upload(graph, consent=True)
        def completed(result, error):
            if self._utility_view == "diagram" and self._diagram_request is token:
                self.query_one("#utility-note", Static).update(error or sanitize_terminal(result))
        self._background(send, completed)

    def _cancel_run(self):
        if self._starting:
            self._starting = False
            self._service_stop.set()
            self.query_one("#live-run", LiveRun).stop_activity("Cancelled before submission")
            self.query_one("#notice", Static).update("Cancelled. No investigation was submitted.")
        elif self.session:
            self.session.cancel()

    def action_toggle_process_output(self):
        views = list(self.query(LiveRun))
        if views:
            expanded = views[0].toggle_output()
            self.query_one("#notice", Static).update("Process output expanded. Ctrl+T collapses it." if expanded else "Process output collapsed. Ctrl+T expands it.")

    def action_copy_or_cancel(self):
        selected = (self.focused.selected_text if isinstance(self.focused, Input) else "") or self.screen.get_selected_text()
        if selected:
            from wizard.cli.tui.clipboard import write_text
            # Use the OS clipboard, not OSC 52 (often disabled by Windows/VS Code).
            self._background(lambda: write_text(selected), lambda _, error: self.query_one("#notice", Static).update(error or "Copied."))
        elif self._run_active():
            self.action_cancel_current()
        else:
            self.query_one("#notice", Static).update("Select text to copy. Ctrl+A selects the input; Ctrl+C copies it.")

    def _paste_target(self):
        if isinstance(self.focused, Input):
            return self.focused
        if self.query_one("#account-panel").display:
            return next((field for field in self.query("#account-panel Input") if field.display and not field.disabled), None)
        return self.query_one("#intent", Input)

    def action_select_input(self):
        target = self._paste_target()
        if target is not None:
            target.focus()
            target.action_select_all()

    def on_paste(self, event: Paste):
        # Terminal-managed Ctrl+V arrives as a Paste event, not a key binding.
        # Input handles its own paste; this fallback handles menu/button focus.
        if not isinstance(self.focused, Input):
            target = self._paste_target()
            if target is not None:
                event.stop()
                target.focus()
                start, end = target.selection
                target.replace(sanitize_terminal(event.text).replace("\n", " "), start, end)

    def action_paste_input(self):
        target = self._paste_target()
        if target is None:
            return
        target.focus()
        from wizard.cli.tui.clipboard import read_text
        def completed(value, error):
            if error:
                self.query_one("#notice", Static).update(error)
            elif target.is_mounted:
                start, end = target.selection
                target.replace(sanitize_terminal(value).replace("\n", " "), start, end)
        self._background(read_text, completed)

    def action_cancel_current(self):
        if self._run_active():
            self._cancel_run()
        elif self.query_one("#account-panel").display:
            self._cancel_login()
        else:
            self.query_one("#intent", Input).value = ""
            self.query_one("#notice", Static).update("No check is running.")

    def _stop_owned_services(self):
        with self._cleanup_lock:
            if self._services_stopped or self._supervisor is None:
                return
            self._services_stopped = True
            self._supervisor.stop(announce=False)

    def shutdown(self):
        """Called after Textual releases the terminal; HTTP cleanup cannot block rendering."""
        self._ui_closing = True
        self._service_stop.set()
        if self.session:
            self.session.shutdown(timeout=2)
        if self._startup_thread and self._startup_thread.is_alive():
            self._startup_thread.join(timeout=8)
            if self._startup_thread.is_alive():
                return  # Its finally block cleans up once startup has finished.
        self._stop_owned_services()

    def exit(self, *args, **kwargs):
        self._ui_closing = True
        self._service_stop.set()
        if self._account_login:
            self._account_login.cancel()
        if self.side_chat:
            self.side_chat.close()
        return super().exit(*args, **kwargs)


def run_native(project=None):
    app = WizardApp(project)
    try:
        app.run()
    finally:
        app.shutdown()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Open the native Wizard UI; select a check and press Enter to run")
    parser.add_argument("project", nargs="?")
    parser.add_argument("--diagnose-reaper", action="store_true", help="Print safe image/UI diagnostics without starting services")
    arguments = parser.parse_args()
    if arguments.diagnose_reaper:
        import asyncio
        import json
        import os
        import sys
        async def diagnose():
            app = WizardApp(arguments.project)
            async with app.run_test(size=(100, 32)) as pilot:
                await pilot.pause()
                guide = app.query_one("#guide", ReaperGuide)
                details = guide.rendering_status()
                details.update(
                    ui="Textual preview",
                    ui_file=str(Path(__file__).resolve()),
                    python=sys.executable,
                    terminal=os.environ.get("TERM_PROGRAM", "not reported"),
                    windows_terminal=bool(os.environ.get("WT_SESSION")),
                    renderer_requested=os.environ.get("WIZARD_REAPER_RENDERER", "auto"),
                    guide_visible=guide.display and guide.region.width > 0 and guide.region.height > 0,
                )
                return details
        print(json.dumps(asyncio.run(diagnose()), indent=2))
    else:
        run_native(arguments.project)
