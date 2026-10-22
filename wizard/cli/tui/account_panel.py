"""Account presentation only; the existing login worker owns authentication."""
from rich.text import Text
from textual import on
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input, LoadingIndicator, Static


class AccountPanel(Vertical):
    DEFAULT_CSS = """
    AccountPanel { height: auto; margin: 1 0; }
    AccountPanel #account-title { height: 2; color: #DDEEF3; text-align: center; }
    AccountPanel #account-message { height: auto; color: #A1B8C1; }
    AccountPanel #account-cells { height: auto; margin: 1 0; text-align: center; }
    AccountPanel LoadingIndicator { height: 1; color: #8CBFCF; }
    AccountPanel Input { height: 3; background: #111218; border: tall #8CBFCF; }
    AccountPanel Horizontal { height: 4; layout: grid; grid-size: 2; grid-rows: 2 2; }
    AccountPanel Button { width: 1fr; height: 2; }
    """

    class Submit(Message):
        def __init__(self, code):
            super().__init__()
            self.code = code

    class Cancel(Message):
        pass

    class Retry(Message):
        pass

    class Quit(Message):
        pass

    def compose(self):
        yield Static("Link your Wizard account", id="account-title")
        yield Static("Opening the website. Sign in and approve, then enter its code here.", id="account-message", markup=False)
        yield Static("", id="account-cells", markup=False)
        yield Input(placeholder="Paste the 12-character code here", id="account-code", max_length=32, password=True)
        yield LoadingIndicator(id="account-pending")
        with Horizontal():
            yield Button("Connect", id="account-connect")
            yield Button("Cancel", id="account-cancel")
            yield Button("Try again", id="account-retry")
            yield Button("Quit", id="account-quit")

    def on_mount(self):
        self.query_one("#account-pending").display = False
        self.draw_code("")

    def on_resize(self):
        if self.is_mounted:
            self.draw_code(self.query_one("#account-code", Input).value)

    @staticmethod
    def normalized(value):
        return value.replace("-", "").replace(" ", "").upper()

    def draw_code(self, value):
        code = self.normalized(value)
        text = Text()
        width = self.content_size.width
        cell_width = 5 if width >= 64 else 3
        columns = 12 if width >= 40 else 6 if width >= 20 else 4 if width >= 14 else 2 if width >= 6 else 1
        for start in range(0, 12, columns):
            for row in range(3):
                if start or row:
                    text.append("\n")
                for index in range(start, min(start + columns, 12)):
                    if index > start and index % 4 == 0:
                        text.append("  ")
                    digit = code[index] if index < len(code) else " "
                    cell = ("╭" + "─" * (cell_width - 2) + "╮" if row == 0 else
                            "╰" + "─" * (cell_width - 2) + "╯" if row == 2 else
                            "│" + digit.center(cell_width - 2) + "│")
                    text.append(cell, style="bold #E7A168" if index < len(code) else "#B6DDE5" if index == len(code) else "#7E7C88")
        self.query_one("#account-cells", Static).update(text)

    @on(Input.Changed, "#account-code")
    def changed(self, event):
        event.stop()
        self.draw_code(event.value)

    def submit_code(self):
        if self.query_one("#account-connect", Button).disabled:
            return
        field = self.query_one("#account-code", Input)
        code = self.normalized(field.value)
        if len(code) != 12 or any(c not in "0123456789ABCDEF" for c in code):
            self.message("Enter all 12 characters from the website. Letters A–F are allowed.")
            return
        self.post_message(self.Submit(code))
        field.value = ""

    @on(Input.Submitted, "#account-code")
    def submitted(self, event):
        event.stop()
        self.submit_code()

    @on(Button.Pressed)
    def pressed(self, event):
        event.stop()
        if event.button.id == "account-connect":
            self.submit_code()
        elif event.button.id == "account-cancel":
            self.post_message(self.Cancel())
        elif event.button.id == "account-retry":
            self.post_message(self.Retry())
        elif event.button.id == "account-quit":
            self.post_message(self.Quit())

    def message(self, text):
        self.query_one("#account-message", Static).update(text)

    def set_busy(self, busy):
        self.query_one("#account-connect", Button).disabled = busy
        self.query_one("#account-pending").display = busy and getattr(self.app, "motion_enabled", True)
