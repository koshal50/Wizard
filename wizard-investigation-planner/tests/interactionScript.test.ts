/**
 * The interaction script — the decision table that lets a run operate a page.
 *
 * These are the rules, stated as tests, because every one of them is a claim
 * about someone else's running application: what may be pressed, what may be
 * typed, and what the wizard refuses to do. A rule that drifts here does not
 * fail loudly — it silently starts mutating a page nobody asked it to touch.
 */
import { strict as assert } from "node:assert";
import { test } from "node:test";

import {
  DEFAULT_MAX_STEPS,
  hostAllowed,
  interactionScriptFor,
  probeValueFor,
  type PageControl,
} from "../src/planner/interactionScript.ts";

function ctrl(over: Partial<PageControl>): PageControl {
  return { role: "button", name: "Go", selector: 'role=button[name="Go"]', ...over };
}

const ALLOWED = ["app.test"];

// ── The host rule is the Runtime's rule ─────────────────────────────────────

test("an allowlisted host admits its subdomains and not its lookalikes", () => {
  assert.ok(hostAllowed("app.test", ALLOWED));
  assert.ok(hostAllowed("www.app.test", ALLOWED));
  assert.ok(!hostAllowed("evil-app.test", ALLOWED));
  assert.ok(!hostAllowed("app.test.evil.com", ALLOWED));
  assert.ok(!hostAllowed("", ALLOWED));
  // Fail-closed, exactly like the Runtime's egress guard.
  assert.ok(!hostAllowed("app.test", []));
});

// ── What may be pressed ─────────────────────────────────────────────────────

test("a hidden control is never pressed", () => {
  const steps = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [ctrl({ tag: "button", in_form: true, form_index: 0, visible: false })],
  });
  // Not pressed because it is invisible; and with no visible field there is no
  // form to submit either.
  assert.equal(steps.length, 0);
});

test("a disabled control is never pressed", () => {
  const steps = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [ctrl({ tag: "button", in_form: true, form_index: 0, disabled: true })],
  });
  assert.equal(steps.length, 0);
});

test("a control whose name says it destroys state is never pressed", () => {
  // Each of these would permanently change the application under test.
  for (const name of ["Delete", "Remove item", "Log out", "Reset password", "Cancel order"]) {
    const steps = interactionScriptFor({
      url: "https://app.test/",
      allowedDomains: ALLOWED,
      controls: [
        ctrl({ role: "textbox", tag: "input", input_type: "text", name: "Query",
               selector: "#q", in_form: true, form_index: 0, value: "" }),
        ctrl({ tag: "button", name, in_form: true, form_index: 0 }),
      ],
    });
    assert.equal(steps.length, 1, `${name} must not be pressed`);
    assert.equal(steps[0]!.tool, "type");
  }
});

test("a link that leaves the allowlisted hosts is never followed", () => {
  const steps = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [
      ctrl({ role: "link", tag: "a", name: "Docs", href: "https://elsewhere.test/docs" }),
    ],
  });
  assert.equal(steps.length, 0);
});

test("an on-site link is left alone too — a run scripted to wander is not a script", () => {
  const steps = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [ctrl({ role: "link", tag: "a", name: "About", href: "https://app.test/about" })],
  });
  assert.equal(steps.length, 0);
});

test("a form that posts off the allowlisted hosts is never submitted", () => {
  const steps = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [
      ctrl({ role: "textbox", tag: "input", input_type: "email", name: "Email",
             selector: "#e", in_form: true, form_index: 0, form_action: "https://evil.test/steal" }),
      ctrl({ tag: "button", name: "Send", in_form: true, form_index: 0,
             form_action: "https://evil.test/steal" }),
    ],
  });
  // The field is still filled — that mutates nothing but the local page — and the
  // submit is refused, because a submit is the request the egress guard would abort.
  assert.deepEqual(steps.map((s) => s.tool), ["type"]);
});

// ── What may be typed ───────────────────────────────────────────────────────

test("a probe value is derived from the field, and stated in the step", () => {
  assert.equal(probeValueFor(ctrl({ input_type: "email" })), "wizard.probe@example.test");
  assert.equal(probeValueFor(ctrl({ input_type: "password" })), "Wizard-Probe-1a");
  assert.equal(probeValueFor(ctrl({ input_type: "tel" })), "+15550100");
  assert.equal(probeValueFor(ctrl({ input_type: "text", html_name: "username" })), "wizardprobe");
});

test("a field the wizard cannot honestly fill is skipped, not filled with noise", () => {
  // A number box, a date picker, a file input: there is no value the wizard can
  // derive, and one it invented would make a rejected submission look like a
  // broken application.
  for (const type of ["number", "date", "file", "range", "color"]) {
    assert.equal(probeValueFor(ctrl({ input_type: type })), null, type);
  }
  const steps = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [
      ctrl({ role: "textbox", tag: "input", input_type: "date", name: "Birthday",
             selector: "#b", in_form: true, form_index: 0 }),
      ctrl({ tag: "button", name: "Save", in_form: true, form_index: 0 }),
    ],
  });
  assert.equal(steps.length, 0);
});

