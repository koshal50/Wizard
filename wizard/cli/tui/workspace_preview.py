"""Local post-login design study. Sample content only; never execution evidence."""
from pathlib import Path
from xml.etree import ElementTree as ET

from wizard.cli.tui.modern import ACCENT, BACKGROUND, INK, MUTED
from wizard.cli.tui.reaper import pixels

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
GREEN, AMBER, LINE = "#94B5A0", "#E5A93C", "#25232C"
VIEWS = {"home": "After login", "live": "Live check", "details": "Inspect a step",
         "browser": "Browser proof", "results": "Final report", "help": "Needs your help"}


class Screen:
    def __init__(self, title):
        self.root = ET.Element("{"+NS+"}svg", {"viewBox": "0 0 1600 1000", "width": "1600", "height": "1000"})
        self.el("title").text = title
        self.el("desc").text = "Design preview with illustrative activity and page data. No actual check was run."
        self.rect(0, 0, 1600, 1000, BACKGROUND)

    def el(self, tag, **attrs):
        return ET.SubElement(self.root, "{"+NS+"}"+tag, {k.replace("_", "-"): str(v) for k, v in attrs.items()})

    def rect(self, x, y, w, h, fill, **attrs):
        return self.el("rect", x=x, y=y, width=w, height=h, fill=fill, **attrs)

    def text(self, x, y, value, colour=INK, size=18, **attrs):
        item = self.el("text", x=x, y=y, fill=colour, font_size=size,
                       font_family="JetBrains Mono, Cascadia Code, Consolas, monospace", **attrs)
        item.text = value
        return item

    def rule(self, x, y, width, colour=LINE):
        self.el("line", x1=x, y1=y, x2=x+width, y2=y, stroke=colour, stroke_width=1)

    def header(self, active):
        self.text(56, 59, "wizard", INK, 21)
        self.text(150, 59, "/ my-project", MUTED, 17)
        self.text(1544, 57, "DESIGN PREVIEW · SAMPLE DATA", MUTED, 11, text_anchor="end")
        self.rule(56, 88, 1488)
        for x, label in [(56, "Activity"), (190, "Browser"), (315, "Results")]:
            self.text(x, 125, label, INK if label == active else MUTED, 15)
            if label == active:
                self.rule(x, 139, len(label)*9, ACCENT)
        self.text(1544, 125, "Account connected", MUTED, 13, text_anchor="end")

    def companion(self, message, pose="rest"):
        # Reserved companion lane: never overlaps the composer or activity.
        self.rect(1152, 640, 392, 98, BACKGROUND, stroke="#463A58", rx=7)
        for i, line in enumerate(message):
            self.text(1170, 671+i*24, line, INK, 14)
        self.el("path", d="M 1440 738 l 9 9 l 0 -9", fill=BACKGROUND, stroke="#463A58")
        grid = pixels()
        for y, row in enumerate(grid):
            for x, colour in enumerate(row):
                if colour:
                    self.rect(1388+x*3, 751+y*3, 3, 3, colour)
        if pose == "book":
            self.rect(1420, 824, 24, 23, "#73617E")
            self.rect(1445, 824, 24, 23, "#73617E")
            self.rect(1423, 827, 18, 16, "#C9BBD5")
            self.rect(1448, 827, 18, 16, "#E2D6E8")

    def composer(self, draft, label="Tell Wizard what to check", actions="Details     Browser     Results     Stop"):
        self.text(56, 805, label, MUTED, 13)
        self.rule(56, 826, 1050, ACCENT)
        self.text(72, 867, ">", ACCENT, 21)
        self.text(110, 867, draft, INK, 18)
        self.rect(110+len(draft)*10.8, 847, 9, 24, ACCENT)
        self.rule(56, 891, 1050, ACCENT)
        self.text(56, 926, actions, MUTED, 13)
        self.text(56, 973, "Input stays available while work runs.", MUTED, 11)
        self.text(1544, 973, "No AI calls · no commands executed", MUTED, 11, text_anchor="end")

    def step(self, y, state, title, subtitle, active=False):
        self.el("circle", cx=72, cy=y-6, r=4, fill=ACCENT if active else GREEN)
        self.text(96, y, title, INK, 19)
        self.text(1080, y, state, ACCENT if active else MUTED, 13, text_anchor="end")
        self.text(96, y+28, subtitle, MUTED, 14)


