"""Export the proposed journey as native SVG. Never starts services or logs in."""
from pathlib import Path
import xml.etree.ElementTree as ET

from wizard.cli.tui.modern import ACCENT, BACKGROUND, INK, MUTED
from wizard.cli.tui.reaper import pixels


def export(destination):
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ns = "{http://www.w3.org/2000/svg}"
    root = ET.Element(ns + "svg", {"viewBox": "0 0 2000 1250", "width": "2000", "height": "1250"})
    ET.SubElement(root, ns + "title").text = "Wizard: awakening, connect, prepare, investigate"
    ET.SubElement(root, ns + "desc").text = "Four proposed UI scenes. All account codes, page content and activity are illustrative, not execution evidence."
    def element(tag, **attrs):
        return ET.SubElement(root, ns + tag, {k.replace('_', '-'): str(v) for k, v in attrs.items()})
    def rect(x, y, w, h, fill, **attrs):
        return element("rect", x=x, y=y, width=w, height=h, fill=fill, **attrs)
    def text(x, y, label, colour=INK, size=17, **attrs):
        item = element("text", x=x, y=y, fill=colour, font_size=size,
                       font_family="JetBrains Mono, Cascadia Code, Consolas, monospace", **attrs)
        item.text = label
    def line(x, y, width, colour=ACCENT):
        element("line", x1=x, y1=y, x2=x+width, y2=y, stroke=colour, stroke_width=1)
    def mascot(x, y, pose="rest"):
        for row, colours in enumerate(pixels()):
            for col, colour in enumerate(colours):
                if colour:
                    rect(x+col*3, y+row*3, 3, 3, colour)
        if pose == "book":
            rect(x+26, y+67, 32, 28, "#514361")
            rect(x+59, y+67, 32, 28, "#514361")
            rect(x+30, y+70, 26, 20, "#C5BAD6")
            rect(x+62, y+70, 26, 20, "#DBD2E6")
    def bubble(x, y, lines, width=380):
        height = 24+len(lines)*24
        rect(x, y, width, height, BACKGROUND, stroke="#514265", stroke_width=1, rx=8)
        for i, value in enumerate(lines):
            text(x+17, y+29+i*24, value, INK, 15)
        element("path", d=f"M {x+width-58} {y+height} l 9 9 l 0 -9", fill=BACKGROUND,
                stroke="#514265", stroke_width=1)
    def composer(x, y, label, width=800):
        line(x, y, width)
        text(x+10, y+33, ">", ACCENT, 20)
        text(x+35, y+33, label, INK, 18)
        rect(x+35+len(label)*10.8, y+14, 10, 23, ACCENT)
        line(x, y+52, width)
    rect(0, 0, 2000, 1250, "#101014")
    text(48, 44, "WIZARD / INTERFACE STUDY", MUTED, 13, letter_spacing=2)
    text(1952, 44, "DESIGN ONLY · NO LIVE EXECUTION", MUTED, 12, text_anchor="end")
    scenes = [(40, 80, "01 / AWAKENING"), (1020, 80, "02 / CONNECT YOUR ACCOUNT"),
              (40, 655, "03 / GETTING READY"), (1020, 655, "04 / THE LIVE WORKSPACE")]
    for x, y, label in scenes:
        rect(x, y, 940, 535, BACKGROUND)
        text(x+26, y+32, label, MUTED, 12, letter_spacing=1.5)
    x, y, _ = scenes[0]
    text(x+32, y+85, "wizard · prove what actually works.", MUTED, 15)
    text(x+32, y+157, "Your project. Real checks. Clear proof.", INK, 21)
    text(x+32, y+187, "Start with a question. I'll help with the rest.", MUTED, 15)
    bubble(x+510, y+230, ["Welcome to Wizard.", "I check your project with real proof.", "Type /login to connect your account."])
    mascot(x+740, y+350)
    composer(x+32, y+425, "/login", width=650)
    text(x+32, y+506, "Continue locally                         Skip introduction", MUTED, 12)
    x, y, _ = scenes[1]
    text(x+470, y+126, "Connect your account", INK, 23, text_anchor="middle")
    text(x+470, y+157, "Enter the code shown on the website.", MUTED, 15, text_anchor="middle")
    sample = "482971A536"
    for i in range(12):
        bx = x+93+i*59+(i//4)*24
        rect(bx, y+196, 48, 66, BACKGROUND, stroke=ACCENT if i <= len(sample) else "#29262F", rx=5)
        if i < len(sample):
            text(bx+24, y+239, sample[i], ACCENT, 30, text_anchor="middle")
        elif i == len(sample):
            rect(bx+18, y+210, 12, 36, ACCENT)
    text(x+470, y+300, "Paste the whole code                 Connect", MUTED, 14, text_anchor="middle")
    bubble(x+482, y+335, ["Browser opened.", "Paste or type your code above."], width=410)
    mascot(x+756, y+395)
    x, y, _ = scenes[2]
    text(x+32, y+85, "wizard · my-project", MUTED, 15)
    text(x+100, y+224, "You're signed in.", INK, 23)
    text(x+100, y+256, "Getting your workspace ready...", MUTED, 16)
    line(x+100, y+294, 520, "#24202D")
    for i, colour in enumerate(["#282031", "#45345F", ACCENT, "#C4A9F0", "#E5A93C", "#695137"]):
        rect(x+252+i*15, y+291, 13, 5, colour)
    text(x+100, y+329, "Show only while real setup is running.", MUTED, 12)
    bubble(x+478, y+360, ["Account connected.", "Getting things ready for you."], width=414)
    mascot(x+758, y+395, "book")
    x, y, _ = scenes[3]
    from wizard.cli.tui.workspace_preview import draw
    workspace = draw("live")
    workspace.set("x", str(x))
    workspace.set("y", str(y+48))
    workspace.set("width", "940")
    workspace.set("height", "480")
    root.append(workspace)
    text(48, 1230, "Original terminal pixel character · code format preserved · sample content only", MUTED, 12)
    Path(destination).write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")


if __name__ == "__main__":
    import sys
    export(sys.argv[1])
