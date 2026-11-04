"""HTTP-handler regression checks without opening a listening socket."""
import io
import json
import os
import sys
import unittest
from http.client import HTTPMessage
from http.cookies import SimpleCookie
from unittest.mock import patch

from poker_lab.game import Table
from poker_lab import server


class ServerTests(unittest.TestCase):
    def setUp(self):
        server.SESSIONS.clear()
        self.now = 1000.0
        clock = patch.object(server.time, "monotonic", lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.addCleanup(server.SESSIONS.clear)

    def request(self, method, path, payload=None, sid="test-session", headers=None):
        data = json.dumps(payload or {}).encode()
        handler = object.__new__(server.Handler)
        handler.path = path
        handler.rfile = io.BytesIO(data)
        handler.wfile = io.BytesIO()
        request_headers = {"Host": "poker.example", "Content-Length": str(len(data))}
        if sid is not None:
            request_headers["Cookie"] = "poker_session=" + sid
        request_headers.update(headers or {})
        handler.headers = HTTPMessage()
        for name, value in request_headers.items():
            if value is not None:
                handler.headers[name] = value
        status = []
        response_headers = {}
        handler.send_response = status.append
        handler.send_header = lambda name, value: response_headers.update({name: value})
        handler.end_headers = lambda: None
        getattr(handler, "do_" + method)()
        return status[0], json.loads(handler.wfile.getvalue()), response_headers

    def add_session(self, sid="test-session", seed=1):
        table = Table(seed=seed)
        with server.LOCK:
            server._store_session(sid, table)
        return table

    def fill_sessions(self):
        for index in range(server.MAX_SESSIONS):
            self.add_session(f"session-{index}", seed=index)
            self.now += 1

    def test_reset_keeps_version_monotonic_and_rejects_old_requests(self):
        table = self.add_session()
        old_version = table.version
        status, state, _ = self.request("POST", "/api/reset", {})
        self.assertEqual(status, 200)
        self.assertGreater(state["version"], old_version)
        before = server.SESSIONS["test-session"].table.snapshot()
        status, _, _ = self.request("POST", "/api/step", {"version": old_version})
        self.assertEqual(status, 409)
        self.assertEqual(before, server.SESSIONS["test-session"].table.snapshot())

    def test_reconnect_resumes_same_hand_and_session_isolation(self):
        table = self.add_session(seed=2)
        table.act(table.actor, "check_call")
        status, state, _ = self.request("POST", "/api/session", {})
        self.assertEqual(status, 200)
        self.assertEqual(state, table.snapshot())
        status, _, _ = self.request("POST", "/api/step", {"version": table.version}, sid="unknown")
        self.assertEqual(status, 401)

    def test_same_origin_http_https_and_ports_are_accepted(self):
        table = self.add_session()
        for origin, host in (
            ("http://poker.example", "poker.example"),
            ("https://poker.example", "poker.example"),
            ("https://POKER.example", "poker.example"),
            ("http://127.0.0.1:8765", "127.0.0.1:8765"),
            ("https://poker.example:8443", "poker.example:8443"),
            ("http://poker.example", "poker.example:80"),
            ("https://poker.example:443", "poker.example"),
            ("http://[::1]:8765", "[::1]:8765"),
        ):
            with self.subTest(origin=origin, host=host):
                status, body, _ = self.request("POST", "/api/session", headers={"Origin": origin, "Host": host})
                self.assertEqual(status, 200)
                self.assertEqual(body, table.snapshot())

    def test_foreign_or_malformed_origins_are_rejected(self):
        self.add_session()
        for origin, host in (
            ("https://foreign.example", "poker.example"),
            ("https://poker.example.foreign.example", "poker.example"),
            ("https://poker.example:8443", "poker.example"),
            ("http://poker.example:443", "poker.example"),
            ("https://poker.example", "poker.example:80"),
            ("null", "poker.example"),
            ("", "poker.example"),
            ("ftp://poker.example", "poker.example"),
            ("https://poker.example:bad", "poker.example"),
            ("https://poker.example:99999", "poker.example"),
            ("https://[::1", "poker.example"),
            ("https://poker.example", None),
        ):
            with self.subTest(origin=origin, host=host):
                status, body, headers = self.request("POST", "/api/session", headers={"Origin": origin, "Host": host})
                self.assertEqual(status, 403)
                self.assertIn("error", body)
                self.assertNotIn("Set-Cookie", headers)

    def test_session_cookie_is_secure_only_for_forwarded_https(self):
        for proto in (None, "http", "https", " HTTPS "):
            with self.subTest(proto=proto):
                status, _, headers = self.request("POST", "/api/session", sid=None, headers={"X-Forwarded-Proto": proto})
                self.assertEqual(status, 200)
                cookie = SimpleCookie(headers["Set-Cookie"])["poker_session"]
                self.assertTrue(cookie["httponly"])
                self.assertEqual(cookie["samesite"], "Strict")
                self.assertEqual(cookie["path"], "/")
                self.assertEqual(bool(cookie["secure"]), proto is not None and proto.strip().lower() == "https")
                self.assertIn(cookie.value, server.SESSIONS)

    def test_lru_eviction_at_100_sessions_preserves_recently_read_table(self):
        self.assertEqual(server.MAX_SESSIONS, 100)
        self.fill_sessions()
        status, _, _ = self.request("GET", "/api/state", sid="session-0")
        self.assertEqual(status, 200)
        self.now += 1
        status, _, headers = self.request("POST", "/api/session", sid=None)
        self.assertEqual(status, 200)
        new_sid = SimpleCookie(headers["Set-Cookie"])["poker_session"].value
        self.assertEqual(len(server.SESSIONS), 100)
        self.assertIn("session-0", server.SESSIONS)
        self.assertNotIn("session-1", server.SESSIONS)
        self.assertIn(new_sid, server.SESSIONS)
        self.assertEqual(self.request("GET", "/api/state", sid="session-1")[0], 401)

    def test_reset_at_capacity_replaces_one_session_without_evicting_another(self):
        self.fill_sessions()
        previous = server.SESSIONS["session-0"].table
        status, _, headers = self.request("POST", "/api/reset", sid="session-0")
        self.assertEqual(status, 200)
        self.assertEqual(set(server.SESSIONS), {f"session-{i}" for i in range(100)})
        self.assertIsNot(server.SESSIONS["session-0"].table, previous)
        self.assertEqual(next(reversed(server.SESSIONS)), "session-0")
        self.assertNotIn("Set-Cookie", headers)

    def test_idle_expiry_is_strictly_after_two_hours(self):
        self.assertEqual(server.SESSION_IDLE_SECONDS, 7200)
        self.add_session()
        self.now += 7200
        self.request("GET", "/healthz", sid=None)
        self.assertIn("test-session", server.SESSIONS)
        self.now += 0.001
        status, body, _ = self.request("GET", "/api/state")
        self.assertEqual(status, 401)
        self.assertIn("重新连接", body["error"])
        self.assertNotIn("test-session", server.SESSIONS)

    def test_state_history_and_replay_reads_refresh_idle_time_and_lru(self):
        table = self.add_session()
        while table.state.status:
            table.act(table.actor, "fold")
        for path in ("/api/state", "/api/history", "/api/hand/1"):
            with self.subTest(path=path):
                with server.LOCK:
                    server._store_session("test-session", table)
                self.add_session("other-session")
                self.now += 7199
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertEqual(server.SESSIONS["test-session"].last_seen, self.now)
                self.assertEqual(next(reversed(server.SESSIONS)), "test-session")
                self.now += 2
                self.request("GET", "/healthz", sid=None)
                self.assertIn("test-session", server.SESSIONS)
                self.assertNotIn("other-session", server.SESSIONS)

    def test_restart_returns_401_then_reconnect_creates_a_fresh_table(self):
        previous = self.add_session()
        previous.act(previous.actor, "check_call")
        server.SESSIONS.clear()
        for method, path in (("GET", "/api/state"), ("POST", "/api/step")):
            status, body, headers = self.request(method, path, {"version": previous.version})
            self.assertEqual(status, 401)
            self.assertIn("重新连接", body["error"])
            self.assertNotIn("Set-Cookie", headers)
        status, state, headers = self.request("POST", "/api/session")
        self.assertEqual(status, 200)
        new_sid = SimpleCookie(headers["Set-Cookie"])["poker_session"].value
        self.assertNotEqual(new_sid, "test-session")
        self.assertIsNot(server.SESSIONS[new_sid].table, previous)
        self.assertEqual(state["hand_id"], 1)
        self.assertFalse(state["complete"])
        self.assertEqual(server.SESSIONS[new_sid].table.hands, [])
        self.assertEqual(self.request("GET", "/api/state", sid=new_sid)[1], state)

    def test_health_check_has_no_session_or_cookie(self):
        status, body, headers = self.request("GET", "/healthz", sid=None)
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertLess(int(headers["Content-Length"]), 32)
        self.assertNotIn("Set-Cookie", headers)
        self.assertFalse(server.SESSIONS)

    def test_health_check_expires_idle_sessions_without_refreshing_live_ones(self):
        self.add_session("expired")
        self.now += 7200
        self.add_session()
        last_seen = server.SESSIONS["test-session"].last_seen
        self.now += 1
        status, _, headers = self.request("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertNotIn("expired", server.SESSIONS)
        self.assertEqual(server.SESSIONS["test-session"].last_seen, last_seen)
        self.assertNotIn("Set-Cookie", headers)

    def test_binding_defaults_environment_and_cli_port_override(self):
        for environment, args, address in (
            ({}, [], ("127.0.0.1", 8765)),
            ({"HOST": "0.0.0.0", "PORT": "10000"}, [], ("0.0.0.0", 10000)),
            ({"HOST": "0.0.0.0", "PORT": "10000"}, ["--port", "8766"], ("0.0.0.0", 8766)),
            ({}, ["--port", "8766"], ("127.0.0.1", 8766)),
        ):
            with self.subTest(environment=environment, args=args):
                with patch.dict(os.environ, environment, clear=True), patch.object(sys, "argv", ["server", *args]), \
                        patch.object(server, "ThreadingHTTPServer") as http_server, patch("builtins.print"):
                    server.main()
                http_server.assert_called_once_with(address, server.Handler)
                http_server.return_value.serve_forever.assert_called_once_with()
                http_server.return_value.server_close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
