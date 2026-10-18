"""Installed PowerShell client against real HTTP/PostgreSQL, without frontend pages."""

import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from backend.app import create_app
from backend.config import Settings
from backend.db import missing_account_tables
from wizard.cli.account_login import LoginFlow

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
LOAD = ". './backend/scripts/cli-auth-browser.ps1'; "


def ps(code, data=None):
    if not POWERSHELL:
        pytest.skip("PowerShell 5.1+ required")
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            LOAD + code,
        ],
        input=json.dumps(data),
        text=True,
        capture_output=True,
        cwd=ROOT,
        timeout=20,
        check=False,
    )


@pytest.mark.parametrize(
    "suffix,local,valid",
    [
        ("", True, True),
        ("", False, False),
        ("&ticket=duplicate", True, False),
        ("&verifier=forbidden", True, False),
    ],
)
def test_url_parser(suffix, local, valid):
    url = (
        "http://localhost:8090/cli/authorize#request_id=11111111-1111-4111-8111-111111111111&ticket="
        + "A" * 43
        + suffix
    )
    result = ps(
        "$d=[Console]::In.ReadToEnd()|ConvertFrom-Json; try {"
        "$v=ConvertTo-WizardContextUrl $d.url 'http://localhost:8090' $d.local;"
        "Write-Output 'VALID'} catch {Write-Output 'REJECTED'}",
        {"url": url, "local": local},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ("VALID" if valid else "REJECTED")


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (200, "[]", "200:True:request_failed:7"),
        (200, "broken-json", "200:True:malformed_response:7"),
        (429, '{"error":"rate_limited"}', "429:False:rate_limited:7"),
        (401, '{"error":"invalid_credentials"}', "401:False:invalid_credentials:7"),
    ],
)
def test_transport_validates_response_and_rate_limits(status, body, expected):
    result = ps(
        """
$d=[Console]::In.ReadToEnd()|ConvertFrom-Json
function Invoke-WebRequest {param($Uri,$Method,$WebSession,$Headers,$TimeoutSec,
 $MaximumRedirection,$UseBasicParsing,$Verbose,$Debug,$SkipHttpErrorCheck)
 [pscustomobject]@{StatusCode=$d.status;Content=$d.body;Headers=@{'Retry-After'='7'}}
}
$state=[pscustomobject]@{Origin='https://example.test';Session=$null;Timeout=2;Csrf=''}
$r=Invoke-WizardWebRequest $state '/api/auth/context'
Write-Output ('{0}:{1}:{2}:{3}' -f $r.Status,$r.Malformed,$r.Code,$r.RetryAfter)
""",
        {"status": status, "body": body},
    )
    assert result.returncode == 0 and not result.stderr
    # An array is malformed even if it contains no machine error field.
    if body == "[]":
        expected = "200:True:malformed_response:7"
    assert result.stdout.strip() == expected


def test_bounded_network_reads_and_unconfirmed_cancellation():
    result = ps("""
$script:calls=0
function Wait-WizardBrowser {param($Seconds)}
function Invoke-WizardWebRequest {param($State,$Path,$Method,$Body)
 $script:calls++
 [pscustomobject]@{Status=0;Data=$null;Code='network_error';RetryAfter=0;Malformed=$false}
}
$s=[pscustomobject]@{CancelAttempted=$false;TerminalConfirmed=$false;RequestId='test'}
$r=Invoke-WizardGet $s '/api/auth/context'
if($script:calls -ne 3 -or $r.Status -ne 0){throw 'unbounded reads'}
$confirmed=Invoke-WizardBrowserCancel $s
if($script:calls -ne 5 -or $confirmed -or $s.TerminalConfirmed){throw 'false cancellation'}
Write-Output 'BOUNDED'
""")
    assert result.returncode == 0 and not result.stderr
    assert "Cancellation was NOT confirmed" in result.stdout
    assert result.stdout.rstrip().endswith("BOUNDED")


@pytest.fixture
def live_account_server(database, clock):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    origin = "http://127.0.0.1:" + str(sock.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(Settings("test", origin, b"s" * 32, True), database, clock),
            access_log=False,
            log_level="error",
        )
    )
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        yield origin
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()


HARNESS = (
    LOAD
    + """$d=[Console]::In.ReadToEnd()|ConvertFrom-Json
$script:answers=New-Object 'System.Collections.Generic.Queue[string]'
foreach($a in $d.answers){$script:answers.Enqueue($a)}
function Read-Host {param($Prompt,[switch]$AsSecureString)
 if($script:answers.Count -eq 0){throw 'Unexpected prompt'}
 $a=$script:answers.Dequeue()
 if($AsSecureString){return ConvertTo-SecureString $a -AsPlainText -Force}
 return $a
}
exit (Invoke-WizardBrowserSimulator -Origin $d.origin -AllowLocal $true -PollInterval 1)
"""
)


