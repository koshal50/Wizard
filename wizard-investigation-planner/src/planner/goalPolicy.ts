/**
 * What a goal is proven by, and what each command family is willing to pay for.
 *
 * A plan's goals come from two places: the manifest, which proposes the same set
 * for a repository however the user phrased the question, and the user's own
 * targets. Before this module the manifest's set was unconditional — every
 * family inherited it whole and could only add to it — so `wizard report` ran
 * the test suite, `wizard explain architecture` ran the runtime probe, and four
 * command families produced four near-identical runs. The family had exactly one
 * lever in the whole system (the Runtime reads `inv.intent` only to hand it to
 * the Planner) and nothing was pulling it.
 *
 * Two facts about a goal decide everything here, and both live in this file so
 * they cannot drift apart:
 *
 *   - Its EVIDENCE: which claim types the kernel's goal engine counts toward it,
 *     and whether it can only be closed by code that actually ran. Two readers
 *     disagreeing about this is a silent failure — a goal the plan believes a
 *     file closes, and the goal engine believes needs execution, can never be
 *     satisfied by anything, and it reads exactly like a goal the run failed to
 *     prove.
 *   - Its ORIGIN: whether the manifest proposed it or a target named it. "Verify
 *     Runtime" appears on both paths — the manifest suggests it for every Node
 *     repository, and `wizard verify runtime` names it — and the two are not the
 *     same goal. One is context, the other is the question.
 */

/** A command family. The Runtime's own vocabulary, not ours to extend. */
export type CommandFamily = "investigate" | "verify" | "explain" | "report";

/**
 * Where a goal in the plan came from.
 *
 *   manifest  — the repository suggests it. Context. Every family would get it.
 *   named     — a target names it in the vocabulary below ("runtime" → Verify
 *               Runtime). This is the user's question, in the plan's own words.
 *   inspected — a target resolved to files, or to nothing, and produced a
 *               read-the-files goal named after the user's word.
 */
export type GoalOrigin = "manifest" | "named" | "inspected";

export interface PlannedGoal {
  name: string;
  origin: GoalOrigin;
}

// ── Evidence routing ─────────────────────────────────────────────────────────

/** How the kernel's goal engine counts a goal as satisfied. */
export interface GoalEvidence {
  required_claim_types: string[];
  requires_execution_evidence: boolean;
}

/**
 * How a goal name is routed. First match wins, and the order is the algorithm:
 * "Inspect runtime internals" is a read-the-files goal that happens to contain
 * the word "runtime", and only testing the `Inspect` prefix first keeps it from
 * being routed as a runtime probe it cannot possibly satisfy.
 *
 * Every claim type named here must be one the kernel's extractors can actually
 * produce, from an action the plan can actually propose. A goal whose evidence
 * cannot exist is unsatisfiable by construction.
 */
const ROUTES: ReadonlyArray<{ match: RegExp; evidence: GoalEvidence }> = [
  { match: /^inspect\b/, evidence: { required_claim_types: ["FILE_READ"], requires_execution_evidence: false } },
  // Before the web route, because "Operate Web Surface" contains "Web" and only
  // the prefix test keeps it from being routed as the read-the-page goal it is
  // the opposite of. INTERACTION is a claim type a navigate cannot produce: the
  // kernel's browser extractor types `interacted:<selector>` and
  // `effect:<selector>` that way, so reaching a page and operating it are two
  // goals closed by two different pieces of evidence — and a run that reaches a
  // page and stops can no longer report that it did what was asked.
  { match: /^operate\b/, evidence: { required_claim_types: ["INTERACTION"], requires_execution_evidence: true } },
  { match: /web|browser|http/, evidence: { required_claim_types: ["WEB"], requires_execution_evidence: false } },
  { match: /runtime/, evidence: { required_claim_types: ["RUNTIME"], requires_execution_evidence: true } },
  { match: /depend|package/, evidence: { required_claim_types: ["PACKAGE"], requires_execution_evidence: false } },
  // No execution requirement: containerisation is *declared* by a file, and the
  // kernel's DEPLOYMENT claims come from reading a Dockerfile or a compose file.
  // Demanding execution evidence as well made the goal unsatisfiable by
  // construction — the evidence it asked for is not the kind that can exist.
  { match: /container|docker|deploy/, evidence: { required_claim_types: ["DEPLOYMENT"], requires_execution_evidence: false } },
  // Tests are only really verified by running them. A file-tier TESTING claim (a
  // pytest section in pyproject.toml) says the suite is *configured*, which is
  // not what "verify the tests" asks.
  { match: /test|spec|coverage/, evidence: { required_claim_types: ["TESTING"], requires_execution_evidence: true } },
  { match: /investigate|repository|filesystem/, evidence: { required_claim_types: ["FILESYSTEM"], requires_execution_evidence: false } },
];

