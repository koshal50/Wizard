"""The interaction script — given a page's controls, what the run should do to it.

**The source of truth for every rule in this file is
`wizard-investigation-planner/src/planner/interactionScript.ts`**, and this is
its mirror for the built-in planner. The same reason `goal_policy.py` is a
mirror of `goalPolicy.ts`: the Runtime's `MockPlanner` is the planner a run gets
when `options.planner_url` is unset, and it reaches the same page the
TypeScript planner reaches. Two implementations of "which controls may a run
press" that disagree is not a cosmetic divergence — one of them mutates someone's
application.

The browser plane could previously only *read* an application: navigate to a
URL, snapshot it, extract its text. Every control the page offered was visible in
the accessibility tree and unreachable in the plan, because nothing turned "there
is a button called Sign in" into "press it". This module is that turn.

It is a DECISION TABLE, not a model call. The same page produces the same script
on every run, every step carries the reason it was chosen, and the steps become
ordinary plan nodes — so the script is visible in the trace before it runs, and
each step's effect lands in the Knowledge Graph as its own immutable observation.
Nothing here executes anything: it proposes, the Runtime validates and runs, and
the kernel's extractors decide what the result meant.

Two rules shape everything below. They are the first file's rules, restated
rather than re-decided.

WHAT IS SAFE TO PRESS. A run is a guest in someone's running application, and a
click is a real mutation. So the script presses only controls it can justify: the
app's own form controls, visible, enabled, inside the allowlisted host, and never
a control whose name says it destroys something. Everything else is skipped with
a reason — a skip is a decision and it belongs in the trace beside the steps that
were taken.

WHAT VALUE TO TYPE. The wizard cannot know a valid password, and inventing one
that quietly fails would make an honest "the login was rejected" look like a
broken app. So a field is typed only when a probe value is DERIVABLE from the
field itself (`type=email` gets an address-shaped string), the derived value is
stated in the step, and a field the wizard cannot honestly fill is left alone
rather than filled with noise.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

#: The default script length. Long enough for a sign-in, short enough to afford.
DEFAULT_MAX_STEPS = 6


@dataclass(frozen=True)
class ScriptStep:
    """One thing to do to the page, and why.

    `tool` is the Runtime's own vocabulary — `click` and `type` are what
    `browser_click` and `browser_type` mean — and `why` is shown to the user. A
    step with no reason is a mutation nobody can argue about.
    """

    tool: str
    selector: str
    why: str
    text: str | None = None


# ── Safety: which controls a run may press ───────────────────────────────────

#: Names that mean "this control removes something".
#:
#: Deliberately a word list rather than a heuristic score: the rule has to be
#: predictable enough to argue about, and a false positive here costs a step the
#: run never needed, while a false negative destroys state in someone's app. The
#: list is anchored on word boundaries so "Delete account" is caught and
#: "Deleted items" (a link to a view, not an action) is not caught by "delete"
#: inside a longer word.
DESTRUCTIVE = re.compile(
    r"\b(delete|remove|destroy|drop|purge|erase|truncate|reset|clear|revoke|"
    r"unsubscribe|deactivate|disable|logout|log out|sign out|disconnect|"
    r"terminate|kill|cancel|discard)\b",
    re.IGNORECASE,
)

#: Roles whose whole job is a value the wizard would have to invent.
TYPED_ROLES = frozenset({"textbox", "combobox", "searchbox", "spinbutton"})

#: Types the wizard refuses to invent a value for, and would rather skip.
UNINVENTABLE_TYPES = frozenset({
    "file", "number", "range", "date", "time", "month", "week",
    "datetime-local", "color",
})


def _field(control: dict, key: str, default=None):
    """One key of a control, or `default` when it is absent or null.

    The controls arrive as JSON from a page JavaScript built, so a key can be
    missing, null, or a type nobody promised. Every read goes through here so a
    malformed control is a control that is skipped, never an exception that ends
    a run.
    """
    value = control.get(key, default)
    return default if value is None else value


def host_of(url: str) -> str:
    """The hostname of a URL, lowercased, or "" when it is not one."""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def host_allowed(host: str, allowed: list[str]) -> bool:
    """The Runtime's own rule: exact domain, or a subdomain of one."""
    for domain in allowed:
        d = str(domain).lower().lstrip(".")
        if host == d or host.endswith("." + d):
            return True
    return False


