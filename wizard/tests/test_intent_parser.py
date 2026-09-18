"""Tests for the deterministic intent parser.

The parser exists because free text used to go nowhere. These tests pin the
properties that make it trustworthy rather than clever: it is pure, it never
guesses, it reports what it did not understand, and it can only ever ADD to
what the menu already chose.
"""

from __future__ import annotations

import pytest

from wizard.cli.models.investigation_request import RequestOptions
from wizard.cli.parser.command_parser import CommandValidationError
from wizard.cli.parser.intent_builder import build_intent
from wizard.cli.parser.intent_parser import (
    describe,
    domains_from_urls,
    parse_intent,
    validate_parsed,
)


# ── Determinism and purity ───────────────────────────────────────────────────

def test_the_same_text_always_parses_the_same_way():
    text = "check the api routes and the auth flow at https://example.com/login"
    first = parse_intent(text, "investigate")
    second = parse_intent(text, "investigate")
    assert first == second


def test_parsing_follows_the_order_the_aliases_appear_in_the_text():
    """Not the order by alias length: "auth" appears first, so authentication
    is reported first even though "api" is the shorter string."""
    parsed = parse_intent("look at the auth flow, then the api", "investigate")
    assert parsed.targets == ("authentication", "api")


# ── The menu always wins, and text can only add ──────────────────────────────

def test_menu_target_comes_first_and_survives():
    parsed = parse_intent("also check the security headers", "investigate", menu_target="api")
    assert parsed.targets[0] == "api"
    assert "security" in parsed.targets
    assert parsed.evidence[0].source == "menu"


def test_menu_target_is_not_duplicated_when_the_text_names_it_too():
    parsed = parse_intent("investigate the api", "investigate", menu_target="api")
    assert parsed.targets == ("api",)


# ── Alias matching is lexical and bounded ────────────────────────────────────

def test_a_target_is_matched_by_its_own_name():
    assert parse_intent("tell me about deployment", "investigate").targets == ("deployment",)


def test_an_extra_alias_selects_its_target():
    parsed = parse_intent("where is the login handled", "investigate")
    assert parsed.targets == ("authentication",)
    assert parsed.evidence[0].alias == "login"


def test_an_alias_does_not_match_inside_a_longer_word():
    """`api` must not fire on "capital", nor `ci` on "special"."""
    parsed = parse_intent("the capital city is special", "verify")
    assert parsed.targets == ()


def test_a_phrase_alias_wins_over_the_shorter_word_it_contains():
    """"package manager" must not also report "packages" as a second target."""
    parsed = parse_intent("read the package manager lockfile", "verify")
    assert parsed.targets == ("dependencies",)


def test_an_alias_valid_for_another_family_is_not_matched():
    """`build` is an investigate target, not a verify one."""
    assert parse_intent("check the build", "verify").targets == ()
    assert parse_intent("check the build", "investigate").targets == ("build",)


# ── URLs ─────────────────────────────────────────────────────────────────────

def test_a_url_is_captured_and_stripped_of_trailing_punctuation():
    parsed = parse_intent("open https://example.com/login, please", "investigate")
    assert parsed.urls == ("https://example.com/login",)


def test_a_url_host_is_not_mistaken_for_a_target_alias():
    """The host contains no alias here, but the path might; URLs are removed
    from the words before alias matching, so neither can leak through."""
    parsed = parse_intent("visit https://example.com/security", "investigate")
    assert parsed.urls == ("https://example.com/security",)
    assert parsed.targets == ()


def test_two_urls_are_kept_in_first_seen_order_without_duplicates():
    parsed = parse_intent("https://a.test then https://b.test then https://a.test", "investigate")
    assert parsed.urls == ("https://a.test", "https://b.test")


def test_domains_from_urls_returns_hosts_only():
    assert domains_from_urls(("https://example.com:8443/a/b", "http://sub.test/x")) == (
        "example.com", "sub.test",
    )


# ── Honesty about what was not understood ────────────────────────────────────

def test_unrecognised_words_are_reported_rather_than_guessed_at():
    parsed = parse_intent("please frobnicate the widget", "investigate")
    assert parsed.targets == ()
    assert "frobnicate" in parsed.unmatched
    assert "widget" in parsed.unmatched


