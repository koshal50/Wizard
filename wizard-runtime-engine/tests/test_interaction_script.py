"""The interaction script: which controls a run may press, and with what.

`ports/interaction_script.py` is the Python mirror of
`wizard-investigation-planner/src/planner/interactionScript.ts`, and it is the
only place in the built-in planner that decides to *mutate someone's running
application*. The TypeScript side has `interactionScript.test.ts`; this is the
other half, and it exists because two implementations of "which controls may a
run press" that disagree is not a cosmetic divergence — one of them clicks.

The rules being asserted, restated from the module docstring:

  - a control is pressed only if it is visible, enabled, inside the allowlisted
    host, and not named after something destructive;
  - a field is typed only when a value is DERIVABLE from the field itself, and
    an underivable field is skipped and said to be skipped;
  - a form's fields are typed before its own submit is pressed, and it is
    submitted only if something was actually typed into it.

The last group is the regressions: each one is a way the script produced a
script that looked plausible and did nothing.
"""
from __future__ import annotations

from wizard_kernel.ports.interaction_script import (
    DEFAULT_MAX_STEPS,
    ScriptStep,
    interaction_script_for,
    probe_value_for,
)


def _field(selector: str, **kw) -> dict:
    """A form field control, with the keys the page always emits."""
    control = {
        "selector": selector,
        "role": "textbox",
        "name": kw.pop("name", selector),
        "input_type": kw.pop("input_type", "text"),
        "visible": True,
        "in_form": True,
        "form_index": 0,
    }
    control.update(kw)
    return control


def _button(selector: str, **kw) -> dict:
    control = {
        "selector": selector,
        "role": "button",
        "name": kw.pop("name", "Submit"),
        "tag": "button",
        "visible": True,
        "in_form": True,
        "form_index": 0,
    }
    control.update(kw)
    return control


#: A sign-in page: the ordinary shape the script exists for.
_SIGN_IN = [
    _field("#email", name="Email", input_type="email"),
    _field("#password", name="Password", input_type="password"),
    _button("button[type=submit]", name="Sign in"),
]

_URL = "http://localhost:5173/login"
_HOSTS = ["localhost"]


def _tools(steps: list[ScriptStep]) -> list[tuple[str, str]]:
    return [(s.tool, s.selector) for s in steps]


# ── The ordinary case ─────────────────────────────────────────────────────────

def test_a_sign_in_form_is_filled_and_then_submitted():
    """Fields first, submit last, and that order is the only one a browser takes.

    A script that pressed the button first would submit an empty form and then
    type into the page that came back — which is not a probe of the login, it is
    a stray mutation of whatever the app did next.
    """
    steps = interaction_script_for(_URL, _SIGN_IN, _HOSTS)
    assert _tools(steps) == [
        ("type", "#email"),
        ("type", "#password"),
        ("click", "button[type=submit]"),
    ]


def test_every_step_carries_the_reason_it_was_chosen():
    """A step with no reason is a mutation nobody can argue about."""
    for step in interaction_script_for(_URL, _SIGN_IN, _HOSTS):
        assert step.why and step.why.strip()


def test_the_value_typed_is_stated_in_the_step():
    """The trace must be able to say exactly what was typed.

    A value generated per run cannot be explained afterwards, so the derived
    ones are constants — and this asserts the constant, not a shape, because
    "derived from the field" is a claim about determinism.
    """
    steps = interaction_script_for(_URL, _SIGN_IN, _HOSTS)
    assert steps[0].text == "wizard.probe@example.test"
    assert steps[1].text == "Wizard-Probe-1a"


# ── What a run may not press ──────────────────────────────────────────────────

def test_a_control_that_destroys_something_is_never_pressed():
    """The one refusal that costs state rather than a step."""
    controls = [
        _field("#email", name="Email", input_type="email"),
        _button("#delete", name="Delete account"),
    ]
    assert _tools(interaction_script_for(_URL, controls, _HOSTS)) == [("type", "#email")]