def _refusal(control: dict, allowed_domains: list[str]) -> str | None:
    """Why this control must not be pressed, or None when it may be."""
    if _field(control, "visible", True) is False:
        return "not visible — its click would time out, not fail"
    if _field(control, "disabled", False):
        return "disabled — pressing it cannot change anything"
    if DESTRUCTIVE.search(str(_field(control, "name", ""))):
        return "its name says it destroys state, which no run may do"
    href = _field(control, "href")
    if _field(control, "role") == "link" and href:
        host = host_of(str(href))
        if not host_allowed(host, allowed_domains):
            return f"it links to {host or 'an unknown host'}, outside the allowlisted hosts"
    return None


def _form_refusal(control: dict, allowed_domains: list[str]) -> str | None:
    """Why this control's own form must not be submitted, or None.

    A href-less control can still leave the site: a submit button posts wherever
    its form points. Checked separately from the link case because the danger is
    in a different attribute, and a form posting off-host would be aborted by the
    Runtime's egress guard — one wasted budget slot and one confusing trace line.
    """
    if not _field(control, "in_form", False):
        return None
    action = _field(control, "form_action")
    if not action:
        return None
    host = host_of(str(action))
    if host_allowed(host, allowed_domains):
        return None
    return f"its form posts to {host or 'an unknown host'}, outside the allowlisted hosts"


# ── Probe values ─────────────────────────────────────────────────────────────

def probe_value_for(control: dict) -> str | None:
    """A value for this field, derived from the field itself, or None.

    None is a real answer and the reason it exists is the whole point of this
    function: a wizard that typed a plausible-looking password into every
    password box would produce a run that *looks* like it signed in, fails, and
    leaves the reader unable to tell "this app rejects logins" from "this run
    made one up". A field with no derivable value is skipped and said to be
    skipped.
    """
    kind = str(_field(control, "input_type", "text") or "text").lower()
    if kind in UNINVENTABLE_TYPES:
        return None
    if kind == "email":
        return "wizard.probe@example.test"
    if kind == "password":
        # Stated as a constant rather than generated: the trace must be able to
        # say exactly what was typed, and a credential that changes per run
        # cannot be verified or explained afterwards.
        return "Wizard-Probe-1a"
    if kind == "tel":
        return "+15550100"
    if kind == "url":
        return "https://example.test/"
    if kind == "search":
        return "probe"
    # A plain text field. Named fields get a value shaped like their own name, so
    # a `username` box receives something a human validator would accept.
    name = str(_field(control, "html_name") or _field(control, "name", "") or "").lower()
    if re.search(r"user|login|handle|nick", name):
        return "wizardprobe"
    if re.search(r"name", name):
        return "Wizard Probe"
    if re.search(r"search|query|q$", name):
        return "probe"
    return "probe"


# ── The script ───────────────────────────────────────────────────────────────

def _is_typed(control: dict) -> bool:
    return str(_field(control, "role", "")) in TYPED_ROLES


def _form_index(control: dict) -> int:
    """Which form this control belongs to, or -1 when it belongs to none.

    The page numbers its forms by position (`world/browser/runtime.py` emits
    `forms.indexOf(form)`), so **0 is the first form** and the most ordinary
    index there is. Reading it through a falsy test — `form_index or -1` — turns
    the first form on every page into "no form at all": its fields stop being
    fields of anything, no group ever counts itself filled, and the only thing
    left for the script is the lone-loose-button fallback. A real sign-in page
    came out as a single unexplained click on its submit button with both inputs
    untouched, which is what a reader sees as a browser that opens a page and
    does nothing to it.

    This is `control.form_index ?? -1` on the TypeScript side, and it is spelled
    out here because the two must agree about which controls are one operation.
    """
    if not _field(control, "in_form", False):
        return -1
    index = _field(control, "form_index", -1)
    try:
        return int(index)
    except (TypeError, ValueError):
        # A page can emit anything. An index nobody can read is not the first
        # form; it is a control that belongs to no operation the script can name.
        return -1