/** A goal nothing routes: it exists to be reported on, not to be proven. */
const NO_EVIDENCE: GoalEvidence = { required_claim_types: [], requires_execution_evidence: false };

export function goalEvidenceFor(name: string): GoalEvidence {
  const n = name.toLowerCase();
  for (const route of ROUTES) {
    if (route.match.test(n)) return route.evidence;
  }
  return NO_EVIDENCE;
}

/**
 * Whether closing this goal means running something.
 *
 * This is the axis the command families differ on most, and the reason it is
 * derived from the routing rather than listed a second time: a goal that needs
 * execution evidence and a goal that is "worth executing for" are the same goal,
 * and a family policy built on a separate list would slowly stop agreeing with
 * the goal engine about which ones those are.
 */
export function isProven(name: string): boolean {
  return goalEvidenceFor(name).requires_execution_evidence;
}

/** The read-the-files goals, which the user's own words produce. */
export function isInspected(name: string): boolean {
  return /^inspect\b/i.test(name);
}

// ── The vocabulary a target is read in ───────────────────────────────────────

/**
 * The families whose question cannot be answered by looking at the page.
 *
 * `verify <url>` is a request to prove an application works, and reading its
 * HTML proves nothing about it — a web app is a thing that responds to being
 * used. `investigate <url>` is the broad version of the same request. `report`
 * and `explain` are absent because they describe: a report that pressed a
 * button would be doing the work of another command, which is the mistake the
 * family filter exists to prevent.
 *
 * This is the second half of the gate and it was missing. The words list below
 * was the whole of it, and words are the one thing a command's *target* is not:
 * `wizard verify http://localhost:5173` names an address, `isAddress` filters it
 * out of the word test, and the run reached the page and never touched it —
 * every URL-shaped target in the product read "verify" as "look at".
 */
const OPERATING_FAMILIES: ReadonlySet<string> = new Set(["verify", "investigate"]);

/**
 * Does the request ask the run to *operate* an application, rather than read it?
 *
 * The one gate on the interaction script. Pressing a form's controls creates and
 * mutates real state in someone's running app, so it stays opt-in — but by the
 * two things the user actually states: the words they typed, and the command
 * they ran. Opting in by *question alone* meant the command could not ask for
 * anything, which is the opposite failure and the one this was built to fix; a
 * run pointed at a live application by `verify` reached it and stopped.
 *
 * So there are two ways in, and both are the user speaking. A sentence or a
 * target naming an operation ("log in", "walk through the checkout", "ui") is
 * the plain case. A family that means *prove this works*, aimed at an address
 * rather than at a file, is the other: the address is the object, and proving a
 * running application works means exercising it.
 *
 * The words are operations, not topics. "ui", "frontend" and "end to end" name a
 * surface the user wants driven; "log in", "submit" and "click" name an action.
 * Generic verbs are deliberately absent — `\buse\b` alone made "which dependencies
 * does this project use" an instruction to type into a login form, and a false
 * positive here does not cost a step, it mutates someone's page. The family test
 * carries the same caution: it needs an address in the target list, so no amount
 * of `verify package.json` becomes a click.
 */
export const ACTS_ON_PAGE =
  /\b(log ?in|log ?out|sign ?in|sign ?up|sign ?out|register|submit|checkout|purchase|interact|operate|click|press|fill (?:in|out)|the (?:form|button|page|app|ui)|ui|frontend|front[- ]end|end[- ]to[- ]end|e2e|walk ?through|go ?through|drive the app|exercise the app)\b/i;

/** Does any of these words ask for the application to be operated? */
export function namesOperation(words: readonly string[]): boolean {
  return words.some((w) => ACTS_ON_PAGE.test(w));
}

