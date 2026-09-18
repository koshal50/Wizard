"""The local sandbox's process environment and output decoding.

Both of the things checked here are invisible until a command behaves oddly, and
both make the *project* look broken when they go wrong — which is the worst kind
of bug in a tool whose whole job is to report what a repository does.

`_SAFE_ENV` is a whitelist, so the failures are of two kinds: dropping something
a command needed, and keeping something it should not have.
"""
from __future__ import annotations

import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from wizard_kernel.world.sandbox.local import LocalProcessRuntime, _safe_env


# ── The environment whitelist ─────────────────────────────────────────────────

def test_the_whitelist_matches_environment_keys_case_insensitively(monkeypatch):
    """Windows hands `os.environ` keys back upper-cased.

    The whitelist names the variable "SystemRoot". Comparing the two literally
    never matches, so the entry silently does nothing — and the variable it was
    written to keep is dropped from every command the sandbox runs.
    """
    monkeypatch.setattr(os, "environ", {"SYSTEMROOT": r"C:\Windows", "PATH": "/bin"})
    env = _safe_env()
    assert env.get("SYSTEMROOT") == r"C:\Windows"


def test_dropping_systemroot_is_not_survivable(monkeypatch):
    """Why the case matters, stated as the consequence rather than the symptom.

    Without SystemRoot a process cannot create a listening socket, so every test
    that binds a port dies with `listen UNKNOWN: unknown error`. That happens
    inside the sandbox and not outside it, so the investigation reports a working
    project as broken and the fault reads as the project's.
    """
    monkeypatch.setattr(os, "environ", {"SYSTEMROOT": r"C:\Windows", "COMSPEC": "cmd.exe"})
    assert "SYSTEMROOT" in _safe_env()


def test_the_whitelist_still_drops_what_it_does_not_name(monkeypatch):
    """A whitelist that keeps everything is not a whitelist.

    The point of reducing the environment is that a command does not inherit the
    credentials and configuration of the process that launched it. Case-folding
    the comparison must not turn that into "pass everything through".
    """
    monkeypatch.setattr(os, "environ", {
        "PATH": "/bin",
        "AWS_SECRET_ACCESS_KEY": "should-not-travel",
        "GITHUB_TOKEN": "should-not-travel",
        "NPM_TOKEN": "should-not-travel",
    })
    env = _safe_env()
    assert set(env) == {"PATH"}


def test_a_command_runs_with_the_reduced_environment(tmp_path, monkeypatch):
    """`_safe_env` is only worth anything if exec actually uses it.

    The variable is set here rather than assumed: on a machine that happens not
    to define it, asserting its absence would pass without testing anything.
    """
    monkeypatch.setenv("WIZARD_TEST_SECRET", "should-not-travel")
    sandbox = LocalProcessRuntime()
    sandbox.start(str(tmp_path))
    try:
        result = sandbox.exec(
            f'"{sys.executable}" -c "import os; print(os.environ.get(\'WIZARD_TEST_SECRET\'))"',
            timeout_sec=60,
        )
    finally:
        sandbox.stop()

    assert result.ok, result.stderr
    assert "should-not-travel" not in result.stdout


# ── Output decoding ───────────────────────────────────────────────────────────

def test_output_the_locale_codec_cannot_decode_is_still_returned(tmp_path):
    """Command output is bytes, and the locale codec is not a decoder for it.

    The default on Windows is cp1252, which raises on the UTF-8 box-drawing and
    tick characters test runners emit. The reader thread died mid-read,
    `communicate()` came back as `(None, None)`, and the operator was shown
    "'NoneType' object is not subscriptable" — a message about this file,
    reported as the project's error.
    """
    sandbox = LocalProcessRuntime()
    sandbox.start(str(tmp_path))
    try:
        # Written as an escape: the codepoint is the point, and a source file
        # that cannot be read without the right codec cannot test this.
        result = sandbox.exec(
            f'"{sys.executable}" -c "'
            f'import sys; sys.stdout.buffer.write(\'\\u2713 \\u2500\'.encode())"',
            timeout_sec=60,
        )
    finally:
        sandbox.stop()

    assert result.ok, result.stderr
    assert "\u2713" in result.stdout, repr(result.stdout)


def test_a_command_that_emits_invalid_utf8_does_not_lose_its_output(tmp_path):
    """Replacement, not an exception: a mangled character beats a missing log."""
    sandbox = LocalProcessRuntime()
    sandbox.start(str(tmp_path))
    try:
        result = sandbox.exec(
            f'"{sys.executable}" -c "'
            f'import sys; sys.stdout.buffer.write(b\'before \\xff after\')"',
            timeout_sec=60,
        )
    finally:
        sandbox.stop()

    assert result.ok, result.stderr
    assert "before" in result.stdout and "after" in result.stdout