def test_a_word_boundary_keeps_a_view_from_being_read_as_an_action():
    """"Deleted items" is a link to a list, not a button that deletes.

    Pressed loose, so the name is the only thing that could refuse it — a button
    inside a form is refused for a second reason (nothing was filled into it),
    and that would mask the claim being made here.
    """
    controls = [_button("#deleted-items", name="Deleted items", in_form=False)]
    assert _tools(interaction_script_for(_URL, controls, _HOSTS)) == [("click", "#deleted-items")]


def test_an_invisible_or_disabled_control_is_skipped():
    """Both would time out rather than fail, and a timeout is not a finding."""
    controls = [
        _field("#hidden", name="Hidden", visible=False),
        _field("#off", name="Off", disabled=True),
        _field("#email", name="Email", input_type="email"),
    ]
    assert _tools(interaction_script_for(_URL, controls, _HOSTS)) == [("type", "#email")]


def test_a_link_off_the_allowlisted_host_is_not_followed():
    """A run is a guest, and the allowlist is the whole of its invitation."""
    controls = [_button("#away", name="Elsewhere", href="https://example.com/x")]
    assert interaction_script_for(_URL, controls, _HOSTS) == []


def test_a_form_posting_off_host_is_not_submitted():
    """The danger is in a different attribute, so it is a different check.

    A href-less button can still leave the site: it posts wherever its form
    points.
    """
    controls = [
        _field("#q", name="Search", input_type="search"),
        _button("#go", name="Go", form_action="https://elsewhere.test/s"),
    ]
    assert _tools(interaction_script_for(_URL, controls, _HOSTS)) == [("type", "#q")]


def test_a_field_the_page_already_filled_is_not_overwritten():
    """Re-typing is not the same operation as filling an empty box."""
    controls = [
        _field("#email", name="Email", input_type="email", value="a@b.test"),
        _button("#go", name="Go"),
    ]
    assert interaction_script_for(_URL, controls, _HOSTS) == []


# ── What a run refuses to invent ──────────────────────────────────────────────

def test_a_field_no_value_can_be_derived_for_is_skipped():
    """The whole reason `probe_value_for` may return None.

    A wizard that typed a plausible-looking date into every date box would
    produce a run that *looks* like it filled the form, fails, and leaves the
    reader unable to tell "this app rejects the input" from "this run made one
    up".
    """
    for kind in ("file", "number", "date", "color", "range"):
        assert probe_value_for(_field("#x", input_type=kind)) is None
        assert interaction_script_for(_URL, [_field("#x", input_type=kind)], _HOSTS) == []


def test_a_form_whose_only_field_is_unfillable_is_not_submitted():
    """One submit per form, and only if that form was actually FILLED.

    Counting the fields the script looked at rather than the ones it typed into
    submits a form it left untouched — which is not a probe, it is a stray
    mutation.
    """
    controls = [
        _field("#dob", name="Date of birth", input_type="date"),
        _button("#save", name="Save"),
    ]
    assert interaction_script_for(_URL, controls, _HOSTS) == []


def test_a_named_text_field_gets_a_value_shaped_like_its_own_name():
    assert probe_value_for(_field("#u", name="username")) == "wizardprobe"
    assert probe_value_for(_field("#n", name="full name")) == "Wizard Probe"
    assert probe_value_for(_field("#s", name="search query")) == "probe"


# ── More than one form on a page ──────────────────────────────────────────────

def test_two_forms_do_not_fill_one_and_submit_the_other():
    """The reason the script groups by form at all.

    A search bar beside a sign-in is two operations the page offers, and a
    script that took the fields in DOM order and the last button on the page
    would fill the search box and press Sign in.
    """
    controls = [
        _field("#q", name="Search", input_type="search", form_index=0),
        _button("#search-go", name="Search", form_index=0),
        _field("#email", name="Email", input_type="email", form_index=1),
        _button("#sign-in", name="Sign in", form_index=1),
    ]
    assert _tools(interaction_script_for(_URL, controls, _HOSTS)) == [
        ("type", "#q"),
        ("click", "#search-go"),
        ("type", "#email"),
        ("click", "#sign-in"),
    ]


