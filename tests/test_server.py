"""HTTP-handler regression checks without opening a listening socket."""
import io
import json
import unittest
from http.client import HTTPMessage

from poker_lab.game import Table
from poker_lab.server import Handler, SESSIONS


class ServerTests(unittest.TestCase):
    def request(self, path, payload, sid="test-session"):
        data = json.dumps(payload).encode()
        handler = object.__new__(Handler)
        handler.path = path
        handler.rfile = io.BytesIO(data)
        handler.headers = HTTPMessage()
        handler.headers["Content-Length"] = str(len(data))
        handler.headers["Cookie"] = "poker_session=" + sid
        result = []
        handler.reply = lambda status, body, cookie=None: result.append((status, body))
        handler.do_POST()
        return result[0]

    def tearDown(self):
        SESSIONS.pop("test-session", None)

    def test_reset_keeps_version_monotonic_and_rejects_old_requests(self):
        table = SESSIONS["test-session"] = Table(seed=1)
        old_version = table.version
        status, state = self.request("/api/reset", {})
        self.assertEqual(status, 200)
        self.assertGreater(state["version"], old_version)
        before = SESSIONS["test-session"].snapshot()
        status, _ = self.request("/api/step", {"version": old_version})
        self.assertEqual(status, 409)
        self.assertEqual(before, SESSIONS["test-session"].snapshot())

    def test_reconnect_resumes_same_hand_and_session_isolation(self):
        table = SESSIONS["test-session"] = Table(seed=2)
        table.act(table.actor, "check_call")
        status, state = self.request("/api/session", {})
        self.assertEqual(status, 200)
        self.assertEqual(state, table.snapshot())
        status, _ = self.request("/api/step", {"version": table.version}, sid="unknown")
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
