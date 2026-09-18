/**
 * HeuristicLLMProvider — the offline, deterministic default provider.
 *
 * It produces genuinely useful planning output WITHOUT any network access or API
 * key, by reading the structured `request.context` the Planner assembles and
 * applying fixed rules. This is what makes the whole system runnable offline and
 * reproducible in CI: same context in → same plan out, and ZERO real LLM calls.
 *
 * It dispatches on `request.purpose`:
 *   - technology_plan → derive a TechnologyPlan from the manifest summary.
 *   - ongoing_plan    → propose the next investigation nodes to fill the current
 *                       goal's missing requirements (a read→parse→verify chain,
 *                       plus a guarded execute probe for runtime goals).
 *   - escalation      → conservative recovery: at most one re-read, else record.
 *
 * The object it builds is still run through the caller's schema, so if a context
 * is malformed the call fails honestly instead of returning garbage.
 */
import type { Schema } from "../../validation/schema.ts";
import { safeParse } from "../../validation/schema.ts";
import type { LLMProvider, LLMRequest, LLMResult } from "../LLMProvider.ts";
import { llmErr, llmOk } from "../LLMProvider.ts";
import {
  goalsForFamily,
  goalsNamedBy,
  goalsNamedByCommand,
  operatesSurface,
  type GoalOrigin,
  type PlannedGoal,
} from "../../planner/goalPolicy.ts";
import {
  interactionScriptFor,
  newNodeId,
  type PageControl,
} from "../../planner/interactionScript.ts";

// ── Context contracts (what the Planner puts in request.context) ─────────────

interface ManifestContext {
  languages?: string[];
  frameworks?: string[];
  packageManagers?: string[];
  dependencies?: string[];
  databases?: string[];
  keyFiles?: string[];
  entryFiles?: string[];
  projectType?: string;
  /** Every file the scan saw — what a named target is resolved against. */
  treeFiles?: string[];
  /**
   * The command family: "investigate" | "verify" | "explain" | "report".
   *
   * A family, not a sentence. This seam used to read it as the user's own
   * words, which is how `explain` became a goal called "Inspect explain" that
   * no repository can answer.
   */
  intent?: string;
  /** The user's question, verbatim. Absent when they typed none. */
  question?: string;
  /** The things the user named, verbatim. */
  targets?: string[];
}

interface RequirementContext {
  claimType: string;
  description?: string;
  expectedValue?: string;
}

interface OngoingContext {
  goalTechnology?: string;
  allowExecution?: boolean;
  missingRequirements?: RequirementContext[];
  priorityFiles?: string[];
  parsedObservationIds?: Record<string, string>; // filePath -> observationId
  fileObservationIds?: Record<string, string>; // filePath -> observationId (raw read)
  // Files a node already in the Runtime's graph is going to read. Not the same
  // question as fileObservationIds ("what has run"): a read that is queued has
  // not run yet, so it is absent from the index while its evidence is already
  // on its way, and proposing it again yields a node the Runtime refuses.
  queuedReadPaths?: string[];
  browserEnabled?: boolean;
  allowedDomains?: string[];
  browserTargets?: string[];
  visitedUrls?: string[];
  /** The page the run is currently on, and what it offers. */
  pageUrl?: string;
  pageControls?: PageControl[];
  /** Selectors already typed into or pressed. Never scripted a second time. */
  interactedSelectors?: string[];
  intent?: string;
  /** The user's sentence, verbatim. Distinct from `intent` — that one is the family. */
  question?: string;
  targets?: string[];
}

interface EscalationCtx {
  nodeId?: string;
  filePath?: string;
  alreadyReadPaths?: string[];
  reason?: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}
function strArr(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}
function has(hay: string[], needle: string): boolean {
  return hay.some((h) => h.toLowerCase().includes(needle.toLowerCase()));
}

// ── The user's question ───────────────────────────────────────────────────────
// The manifest is the same for every investigation of a repository. The
// question, the targets and the command family are the only inputs that differ,
// and they are what this provider used to ignore entirely — so two runs on one
// repo produced the same technologies, the same goals, the same nodes and the
// same commands, whatever was asked. Everything below turns those three inputs
// into plan material.
//
// Which of a goal's claim types are the ones the kernel counts is NOT decided
// here: it is decided once, in planner/goalPolicy.ts, because a provider that
// believes a goal is closable by reading a file and a goal engine that requires
// execution evidence for it produce a goal that can never be satisfied — and
// nothing about the resulting run distinguishes that from a goal the run failed
// to prove.
//
// Two rules keep it honest:
//   1. A goal this provider invents must be closable — its required claim types
//      (routed by goalDefFor in http/contracts.ts) must be ones the kernel's
//      extractors can actually produce from an action the plan can propose.
//   2. A target this provider cannot resolve to a file contributes nothing
//      rather than a guess. Its goal stays open, and the run says so.

/** The verb a user leads with when they are naming a subject to look into. */
const _LEADING_VERB =
  /^(?:please\s+)?(?:investigate|inspect|examine|explore|analyse|analyze|review|check|verify|find|map|trace|understand|audit|look\s+(?:at|into)|walk\s+through|tell\s+me\s+about)\b[\s:,-]*/i;

/**
 * A clause that asks something is not a subject to go and read.
 *
 * "how does this get deployed" and "verify the test suite is real" both survive
 * leading-verb stripping and would otherwise become goals named after a whole
 * sentence. A subject is a noun phrase; an interrogative word or a finite verb
 * says this is a question, and a question is answered by the *keyword* goals
 * below ("how does this get deployed" → Verify Containerization), not by being
 * repeated back as an Inspect goal.
 */
const _NOT_A_SUBJECT =
  /\b(how|what|why|where|when|which|who|whom|whose|does|do|did|is|are|was|were|has|have|had|can|could|should|would|will|must|if|whether|there)\b/i;