def test_a_form_with_nothing_to_type_into_is_not_submitted():
    """A form the script cannot fill is a form it has no business pressing."""
    controls = [
        _field("#a", name="A", input_type="date", form_index=0),
        _button("#go0", name="Go", form_index=0),
        _field("#email", name="Email", input_type="email", form_index=1),
        _button("#go1", name="Go", form_index=1),
    ]
    assert _tools(interaction_script_for(_URL, controls, _HOSTS)) == [
        ("type", "#email"),
        ("click", "#go1"),
    ]


# ── Regressions ───────────────────────────────────────────────────────────────

def test_the_first_form_on_a_page_is_a_form():
    """**The bug that made the browser look like it did nothing.**

    The page numbers its forms by position, so index **0** is the first form and
    the most ordinary index there is. Read through a falsy test — `form_index or
    -1` — that 0 becomes "no form at all": the sign-in page's two inputs stopped
    being fields of anything, no group ever counted itself filled, and the only
    thing left was the lone-loose-button fallback. A real login page came out as
    a single unexplained click on its submit button with both inputs untouched.

    Asserted on the whole script rather than on the index, because the index is
    not what the user sees. What they see is whether the form was filled.
    """
    steps = interaction_script_for(_URL, _SIGN_IN, _HOSTS)
    assert ("type", "#email") in _tools(steps)
    assert ("type", "#password") in _tools(steps)


def test_a_form_index_that_is_not_a_number_belongs_to_no_operation():
    """A control outside every form is scripted as loose, not as the first form."""
    controls = [
        _field("#email", name="Email", input_type="email", form_index="first"),
        _button("#go", name="Go", form_index=None),
    ]
    # Neither control can be grouped, so the fallback offers the one pressable
    # control — and no field is typed into a form that does not exist.
    assert _tools(interaction_script_for(_URL, controls, _HOSTS)) == [("click", "#go")]


def test_a_control_outside_a_form_is_not_part_of_an_operation():
    """A lone button is worth one step; a lone field is not worth anything."""
    loose = [_field("#email", name="Email", input_type="email", in_form=False)]
    assert interaction_script_for(_URL, loose, _HOSTS) == []


def test_the_only_loose_button_is_pressed_when_nothing_else_was_scripted():
    controls = [_button("#start", name="Start", in_form=False)]
    steps = interaction_script_for(_URL, controls, _HOSTS)
    assert _tools(steps) == [("click", "#start")]
    assert _URL in steps[0].why


def test_a_control_the_run_already_acted_on_is_not_pressed_twice():
    """A half-completed form must not restart, and must not stall either.

    A field the run has already typed into counts as filled even though it is
    not scripted again — otherwise re-planning a half-completed form finds no
    fields to fill and, by the rule above, never submits it. The second call
    would then stop one step short, forever.
    """
    steps = interaction_script_for(_URL, _SIGN_IN, _HOSTS, acted=["#email", "#password"])
    assert _tools(steps) == [("click", "button[type=submit]")]


def test_a_run_that_acted_on_the_whole_form_has_nothing_left_to_do():
    acted = ["#email", "#password", "button[type=submit]"]
    assert interaction_script_for(_URL, _SIGN_IN, _HOSTS, acted=acted) == []


def test_the_script_stops_at_the_step_budget():
    """A page offering more controls than the run can afford gets the prefix.

    The budget is a refusal, so it truncates rather than dropping steps out of
    the middle: a script that skipped its own submit would leave a filled form
    unsent, which is a mutation with no finding attached.
    """
    controls = [_field(f"#f{i}", name=f"F{i}") for i in range(20)]
    controls.append(_button("#go", name="Go"))
    steps = interaction_script_for(_URL, controls, _HOSTS, max_steps=3)
    assert _tools(steps) == [("type", "#f0"), ("type", "#f1"), ("type", "#f2")]
    assert len(steps) <= 3 < DEFAULT_MAX_STEPS


def test_a_control_that_is_not_an_object_is_skipped_rather_than_raising():
    """The controls arrive as JSON from a page JavaScript built."""
    controls = [None, "not a control", 7, _field("#email", name="Email", input_type="email")]
    assert _tools(interaction_script_for(_URL, controls, _HOSTS)) == [("type", "#email")]