def _is_pressable(control: dict) -> bool:
    return _field(control, "role") == "button" or _field(control, "tag") == "button"


def interaction_script_for(
    url: str,
    controls: list[dict],
    allowed_domains: list[str] | None = None,
    acted: list[str] | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> list[ScriptStep]:
    """The steps this page warrants, in the order they must run.

    Grouped by form, because that is the unit the application actually offers: a
    form's fields and its own submit button are one operation, and a page with
    two forms (sign in / sign up, a search bar beside a login) would otherwise
    get a script that fills one and submits the other. Within a group the fields
    come first in DOM order and the submit control last, which is the only order
    a browser accepts.
    """
    seen = set(acted or ())
    domains = list(allowed_domains or ())
    steps: list[ScriptStep] = []

    # form index -> {"fields", "submits", "filled"}. -1 holds controls outside
    # any form, so they are scripted after the forms rather than mixed into the
    # first.
    groups: dict[int, dict] = {}
    loose: list[dict] = []

    for control in controls:
        if not isinstance(control, dict):
            continue
        typed, pressable = _is_typed(control), _is_pressable(control)
        if not typed and not pressable:
            continue
        selector = str(_field(control, "selector", ""))
        if not selector:
            continue
        already = selector in seen
        if not already and _refusal(control, domains):
            continue
        if not already and pressable and _form_refusal(control, domains):
            continue
        # A field the page already filled is one the run must not overwrite: it
        # may hold what a previous step correctly set, and re-typing is not the
        # same operation as filling an empty box.
        if not already and typed and str(_field(control, "value", "") or "") != "":
            continue

        key = _form_index(control)
        if key == -1:
            if not already:
                loose.append(control)
            continue
        group = groups.setdefault(key, {"fields": [], "submits": [], "filled": 0})
        if typed:
            # A field the run has already typed into counts as filled even though
            # it is not scripted again — otherwise re-planning a half-completed
            # form finds no fields to fill and, by the rule below, never submits
            # it. The second call would then stop one step short, forever.
            if already:
                group["filled"] += 1
            else:
                group["fields"].append(control)
        elif not already:
            group["submits"].append(control)

    for key in sorted(groups):
        group = groups[key]
        filled = group["filled"]
        for fld in group["fields"]:
            if len(steps) >= max_steps:
                return steps
            text = probe_value_for(fld)
            if text is None:
                continue  # skipped, and the skip is the honest answer
            steps.append(ScriptStep(
                tool="type",
                selector=str(fld["selector"]),
                text=text,
                why=f'"{_field(fld, "name", "")}" is an empty '
                    f'{_field(fld, "input_type", "text") or "text"} field the page offers to fill',
            ))
            filled += 1
        # One submit per form, and only if that form was actually FILLED.
        # Counting the fields the script looked at rather than the ones it typed
        # into submits a form it left untouched — which is not a probe, it is a
        # stray mutation.
        if group["submits"] and filled > 0:
            if len(steps) >= max_steps:
                return steps
            submit = group["submits"][-1]
            steps.append(ScriptStep(
                tool="click",
                selector=str(submit["selector"]),
                why=f'"{_field(submit, "name", "")}" submits the form the previous steps filled',
            ))

    # Controls outside a form are not part of an operation, so only a lone
    # pressable one is worth a step, and only when nothing else was scripted.
    if not steps:
        button = next((c for c in loose if _is_pressable(c)), None)
        if button is not None:
            steps.append(ScriptStep(
                tool="click",
                selector=str(button["selector"]),
                why=f'"{_field(button, "name", "")}" is the only control on {url} '
                    "the run can honestly press",
            ))

    return steps
