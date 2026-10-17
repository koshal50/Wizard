"""Real loopback HTTP + PostgreSQL + actual CLI protocol (website pages live on another branch)."""

import socket
import threading
import time

import httpx
import uvicorn

from backend.app import create_app
from backend.config import Settings
from wizard.cli.account_login import LoginFlow


def test_actual_http_cli_and_separate_website_session(database):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    origin = "http://127.0.0.1:" + str(sock.getsockname()[1])
    app = create_app(Settings("test-only", origin, b"x" * 32, True), database)
    server = uvicorn.Server(
        uvicorn.Config(app, access_log=False, log_level="error", lifespan="on")
    )
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()

    class Store:
        value = None

        def load(self):
            return self.value

        def save(self, value):
            self.value = value

    store = Store()
    flow = LoginFlow(origin, store=store, opener=lambda _: False)
    try:
        deadline = time.monotonic() + 5
        while not server.started:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        with httpx.Client(
            base_url=origin, timeout=3, follow_redirects=False
        ) as browser:
            message = flow.start()
            from urllib.parse import parse_qs, urlsplit

            url = message.split("Open this URL manually:\n")[1].split("\n")[0]
            fragment = parse_qs(urlsplit(url).fragment)

            def browser_post(path, data):
                ctx = browser.get("/api/auth/context").json()
                return browser.post(
                    path,
                    json=data,
                    headers={"Origin": origin, "X-CSRF-Token": ctx["csrf"]},
                )

            assert (
                browser_post(
                    "/api/cli/browser/bind",
                    {
                        "request_id": fragment["request_id"][0],
                        "ticket": fragment["ticket"][0],
                    },
                ).status_code
                == 200
            )
            assert (
                browser_post(
                    "/register",
                    {
                        "fullName": "HTTP Account",
                        "email": "http@example.test",
                        "password": "long-http-password",
                        "confirmPassword": "long-http-password",
                        "acceptTerms": "on",
                    },
                ).status_code
                == 303
            )
            code = browser_post("/api/cli/browser/approve", {}).json()["code"]
            assert "verified" in flow.submit(code)
            assert store.value["account"]["email"] == "http@example.test"
            assert browser.get("/api/cli/browser").json()["state"] == "exchanged"
            assert (
                browser.get("/cli/complete").status_code == 404
            )  # No fabricated frontend completion.
    finally:
        flow.close(cancel=not flow.complete)
        server.should_exit = True
        thread.join(5)
        sock.close()
        assert not thread.is_alive()
