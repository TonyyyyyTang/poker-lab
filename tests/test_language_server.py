"""Language-neutral HTTP error codes at their actual request boundaries."""
import io
import json
import unittest
from http.client import HTTPMessage
from http.cookies import SimpleCookie
from unittest.mock import patch

from poker_lab import server
import test_server as existing


class LanguageServerTests(unittest.TestCase):
    # Reuse the handler fixture without inheriting and rerunning its test cases.
    setUp = existing.ServerTests.setUp
    request = existing.ServerTests.request
    add_session = existing.ServerTests.add_session

    def assert_error(self, response, status, code):
        actual_status, body, headers = response
        self.assertEqual(actual_status, status)
        self.assertEqual(set(body), {"code", "error"})
        self.assertEqual(body["code"], code)
        self.assertIsInstance(body["error"], str)
        self.assertTrue(body["error"].strip())
        self.assertTrue(body["error"].isascii(), body["error"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        return body

    def raw_post(self, raw, length=None):
        handler = object.__new__(server.Handler)
        handler.path = "/api/session"
        handler.rfile = io.BytesIO(raw)
        handler.wfile = io.BytesIO()
        handler.headers = HTTPMessage()
        handler.headers["Host"] = "poker.example"
        handler.headers["Content-Length"] = str(len(raw)) if length is None else length
        status, headers = [], {}
        handler.send_response = status.append
        handler.send_header = lambda name, value: headers.update({name: value})
        handler.end_headers = lambda: None
        handler.do_POST()
        return status[0], json.loads(handler.wfile.getvalue()), headers

    def to_human_turn(self, table):
        while table.actor != 0:
            self.assertTrue(table.state.status)
            table.act(table.actor, "check_call")

    def shared(self):
        self.add_session()
        status, view, _ = self.request("POST", "/api/tables", {"name": "Host"})
        self.assertEqual(status, 200)
        table = server.TABLES[server.SESSIONS["test-session"].table_id]
        return view["table"]["invite"], table

    def test_expired_for_missing_closed_and_idle_sessions(self):
        for method, path in (("GET", "/api/state"), ("POST", "/api/action"),
                             ("POST", "/api/reset"), ("POST", "/api/leave"),
                             ("POST", "/api/back")):
            self.assert_error(self.request(method, path), 401, "expired")
        table = self.add_session()
        table.close()
        self.assert_error(self.request("GET", "/api/state"), 401, "expired")
        self.add_session()
        self.now += 7201
        self.assert_error(self.request("GET", "/api/history"), 401, "expired")

    def test_not_found_for_unknown_endpoints_and_static_paths(self):
        for method, path in (("GET", "/api/no-such-endpoint"), ("POST", "/api/no-such-endpoint"),
                             ("GET", "/no-such-file"), ("GET", "/t/../README.md")):
            self.assert_error(self.request(method, path), 404, "not_found")

    def test_hand_not_found_for_unfinished_invalid_and_evicted_hands(self):
        table = self.add_session()
        for path in ("/api/hand/1", "/api/hand/no", "/api/hand/999"):
            self.assert_error(self.request("GET", path), 404, "hand_not_found")
        for hand in range(21):
            while table.state.status:
                table.act(table.actor, "fold")
            if hand < 20:
                table.new_hand()
        self.assert_error(self.request("GET", "/api/hand/1"), 404, "hand_not_found")
        self.assertEqual(self.request("GET", "/api/hand/21")[0], 200)

    def test_invite_not_found_and_table_full(self):
        self.assert_error(self.request("POST", "/api/join", {"code": "missing", "name": "Guest"}, sid=None),
                          404, "invite_not_found")
        code, table = self.shared()
        for seat in range(1, 6):
            response = self.request("POST", "/api/join", {"code": code, "name": f"Guest {seat}"}, sid=None)
            self.assertEqual(response[0], 200)
        self.assert_error(self.request("POST", "/api/join", {"code": code, "name": "Extra"}, sid=None),
                          409, "table_full")
        table.close()
        self.assert_error(self.request("POST", "/api/join", {"code": code, "name": "Guest"}, sid=None),
                          404, "invite_not_found")

    def test_bad_name_for_creation_and_join_preserves_binding(self):
        code, _ = self.shared()
        binding = server.SESSIONS["test-session"]
        for name in (None, False, [], "", "  ", "abcdefghijklm", "A\x00B", "A\u202eB"):
            with self.subTest(name=name):
                self.assert_error(self.request("POST", "/api/tables", {"name": name}), 400, "bad_name")
                self.assert_error(self.request("POST", "/api/join", {"code": code, "name": name}, sid=None),
                                  400, "bad_name")
                self.assertIs(server.SESSIONS["test-session"], binding)

    def test_bad_request_for_json_length_after_and_version(self):
        for raw in (b"{", b"[]", b"null", b'"text"', b"\xff"):
            with self.subTest(raw=raw):
                self.assert_error(self.raw_post(raw), 400, "bad_request")
        for length in ("bad", "-1", "4097"):
            self.assert_error(self.raw_post(b"{}", length), 400, "bad_request")
        table = self.add_session()
        for query in ("after=no", "after=", "after=-1", "after=1.5", "after=1&after=2"):
            self.assert_error(self.request("GET", "/api/state?" + query), 400, "bad_request")
        self.to_human_turn(table)
        for endpoint in ("/api/action", "/api/next"):
            for version in (None, -1, True, 1.0, "1", [], {}):
                with self.subTest(endpoint=endpoint, version=version):
                    self.assert_error(self.request("POST", endpoint, {"version": version, "action": "check_call"}),
                                      400, "bad_request")
            self.assert_error(self.request("POST", endpoint, {"action": "check_call"}), 400, "bad_request")

    def test_stale_versions_reject_previous_future_and_duplicate_actions(self):
        table = self.add_session()
        self.to_human_turn(table)
        for version in (table.version - 1, table.version + 1):
            self.assert_error(self.request("POST", "/api/action", {"version": version, "action": "check_call"}),
                              409, "stale")
        version = table.version
        payload = {"version": version, "action": "check_call"}
        self.assertEqual(self.request("POST", "/api/action", payload)[0], 200)
        self.assert_error(self.request("POST", "/api/action", payload), 409, "stale")
        self.assert_error(self.request("POST", "/api/next", {"version": version}), 409, "stale")

    def test_not_your_turn_and_hand_in_progress(self):
        table = self.add_session()
        self.assertNotEqual(table.actor, 0)
        self.assert_error(self.request("POST", "/api/action", {"version": table.version, "action": "check_call"}),
                          409, "not_your_turn")
        self.assert_error(self.request("POST", "/api/next", {"version": table.version}), 409, "hand_in_progress")
        while table.state.status:
            table.act(table.actor, "fold")
        self.assert_error(self.request("POST", "/api/action", {"version": table.version, "action": "check_call"}),
                          409, "not_your_turn")

    def test_illegal_actions_have_one_code_without_mutating_state(self):
        table = self.add_session()
        self.to_human_turn(table)
        before = table.view(0)
        for action, amount in (("unknown", None), (None, None), ("raise", None),
                               ("raise", True), ("raise", 0), ("raise", 201)):
            with self.subTest(action=action, amount=amount):
                self.assert_error(self.request("POST", "/api/action", {
                    "version": table.version, "action": action, "amount": amount}), 409, "illegal_action")
                self.assertEqual(table.view(0), before)
        table.act(0, "check_call")
        self.to_human_turn(table)
        self.assertTrue(table.legal()["can_check"])
        self.assert_error(self.request("POST", "/api/action", {"version": table.version, "action": "fold"}),
                          409, "illegal_action")

    def test_not_seated_for_pending_and_departed_players(self):
        code, table = self.shared()
        status, _, headers = self.request("POST", "/api/join", {"code": code, "name": "Guest"}, sid=None)
        self.assertEqual(status, 200)
        guest = SimpleCookie(headers["Set-Cookie"])["poker_session"].value
        for endpoint in ("/api/action", "/api/next", "/api/back"):
            self.assert_error(self.request("POST", endpoint, {"version": table.version, "action": "check_call"}, sid=guest),
                              409, "not_seated")
        # A retired seat must also reject a request that already resolved its binding.
        table.leave(0)
        self.assert_error(self.request("POST", "/api/action", {"version": table.version, "action": "check_call"}),
                          409, "not_seated")

    def test_forbidden_origin_covers_every_mutating_endpoint(self):
        for endpoint in ("session", "reset", "action", "next", "tables", "join", "leave", "back"):
            self.assert_error(self.request("POST", "/api/" + endpoint, headers={"Origin": "https://other.example"}),
                              403, "forbidden_origin")

    def test_unexpected_exceptions_are_sanitized_server_errors(self):
        table = self.add_session()
        self.to_human_turn(table)
        with patch.object(table, "act", side_effect=RuntimeError("private detail 私密")), patch("traceback.print_exc"):
            body = self.assert_error(self.request("POST", "/api/action", {
                "version": table.version, "action": "check_call"}), 500, "server_error")
        self.assertNotIn("private detail", body["error"])
        with patch.object(server, "Table", side_effect=RuntimeError("private detail 私密")), patch("traceback.print_exc"):
            self.assert_error(self.request("POST", "/api/session", sid=None), 500, "server_error")
        with patch.object(table, "view", side_effect=RuntimeError("private detail 私密")), patch("traceback.print_exc"):
            self.assert_error(self.request("GET", "/api/state"), 500, "server_error")


if __name__ == "__main__":
    unittest.main()