/** How many subjects one intent may contribute. A run has a budget. */
const _MAX_SUBJECTS = 3;

/**
 * The subjects an intent names, e.g. "investigate the auth flow and verify the
 * runtime" → ["auth flow"].
 *
 * Goals from subjects are named `Inspect …`, and that prefix is the routing
 * marker: goalDefFor sends an `Inspect …` goal to the read-the-files family
 * whatever else the subject happens to say. Naming the goal after the user's
 * own words is what makes the report answer the question that was asked.
 */
function intentSubjects(intent: string): string[] {
  const subjects: string[] = [];
  for (const clause of intent.split(/\s*(?:,|;|\band\b|\bthen\b|\balso\b)\s*/i)) {
    let s = clause.trim().replace(_LEADING_VERB, "").trim();
    s = s.replace(/^(?:the|a|an|our|my|this|that|its)\s+/i, "").trim();
    s = s.replace(/[.?!]+$/, "").trim();
    if (s.length < 3 || s.length > 60) continue;
    if (_NOT_A_SUBJECT.test(s)) continue;
    subjects.push(s);
    if (subjects.length >= _MAX_SUBJECTS) break;
  }
  return subjects;
}

/**
 * Words that carry no subject of their own.
 *
 * Deliberately function words only — no content words. The real filter is the
 * one below it: a word is kept only if it resolves to a file that exists, so
 * "lose" and "session" in "why does the login form lose my session" are dropped
 * by the repository itself rather than by a list someone had to guess at. This
 * set exists only for the words that *would* resolve and still mean nothing to
 * act on.
 */
const _FUNCTION_WORD = new Set([
  "about", "after", "again", "against", "also", "because", "been", "before",
  "being", "between", "both", "cannot", "could", "does", "doing", "done",
  "down", "during", "each", "either", "else", "even", "ever", "every", "from",
  "further", "have", "having", "here", "into", "itself", "just", "least",
  "less", "like", "many", "might", "more", "most", "much", "must", "neither",
  "never", "only", "other", "ourselves", "over", "same", "shall", "should",
  "since", "some", "still", "such", "than", "that", "their", "theirs", "them",
  "themselves", "then", "there", "these", "they", "this", "those", "through",
  "under", "until", "very", "were", "what", "when", "where", "whether",
  "which", "while", "whose", "will", "with", "within", "without", "would",
  "your", "yours", "yourself",
]);

/**
 * The words in a question that name something the repository actually has.
 *
 * A question is not a subject: "why does the login form lose my session" is a
 * sentence, and `intentSubjects` is right to refuse it — repeating it back
 * would make a goal called "Inspect why does the login form lose my session".
 * But refusing it entirely left the sentence recorded and never acted on, so a
 * question planned exactly like a bare `investigate` and the run went and read
 * the manifests instead of the login page.
 *
 * So the question is taken apart rather than repeated: each word is looked up
 * in the repository's own file list, and only the ones that land are kept. The
 * goal that comes out is named after the user's own word ("Inspect login") and
 * carries real paths, which is the same standard every other goal here is held
 * to. A word that matches nothing is dropped rather than turned into a goal —
 * this path never produces an unresolved interest, because most of a question
 * is not nouns and the run would spend its budget on "Inspect lose".
 */
function questionWords(
  question: string,
  files: string[],
  norm: string[],
): string[] {
  const words = question
    .toLowerCase()
    .split(/[^a-z0-9_.-]+/)
    .filter((w) => w.length >= 4);
  const kept: string[] = [];
  for (const word of words) {
    if (_FUNCTION_WORD.has(word)) continue;
    if (kept.includes(word)) continue;
    if (lookupInterest(word, files, norm).length === 0) continue;
    kept.push(word);
    if (kept.length >= _MAX_SUBJECTS) break;
  }
  return kept;
}

/** How many files one interest may pull in, and how many interests in total. */
const _FILES_PER_INTEREST = 8;
const _MAX_INTEREST_FILES = 12;
const _MAX_INTERESTS = 4;

/** An interest is something the user asked about, and the files behind it. */
interface Interest {
  /** The user's own words for it. Becomes the goal name. */
  name: string;
  /** Real repository paths. What the run should actually go and read. */
  files: string[];
}

/**
 * One interest looked up in the repository's own file list: as an exact file,
 * then as a directory, then as a name fragment — each step a weaker claim than
 * the last, and all three grounded in a path that exists, so nothing here can
 * send the Runtime after a file that is not there.
 */
/**
 * One interest looked up in the repository's own file list: as an exact file,
 * then as a directory, then as a name fragment — each step a weaker claim than
 * the last, and all three grounded in a path that exists, so nothing here can
 * send the Runtime after a file that is not there.
 *
 * `norm` is the tree normalised for comparison only; the match is returned as
 * the original string. Handing back the normalised form looks equivalent and is
 * not: the Runtime's observation index keys on the path as the filesystem
 * reports it, so a plan that spells a Windows path with forward slashes
 * describes a file the index has never heard of — and the planner then proposes
 * that read again, and again, until the duplicate-request validator refuses it.
 */
