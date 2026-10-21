"""Session-only conversational state, independent of primary command workers."""

import threading
from uuid import uuid4

import httpx


def request_reply(conversation_id, session_id, messages):
    from wizard.cli.runtime_client.account import account_headers
    from wizard.cli.runtime_client.client import base_url

    # base_url includes /v1/investigations for the primary transport.
    url = base_url().split("/v1/investigations")[0] + "/v1/btw"
    with httpx.Client(timeout=httpx.Timeout(70, connect=3), trust_env=False) as client:
        response = client.post(url, headers=account_headers(), json={
            "conversation_id": conversation_id, "session_id": session_id, "messages": messages})
        if response.is_error:
            raise RuntimeError("Side conversation unavailable (HTTP " + str(response.status_code) + "). Try again.")
        packet = response.json()
    if packet.get("conversation_id") != conversation_id:
        raise RuntimeError("Side conversation response identity did not match.")
    answer = packet.get("text")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Provider returned an empty answer. Try again.")
    return answer


class SideChat:
    def __init__(self, on_change, session_id=None, responder=None):
        self.id = str(uuid4())
        self.session_id = session_id or str(uuid4())
        self.messages = []
        self.pending = False
        self.error = ""
        self.closed = False
        self.lock = threading.RLock()
        self.worker = None
        self.on_change = on_change
        self.responder = responder or request_reply

    def snapshot(self):
        with self.lock:
            return {"id": self.id, "messages": [dict(m) for m in self.messages],
                    "pending": self.pending, "error": self.error}

    def submit(self, question):
        question = question.strip()
        with self.lock:
            if not question or self.closed or self.pending:
                return False
            self.messages.append({"role": "user", "content": question})
            messages = [dict(m) for m in self.messages]
            self.pending, self.error = True, ""
            self.worker = threading.Thread(target=self._respond, args=(messages,), name="btw-response", daemon=True)
            self.worker.start()
        self.on_change()
        return True

    def _respond(self, messages):
        try:
            answer = self.responder(self.id, self.session_id, messages)
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Empty response")
            error = ""
        except Exception:  # noqa: BLE001 -- provider failures cannot terminate the TUI worker
            answer = None
            error = "Side conversation could not respond. Check the provider connection and try again."
        with self.lock:
            if self.closed:
                return
            if answer is not None:
                self.messages.append({"role": "assistant", "content": answer})
            self.pending, self.error = False, error
        self.on_change()

    def close(self):
        with self.lock:
            self.closed = True
        # A bounded provider request may finish on its daemon thread; it cannot
        # mutate the closed conversation or touch the parent execution.