@pytest.mark.parametrize("mode", ["register", "login", "cancel", "expiry"])
def test_simulator_real_session_and_cli(live_account_server, database, clock, mode):
    if not POWERSHELL:
        pytest.skip("PowerShell required")
    origin = live_account_server
    if mode == "login":
        import httpx

        with httpx.Client(base_url=origin) as browser:
            csrf = browser.get("/api/auth/context").json()["csrf"]
            response = browser.post(
                "/register",
                headers={"Origin": origin, "X-CSRF-Token": csrf},
                json={
                    "email": "sim@example.test",
                    "fullName": "Simulator",
                    "password": "test-password-12345",
                    "confirmPassword": "test-password-12345",
                    "acceptTerms": "on",
                },
            )
            assert response.status_code == 303

    class Store:
        value = None

        def load(self):
            return self.value

        def save(self, value):
            self.value = value

    store = Store()
    flow = LoginFlow(origin, store=store, opener=lambda _: False)
    process = None
    try:
        url = flow.start().split("Open this URL manually:\n")[1].split("\n")[0]
        answers = [url]
        if mode == "cancel":
            answers += ["/cancel"]
        elif mode == "login":
            answers += ["L", "sim@example.test", "test-password-12345", "YES"]
        else:
            answers += [
                "R",
                "Simulator",
                "sim@example.test",
                "test-password-12345",
                "test-password-12345",
                "YES",
                "YES",
            ]
        process = subprocess.Popen(
            [
                POWERSHELL,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                HARNESS,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=ROOT,
        )
        process.stdin.write(json.dumps({"origin": origin, "answers": answers}))
        process.stdin.close()
        watchdog = threading.Timer(30, process.kill)
        watchdog.start()
        code_seen = False
        for line in process.stdout:
            match = re.search(r"Authorization code: ([A-F0-9]{12})", line)
            if match:
                code_seen = True
                if mode == "expiry":
                    from datetime import timedelta

                    clock.now += timedelta(seconds=601)
                else:
                    assert "verified" in flow.submit(match[1])
            if "Backend confirmed successful code exchange" in line:
                assert flow.complete
        process.wait(timeout=15)
        assert not process.stderr.read(), (
            "Simulator emitted an unsanitized PowerShell error"
        )
        if mode in {"register", "login"}:
            assert process.returncode == 0, "Simulator did not confirm backend exchange"
            assert code_seen and store.value["account"]["email"] == "sim@example.test"
        else:
            assert process.returncode == 1
            assert not flow.complete and store.value is None
            with database.connection() as conn:
                row = conn.execute("SELECT state FROM cli_authorizations").fetchone()
            assert row["state"] == "cancelled"
    finally:
        if process:
            watchdog.cancel()
        if process and process.poll() is None:
            process.kill()
        flow.close(cancel=not flow.complete)


def test_read_only_table_preflight(database):
    assert missing_account_tables(database.pool.conninfo) == []


def test_terminal_dispatcher_simulator_and_native_storage(live_account_server):
    """Real /login dispatcher, private verifier, account verification and native store.

    Only OS browser launching is disabled; no frontend exists in this test.
    """
    if not POWERSHELL or os.name != "nt":
        pytest.skip("Windows PowerShell/native Credential Manager required")
    import ctypes
    from ctypes import wintypes

    from wizard.cli.account_storage import CredentialStore

    origin = live_account_server
    store = CredentialStore(origin)
    assert (
        store.load() is None
    )  # Unique ephemeral port; never overwrite user credentials.
    env = dict(
        os.environ,
        WIZARD_ACCOUNT_URL=origin,
        WIZARD_ACCOUNT_LOCAL_DEV="1",
        COLUMNS="2400",
        NO_COLOR="1",
        PYTHONUNBUFFERED="1",
    )
    # Same entry point as wizard.exe, suppressing only the external browser side effect.
    cli = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys,webbrowser; webbrowser.open=lambda *_args,**_kw:False; "
                "sys.argv=['wizard','/login']; from wizard.cli.main import main; main()"
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
        text=True,
        env=env,
    )
    simulator = None
    lines = queue.Queue()

    def drain(stream):
        for line in stream:
            lines.put(line)

    threading.Thread(target=drain, args=(cli.stdout,), daemon=True).start()
    try:
        deadline = time.monotonic() + 15
        url = None
        while time.monotonic() < deadline:
            line = lines.get(timeout=5)
            if line.strip().startswith(origin + "/cli/authorize#"):
                url = line.strip()
                break
        assert url, "Actual terminal dispatcher did not print authorization URL"
        simulator = subprocess.Popen(
            [
                POWERSHELL,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                HARNESS,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=ROOT,
        )
        simulator.stdin.write(
            json.dumps(
                {
                    "origin": origin,
                    "answers": [
                        url,
                        "R",
                        "Terminal",
                        "terminal@example.test",
                        "terminal-password-123",
                        "terminal-password-123",
                        "YES",
                        "YES",
                    ],
                }
            )
        )
        simulator.stdin.close()
        timer = threading.Timer(30, simulator.kill)
        timer.start()
        exchanged = False
        for line in simulator.stdout:
            match = re.search(r"Authorization code: ([A-F0-9]{12})", line)
            if match:
                cli.stdin.write(match[1] + "\n")
                cli.stdin.flush()
                cli.stdin.close()
            if "Backend confirmed successful code exchange" in line:
                exchanged = True
        simulator.wait(timeout=5)
        timer.cancel()
        cli.wait(timeout=10)
        assert exchanged and simulator.returncode == 0
        assert not simulator.stderr.read()
        if cli.returncode != 0:
            messages = "".join(list(lines.queue))
            if "Windows error 1312" in messages:
                pytest.skip(
                    "Native Credential Manager unavailable in sandbox logon; rerun outside sandbox"
                )
        assert cli.returncode == 0, (
            "Actual CLI verification or secure persistence failed"
        )
        value = store.load()
        assert value and value["account"]["email"] == "terminal@example.test"
        import httpx

        response = httpx.get(
            origin + "/api/account/me",
            headers={
                "Authorization": "Bearer " + value["access_token"],
            },
        )
        assert response.status_code == 200
    finally:
        if cli.poll() is None:
            cli.kill()
        if simulator and simulator.poll() is None:
            simulator.kill()
        # Delete only this test's unique account target, never other saved credentials.
        api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW(store.target, 1, 0)