test("a field the page already filled is not overwritten", () => {
  const steps = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [
      ctrl({ role: "textbox", tag: "input", input_type: "email", name: "Email",
             selector: "#e", in_form: true, form_index: 0, value: "already@set.test" }),
      ctrl({ tag: "button", name: "Save", in_form: true, form_index: 0 }),
    ],
  });
  assert.equal(steps.length, 0);
});

// ── The script's shape ──────────────────────────────────────────────────────

test("a sign-in form becomes fill, fill, submit — in that order", () => {
  const steps = interactionScriptFor({
    url: "https://app.test/login",
    allowedDomains: ALLOWED,
    controls: [
      ctrl({ role: "textbox", tag: "input", input_type: "email", name: "Email",
             selector: 'role=textbox[name="Email"]', in_form: true, form_index: 0 }),
      ctrl({ role: "textbox", tag: "input", input_type: "password", name: "Password",
             selector: 'role=textbox[name="Password"]', in_form: true, form_index: 0 }),
      ctrl({ tag: "button", name: "Sign in", selector: 'role=button[name="Sign in"]',
             in_form: true, form_index: 0 }),
    ],
  });
  assert.deepEqual(steps.map((s) => [s.tool, s.selector]), [
    ["type", 'role=textbox[name="Email"]'],
    ["type", 'role=textbox[name="Password"]'],
    ["click", 'role=button[name="Sign in"]'],
  ]);
  assert.equal(steps[0]!.text, "wizard.probe@example.test");
  assert.ok(steps.every((s) => s.why.length > 0), "every step states why it exists");
});

test("two forms are scripted separately, field-groups with their own submit", () => {
  // A page with a search bar and a login box: filling one and submitting the
  // other is the mistake this grouping exists to prevent.
  const steps = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [
      ctrl({ role: "textbox", tag: "input", input_type: "search", name: "Search",
             selector: "#s", in_form: true, form_index: 0 }),
      ctrl({ tag: "button", name: "Search", selector: "#go-search", in_form: true, form_index: 0 }),
      ctrl({ role: "textbox", tag: "input", input_type: "email", name: "Email",
             selector: "#e", in_form: true, form_index: 1 }),
      ctrl({ tag: "button", name: "Sign in", selector: "#go-login", in_form: true, form_index: 1 }),
    ],
  });
  assert.deepEqual(steps.map((s) => s.selector), ["#s", "#go-search", "#e", "#go-login"]);
});

test("a form with no fillable field is not submitted", () => {
  // Submitting a form the script did not touch is not a probe, it is a stray
  // mutation of someone's application.
  const steps = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [
      ctrl({ tag: "button", name: "Continue", selector: "#c", in_form: true, form_index: 0 }),
    ],
  });
  assert.equal(steps.length, 0);
});

test("a control already acted on is never scripted again", () => {
  const controls = [
    ctrl({ role: "textbox", tag: "input", input_type: "email", name: "Email",
           selector: "#e", in_form: true, form_index: 0 }),
    ctrl({ tag: "button", name: "Sign in", selector: "#go", in_form: true, form_index: 0 }),
  ];
  assert.equal(interactionScriptFor({ url: "u", allowedDomains: ALLOWED, controls }).length, 2);
  // Browser tools are exempt from the Runtime's duplicate dedup, so a provider
  // that could not see this would re-type the same field on every call.
  const again = interactionScriptFor({
    url: "u", allowedDomains: ALLOWED, controls, acted: ["#e", "#go"],
  });
  assert.equal(again.length, 0);
});

test("the script is bounded", () => {
  const controls: PageControl[] = [];
  for (let i = 0; i < 30; i++) {
    controls.push(ctrl({ role: "textbox", tag: "input", input_type: "text",
                         name: `F${i}`, selector: `#f${i}`, in_form: true, form_index: 0 }));
  }
  const steps = interactionScriptFor({ url: "u", allowedDomains: ALLOWED, controls });
  assert.equal(steps.length, DEFAULT_MAX_STEPS);
});

test("a page of nothing but links yields no script", () => {
  const steps = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [
      ctrl({ role: "link", tag: "a", name: "Home", href: "https://app.test/" }),
      ctrl({ role: "link", tag: "a", name: "About", href: "https://app.test/about" }),
    ],
  });
  assert.equal(steps.length, 0);
});

test("a lone button outside any form is pressed only when nothing else was scripted", () => {
  const alone = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [ctrl({ tag: "button", name: "Reveal", selector: "#r", in_form: false })],
  });
  assert.deepEqual(alone.map((s) => [s.tool, s.selector]), [["click", "#r"]]);

  // With a real form present the loose button is noise — it is not part of the
  // operation, and a script is not a tour of every pressable thing.
  const withForm = interactionScriptFor({
    url: "https://app.test/",
    allowedDomains: ALLOWED,
    controls: [
      ctrl({ tag: "button", name: "Reveal", selector: "#r", in_form: false }),
      ctrl({ role: "textbox", tag: "input", input_type: "email", name: "Email",
             selector: "#e", in_form: true, form_index: 0 }),
      ctrl({ tag: "button", name: "Sign in", selector: "#go", in_form: true, form_index: 0 }),
    ],
  });
  assert.deepEqual(withForm.map((s) => s.selector), ["#e", "#go"]);
});

test("an empty page yields an empty script", () => {
  assert.deepEqual(interactionScriptFor({ url: "u", allowedDomains: ALLOWED, controls: [] }), []);
});
