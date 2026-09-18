/**
 * The interaction script — given a page's controls, what the run should do to it.
 *
 * The browser plane could previously only *read* an application: navigate to a
 * URL, snapshot it, extract its text. Every control the page offered was visible
 * in the accessibility tree and unreachable in the plan, because nothing turned
 * "there is a button called Sign in" into "press it". This module is that turn.
 *
 * It is a DECISION TABLE, not a model call. The same page produces the same
 * script on every run, every step carries the reason it was chosen, and the
 * steps are materialised as ordinary plan nodes — so the script is visible in
 * the trace before it runs, and each step's effect lands in the Knowledge Graph
 * as its own immutable observation. Nothing here executes anything: it proposes,
 * the Runtime validates and runs, and the kernel's extractors decide what the
 * result meant.
 *
 * Two rules shape everything below.
 *
 * WHAT IS SAFE TO PRESS. A run is a guest in someone's running application, and
 * a click is a real mutation. So the script presses only controls it can justify:
 * the app's own form controls, visible, enabled, inside the allowlisted host, and
 * never a control whose name says it destroys something. Everything else is
 * skipped with a reason — a skip is a decision and it belongs in the trace
 * beside the steps that were taken.
 *
 * WHAT VALUE TO TYPE. The wizard cannot know a valid password, and inventing one
 * that quietly fails would make an honest "the login was rejected" look like a
 * broken app. So a field is typed only when a probe value is DERIVABLE from the
 * field itself (`type=email` gets an address-shaped string), the derived value is
 * stated in the step, and a field the wizard cannot honestly fill is left alone
 * rather than filled with noise.
 */
import { randomUUID } from "node:crypto";

/**
 * A fresh node id.
 *
 * Mints here rather than at the wire edge because a script's steps have to name
 * each other: step two depends on step one, and a dependency is an id. The edge
 * (`http/contracts.ts::nodeId`) delegates to this, so there is one id format in
 * the codebase rather than two that agree by coincidence.
 */
export function newNodeId(): string {
  return `node_${randomUUID().replace(/-/g, "").slice(0, 6)}`;
}

/** One control, as the page reported it. Mirrors runtime.py::_controls. */
export interface PageControl {
  role: string;
  name: string;
  selector: string;
  tag?: string;
  input_type?: string | null;
  html_name?: string | null;
  href?: string | null;
  disabled?: boolean;
  visible?: boolean;
  in_form?: boolean;
  form_index?: number | null;
  form_action?: string | null;
  required?: boolean;
  value?: string;
}

export interface ScriptStep {
  tool: "click" | "type";
  selector: string;
  /** Only for a type step — the probe value, stated so the trace can show it. */
  text?: string;
  /** Why this step exists. Shown to the user; never decorative. */
  why: string;
}

export interface ScriptInput {
  url: string;
  controls: readonly PageControl[];
  /** Fail-closed, exactly as the Runtime's own egress guard reads it. */
  allowedDomains: readonly string[];
  /** Selectors the run has already pressed or typed into — never repeated. */
  acted?: readonly string[];
  /** Bounded, because a script is paid for out of a finite budget. */
  maxSteps?: number;
}

/** The default script length. Long enough for a sign-in, short enough to afford. */
export const DEFAULT_MAX_STEPS = 6;

// ── Safety: which controls a run may press ───────────────────────────────────

/**
 * Names that mean "this control removes something".
 *
 * Deliberately a word list rather than a heuristic score: the rule has to be
 * predictable enough to argue about, and a false positive here costs a step the
 * run never needed, while a false negative destroys state in someone's app. The
 * list is anchored on word boundaries so "Delete account" is caught and
 * "Deleted items" (a link to a view, not an action) is not caught by "delete"
 * inside a longer word.
 */
const DESTRUCTIVE =
  /\b(delete|remove|destroy|drop|purge|erase|truncate|reset|clear|revoke|unsubscribe|deactivate|disable|logout|log out|sign out|disconnect|terminate|kill|cancel|discard)\b/i;

/** Roles whose whole job is a value the wizard would have to invent. */
const TYPED_ROLES = new Set(["textbox", "combobox", "searchbox", "spinbutton"]);

/** Types the wizard refuses to invent a value for, and would rather skip. */
const UNINVENTABLE_TYPES = new Set([
  "file", "number", "range", "date", "time", "month", "week", "datetime-local", "color",
]);

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
}

/** The Runtime's own rule: exact domain, or a subdomain of one. */
export function hostAllowed(host: string, allowed: readonly string[]): boolean {
  for (const domain of allowed) {
    const d = domain.toLowerCase().replace(/^\./, "");
    if (host === d || host.endsWith("." + d)) return true;
  }
  return false;
}

/** Why this control must not be pressed, or null when it may be. */
function refusal(control: PageControl, allowedDomains: readonly string[]): string | null {
  if (control.visible === false) return "not visible — its click would time out, not fail";
  if (control.disabled) return "disabled — pressing it cannot change anything";
  if (DESTRUCTIVE.test(control.name)) return "its name says it destroys state, which no run may do";
  if (control.role === "link" && control.href) {
    const host = hostOf(control.href);
    if (!hostAllowed(host, allowedDomains)) {
      return `it links to ${host || "an unknown host"}, outside the allowlisted hosts`;
    }
  }
  return null;
}

/**
 * A href-less control can still leave the site: a submit button posts wherever
 * its form points. Checked separately from the link case because the danger is
 * in a different attribute, and a form posting off-host would be aborted by the
 * Runtime's egress guard — one wasted budget slot and one confusing trace line.
 */