def draw(view):
    s = Screen("Wizard / " + VIEWS[view])
    s.header("Browser" if view == "browser" else "Results" if view == "results" else "Activity")
    if view == "home":
        s.text(56, 227, "What should we check next?", INK, 28)
        s.text(56, 269, "Describe a goal. Wizard will show its work as it goes.", MUTED, 16)
        s.text(56, 360, "START A CHECK", MUTED, 12, letter_spacing=2)
        for y, title, body in [(407, "Check this project", "Find how to run it and check whether it works."),
                               (484, "Understand the project", "Explore its parts and how they connect.")]:
            s.text(56, y, title, INK, 19)
            s.text(56, y+27, body, MUTED, 14)
        s.rule(56, 550, 1050)
        s.text(56, 590, "RECENT CHECKS", MUTED, 12, letter_spacing=2)
        s.text(56, 634, "Your checks will appear here.", MUTED, 16)
        s.text(56, 664, "Opening a report never starts a new run.", MUTED, 13)
        s.companion(["You're signed in.", "What would you like to check?", "Type below to get started."])
        s.composer("", actions="/ commands     Recent checks     Open report")
    elif view in {"live", "details"}:
        s.text(56, 200, "Check sign up and log in", INK, 25)
        s.text(56, 231, "Working locally · browser enabled", MUTED, 14)
        s.text(1080, 200, "01:42", MUTED, 15, text_anchor="end")
        if view == "live":
            s.step(299, "Done", "Read the project", "Found how the app starts.  1.2s")
            s.step(378, "Done", "Start the app", "Started a process and confirmed a reachable address.  3.4s")
            s.step(457, "Done", "Open the page", "Page loaded. Saved the page's buttons and fields.  0.8s")
            s.rule(56, 501, 1050)
            s.step(548, "Running", "Fill the sign-up form", "Using the field labels from the current page.", True)
            s.text(96, 621, "LAST ACTION", MUTED, 11, letter_spacing=1.5)
            s.text(96, 657, 'Fill field labelled "Email"', ACCENT, 18)
            s.text(96, 688, "Value hidden · waiting for the browser result", MUTED, 14)
            s.text(96, 738, "New results appear here. Select a step to see its proof.", MUTED, 13)
        else:
            s.text(56, 303, "Selected step", MUTED, 12)
            s.text(56, 340, "Start the app", INK, 23)
            for y, label, value in [(395, "Requested", "Start the command found in project configuration"),
                                     (445, "Allowed", "Working directory and command passed validation"),
                                     (495, "Executed", "Process started; output captured"),
                                     (545, "Observed", "A discovered address accepted a connection")]:
                s.text(56, y, label, ACCENT, 14)
                s.text(210, y, value, INK, 14)
            s.rule(56, 582, 1050)
            s.text(56, 620, "This proves the app was reachable at this step.", INK, 16)
            s.text(56, 650, "It does not prove that sign up or login works.", MUTED, 14)
            s.text(56, 704, "Command & output     Saved observation     Back to activity", ACCENT, 13)
        s.companion(["The page is open.", "I'm checking the form.", "You can inspect any step."], "book")
        s.text(1170, 301, "THIS CHECK", MUTED, 11, letter_spacing=1.5)
        s.text(1170, 345, "Sign-up page", INK, 16)
        s.text(1170, 372, "Passed · page observed", GREEN, 12)
        s.text(1170, 422, "Create an account", INK, 16)
        s.text(1170, 449, "Still checking", ACCENT, 12)
        s.text(1170, 499, "Log in", INK, 16)
        s.text(1170, 526, "Not checked yet", MUTED, 12)
        s.text(1170, 583, "Usage updates after AI responses.", MUTED, 11)
        s.composer("", "Add guidance for the next step")
    elif view == "browser":
        s.text(56, 201, "What the browser actually saw", INK, 25)
        s.text(56, 233, "Latest saved page · captured 2 seconds ago", MUTED, 14)
        s.text(56, 301, "PAGE", MUTED, 11, letter_spacing=1.5)
        s.text(56, 341, "Create an account", INK, 23)
        s.text(56, 373, "Address available in Details", MUTED, 14)
        s.rule(56, 405, 1050)
        s.text(56, 449, "OBSERVED CONTROLS", MUTED, 11, letter_spacing=1.5)
        for y, label, state in [(493, "Email", "Text field · visible · enabled"),
                                 (539, "Password", "Private field · value hidden"),
                                 (585, "Create account", "Button · visible · enabled")]:
            s.text(56, y, label, INK, 17)
            s.text(370, y, state, MUTED, 14)
        s.rule(56, 623, 1050)
        s.text(56, 665, "After the last action", INK, 18)
        s.text(56, 698, "Email field changed. No successful submission observed yet.", MUTED, 14)
        s.text(56, 746, "Saved snapshot     Open screenshot if captured     Activity", ACCENT, 13)
        s.companion(["These are the page's real fields", "in this design example.", "Private values stay hidden."])
        s.composer("", "Ask about the current page", actions="Activity     Details     Results     Stop")
    elif view == "results":
        s.text(56, 206, "Finished. Here is what we confirmed.", INK, 25)
        s.text(56, 243, "2 passed · 1 not confirmed", MUTED, 16)
        s.step(322, "Passed", "Sign-up page opens", "Page and form controls were observed in the browser.")
        s.step(412, "Passed", "Account creation", "Submission produced an observed success state.")
        s.el("circle", cx=72, cy=496, r=4, fill=AMBER)
        s.text(96, 502, "Login", INK, 19)
        s.text(1080, 502, "Not confirmed", AMBER, 13, text_anchor="end")
        s.text(96, 533, "No valid account credentials were available for this check.", MUTED, 14)
        s.rule(56, 581, 1050)
        s.text(56, 625, "YOUR REPORT", MUTED, 11, letter_spacing=1.5)
        s.text(56, 666, "How to run the app, what was tested, and the saved proof.", INK, 16)
        s.text(56, 711, "Open report     See proof     How to run     Run a new check", ACCENT, 13)
        s.companion(["Two checks passed.", "Login still needs confirmation.", "The report explains why."])
        s.composer("", "What would you like to check next?", actions="Open report     New check     / commands")
    else:
        s.text(56, 202, "The app is not ready yet.", INK, 25)
        s.text(56, 243, "The process started, but no reachable address was confirmed.", MUTED, 16)
        s.rule(56, 282, 1050)
        s.text(56, 328, "What happened", INK, 18)
        s.text(56, 366, "Startup output reported a missing required setting.", MUTED, 15)
        s.text(56, 414, "What is still unconfirmed", INK, 18)
        s.text(56, 452, "Page loading, form submission, and login.", MUTED, 15)
        s.text(56, 527, "See startup output     Show missing setting     Stop", ACCENT, 14)
        s.text(56, 591, "Nothing will be marked Passed without proof.", MUTED, 14)
        s.companion(["I couldn't confirm the app", "is ready. Open the output", "to see what's missing."])
        s.composer("", "Ask about this problem", actions="See details     Stop     / commands")
    return s.root