/**
 * A target that names a place rather than an action. The same test the Runtime
 * uses to decide a target is a browser target at all (ports/planner.py
 * `_looks_like_url`), so the two agree about which targets are addresses.
 */
export function isAddress(target: string): boolean {
  const t = target.trim().toLowerCase();
  return t.startsWith("http://") || t.startsWith("https://");
}

/**
 * Does the *request* ask for the application to be operated?
 *
 * The one gate, read by both the goal declaration and the script rule. It takes
 * the request apart the way the two of them need it: the sentence is the
 * instruction and the targets are its objects, but an address is not an object —
 * it is a location, and a location's own text is not the user asking for
 * anything.
 *
 * That distinction is not pedantry. `/register` in a target's path is the app's
 * own name for one of its routes, and "register" is in the word list above — so
 * a gate that read every target as a word turned the request "which routes does
 * this client define", aimed at `http://localhost:5173/register`, into an
 * instruction to submit a sign-up form. That is the false positive that mutates
 * someone's page, produced by the target list alone with no sentence involved.
 *
 * `family` is the command that was run. Omitted means the words decide alone,
 * which is what a caller with no family to give should get.
 */
export function operatesSurface(
  question: string,
  targets: readonly string[],
  family = "",
): boolean {
  if (namesOperation([question, ...targets.filter((t) => !isAddress(t))])) {
    return true;
  }
  return OPERATING_FAMILIES.has(family) && targets.some(isAddress);
}

/**
 * The goals a user's *request* can name, and the words that name them.
 *
 * Matched against the request's words — the command's targets and the sentence
 * the user typed — but never against the command family. `verify` and `explain`
 * are verbs, and a verb is not a subject; reading them as text is what produced
 * goals called "Inspect explain" and "Inspect report", which no repository can
 * answer and which the run then spent budget failing to.
 *
 * The sentence is matched for the same reason the targets are: this list exists
 * to recognise what the user *said they wanted checked*, and "how do the tests
 * run" says it as plainly as the target word "testing" does. Matching only the
 * targets is what made a typed sentence a no-op — its words were stripped to
 * the few the command vocabulary knows, and every sentence that named a goal in
 * ordinary English instead of in that one word named nothing at all.
 */
export const NAMED_GOALS: ReadonlyArray<{ name: string; namedBy: RegExp }> = [
  { name: "Verify Test Suite", namedBy: /\b(tests?|testing|specs?|coverage|vitest|jest|pytest|mocha|ci)\b/ },
  { name: "Verify Runtime", namedBy: /\b(runtimes?|boot|serves?|served|start|builds?|install|version)\b/ },
  { name: "Verify Containerization", namedBy: /\b(deploy(?:ment)?s?|docker|compose|kubernetes|k8s|containers?|images?)\b/ },
  { name: "Verify Dependencies", namedBy: /\b(dependenc(?:y|ies)|packages?|librar(?:y|ies)|vulnerab\w*|outdated|audit)\b/ },
  { name: "Operate Web Surface", namedBy: ACTS_ON_PAGE },
];

/** The goals these words name, in the vocabulary above. */
export function goalsNamedBy(targets: readonly string[]): Set<string> {
  const named = new Set<string>();
  for (const target of targets) {
    for (const { name, namedBy } of NAMED_GOALS) {
      if (namedBy.test(target)) named.add(name);
    }
  }
  return named;
}

/**
 * The goals a whole request names: its targets *and* the user's own sentence.
 *
 * Both the provider that attaches named goals and the family filter that keeps
 * them call this rather than reproducing the union, because the two disagreeing
 * is silent and expensive: the provider attaches a goal the filter then deletes,
 * and the run reports on a request in which the user's words had no effect —
 * which is exactly the bug, one layer down.
 */
export function goalsNamedByRequest(
  targets: readonly string[],
  question: string,
): Set<string> {
  // The empty question is dropped rather than passed through: `\b` matches an
  // empty string's boundaries in some engines, and a set built from no words
  // should be empty by construction, not by luck.
  return goalsNamedBy(question.trim() ? [...targets, question] : targets);
}