function lookupInterest(needle: string, files: string[], norm: string[]): string[] {
  const clean = needle.replace(/\\/g, "/").replace(/^\.\//, "").replace(/\/+$/, "").trim();
  if (!clean) return [];

  let idx = norm.map((_, i) => i).filter((i) => norm[i] === clean);
  if (idx.length === 0) {
    const prefix = clean + "/";
    idx = norm.map((_, i) => i).filter((i) => norm[i]!.startsWith(prefix));
  }
  if (idx.length === 0 && clean.length >= 3) {
    // The interest as a name fragment: "auth" finds routes/auth.js,
    // auth.test.js, src/middleware/auth.js. A substring test rather than a
    // last-segment one, so the common "auth/…" directory case is not missed.
    idx = norm.map((_, i) => i).filter((i) => norm[i]!.includes(clean));
  }

  // Nothing matched, which usually means the user's word is *longer* than the
  // name in the repository rather than different from it: the CLI target is
  // "authentication" and the file is auth.js. Shrink the needle until it lands,
  // longest stub first, so the most specific match wins and a shorter one only
  // gets its turn when the longer one found nothing at all.
  if (idx.length === 0 && clean.length > 4) {
    for (let n = clean.length - 1; n >= 4; n--) {
      const stub = clean.slice(0, n);
      const found = norm.map((_, i) => i).filter((i) => norm[i]!.includes(stub));
      if (found.length > 0) return found.map((i) => files[i]!);
    }
  }
  return idx.map((i) => files[i]!);
}

/** An interest's files, and whether the name itself is what found them. */
interface Resolved {
  files: string[];
  /** The name landed whole, rather than one word of it landing on its own. */
  asPhrase: boolean;
}

/**
 * The files behind one interest. A phrase is tried whole before its words are
 * tried separately, because the user's phrasing is usually longer than a
 * filename: "authentication flow" matches nothing, while its word
 * "authentication" matches routes/auth.js, middleware/auth.js and auth.test.js.
 * Falling back from phrase to word is what keeps a named interest from
 * resolving to nothing; taking the widest result keeps it from resolving to
 * the wrong single file.
 *
 * Which of the two landed is reported, not just what came back, because the two
 * are not equally good answers and the caller has to be able to tell them
 * apart. "authentication" finding auth.js is the repository confirming the name
 * the user gave. "form" finding TaskForm.jsx inside the phrase "fill the
 * sign-up form" is the repository answering a question nobody asked — see
 * `collectInterests` for what that distinction is used to reject.
 */
function resolveInterest(name: string, files: string[], norm: string[]): Resolved {
  const lowerName = name.toLowerCase();
  const needles = [lowerName];
  const words = lowerName.split(/\s+/).filter((w) => w.length >= 4);
  if (words.length > 1) needles.push(...words);

  let best: string[] = [];
  let asPhrase = false;
  for (const needle of needles) {
    const hits = lookupInterest(needle, files, norm);
    if (needle === lowerName && hits.length > 0) asPhrase = true;
    if (hits.length > best.length) best = hits;
    // The phrase itself landed. Its individual words are each narrower, so
    // none of them can improve on it.
    if (needle === lowerName && best.length > 0) break;
  }
  return { files: best.slice(0, _FILES_PER_INTEREST), asPhrase };
}

/**
 * What the user asked about, resolved to files, with the duplicates merged.
 *
 * Targets and subjects are the same kind of thing — something named, that the
 * repository may or may not contain — so they go through one resolver and one
 * dedupe. "investigate the authentication flow" with target "auth" is one
 * interest, not two: both resolve to the same files, and emitting both would put
 * two goals on the plan that the same three reads close together.
 *
 * The two sources are held to different standards, and this is where that is
 * decided. A TARGET is the user pointing at something: "architecture" and "ci"
 * are real things to ask about and neither is a filename, so a target that
 * resolves to nothing is still reported back and becomes a goal closed by the
 * run's own reading. A phrase taken out of a SENTENCE is not a name until the
 * repository answers to it — see `questionWords` for the same rule applied to
 * single words — and admitting one that resolves to nothing is how the request
 * "log in to the app, fill the sign-up form and submit it" produced three goals
 * called "Inspect log in to the app", "Inspect fill the sign-up form" and
 * "Inspect submit it". Nothing in the repository answers to any of them, all
 * three require only FILE_READ, and the run's five file reads therefore closed
 * all three — a report claiming to have answered three questions that were
 * never questions, on evidence that had nothing to do with them.
 *
 * Dropping the phrases that resolve to nothing fixed two of the three and left
 * the third, because "fill the sign-up form" does not resolve to nothing: its
 * word "form" is in TaskForm.jsx. One generic word out of a clause is not the
 * repository confirming a name — it is the repository answering a question
 * nobody asked. So the two sources are held to two standards, and it is the
 * phrase/word split in `resolveInterest` that separates them: a name the user
 * chose may land on one of its words, because the word is a shorter version of
 * the name they gave; a clause of their prose may not, because the clause was
 * never a name to begin with.
 */
function collectInterests(
  question: string,
  targets: string[],
  treeFiles: string[],
): { resolved: Interest[]; unresolved: string[] } {
  // `files` keeps the repository's own spelling; `norm` is for comparison. The
  // paths that leave here are handed to the Runtime as tool parameters, so they
  // have to be the strings the filesystem actually answers to.
  const files = treeFiles;
  const norm = treeFiles.map((f) => f.replace(/\\/g, "/").toLowerCase());

  // Targets first: they are what the user explicitly pointed at, so they win
  // both the ordering and any dedupe tie.
  const named: string[] = [];
  for (const raw of targets.slice(0, _MAX_INTERESTS)) {
    // A URL is the browser's business, not the filesystem's.
    if (/^https?:\/\//i.test(raw)) continue;
    const t = raw.replace(/\\/g, "/").replace(/^\.\//, "").replace(/\/+$/, "").trim();
    if (t) named.push(t);
  }
  // Everything from here on came out of the sentence, so it is held to the
  // standard below.
  const fromTargets = named.length;
  named.push(...intentSubjects(question));
  // Then the question's own words, which are a weaker source than a subject —
  // see questionWords for why they are admitted only when they resolve.
  named.push(...questionWords(question, files, norm));

  const candidates: Interest[] = [];
  const unresolved: string[] = [];
  for (const [i, name] of named.entries()) {
    const { files: hits, asPhrase } = resolveInterest(name, files, norm);
    const namedByUser = i < fromTargets;
    // A phrase out of a sentence that resolves to nothing was never a name. It
    // is dropped rather than reported, because "unresolved" means "the user
    // named this and the repository does not have it" — and a clause of their
    // prose is not a name they gave.
    //
    // The same holds for a clause that resolves only through one of its words.
    // A name the user chose may land on a word of itself — "authentication"
    // becoming auth.js is the repository answering to a shorter version of what
    // they typed. A clause may not: "fill the sign-up form" landing on
    // TaskForm.jsx because the word "form" is in the filename is the repository
    // answering a question nobody asked, and it produced a goal named after the
    // instruction that the run's next file read closed.
    if (hits.length === 0 || (!namedByUser && !asPhrase)) {
      if (namedByUser) unresolved.push(name);
      continue;
    }
    candidates.push({ name, files: hits });
  }

  // Drop an interest whose files are already fully covered by another. Same
  // evidence means the same goal, so one of the two names is redundant — and
  // the wider one, or the earlier one when they are the same width, is the one
  // whose name the user is more likely to recognise.
  const covered = (a: Interest, b: Interest) => a.files.every((f) => b.files.includes(f));
  const resolved = candidates.filter((c, i) =>
    !candidates.some((o, j) =>
      o !== c && covered(c, o) && (o.files.length > c.files.length || j < i)));

  return { resolved: resolved.slice(0, _MAX_INTERESTS), unresolved };
}

/**
 * Attach the user's question to the plan.
 *
 * The goals go on the *primary* technology — the first one detected — rather
 * than on a synthetic entry of their own. Two things depend on the technology's
 * name: the Runtime picks the technology whose goals are still open when it asks
 * for the next step, and this provider chooses its runtime and test probes from
 * that name (`pickRuntimeProbe` / `pickTestProbe`). A "User Request" pseudo-
 * technology would carry the goals but answer to neither, so the goals would sit
 * open with no command that could ever close them.
 *
 * `origin` is filled in as goals are attached, because the two paths to one goal
 * name are not the same goal: "Verify Runtime" is proposed for every Node
 * repository by the manifest and named by `wizard verify runtime` by the user,
 * and the command family keeps them for different reasons. Recording it here,
 * where the attaching happens, is the only place that knows which path was taken.
 */
function attachUserRequest(
  technologies: unknown[],
  ctx: ManifestContext,
  origin: Map<string, GoalOrigin>,
): void {
  if (technologies.length === 0) return;
  // The user's sentence, if they typed one. Nothing else in the plan can answer
  // "investigate the auth flow" — `targets` holds only the words the command
  // vocabulary recognises, and a request assembled from the menu alone has none.
  const question = (ctx.question ?? "").trim();
  const targets = ctx.targets ?? [];

  // The goals the *request's words* name — the targets and the user's sentence.
  // The command family is deliberately not part of this TEXT: `intent` is
  // "investigate" | "verify" | "explain" | "report", and matching it here —
  // which is what this used to do — reads a verb as a subject and invents goals
  // called "Inspect explain" and "Inspect report" that no repository can answer.
  // The family's effect on the *proposed* goals is in goalsForFamily, which
  // chooses among them; `goalsNamedByCommand` is the one goal it does name, and
  // it names it from `operatesSurface` rather than from the text.
  const named = goalsNamedByCommand(ctx.intent ?? "", targets, question);
  for (const goal of named) origin.set(goal, "named");

  // A target whose own word already produced a verification goal needs no
  // second, read-only goal under the same name — "runtime" is answered by
  // running the runtime probe, not by also reading whatever matches "runtime".
  const coveredByFamily = (t: string) => goalsNamedBy([t]).size > 0;

  const { resolved, unresolved } = collectInterests(
    question,
    targets.filter((t) => !coveredByFamily(t)),
    ctx.treeFiles ?? [],
  );

  const goalNames: string[] = [];
  for (const interest of resolved) {
    const goal = `Inspect ${interest.name}`;
    goalNames.push(goal);
    origin.set(goal, "inspected");
  }

  // A name nothing in the repository answers to is still something the user
  // asked about — "architecture" and "ci" are real CLI targets and neither is a
  // filename. It gets a goal with no files of its own, closed by the run's own
  // reading of the repository, and the plan records that no file matched by
  // name. Dropping it instead is how a run ends up reporting on a question
  // nobody asked while the one that was asked leaves no trace.
  const unmatched = [...new Set(unresolved)];
  for (const u of unmatched.slice(0, _MAX_INTERESTS)) {
    const goal = `Inspect ${u}`;
    goalNames.push(goal);
    origin.set(goal, "inspected");
  }

  const targetFiles = resolved.flatMap((i) => i.files);
  const reached = [...named, ...goalNames];

  const primary = technologies[0] as {
    initialGoals?: string[];
    priorityFiles?: string[];
    signals?: string[];
  };
  const signals = (primary.signals ??= []);
  if (question) signals.push(`user question: ${question}`);
  for (const t of targets) signals.push(`target: ${t}`);
  // Said out loud rather than dropped. An interest nothing in the repository
  // answers to is still something the user asked about, and the plan is where
  // that fact belongs — silently discarding it is how a run ends up reporting
  // on a question nobody asked.
  //
  // Recorded before the early return below, because a question that resolved to
  // nothing is exactly the one that most needs to be on the record: it is the
  // only way the report can say the user asked about something this repository
  // does not answer to, rather than quietly reporting on a different question.
  if (reached.length === 0 && targetFiles.length === 0) return;

  // Which goals the plan already carries, on any technology. A goal the user
  // named is not automatically the primary technology's: "Verify
  // Containerization" belongs to whichever technology declared Docker, and
  // attaching a second copy to Node.js would put the same goal on the plan
  // twice — two goals that one piece of evidence closes, and a run that reports
  // having proved something twice.
  const carried = new Set<string>();
  for (const tech of technologies as { initialGoals?: string[] }[]) {
    for (const goal of tech.initialGoals ?? []) carried.add(goal);
  }

  const goalList = (primary.initialGoals ??= []);
  for (const name of reached) {
    if (!carried.has(name) && !goalList.includes(name)) goalList.push(name);
  }
  // Target files lead the priority list: they are what the user named, and the
  // Runtime seeds one read node per priority file in this order, so the files
  // the user asked about are read before the generic manifests.
  const priority = (primary.priorityFiles ??= []);
  const deduped = [...new Set(targetFiles)];
  primary.priorityFiles = [...deduped.slice(0, _MAX_INTEREST_FILES),
                          ...priority.filter((p) => !deduped.includes(p))];
}

// ── technology_plan ───────────────────────────────────────────────────────────

/**
 * Files that say a suite exists to be run.
 *
 * The stronger signal — the manifest's own `test` script — is not available at
 * plan time: it comes from parsing package.json, which happens during the run.
 * A test file is enough to justify a goal that *asks* whether the suite runs,
 * and the goal is what makes the run go and find out.
 *
 * Matching is deliberately broad, and the asymmetry is deliberate too. A false
 * positive costs one execution probe and reports honestly when there is nothing
 * to run. A false negative means the run reads files and executes nothing at
 * all, which is the failure this exists to prevent — a plan that never runs a
 * project cannot say whether the project works.
 */
const _TEST_FILE =
  /(^|[\\/])(__tests__|__test__|tests?|specs?)([\\/]|$)|\.(test|spec)\.[^\\/]+$|(^|[\\/])test_[^\\/]+\.py$|_test\.(py|go)$/i;

function hasTestFiles(treeFiles: string[]): boolean {
  return treeFiles.some((f) => _TEST_FILE.test(f));
}

function buildTechnologyPlan(ctx: ManifestContext): unknown {
  const languages = ctx.languages ?? [];
  const frameworks = ctx.frameworks ?? [];
  const packageManagers = ctx.packageManagers ?? [];
  const databases = ctx.databases ?? [];
  const keyFiles = ctx.keyFiles ?? [];
  const entryFiles = ctx.entryFiles ?? [];
  const technologies: unknown[] = [];

  // A repository with tests gets a goal that runs them. Stated once here rather
  // than per technology: the goal is routed by its own name (http/contracts.ts
  // ::goalDefFor), so whichever technology carries it gets the same requirement,
  // and the probe that closes it is chosen from that technology's name.
  const testGoals = hasTestFiles(ctx.treeFiles ?? []) ? ["Verify Test Suite"] : [];

  const nodeish =
    has(languages, "JavaScript") ||
    has(languages, "TypeScript") ||
    packageManagers.some((p) => ["npm", "pnpm", "yarn"].includes(p)) ||
    keyFiles.some((f) => f.endsWith("package.json"));
  if (nodeish) {
    technologies.push({
      name: "Node.js",
      confidence: keyFiles.some((f) => f.endsWith("package.json")) ? "high" : "medium",
      signals: [
        ...packageManagers.map((p) => `package manager: ${p}`),
        ...keyFiles.filter((f) => f.endsWith("package.json")).map((f) => `manifest: ${f}`),
      ],
      initialGoals: ["Verify Runtime", "Verify Dependencies", ...testGoals],
      priorityFiles: [
        ...keyFiles.filter((f) => f.endsWith("package.json")),
        ...entryFiles,
      ].slice(0, 5),
    });
  }

  const pythonish =
    has(languages, "Python") ||
    has(frameworks, "Django") ||
    keyFiles.some((f) => f.endsWith("requirements.txt") || f.endsWith("pyproject.toml") || f.endsWith("manage.py"));
  if (pythonish) {
    technologies.push({
      name: has(frameworks, "Django") ? "Django" : "Python",
      confidence: keyFiles.some((f) => f.endsWith("requirements.txt") || f.endsWith("manage.py")) ? "high" : "medium",
      signals: [
        ...frameworks.filter((f) => f === "Django").map((f) => `framework: ${f}`),
        ...keyFiles
          .filter((f) => f.endsWith("requirements.txt") || f.endsWith("manage.py") || f.endsWith("pyproject.toml"))
          .map((f) => `manifest: ${f}`),
      ],
      initialGoals: ["Verify Runtime", "Verify Dependencies", ...testGoals],
      priorityFiles: keyFiles
        .filter((f) => f.endsWith("requirements.txt") || f.endsWith("manage.py") || f.endsWith("pyproject.toml"))
        .slice(0, 5),
    });
  }

  if (keyFiles.some((f) => f.endsWith("Dockerfile") || f.includes("docker-compose"))) {
    technologies.push({
      name: "Docker",
      confidence: "high",
      signals: keyFiles.filter((f) => f.endsWith("Dockerfile") || f.includes("docker-compose")).map((f) => `file: ${f}`),
      initialGoals: ["Verify Containerization"],
      priorityFiles: keyFiles.filter((f) => f.endsWith("Dockerfile") || f.includes("docker-compose")).slice(0, 3),
    });
  }

  for (const db of databases) {
    technologies.push({
      name: db,
      confidence: "medium",
      signals: [`database signal: ${db}`],
      initialGoals: ["Verify Dependencies"],
      priorityFiles: [],
    });
  }

  if (technologies.length === 0) {
    technologies.push({
      name: ctx.projectType || "Unknown",
      confidence: "low",
      signals: ["no strong technology signals detected"],
      initialGoals: ["Verify Runtime"],
      priorityFiles: entryFiles.slice(0, 3),
    });
  }

  // The user's question, last, so it lands on the technology the run will
  // actually work on and can add goals no manifest signal would have produced.
  //
  // Every goal proposed so far came from the manifest, and the map says so
  // before the user's own goals are attached and re-tag themselves. Which path
  // a goal arrived by is what the command family reads: "Verify Runtime" is
  // context when the manifest suggests it for a Node repository, and the
  // question itself when someone runs `verify runtime`.
  const origin = new Map<string, GoalOrigin>();
  for (const tech of technologies as { initialGoals?: string[] }[]) {
    for (const goal of tech.initialGoals ?? []) origin.set(goal, "manifest");
  }
  attachUserRequest(technologies, ctx, origin);

  // The family goes last and is the only thing that REMOVES a goal. Everything
  // above proposes — the manifest what the repository suggests, the targets
  // what the user named — and this decides which proposals the command that was
  // actually run is willing to pay for. Investigate, verify, explain and report
  // were one command until this line existed: all four inherited the manifest's
  // whole set unconditionally and could only add to it, so `report` ran the
  // test suite and `explain architecture` ran the runtime probe.
  applyFamily(technologies, ctx, origin);

  return { technologies };
}

/** Restrict every technology's goals to the ones this command family wants. */
function applyFamily(
  technologies: unknown[],
  ctx: ManifestContext,
  origin: Map<string, GoalOrigin>,
): void {
  const family = ctx.intent ?? "";
  // The question is matched here as well as the targets: this filter is what
  // keeps or drops the goals the user's words named, and a sentence that named
  // one ("how do the tests run") has to weigh the same as the one target word
  // that would have ("testing"), or the goal is dropped for having been asked
  // for in the wrong vocabulary.
  const named = goalsNamedByCommand(family, ctx.targets ?? [], ctx.question ?? "");
  const techs = technologies as { initialGoals?: string[] }[];

  const proposed: PlannedGoal[] = [];
  for (const tech of techs) {
    for (const name of tech.initialGoals ?? []) {
      // A goal the map has never heard of was proposed by a path that did not
      // record itself, which means the manifest. Naming it that way rather than
      // dropping it keeps an unrecorded goal visible in the plan instead of
      // silently vanishing from the run.
      proposed.push({ name, origin: origin.get(name) ?? "manifest" });
    }
  }

  // One decision for the whole plan, not one per technology. The fallback in
  // goalsForFamily answers "the target named nothing this plan can act on",
  // which is a fact about the plan: decided per technology it would let a
  // technology carrying none of the user's goals — Docker, when the question
  // was about architecture — fall back on its own and put the repository-wide
  // context goals straight back into a run that had been scoped to drop them.
  const keep = new Set(goalsForFamily(family, proposed, named));

  for (const tech of techs) {
    tech.initialGoals = (tech.initialGoals ?? []).filter((name) => keep.has(name));
  }
}

// ── ongoing_plan ──────────────────────────────────────────────────────────────

/**
 * Propose nodes to satisfy the goal's missing requirements. Strategy:
 *   - If a priority file has not been read → propose a READ node.
 *   - If a priority file has been read but not parsed → propose a PARSE node.
 *   - For a runtime requirement with execution allowed → propose a guarded
 *     EXECUTE probe.
 *   - Always cap the batch so the budget is respected.
 */
/**
 * The separator-independent comparison key for a repository-relative path.
 *
 * The Runtime builds its `file_observation_ids` index with the same rule
 * (loop.py::canonical_rel_path) because the two sides hold genuinely different
 * spellings of the same file: the manifest's file list carries the platform's
 * native form (`client\\src\\app.js` on Windows), while the Runtime's index is
 * built from what a tool reported after the validator resolved the path. A
 * literal comparison therefore calls an already-read Windows file unread, and
 * the reopened read is rejected as a duplicate — a failed node and a spent
 * budget slot for a question that was already answered.
 */
function canonicalRel(path: string): string {
  return path.replace(/\\/g, "/");
}

function buildOngoingPlan(ctx: OngoingContext): unknown {
  const nodes: unknown[] = [];
  const priorityFiles = ctx.priorityFiles ?? [];
  const fileObs = ctx.fileObservationIds ?? {};
  const parsedObs = ctx.parsedObservationIds ?? {};
  const missing = ctx.missingRequirements ?? [];
  const tech = ctx.goalTechnology ?? "the technology";

  // The two indexes are keyed canonically; compare the same way. Membership is
  // all this step needs, so the planner's own spelling is what goes into the
  // node — the path a tool request should carry is the one the repository's
  // file list gave us.
  const readKeys = new Set(Object.keys(fileObs).map(canonicalRel));
  const parsedKeys = new Set(Object.keys(parsedObs).map(canonicalRel));
  // A queued read counts as read for the purpose of not proposing it again: the
  // evidence is already scheduled, so a second node for the same file can only
  // duplicate it.
  for (const path of ctx.queuedReadPaths ?? []) {
    readKeys.add(canonicalRel(path));
  }

  // 1. Read any priority file we have not read yet.
  // The success claim is FILE_READ, the same claim a seeded read node asserts
  // (http/contracts.ts::seedReadNode). It used to be FILE_PRESENT here, a second
  // name for the same fact, which meant a read proposed during the ongoing phase
  // admitted a claim no goal was ever written against.
  for (const file of priorityFiles) {
    if (!readKeys.has(canonicalRel(file))) {
      nodes.push({
        type: "read",
        action: { type: "read", filePath: file },
        hypothesis: `${file} exists and is readable`,
        successClaim: { type: "FILE_READ", value: file },
        failureClaim: { type: "FILE_READ", value: `missing:${file}` },
      });
    }
  }

  // 2. Parse read-but-unparsed structured files.
  for (const [file, obsId] of Object.entries(fileObs)) {
    if (parsedKeys.has(canonicalRel(file))) continue;
    const parser = pickParser(file);
    if (!parser) continue;
    nodes.push({
      type: "parse",
      action: { type: "parse", sourceObservationId: obsId, parser },
      hypothesis: `${file} parses as ${parser} and declares runtime metadata`,
      successClaim: { type: "MANIFEST_PARSED", value: file },
      failureClaim: { type: "MANIFEST_PARSED", value: `unparseable:${file}` },
    });
  }

  // 3. For runtime requirements, propose a guarded execute probe.
  // The claim type comes from the requirement itself, not a literal. The
  // technology plan emits goal claim types from goalDefFor() ("RUNTIME"), and
  // the Runtime echoes those same types back in missingRequirements — so gating
  // on a hardcoded "RUNTIME_STATUS" never matched, and even a matched probe
  // would have created a claim the goal does not require. Read the type off the
  // requirement so the probe produces exactly the evidence that was asked for.
  const runtimeReq = missing.find((m) => /runtime/i.test(m.claimType));
  if (runtimeReq && ctx.allowExecution) {
    const probe = pickRuntimeProbe(tech);
    if (probe) {
      nodes.push({
        type: "execute",
        action: { type: "execute", command: probe.command, timeoutMs: 60000 },
        hypothesis: probe.hypothesis,
        successClaim: { type: runtimeReq.claimType, value: "verified", trustWeight: 0.9 },
        failureClaim: { type: runtimeReq.claimType, value: "broken" },
        unexpectedAction: "escalate_to_planner",
      });
    }
  }

  // 3b. For a test requirement, run the suite. "Verify Test Suite" carries
  // requires_execution_evidence, so reading a pytest section out of a manifest
  // cannot close it — the only thing that can is the suite actually running and
  // reporting, which is what the kernel's command_result extractor turns into an
  // execution-tier TESTING claim ("N passed"). This is also the step that makes a
  // run do real work instead of walking a file list.
  const testReq = missing.find((m) => /^testing$/i.test(m.claimType));
  if (testReq && ctx.allowExecution) {
    const probe = pickTestProbe(tech);
    if (probe) {
      nodes.push({
        type: "execute",
        action: { type: "execute", command: probe.command, timeoutMs: 120000 },
        hypothesis: probe.hypothesis,
        successClaim: { type: testReq.claimType, value: "suite-reported", trustWeight: 0.9 },
        failureClaim: { type: testReq.claimType, value: "suite-unavailable" },
        unexpectedAction: "escalate_to_planner",
      });
    }
  }

  // 4. Browser requirements: observe a named URL the Runtime has not observed yet.
  // Gated on the missing requirement, not on the URL alone — re-navigating a page
  // whose WEB claims are already admitted buys nothing and costs a budget slot.
  const webReq = missing.find((m) => /^web$/i.test(m.claimType));
  if (webReq && ctx.browserEnabled) {
    const visited = new Set(ctx.visitedUrls ?? []);
    const unvisited = (ctx.browserTargets ?? []).filter((u) => !visited.has(u));
    const url = unvisited[0] ?? (visited.size === 0 ? (ctx.browserTargets ?? [])[0] : undefined);
    if (url) {
      const step = visited.has(url) ? ("extract" as const) : ("navigate" as const);
      nodes.push({
        type: "browser",
        action: step === "navigate"
          ? { type: "browser", tool: "navigate", url }
          : { type: "browser", tool: "extract" },
        hypothesis: step === "navigate"
          ? `${url} is reachable and serves a page`
          : `${url} has readable content`,
        successClaim: { type: webReq.claimType, value: url },
      });
    }
  }

  // 4b. The page the run is standing on, and what to do with it.
  //
  // Reading a page and operating it are different investigations, and until now
  // only the first was reachable: the browser could navigate, snapshot and
  // extract, so every WEB claim came from looking. The controls were in the
  // accessibility tree the whole time and nothing turned "there is a button
  // called Sign in" into "press it" — the plane was a reader.
  //
  // The script itself is decided in planner/interactionScript.ts, not here, so
  // the rule about which controls may be pressed has one home and one test. The
  // gate comes from planner/goalPolicy.ts for the same reason: that module also
  // decides whether the plan declares "Operate Web Surface", and a second copy
  // of the rule here could leave a plan with a goal nothing plans the steps for.
  if (ctx.browserEnabled && (ctx.pageControls ?? []).length > 0) {
    if (operatesSurface(ctx.question ?? "", ctx.targets ?? [], ctx.intent ?? "")) {
      const steps = interactionScriptFor({
        url: ctx.pageUrl ?? "",
        controls: ctx.pageControls ?? [],
        allowedDomains: ctx.allowedDomains ?? [],
        acted: ctx.interactedSelectors ?? [],
      });
      // Chained, because a script is ordered: filling a form after submitting it
      // is not the same operation, and the Runtime runs a node only once its
      // dependencies have. The chain is also what makes the script legible in
      // the trace — one step per line, in the order the page will receive them.
      //
      // No successClaim, deliberately. A step's evidence is what the kernel's
      // own extractors read out of the observation — `interacted:<selector>` and
      // `effect:<selector>` — and a claim asserted here would be about the
      // planner's intention rather than the page's behaviour. "I clicked Sign in"
      // is not the same finding as "clicking Sign in changed the page", and only
      // the second one is evidence.
      let previous: string | undefined;
      for (const step of steps) {
        const id = newNodeId();
        nodes.push({
          type: "browser",
          nodeId: id,
          action: step.tool === "type"
            ? { type: "browser", tool: "type", selector: step.selector, text: step.text }
            : { type: "browser", tool: "click", selector: step.selector },
          hypothesis: step.why,
          dependencies: previous ? [previous] : [],
        });
        previous = id;
      }
    }
  }

  return { nodes, rationale: `heuristic ongoing plan for ${tech}: ${nodes.length} node(s)` };
}


function pickParser(file: string): string | null {
  if (file.endsWith("package.json")) return "package-json";
  if (file.endsWith("Dockerfile")) return "dockerfile";
  if (file.endsWith("requirements.txt")) return "requirements";
  if (file.endsWith(".json")) return "json";
  return null;
}

function pickRuntimeProbe(tech: string): { command: string; hypothesis: string } | null {
  const t = tech.toLowerCase();
  if (t.includes("node")) {
    return { command: "node --version", hypothesis: "Node.js runtime is available" };
  }
  if (t.includes("python") || t.includes("django")) {
    return { command: "python --version", hypothesis: "Python runtime is available" };
  }
  if (t.includes("docker")) {
    return { command: "docker --version", hypothesis: "Docker runtime is available" };
  }
  return null;
}

/**
 * The command that runs this technology's test suite. `--silent`/`-q` because the
 * kernel's extractor reads the summary line ("N passed"), and a reporter that
 * buries it under per-test noise only makes that line harder to find.
 */
function pickTestProbe(tech: string): { command: string; hypothesis: string } | null {
  const t = tech.toLowerCase();
  if (t.includes("node")) {
    return { command: "npm test --silent", hypothesis: "the Node test suite runs and reports results" };
  }
  if (t.includes("python") || t.includes("django")) {
    return { command: "python -m pytest -q", hypothesis: "the Python test suite runs and reports results" };
  }
  return null;
}

// ── escalation ────────────────────────────────────────────────────────────────

function buildEscalation(ctx: EscalationCtx): unknown {
  const alreadyRead = ctx.alreadyReadPaths ?? [];
  // Conservative recovery: if there is a file we have NOT yet read, read it once.
  if (ctx.filePath && !alreadyRead.includes(ctx.filePath)) {
    return {
      nodes: [
        {
          type: "read",
          action: { type: "read", filePath: ctx.filePath },
          hypothesis: `re-reading ${ctx.filePath} clarifies the unexpected result`,
          successClaim: { type: "FILE_READ", value: ctx.filePath },
        },
      ],
      rationale: `escalation recovery: read ${ctx.filePath}`,
    };
  }
  // Otherwise record only — do not spend budget guessing.
  return { nodes: [], rationale: "escalation: no deterministic recovery; recording only" };
}

// ── Provider ──────────────────────────────────────────────────────────────────

export class HeuristicLLMProvider implements LLMProvider {
  readonly name = "heuristic";

  async generateStructured<T>(request: LLMRequest, schema: Schema<T>): Promise<LLMResult<T>> {
    const ctx = (request.context ?? {}) as Record<string, unknown>;
    let built: unknown;
    switch (request.purpose) {
      case "technology_plan":
        built = buildTechnologyPlan(readManifestContext(ctx));
        break;
      case "ongoing_plan":
        built = buildOngoingPlan(readOngoingContext(ctx));
        break;
      case "escalation":
        built = buildEscalation(readEscalationContext(ctx));
        break;
      default:
        return llmErr<T>([`heuristic: unknown purpose ${String(request.purpose)}`], "", this.name);
    }

    const raw = JSON.stringify(built);
    const parsed = safeParse(schema, built);
    if (!parsed.ok) return llmErr<T>(parsed.errors, raw, this.name);
    return llmOk<T>(parsed.value, raw, this.name);
  }
}

function readManifestContext(ctx: Record<string, unknown>): ManifestContext {
  const m = (ctx.manifest as Record<string, unknown>) ?? ctx;
  return {
    languages: strArr(m.languages),
    frameworks: strArr(m.frameworks),
    packageManagers: strArr(m.packageManagers),
    dependencies: strArr(m.dependencies),
    databases: strArr(m.databases),
    keyFiles: strArr(m.keyFiles),
    entryFiles: strArr(m.entryFiles),
    projectType: str(m.projectType),
    treeFiles: strArr(m.treeFiles),
    intent: str(m.intent),
    question: str(m.question),
    targets: strArr(m.targets),
  };
}

function readOngoingContext(ctx: Record<string, unknown>): OngoingContext {
  const missingRaw = Array.isArray(ctx.missingRequirements) ? ctx.missingRequirements : [];
  const missingRequirements: RequirementContext[] = [];
  for (const r of missingRaw) {
    const o = r as Record<string, unknown>;
    const claimType = str(o.claimType);
    if (!claimType) continue;
    missingRequirements.push({ claimType, description: str(o.description), expectedValue: str(o.expectedValue) });
  }

  return {
    goalTechnology: str(ctx.goalTechnology),
    allowExecution: typeof ctx.allowExecution === "boolean" ? ctx.allowExecution : false,
    missingRequirements,
    priorityFiles: strArr(ctx.priorityFiles),
    fileObservationIds: asStringRecord(ctx.fileObservationIds),
    parsedObservationIds: asStringRecord(ctx.parsedObservationIds),
    queuedReadPaths: strArr(ctx.queuedReadPaths),
    browserEnabled: ctx.browserEnabled === true,
    allowedDomains: strArr(ctx.allowedDomains),
    browserTargets: strArr(ctx.browserTargets),
    visitedUrls: strArr(ctx.visitedUrls),
    pageUrl: str(ctx.pageUrl),
    pageControls: (Array.isArray(ctx.pageControls) ? ctx.pageControls : []).filter(
      (c): c is PageControl => Boolean(c) && typeof c === "object" && typeof (c as PageControl).selector === "string",
    ),
    interactedSelectors: strArr(ctx.interactedSelectors),
    intent: str(ctx.intent),
    question: str(ctx.question),
    targets: strArr(ctx.targets),
  };
}

function readEscalationContext(ctx: Record<string, unknown>): EscalationCtx {
  return {
    nodeId: str(ctx.nodeId),
    filePath: str(ctx.filePath),
    alreadyReadPaths: strArr(ctx.alreadyReadPaths),
    reason: str(ctx.reason),
  };
}

function asStringRecord(v: unknown): Record<string, string> {
  if (!v || typeof v !== "object" || Array.isArray(v)) return {};
  const out: Record<string, string> = {};
  for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
    if (typeof val === "string") out[k] = val;
  }
  return out;
}
