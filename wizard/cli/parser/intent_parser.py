"""Intent parser — turn the user's free text into targets, deterministically.

The TUI gives the user a menu (family → target) AND a free-text box. Until now
the text box was decorative: `_begin_work` pushed whatever was typed into a
local `steering` list that no request ever carried, so a user who typed
"check the API and https://example.com" got an investigation of whatever the
menu happened to be pointing at. This module is what closes that gap.

The parser is LEXICAL, not semantic, and deliberately so:

  * No model. The workflow must stay deterministic and reproducible — the same
    text always yields the same targets, in the same order, and you can read
    the rule that produced each one.
  * No inference. A target is recognised only because a known alias for it
    appears in the text. It never guesses that "the login flow" means
    "authentication"; if a word is not in the alias table, it is reported as
    unmatched rather than silently mapped to the nearest thing.
  * Every decision is reported. `ParsedIntent.evidence` names the alias that
    matched each target, so the UI can show WHY a target was chosen.

Ordering is significant and stable: targets named explicitly by the menu come
first, then targets discovered in the text in the order the aliases appear.
That means the menu selection always wins, and free text can only ever ADD.

This module knows the *vocabulary* of targets (`command_parser.COMMAND_TARGETS`)
but not their meaning — the same separation the rest of the CLI keeps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from wizard.cli.parser.command_parser import COMMAND_TARGETS, VALID_COMMANDS


# ---------------------------------------------------------------------------
# Alias table — how a target can be spoken about in free text
# ---------------------------------------------------------------------------
# Keys are canonical targets from COMMAND_TARGETS. Values are the lowercase
# words/phrases that should select that target.
#
# Every canonical target is its own alias (added automatically below), so this
# table only needs the EXTRA vocabulary. A target with no extra aliases is
# still discoverable by name.
#
# Multi-word phrases are matched as phrases ("package manager" before
# "package"), so the matcher scans longest-alias-first.

_EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    # investigate / explain
    "architecture": ("structure", "design", "layout", "module", "modules", "codebase", "project structure"),
    "runtime": ("run", "runs", "startup", "start up", "entrypoint", "entry point", "boot", "launch", "main"),
    "deployment": ("deploy", "deploys", "hosting", "release", "production", "ship", "serving"),
    "authentication": ("auth", "login", "log in", "signin", "sign in", "session", "jwt", "oauth", "password"),
    "api": ("endpoint", "endpoints", "rest", "route", "routes", "http api", "handler", "handlers"),
    "security": ("secure", "vulnerability", "vulnerabilities", "exploit", "secret", "secrets", "permission", "permissions"),
    "build": ("compile", "compilation", "bundler", "bundling", "toolchain", "makefile", "transpile"),
    # verify
    "dependencies": ("dependency", "deps", "package manager", "packages", "libraries", "requirements", "lockfile", "lock file"),
    "containers": ("container", "docker", "dockerfile", "image", "compose", "docker-compose"),
    "ci": ("pipeline", "pipelines", "continuous integration", "github actions", "workflow", "workflows", "build pipeline"),
}

# Words that carry no target meaning. They are skipped so "check the api"
# reports only "api" as matched instead of also flagging "check" and "the".
# Kept short on purpose: this is a stoplist, not a parser of English.
_STOPWORDS = frozenset(
    """
    a an the this that these those my our your its it is are was were be been being
    and or but if then than so as of in on at to for from with without into over
    do does did done can could should would will shall may might must
    i we you they he she it me us them
    check checks verify verifies investigate investigates explain explains report
    reports please just only also about around any all some more most
    what which who whom whose where when why how
    file files repo repository project code
    """.split()
)

# A URL is a target too — it is simply one the browser plane serves rather than
# one the file plane does. Trailing punctuation is trimmed because free text
# ends sentences ("visit https://example.com.") and the period is not the host.
_URL_RE = re.compile(r"https?://[^\s<>\"'`,;)\]]+", re.IGNORECASE)

# Characters that end a word but must not be part of it. Kept explicit so
# "api," and "api?" both reduce to "api" without a Unicode-dependent \w class.
_WORD_SPLIT_RE = re.compile(r"[^a-z0-9_/.\-]+")


@dataclass(frozen=True)
class TargetMatch:
    """One target the parser decided on, and why.

    Attributes:
        target: The canonical target string (a key in COMMAND_TARGETS).
        alias: The exact text that matched it, lowercased. Equal to `target`
            when the target was named by the menu rather than read from text.
        source: "menu" when the caller supplied it, "text" when the parser
            found it in the free text.
    """

    target: str
    alias: str
    source: str


@dataclass(frozen=True)
class ParsedIntent:
    """The result of reading free text: targets, URLs, and the evidence for both.

    Attributes:
        action: The command family this parse is for.
        targets: Canonical targets, menu-selected first, then text-discovered.
            Deduplicated, order preserved.
        urls: Absolute http(s) URLs found in the text, in first-seen order.
            These are browser targets — the caller enables the browser plane
            for them rather than passing them as file targets.
        evidence: One TargetMatch per entry in `targets`, same order. This is
            what makes the parse observable: a caller can print "api ← 'api'"
            instead of asserting a target appeared by magic.
        unmatched: Free-text words that are neither stopwords, aliases, nor
            part of a URL. Reported, never guessed at — these are the words the
            parser did NOT understand, and saying so is more honest than
            folding them into the nearest target.
    """

    action: str
    targets: tuple[str, ...] = ()
    urls: tuple[str, ...] = ()
    evidence: tuple[TargetMatch, ...] = ()
    unmatched: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """True when the text contributed nothing — no targets and no URLs."""
        return not self.targets and not self.urls


def _aliases_for(action: str) -> dict[str, str]:
    """Build {alias -> canonical target} for one command family.

    Only targets valid for `action` are included, so the same word can mean
    different things in different families without a special case here. A
    longer alias is allowed to shadow a shorter one ("package manager" before
    "package"); the matcher sorts by length.
    """
    table: dict[str, str] = {}
    for target in COMMAND_TARGETS.get(action, []):
        table[target.lower()] = target
        for alias in _EXTRA_ALIASES.get(target, ()):
            # setdefault: the canonical name always wins over an extra alias
            # that happens to collide with another target's name.
            table.setdefault(alias.lower(), target)
    return table


def parse_intent(
    text: str,
    action: str,
    menu_target: str | None = None,
) -> ParsedIntent:
    """Read free text into targets and URLs for one command family.

    Args:
        text: What the user typed. May be empty.
        action: The command family. Unknown families yield an empty parse
            rather than an exception — the menu is the authority on which
            families exist, and a parse is an enrichment, not a gate.
        menu_target: A target already chosen from the menu. It is included
            first and marked `source="menu"`.

    Returns:
        A ParsedIntent. Never raises on odd input: unknown words land in
        `unmatched`, which is information, not an error.

    The URL scan runs over the ORIGINAL text and the words are stripped of URL
    spans before target matching, so a hostname like "example.com" inside a URL
    can never be mistaken for a target alias.
    """
    targets: list[str] = []
    evidence: list[TargetMatch] = []
    seen: set[str] = set()

    if menu_target:
        targets.append(menu_target)
        evidence.append(TargetMatch(target=menu_target, alias=menu_target.lower(), source="menu"))
        seen.add(menu_target)

    urls: list[str] = []
    for raw_url in _URL_RE.findall(text or ""):
        url = raw_url.rstrip(".")
        if url and url not in urls:
            urls.append(url)

    # Blank out URL spans so their characters cannot match an alias.
    words_text = _URL_RE.sub(" ", text or "")

    table = _aliases_for(action)
    # Longest alias first so "package manager" wins over "package" and "sign in"
    # over "sign" — but the RESULT is ordered by where each alias appears in the
    # text, not by alias length. Sorting by length is only how a shadowing match
    # is resolved; it must not decide the output order, or "the auth flow, then
    # the api" would report api before authentication purely because "api" is a
    # shorter string. Position in the sentence is the meaningful order.
    hits: list[tuple[int, str, str]] = []
    claimed_spans: list[tuple[int, int]] = []
    for alias in sorted(table, key=len, reverse=True):
        # Whole-phrase match on a word boundary, so "api" does not match inside
        # "capital" and "ci" does not match inside "special".
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])")
        for match in pattern.finditer(words_text):
            start, end = match.span()
            # A span already taken by a longer alias is not re-reported: the
            # "manager" in "package manager" must not also count for anything.
            if any(start < c_end and c_start < end for c_start, c_end in claimed_spans):
                continue
            claimed_spans.append((start, end))
            hits.append((start, table[alias], alias))

    for _, target, alias in sorted(hits, key=lambda h: h[0]):
        if target in seen:
            continue
        seen.add(target)
        targets.append(target)
        evidence.append(TargetMatch(target=target, alias=alias, source="text"))

    unmatched: list[str] = []
    for word in _WORD_SPLIT_RE.split(words_text.lower()):
        if not word or word in _STOPWORDS or word in seen:
            continue
        if word in table:
            # Already captured above; a duplicate token is not "unmatched".
            continue
        if word not in unmatched:
            unmatched.append(word)

    return ParsedIntent(
        action=action,
        targets=tuple(targets),
        urls=tuple(urls),
        evidence=tuple(evidence),
        unmatched=tuple(unmatched),
    )


def domains_from_urls(urls: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """The bare hostnames of `urls`, deduplicated, order preserved.

    The Runtime's browser egress allowlist is keyed by host, so a user who
    typed a URL needs that host allowed or the navigation is refused
    fail-closed and the browser plane is enabled for nothing.
    """
    hosts: list[str] = []
    for url in urls:
        match = re.match(r"https?://([^/:?#]+)", url, re.IGNORECASE)
        if match:
            host = match.group(1).lower()
            if host and host not in hosts:
                hosts.append(host)
    return tuple(hosts)


def describe(parsed: ParsedIntent) -> str:
    """One-line, human-readable account of what the parse decided.

    Used by the UI so the user can see the interpretation before/while the
    investigation runs, rather than discovering it from the report.
    """
    parts: list[str] = []
    for match in parsed.evidence:
        if match.source == "menu":
            continue
        parts.append(f"{match.target} ← {match.alias!r}")
    for url in parsed.urls:
        parts.append(f"browser ← {url}")
    if not parts:
        return "no targets or URLs recognised in the text"
    return ", ".join(parts)


def validate_parsed(parsed: ParsedIntent) -> None:
    """Raise CommandValidationError if the parse cannot be run as-is.

    Only two things are fatal, and both are facts about the request rather
    than about the user's wording:

      * an unknown command family (the menu should have prevented it), and
      * a family that requires a target, with none found by menu or text.

    A parse that found *extra* targets is never fatal — extra evidence is the
    point. A parse that found none is fatal only where the pipeline already
    required one.
    """
    from wizard.cli.parser.command_parser import CommandValidationError, validate_target

    if parsed.action not in VALID_COMMANDS:
        raise CommandValidationError(
            f'Unknown command "{parsed.action}".\n'
            f"Valid commands: {', '.join(VALID_COMMANDS)}"
        )
    # validate_target enforces "this family requires a target" and rejects an
    # unknown one. Passing the first target reuses that single source of truth
    # instead of restating the rule here.
    validate_target(parsed.action, parsed.targets[0] if parsed.targets else "")