/**
 * The goals a whole command names: the request's words *and* the command itself.
 *
 * `goalsNamedByRequest` reads the vocabulary and nothing else, and it is right
 * to: families are verbs and a verb is not a subject. But a family is not only
 * text — it is the user choosing what kind of answer they want, and for one goal
 * that choice is the whole of what names it. `Operate Web Surface` is the goal
 * closed by pressing a page's controls, and `wizard verify http://localhost:5173`
 * asks for it without a single word from the list above: the address is the
 * object and `verify` is the demand.
 *
 * Read from `operatesSurface` rather than decided again here, so the goal a plan
 * declares and the script the provider writes cannot come apart — a plan with an
 * "Operate Web Surface" goal and no steps to satisfy it is a run that reports
 * failing at something it was never given the means to do.
 */
export function goalsNamedByCommand(
  family: string,
  targets: readonly string[],
  question: string,
): Set<string> {
  const named = goalsNamedByRequest(targets, question);
  if (operatesSurface(question, targets, family)) {
    named.add("Operate Web Surface");
  }
  return named;
}


// ── What each family wants ───────────────────────────────────────────────────

/**
 * The goals a family keeps, given what the plan proposes and what the targets
 * named.
 *
 * These four were one command. Each branch below is the sentence that makes it
 * a different one, and every branch is a restriction — a family may drop a goal
 * the manifest suggested and may never invent one, so no family can make the run
 * claim more than the repository supports.
 *
 * Where a family and a target disagree, the target wins: `verify runtime` is
 * narrower than verify, because the user said which part they meant.
 */
export function goalsForFamily(
  family: CommandFamily | string,
  proposed: readonly PlannedGoal[],
  named: ReadonlySet<string>,
): string[] {
  // A family nobody stated is not a family that wants nothing. The Runtime
  // types this field as one of the four and always sends one, but a caller that
  // omits it — a test driving the provider directly, a future entry point — must
  // get the manifest's whole proposal rather than an empty plan it would have no
  // way to recognise as its own mistake. Restricting is the exception here, so
  // it is the thing that has to be asked for.
  if (!isFamily(family)) return proposed.map((g) => g.name);

  const keep = (allowed: (g: PlannedGoal) => boolean) =>
    proposed.filter(allowed).map((g) => g.name);

  switch (family) {
    case "report":
      // A report says what the repository is. It runs nothing — a report is not
      // a proof, and running the test suite to produce one is work the user
      // asked for in a different command. It also does not hunt: `report` takes
      // no target, so a question about a named part of the repository is the
      // one thing it was never asked, and `Inspect …` goals are that question.
      return keep((g) => !isProven(g.name) && !isInspected(g.name));

    case "explain":
      // Explaining answers the question that was asked, and nothing else. The
      // repository-wide goals are context an investigation needs and an
      // explanation does not: "explain the runtime" is not a request to also
      // find out about the dependencies.
      {
        const asked = keep((g) => g.origin !== "manifest");
        // A target the vocabulary does not know and no file answers to produces
        // no goal at all, and an explanation with nothing to explain would
        // report on an empty run. Falling back to what the repository can
        // describe is the honest answer to a question it cannot answer by name.
        return asked.length > 0 ? asked : keep((g) => !isProven(g.name));
      }

    case "verify":
      // Verifying proves. Aimed at one thing, it proves that thing and abandons
      // the rest — `verify containers` has no business running the test suite.
      // Aimed at something the vocabulary does not know, it proves what it can:
      // "ci" is a real target and not a goal, and reading it as "prove nothing"
      // would make the command silently do nothing at all.
      return named.size > 0
        ? keep((g) => named.has(g.name))
        : keep((g) => isProven(g.name));

    case "investigate":
    default:
      // Understanding. Everything a file can close, plus whatever the user
      // named that has to be run to be answered — so an investigation is broad
      // by default and narrows to what was aimed at. A target that names no
      // provable goal (`architecture` is a subject, not a probe) leaves a
      // read-only run, which is what investigating architecture is.
      return keep((g) => !isProven(g.name) || named.has(g.name));
  }
}

/** The families the Runtime understands, for callers that need to check one. */
export const FAMILIES: readonly CommandFamily[] = ["investigate", "verify", "explain", "report"];

export function isFamily(value: unknown): value is CommandFamily {
  return typeof value === "string" && (FAMILIES as readonly string[]).includes(value);
}