def test_stopwords_are_not_reported_as_unmatched():
    parsed = parse_intent("what is the runtime", "investigate")
    assert parsed.targets == ("runtime",)
    assert parsed.unmatched == ()


def test_a_word_the_parser_did_not_understand_is_reported_even_alongside_a_match():
    """"doing" is not an alias and not a stopword, so it is reported. Saying so
    is the point: the parser lists what it ignored instead of implying it used
    the whole sentence."""
    parsed = parse_intent("what is the runtime doing", "investigate")
    assert parsed.targets == ("runtime",)
    assert parsed.unmatched == ("doing",)


def test_matched_words_are_not_also_reported_as_unmatched():
    parsed = parse_intent("security and security", "investigate")
    assert parsed.unmatched == ()


def test_empty_text_is_an_empty_parse_not_an_error():
    parsed = parse_intent("", "investigate", menu_target="api")
    assert parsed.targets == ("api",)
    assert parsed.urls == ()


# ── Validation ───────────────────────────────────────────────────────────────

def test_validation_passes_when_the_menu_supplied_the_target():
    validate_parsed(parse_intent("", "investigate", menu_target="api"))


def test_validation_passes_when_only_the_text_supplied_the_target():
    validate_parsed(parse_intent("look at the api", "investigate"))


def test_validation_rejects_a_family_that_requires_a_target_with_none_found():
    with pytest.raises(CommandValidationError):
        validate_parsed(parse_intent("hello there", "investigate"))


def test_validation_rejects_an_unknown_family():
    with pytest.raises(CommandValidationError):
        validate_parsed(parse_intent("anything", "frobnicate"))


# ── describe() is what the UI shows ──────────────────────────────────────────

def test_describe_names_each_target_it_read_and_the_words_it_did_not():
    parsed = parse_intent("check the api", "investigate")
    assert describe(parsed) == "api ← 'api'"


def test_describe_mentions_the_url_that_enabled_the_browser():
    parsed = parse_intent("open https://example.com", "investigate")
    assert "https://example.com" in describe(parsed)


# ── build_intent carries the parse through ───────────────────────────────────

def test_build_intent_unions_menu_and_text_targets_in_order():
    intent = build_intent("investigate", targets=["api", "security"])
    assert intent.targets == ["api", "security"]


def test_build_intent_drops_targets_that_are_invalid_for_the_family():
    intent = build_intent("verify", targets=["runtime", "build"])
    assert intent.targets == ["runtime"]


def test_build_intent_gives_a_targetless_family_no_targets():
    intent = build_intent("report", target=None, targets=["api"])
    assert intent.targets == []


def test_api_targets_puts_named_targets_before_urls():
    intent = build_intent("investigate", targets=["api"], urls=["https://example.com"])
    assert intent.api_targets == ["api", "https://example.com"]


# ── RequestOptions.for_urls: the three things that make a URL work ────────────

def test_for_urls_enables_the_browser_and_allows_the_host():
    opts = RequestOptions().for_urls(["https://example.com/login"])
    assert opts.browser_enabled is True
    assert opts.allowed_domains == ("example.com",)


def test_for_urls_shows_the_window_by_default():
    """A user who names a URL wants to watch it; headless is opt-in."""
    assert RequestOptions().for_urls(["https://example.com"]).browser_headless is False


def test_for_urls_respects_an_explicit_headless_choice():
    opts = RequestOptions(browser_headless=True).for_urls(["https://example.com"])
    assert opts.browser_headless is True


def test_for_urls_unions_with_domains_already_configured():
    """Typing one URL must not silently revoke hosts the environment trusts."""
    opts = RequestOptions(allowed_domains=("trusted.test",)).for_urls(["https://example.com"])
    assert opts.allowed_domains == ("trusted.test", "example.com")


def test_for_urls_with_no_urls_changes_nothing():
    base = RequestOptions(browser_enabled=False)
    assert base.for_urls([]) is base


def test_for_urls_does_not_turn_off_a_browser_that_was_explicitly_enabled():
    opts = RequestOptions(browser_enabled=True).for_urls([])
    assert opts.browser_enabled is True