def export_all(directory):
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    sprite = ET.Element("{"+NS+"}svg", {"viewBox": "0 0 36 44", "width": "144", "height": "176"})
    for row, colours in enumerate(pixels()):
        for col, colour in enumerate(colours):
            if colour:
                ET.SubElement(sprite, "{"+NS+"}rect", {"x": str(col), "y": str(row), "width": "1", "height": "1", "fill": colour})
    (destination / "cli-reaper-pose.svg").write_text(ET.tostring(sprite, encoding="unicode"), encoding="utf-8")
    for name in VIEWS:
        (destination / f"cli-workspace-{name}.svg").write_text(ET.tostring(draw(name), encoding="unicode"), encoding="utf-8")
    buttons = "".join(f'<button type="button" data-view="{name}" aria-pressed="{str(name == "live").lower()}">{label}</button>' for name, label in VIEWS.items())
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wizard — post-login design</title><style>
*{box-sizing:border-box}body{margin:0;background:#08080a;color:#f3f1ec;font:14px Consolas,monospace}
header{padding:24px 28px 12px}h1{font-size:18px;font-weight:500;margin:0 0 10px}p{color:#9d99a5;line-height:1.7;margin:0}
nav{display:flex;gap:8px;flex-wrap:wrap;padding:12px 28px}button{font:inherit;background:none;color:#aaa4b4;border:0;padding:10px 14px;cursor:pointer;border-bottom:1px solid transparent}
button[aria-pressed=true]{color:#f3f1ec;border-color:#9b7ede}button:focus-visible{outline:1px solid #9b7ede}
main{max-width:1600px;margin:auto}img{width:100%;display:block}footer{color:#9d99a5;padding:20px 28px;line-height:1.8}
</style><header><h1>Wizard / after login</h1><p>Choose a screen. This is a local design preview with sample data — not a running investigation.</p></header>
<nav aria-label="Design screens">BUTTONS <a href="cli-live-preview.html" style="color:#b8a0e4;padding:10px">Open the compact motion preview</a></nav><main><img id="screen" src="cli-workspace-live.svg" alt="Live check design"></main>
<footer>Activity grows as real events arrive. Details open on demand. Page captures stay dated. The reaper never covers the input.<br>
The first three onboarding screens remain in cli-storyboard.svg. This study expands the fourth screen and what follows.</footer>
<script>document.querySelectorAll('button[data-view]').forEach(button=>button.addEventListener('click',()=>{
document.querySelectorAll('button[data-view]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
const image=document.getElementById('screen');image.src='cli-workspace-'+button.dataset.view+'.svg';image.alt=button.textContent+' design';}));</script></html>'''
    (destination / "cli-workspace-preview.html").write_text(page.replace("BUTTONS", buttons), encoding="utf-8")


if __name__ == "__main__":
    import sys
    export_all(sys.argv[1])