function formRefusal(control: PageControl, allowedDomains: readonly string[]): string | null {
  if (!control.in_form || !control.form_action) return null;
  const host = hostOf(control.form_action);
  if (hostAllowed(host, allowedDomains)) return null;
  return `its form posts to ${host || "an unknown host"}, outside the allowlisted hosts`;
}

// ── Probe values ─────────────────────────────────────────────────────────────

/**
 * A value for this field, derived from the field itself, or null when the
 * wizard has no honest value to give.
 *
 * Null is a real answer and the reason it exists is the whole point of this
 * function: a wizard that typed a plausible-looking password into every password
 * box would produce a run that *looks* like it signed in, fails, and leaves the
 * reader unable to tell "this app rejects logins" from "this run made one up".
 * A field with no derivable value is skipped and said to be skipped.
 */
export function probeValueFor(control: PageControl): string | null {
  const type = (control.input_type ?? "text").toLowerCase();
  if (UNINVENTABLE_TYPES.has(type)) return null;
  switch (type) {
    case "email":
      return "wizard.probe@example.test";
    case "password":
      // Stated as a constant rather than generated: the trace must be able to
      // say exactly what was typed, and a credential that changes per run cannot
      // be verified or explained afterwards.
      return "Wizard-Probe-1a";
    case "tel":
      return "+15550100";
    case "url":
      return "https://example.test/";
    case "search":
      return "probe";
    default:
      break;
  }
  // A plain text field. Named fields get a value shaped like their own name, so
  // a `username` box receives something a human validator would accept.
  const name = (control.html_name ?? control.name ?? "").toLowerCase();
  if (/user|login|handle|nick/.test(name)) return "wizardprobe";
  if (/name/.test(name)) return "Wizard Probe";
  if (/search|query|q$/.test(name)) return "probe";
  return "probe";
}

// ── The script ───────────────────────────────────────────────────────────────

/**
 * The steps this page warrants, in the order they must run.
 *
 * Grouped by form, because that is the unit the application actually offers: a
 * form's fields and its own submit button are one operation, and a page with two
 * forms (sign in / sign up, a search bar beside a login) would otherwise get a
 * script that fills one and submits the other. Within a group the fields come
 * first in DOM order and the submit control last, which is the only order a
 * browser accepts.
 */
export function interactionScriptFor(input: ScriptInput): ScriptStep[] {
  const acted = new Set(input.acted ?? []);
  const max = input.maxSteps ?? DEFAULT_MAX_STEPS;
  const controls = input.controls ?? [];
  const steps: ScriptStep[] = [];

  // group index → { fields, submits, filled }. -1 holds controls outside any
  // form, so they are scripted after the forms rather than mixed into the first.
  const groups = new Map<number, { fields: PageControl[]; submits: PageControl[]; filled: number }>();
  const loose: PageControl[] = [];

  for (const control of controls) {
    const isTyped = TYPED_ROLES.has(control.role);
    const isPressable = control.role === "button" || control.tag === "button";
    if (!isTyped && !isPressable) continue;
    const alreadyActed = acted.has(control.selector);
    if (!alreadyActed && refusal(control, input.allowedDomains)) continue;
    if (!alreadyActed && isPressable && formRefusal(control, input.allowedDomains)) continue;
    // A field the page already filled is one the run must not overwrite: it may
    // hold what a previous step correctly set, and re-typing is not the same
    // operation as filling an empty box.
    if (!alreadyActed && isTyped && (control.value ?? "") !== "") continue;

    const key = control.in_form ? (control.form_index ?? -1) : -1;
    if (key === -1) {
      if (!alreadyActed) loose.push(control);
      continue;
    }
    const group = groups.get(key) ?? { fields: [], submits: [], filled: 0 };
    if (isTyped) {
      // A field the run has already typed into counts as filled even though it
      // is not scripted again — otherwise re-planning a half-completed form
      // finds no fields to fill and, by the rule below, never submits it. The
      // second call would then stop one step short, forever.
      if (alreadyActed) group.filled++;
      else group.fields.push(control);
    } else if (!alreadyActed) {
      group.submits.push(control);
    }
    groups.set(key, group);
  }

  for (const [, group] of [...groups.entries()].sort((a, b) => a[0] - b[0])) {
    let filled = group.filled;
    for (const field of group.fields) {
      if (steps.length >= max) return steps;
      const text = probeValueFor(field);
      if (text === null) continue; // skipped, and the skip is the honest answer
      steps.push({
        tool: "type",
        selector: field.selector,
        text,
        why: `"${field.name}" is an empty ${field.input_type || "text"} field the page offers to fill`,
      });
      filled++;
    }
    // One submit per form, and only if that form was actually FILLED. Counting
    // the fields the script looked at rather than the ones it typed into submits
    // a form it left untouched — which is not a probe, it is a stray mutation.
    if (group.submits.length > 0 && filled > 0) {
      if (steps.length >= max) return steps;
      const submit = group.submits[group.submits.length - 1]!;
      steps.push({
        tool: "click",
        selector: submit.selector,
        why: `"${submit.name}" submits the form the previous steps filled`,
      });
    }
  }

  // Controls outside a form are not part of an operation, so only a lone
  // pressable one is worth a step, and only when nothing else was scripted.
  if (steps.length === 0) {
    const button = loose.find((c) => c.role === "button" || c.tag === "button");
    if (button) {
      steps.push({
        tool: "click",
        selector: button.selector,
        why: `"${button.name}" is the only control on ${input.url} the run can honestly press`,
      });
    }
  }

  return steps;
}
