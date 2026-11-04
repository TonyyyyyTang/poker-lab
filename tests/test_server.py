"""HTTP-handler regression checks without opening a listening socket."""
import io
import json
import os
import sys
import threading
import unittest
from copy import deepcopy
from http.client import HTTPMessage
from http.cookies import SimpleCookie
from unittest.mock import patch

from poker_lab.game import PLAYERS, Table
from poker_lab import server


class ServerTests(unittest.TestCase):
    def setUp(self):
        server.SESSIONS.clear()
        server.TABLES.clear()
        self.now = 1000.0
        clock = patch.object(server.time, "monotonic", lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.addCleanup(server.SESSIONS.clear)
        self.addCleanup(server.TABLES.clear)

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

    def add_session(self, sid="test-session", seed=1, table=None, seat=0):
        table = table if table is not None else Table(seed=seed)
        with server.REGISTRY_LOCK:
            server._store_session(sid, server._register_table(table), seat)
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
        before = server.TABLES[server.SESSIONS["test-session"].table_id].view(0)
        status, _, _ = self.request("POST", "/api/action", {"version": old_version})
        self.assertEqual(status, 409)
        self.assertEqual(before, server.TABLES[server.SESSIONS["test-session"].table_id].view(0))

    def test_reconnect_resumes_same_hand_and_session_isolation(self):
        table = self.add_session(seed=2)
        table.act(table.actor, "check_call")
        status, state, _ = self.request("POST", "/api/session", {})
        self.assertEqual(status, 200)
        self.assertEqual(state, table.view(0))
        status, _, _ = self.request("POST", "/api/action", {"version": table.version}, sid="unknown")
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
                self.assertEqual(body, table.view(0))

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
        previous = server.TABLES[server.SESSIONS["session-0"].table_id]
        status, _, headers = self.request("POST", "/api/reset", sid="session-0")
        self.assertEqual(status, 200)
        self.assertEqual(set(server.SESSIONS), {f"session-{i}" for i in range(100)})
        self.assertIsNot(server.TABLES[server.SESSIONS["session-0"].table_id], previous)
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
                with server.REGISTRY_LOCK:
                    server._store_session("test-session", server._register_table(table))
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
        server.TABLES.clear()
        for method, path in (("GET", "/api/state"), ("POST", "/api/action")):
            status, body, headers = self.request(method, path, {"version": previous.version})
            self.assertEqual(status, 401)
            self.assertIn("重新连接", body["error"])
            self.assertNotIn("Set-Cookie", headers)
        status, state, headers = self.request("POST", "/api/session")
        self.assertEqual(status, 200)
        new_sid = SimpleCookie(headers["Set-Cookie"])["poker_session"].value
        self.assertNotEqual(new_sid, "test-session")
        self.assertIsNot(server.TABLES[server.SESSIONS[new_sid].table_id], previous)
        self.assertEqual(state["hand_id"], 1)
        self.assertFalse(state["complete"])
        self.assertEqual(server.TABLES[server.SESSIONS[new_sid].table_id].hands, [])
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

    def test_two_human_sessions_share_table_but_not_private_cards(self):
        players = deepcopy(PLAYERS)
        players[2].update(kind="human", name="Guest")
        table = self.add_session(table=Table(seed=8, players=players))
        self.add_session("guest", table=table, seat=2)
        self.assertEqual(len(server.TABLES), 1)
        self.assertEqual(self.request("POST", "/api/action", {"version": table.version, "action": "check_call"})[0], 409)
        for sid, seat in (("guest", 2), ("test-session", 0)):
            status, body, _ = self.request("GET", "/api/state", sid=sid)
            self.assertEqual(status, 200)
            self.assertEqual(set(body), {
                "you", "hand_id", "version", "complete", "street", "board", "pot", "current_actor",
                "dealer", "big_blind", "players", "legal", "actions", "summary", "session_net"})
            self.assertEqual(body["you"], seat)
            self.assertEqual(body["players"][seat]["cards"], table.holes[seat])
            for player in body["players"]:
                if player["id"] != seat:
                    self.assertEqual(player["cards"], [])
        status, _, _ = self.request("POST", "/api/action", {"version": table.version, "action": "check_call"}, sid="guest")
        self.assertEqual(status, 200)
        while table.actor != 0:
            table.act(table.actor, "fold")
        self.assertEqual(self.request("POST", "/api/action", {"version": table.version, "action": "fold"})[0], 200)
        while table.state.status:
            table.act(table.actor, "check_call")
        for sid, seat in (("guest", 2), ("test-session", 0)):
            status, replay, _ = self.request("GET", "/api/hand/1", sid=sid)
            self.assertEqual(status, 200)
            self.assertEqual(set(replay), {"hand_id", "frames", "summary", "notes", "net", "board"})
            self.assertEqual(replay, table.hand(1, seat))
            self.assertEqual(self.request("GET", "/api/history", sid=sid)[1], {"hands": table.history(seat)})
        status, body, _ = self.request("POST", "/api/next", {"version": table.version}, sid="guest")
        self.assertEqual(status, 200)
        self.assertEqual((body["hand_id"], body["you"]), (2, 2))

    def test_shared_table_dropped_only_after_last_session_expires(self):
        players = deepcopy(PLAYERS)
        players[3]["kind"] = "human"
        table = self.add_session(table=Table(players=players))
        table_id = server.SESSIONS["test-session"].table_id
        self.now += 10
        self.add_session("guest", table=table, seat=3)
        self.now += 7191
        self.request("GET", "/healthz", sid=None)
        self.assertNotIn("test-session", server.SESSIONS)
        self.assertIn(table_id, server.TABLES)
        self.assertFalse(table.closed)
        self.now += 10
        self.request("GET", "/healthz", sid=None)
        self.assertFalse(server.SESSIONS)
        self.assertFalse(server.TABLES)
        self.assertTrue(table.closed)
        self.assertIsNone(table.next_due())
        self.assertFalse(table.run_due())

    def test_last_session_eviction_stops_table_and_step_endpoint_is_removed(self):
        old = self.add_session()
        for index in range(100):
            self.now += 1
            self.add_session(f"new-{index}")
        self.assertTrue(old.closed)
        self.assertIsNone(old.next_due())
        self.assertEqual(len(server.TABLES), 100)
        self.assertEqual(self.request("POST", "/api/step", {}, sid="new-99")[0], 404)

    def test_long_poll_immediate_newer_version_and_timeout_contract(self):
        table = self.add_session()
        with patch.object(table.changed, "wait", side_effect=AssertionError("A newer version must not block")):
            self.assertEqual(self.request("GET", "/api/state?after=0")[1], table.view(0))
            self.assertEqual(self.request("GET", "/api/state")[1], table.view(0))

        def timeout(predicate, timeout):
            self.assertFalse(predicate())
            self.assertEqual(timeout, 25)
            return False

        with patch.object(table.changed, "wait_for", side_effect=timeout) as wait:
            self.assertEqual(self.request("GET", f"/api/state?after={table.version}")[1], table.view(0))
            wait.assert_called_once()
        for query in ("after=no", "after=", "after=-1", "after=1&after=2"):
            self.assertEqual(self.request("GET", "/api/state?" + query)[0], 400)

    def poll_during(self, table, change):
        waiting = threading.Event()
        result, errors = [], []
        original_wait = table.changed.wait

        def wait(timeout):
            waiting.set()
            return original_wait(timeout)

        def poll():
            try:
                result.append(self.request("GET", f"/api/state?after={table.version}"))
            except Exception as error:
                errors.append(error)

        with patch.object(table.changed, "wait", side_effect=wait):
            worker = threading.Thread(target=poll, daemon=True)
            worker.start()
            try:
                self.assertTrue(waiting.wait(2))
                change()
                worker.join(2)
                self.assertFalse(worker.is_alive(), "Long poll did not wake")
            finally:
                if worker.is_alive():
                    table.close()
                    worker.join(2)
        self.assertEqual(errors, [])
        return result[0]

    def test_long_poll_wakes_on_action_without_blocking_other_requests(self):
        table = self.add_session()
        previous = table.version

        def change():
            self.assertEqual(self.request("GET", "/healthz", sid=None)[0], 200)
            table.act(table.actor, "check_call")

        status, body, _ = self.poll_during(table, change)
        self.assertEqual(status, 200)
        self.assertGreater(body["version"], previous)
        self.assertEqual(body, table.view(0))

    def test_reset_wakes_poll_even_when_another_session_keeps_old_table(self):
        players = deepcopy(PLAYERS)
        players[3]["kind"] = "human"
        table = self.add_session(table=Table(players=players))
        self.add_session("guest", table=table, seat=3)
        old_id = server.SESSIONS["guest"].table_id
        old_version = table.version

        def reset():
            self.assertEqual(self.request("POST", "/api/reset")[0], 200)

        status, body, _ = self.poll_during(table, reset)
        self.assertEqual(status, 200)
        self.assertGreater(body["version"], old_version)
        self.assertEqual(body["you"], 0)
        self.assertEqual(len(server.TABLES), 2)
        self.assertIs(server.TABLES[old_id], table)
        self.assertFalse(table.closed)
        self.assertEqual(self.request("GET", "/api/state", sid="guest")[1], table.view(3))

    def test_expiry_wakes_poll_and_directly_closed_table_returns_401(self):
        table = self.add_session()

        def expire():
            self.now += 7201
            self.request("GET", "/healthz", sid=None)

        self.assertEqual(self.poll_during(table, expire)[0], 401)
        table = self.add_session()
        table.close()
        self.assertEqual(self.request("GET", "/api/state")[0], 401)
        self.assertFalse(server.TABLES)

    def test_driver_thinks_outside_registry_and_table_locks(self):
        table = self.add_session()
        self.now = table.next_due()
        entered, release = threading.Event(), threading.Event()

        def think(*args):
            entered.set()
            if not release.wait(2):
                raise AssertionError("Policy was not released")
            return {"action": "fold"}

        with patch("poker_lab.bots.choose_action", side_effect=think):
            worker = threading.Thread(target=server.drive_tables)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(server.REGISTRY_LOCK.acquire(timeout=1))
                try:
                    self.assertEqual(self.request("GET", "/healthz", sid=None)[0], 200)
                    self.assertTrue(table.lock.acquire(timeout=1))
                    table.lock.release()
                    server._drop_session("test-session")
                finally:
                    server.REGISTRY_LOCK.release()
            finally:
                release.set()
                worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(table.actions, [])
        self.assertTrue(table.closed)
        self.assertFalse(server.TABLES)


if __name__ == "__main__":
    unittest.main()
