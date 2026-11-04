"""Invite-table HTTP contracts, session rebinding and private-seat boundaries."""
import io
import json
import threading
import unittest
from http.client import HTTPMessage
from http.cookies import SimpleCookie
from unittest.mock import patch

from poker_lab import server


class InviteServerTests(unittest.TestCase):
    def setUp(self):
        server.SESSIONS.clear()
        server.TABLES.clear()
        self.now = 1000.0
        clock = patch.object(server.time, "monotonic", lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.addCleanup(server.SESSIONS.clear)
        self.addCleanup(server.TABLES.clear)

    def request(self, method, path, payload=None, sid=None, headers=None):
        data = json.dumps(payload if payload is not None else {}).encode()
        handler = object.__new__(server.Handler)
        handler.path = path
        handler.rfile = io.BytesIO(data)
        handler.wfile = io.BytesIO()
        handler.headers = HTTPMessage()
        request_headers = {"Host": "poker.example", "Content-Length": str(len(data))}
        if sid is not None:
            request_headers["Cookie"] = "poker_session=" + sid
        request_headers.update(headers or {})
        for name, value in request_headers.items():
            handler.headers[name] = value
        statuses, response_headers = [], {}
        handler.send_response = statuses.append
        handler.send_header = lambda name, value: response_headers.update({name: value})
        handler.end_headers = lambda: None
        getattr(handler, "do_" + method)()
        raw = handler.wfile.getvalue()
        body = json.loads(raw) if response_headers["Content-Type"].startswith("application/json") else raw
        return statuses[0], body, response_headers

    def solo(self):
        status, view, headers = self.request("POST", "/api/session")
        self.assertEqual(status, 200)
        sid = SimpleCookie(headers["Set-Cookie"])["poker_session"].value
        return sid, view

    def shared(self):
        sid, _ = self.solo()
        status, view, _ = self.request("POST", "/api/tables", {"name": "Host"}, sid=sid)
        self.assertEqual(status, 200)
        return sid, view, server.TABLES[server.SESSIONS[sid].table_id]

    def join(self, code, name="Guest", sid=None):
        status, view, headers = self.request("POST", "/api/join", {"code": code, "name": name}, sid=sid)
        self.assertEqual(status, 200)
        if sid is None:
            sid = SimpleCookie(headers["Set-Cookie"])["poker_session"].value
        return sid, view

    @staticmethod
    def finish(table):
        while table.state.status:
            table.act(table.actor, "check_call")

    def next_hand(self, sid, table):
        self.finish(table)
        status, view, _ = self.request("POST", "/api/next", {"version": table.version}, sid=sid)
        self.assertEqual(status, 200)
        return view

    def test_create_replaces_solo_and_exposes_exact_shared_contract(self):
        sid, solo = self.solo()
        old_id = server.SESSIONS[sid].table_id
        old = server.TABLES[old_id]
        status, view, _ = self.request("POST", "/api/tables", {"name": "  Host  "}, sid=sid)
        self.assertEqual(status, 200)
        table_id = server.SESSIONS[sid].table_id
        self.assertNotEqual(table_id, old_id)
        self.assertNotIn(old_id, server.TABLES)
        self.assertTrue(old.closed)
        self.assertEqual(set(view), set(solo))
        self.assertEqual(set(view["table"]), {"shared", "invite"})
        self.assertEqual(solo["table"], {"shared": False, "invite": None})
        self.assertTrue(view["table"]["shared"])
        self.assertRegex(view["table"]["invite"], r"^[A-Za-z0-9_-]{11}$")
        self.assertNotEqual(view["table"]["invite"], table_id)
        self.assertGreater(view["version"], solo["version"])
        self.assertEqual(view["you"], 0)
        self.assertEqual(view["players"][0]["name"], "Host")
        self.assertFalse(view["pending"])
        self.assertIsNone(view["turn_remaining"])
        self.assertIsNone(view["next_hand_in"])
        self.assertEqual(server.TABLES[table_id].turn_seconds, 30)
        self.assertEqual([p["kind"] for p in view["players"]], ["human"] + ["bot"] * 5)
        self.assertTrue(all(p["away"] is False and p["leaving"] is False for p in view["players"]))

    def test_pending_cookie_resumes_without_bot_cards_actions_or_history(self):
        host, initial, table = self.shared()
        guest, pending = self.join(initial["table"]["invite"], "  Friend  ")
        self.assertEqual(pending["you"], 1)
        self.assertTrue(pending["pending"])
        self.assertEqual(pending["players"][1]["kind"], "bot")
        self.assertTrue(all(not p["cards"] for p in pending["players"]))
        self.assertFalse(any(pending["legal"].values()))
        self.assertEqual(self.request("POST", "/api/session", sid=guest)[1], pending)
        again = self.request("POST", "/api/join", {"code": initial["table"]["invite"], "name": "Other"}, sid=guest)
        self.assertEqual(again[0], 200)
        self.assertEqual(again[1], pending)
        self.assertEqual(len(server.SESSIONS), 2)
        while table.actor != 1:
            table.act(table.actor, "check_call")
        pending_turn = self.request("GET", "/api/state", sid=guest)[1]
        self.assertFalse(any(pending_turn["legal"].values()))
        self.assertEqual(pending_turn["players"][1]["cards"], [])
        self.assertEqual(self.request("POST", "/api/action", {"version": table.version, "action": "check_call"}, sid=guest)[0], 409)
        self.finish(table)
        self.assertEqual(self.request("GET", "/api/history", sid=guest)[1], {"hands": []})
        self.assertEqual(self.request("GET", "/api/hand/1", sid=guest)[0], 404)
        self.next_hand(host, table)
        status, seated, _ = self.request("GET", "/api/state", sid=guest)
        self.assertEqual(status, 200)
        self.assertFalse(seated["pending"])
        self.assertEqual(seated["players"][1]["name"], "Friend")
        self.assertEqual(seated["players"][1]["kind"], "human")
        self.assertEqual(seated["players"][1]["stack"] + seated["players"][1]["bet"], 200)
        self.assertEqual(seated["session_net"], 0)
        self.assertEqual(seated["players"][1]["cards"], table.holes[1])
        self.assertTrue(all(not p["cards"] for p in seated["players"] if p["id"] != 1))
        self.assertEqual(self.request("GET", "/api/hand/1", sid=guest)[0], 404)

    def test_two_cookies_play_same_hand_with_private_replays(self):
        host, initial, table = self.shared()
        guest, _ = self.join(initial["table"]["invite"])
        self.next_hand(host, table)
        hole = {seat: table.holes[seat].copy() for seat in (0, 1)}
        acted = set()
        while table.state.status:
            seat = table.actor
            if seat in (0, 1):
                sid = host if seat == 0 else guest
                status, view, _ = self.request("POST", "/api/action", {"version": table.version, "action": "check_call"}, sid=sid)
                self.assertEqual(status, 200)
                self.assertEqual(view["you"], seat)
                acted.add(seat)
            else:
                table.act(seat, "check_call")
        self.assertEqual(acted, {0, 1})
        for sid, seat in ((host, 0), (guest, 1)):
            status, replay, _ = self.request("GET", "/api/hand/2", sid=sid)
            self.assertEqual(status, 200)
            first = replay["frames"][0]
            self.assertEqual(first["players"][seat]["cards"], hole[seat])
            self.assertTrue(all(not p["cards"] for p in first["players"] if p["id"] != seat))
        self.assertEqual([h["hand_id"] for h in self.request("GET", "/api/history", sid=guest)[1]["hands"]], [2])

    def test_name_validation_and_pending_duplicate_names(self):
        host, initial, table = self.shared()
        code = initial["table"]["invite"]
        for name in (None, 123, [], "", "   ", "abcdefghijklm", "A\x00B", "A\nB", "A\x7fB", "A\x85B"):
            with self.subTest(name=name):
                status, body, headers = self.request("POST", "/api/join", {"code": code, "name": name})
                self.assertEqual(status, 400)
                self.assertIn("error", body)
                self.assertNotIn("Set-Cookie", headers)
                self.assertEqual(len(server.SESSIONS), 1)
        names = ("  abcdefghijkl  ", "abcdefghijkl", "abcdefghijkl")
        guests = [self.join(code, name)[0] for name in names]
        self.next_hand(host, table)
        for seat, sid in enumerate(guests, 1):
            view = self.request("GET", "/api/state", sid=sid)[1]
            expected = "abcdefghijkl" + (f" {seat}" if seat > 1 else "")
            self.assertEqual(view["players"][seat]["name"], expected)

    def test_creator_name_is_required_and_validated_before_replacing_binding(self):
        sid, solo = self.solo()
        binding = server.SESSIONS[sid]
        for name in (None, 123, [], "", "   ", "abcdefghijklm", "A\x00B", "A\nB", "A\x7fB", "A\x85B"):
            for cookie in (None, sid):
                with self.subTest(name=name, cookie=cookie):
                    status, _, headers = self.request("POST", "/api/tables", {"name": name}, sid=cookie)
                    self.assertEqual(status, 400)
                    self.assertNotIn("Set-Cookie", headers)
                    self.assertEqual(len(server.SESSIONS), 1)
                    self.assertEqual(len(server.TABLES), 1)
                    self.assertIs(server.SESSIONS[sid], binding)
                    self.assertEqual(self.request("GET", "/api/state", sid=sid)[1], solo)
        status, shared, _ = self.request("POST", "/api/tables", {"name": "  abcdefghijkl  "}, sid=sid)
        self.assertEqual(status, 200)
        self.assertEqual(shared["players"][0]["name"], "abcdefghijkl")
        guest, _ = self.join(shared["table"]["invite"], "abcdefghijkl")
        table = server.TABLES[server.SESSIONS[sid].table_id]
        self.next_hand(sid, table)
        self.assertEqual(self.request("GET", "/api/state", sid=guest)[1]["players"][1]["name"], "abcdefghijkl 2")

    def test_metadata_changes_do_not_invalidate_current_decision(self):
        host, shared, table = self.shared()
        guest, _ = self.join(shared["table"]["invite"])
        self.next_hand(host, table)
        previous_decision = table.version
        while table.actor != 0:
            table.act(table.actor, "check_call")
        version, deadline = table.version, table.next_due()
        self.assertEqual(self.request("POST", "/api/back", sid=guest)[0], 200)
        self.join(shared["table"]["invite"], "Third")
        self.assertEqual(self.request("POST", "/api/leave", sid=guest)[0], 200)
        self.assertGreater(table.version, version)
        self.assertEqual(table.next_due(), deadline)
        for invalid in (previous_decision, table.version + 1, True, "1", None):
            before = table.view(0)
            expected_status = 409 if type(invalid) is int else 400
            self.assertEqual(self.request("POST", "/api/action", {"version": invalid, "action": "check_call"}, sid=host)[0], expected_status)
            self.assertEqual(table.view(0), before)
        payload = {"version": version, "action": "check_call"}
        self.assertEqual(self.request("POST", "/api/action", payload, sid=host)[0], 200)
        self.assertEqual(self.request("POST", "/api/action", payload, sid=host)[0], 409)

    def test_unknown_code_full_table_and_idempotent_join_at_capacity(self):
        host, initial, table = self.shared()
        code = initial["table"]["invite"]
        self.assertEqual(self.request("POST", "/api/join", {"code": "unknown-code", "name": "Guest"})[0], 404)
        guests = [self.join(code, f"Guest {seat}") for seat in range(1, 6)]
        self.assertEqual([view["you"] for _, view in guests], list(range(1, 6)))
        status, body, headers = self.request("POST", "/api/join", {"code": code, "name": "Extra"})
        self.assertEqual((status, body["code"]), (409, "table_full"))
        self.assertEqual(set(body), {"code", "error"})
        self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(len(server.SESSIONS), 6)
        sid, old = guests[0]
        status, current, _ = self.request("POST", "/api/join", {"code": code, "name": "Guest 1"}, sid=sid)
        self.assertEqual(status, 200)
        self.assertEqual(current["you"], old["you"])
        self.assertEqual(len(server.SESSIONS), 6)
        self.assertEqual(len(server.TABLES), 1)

    def test_join_rebinds_existing_cookie_without_version_rollback(self):
        _, shared, target = self.shared()
        guest, _ = self.solo()
        old_id = server.SESSIONS[guest].table_id
        old = server.TABLES[old_id]
        for _ in range(2):
            self.finish(old)
            old.new_hand()
        previous_version = old.version
        _, view = self.join(shared["table"]["invite"], sid=guest)
        self.assertGreater(view["version"], previous_version)
        self.assertNotIn(old_id, server.TABLES)
        self.assertTrue(old.closed)
        self.assertEqual(server.SESSIONS[guest].seat, 1)
        self.assertIs(server.TABLES[server.SESSIONS[guest].table_id], target)

    def test_pending_leave_releases_reservation_and_active_leave_restores_bot(self):
        host, initial, table = self.shared()
        code = initial["table"]["invite"]
        guest, _ = self.join(code)
        status, solo, _ = self.request("POST", "/api/leave", sid=guest)
        self.assertEqual(status, 200)
        self.assertEqual(solo["table"], {"shared": False, "invite": None})
        self.assertEqual(solo["you"], 0)
        self.assertFalse(solo["pending"])
        _, pending = self.join(code, "Returning", sid=guest)
        self.assertEqual(pending["you"], 1)
        self.next_hand(host, table)
        version = table.version
        status, solo, _ = self.request("POST", "/api/leave", sid=guest)
        self.assertEqual(status, 200)
        self.assertGreater(solo["version"], version)
        self.assertTrue(self.request("GET", "/api/state", sid=host)[1]["players"][1]["leaving"])
        self.assertEqual(self.request("GET", "/api/hand/1", sid=guest)[0], 404)
        self.next_hand(host, table)
        public = self.request("GET", "/api/state", sid=host)[1]
        self.assertEqual(public["players"][1]["kind"], "bot")
        self.assertEqual(public["players"][1]["name"], "阿岚")
        self.assertFalse(public["players"][1]["leaving"])
        self.assertEqual(public["players"][1]["stack"] + public["players"][1]["bet"], 200)
        self.assertEqual(table.session_net[1], 0)
        self.assertTrue(all(counts == [0, 0] for counts in table.opponent_stats.snapshot()[1].values()))

    def test_back_clears_away_after_two_timeouts_and_notifies_pollers(self):
        host, _, table = self.shared()
        for timeout in range(2):
            while table.actor != 0:
                table.act(table.actor, "check_call")
            state = self.request("GET", "/api/state", sid=host)[1]
            self.assertEqual(state["turn_remaining"], 30)
            self.now += 30
            self.assertTrue(table.run_due())
            if timeout == 0:
                self.next_hand(host, table)
        self.assertTrue(self.request("GET", "/api/state", sid=host)[1]["players"][0]["away"])
        before = table.version
        status, view, _ = self.request("POST", "/api/back", sid=host)
        self.assertEqual(status, 200)
        self.assertFalse(view["players"][0]["away"])
        self.assertGreater(view["version"], before)

    def test_invite_static_route_keeps_source_and_traversal_private(self):
        _, initial, _ = self.shared()
        code = initial["table"]["invite"]
        status, html, headers = self.request("GET", f"/t/{code}")
        self.assertEqual(status, 200)
        self.assertEqual(html, self.request("GET", "/")[1])
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        for path in ("/t/", "/t/code/extra", "/t/../poker_lab/server.py", "/t/%2e%2e%2fREADME.md", "/poker_lab/server.py", "/.private/USER_CONTEXT.md"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)

    def test_concurrent_joins_reserve_distinct_lowest_bot_seats(self):
        _, initial, _ = self.shared()
        code = initial["table"]["invite"]
        start = threading.Barrier(3)
        results, errors = [], []

        def join(name):
            try:
                start.wait(timeout=2)
                results.append(self.request("POST", "/api/join", {"code": code, "name": name}))
            except Exception as exc:
                errors.append(exc)

        workers = [threading.Thread(target=join, args=(name,)) for name in ("First", "Second")]
        for worker in workers:
            worker.start()
        start.wait(timeout=2)
        for worker in workers:
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual([status for status, _, _ in results], [200, 200])
        self.assertEqual(sorted(view["you"] for _, view, _ in results), [1, 2])
        cookies = [SimpleCookie(headers["Set-Cookie"])["poker_session"].value for _, _, headers in results]
        self.assertEqual(len(set(cookies)), 2)
        self.assertEqual(len(server.SESSIONS), 3)

    def test_failed_join_preserves_existing_binding(self):
        _, initial, _ = self.shared()
        code = initial["table"]["invite"]
        for seat in range(1, 6):
            self.join(code, f"Guest {seat}")
        guest, solo = self.solo()
        binding = server.SESSIONS[guest]
        for requested_code, expected_status in (("missing", 404), (code, 409)):
            status, _, headers = self.request("POST", "/api/join", {"code": requested_code, "name": "Visitor"}, sid=guest)
            self.assertEqual(status, expected_status)
            self.assertNotIn("Set-Cookie", headers)
            self.assertIs(server.SESSIONS[guest], binding)
            self.assertEqual(self.request("GET", "/api/state", sid=guest)[1], solo)

    def test_reset_and_new_table_release_pending_reservations(self):
        for endpoint in ("/api/reset", "/api/tables"):
            with self.subTest(endpoint=endpoint):
                host, initial, table = self.shared()
                guest, pending = self.join(initial["table"]["invite"])
                status, replacement, _ = self.request("POST", endpoint, {"name": "New host"}, sid=guest)
                self.assertEqual(status, 200)
                self.assertGreater(replacement["version"], pending["version"])
                self.assertIs(server.TABLES[server.SESSIONS[host].table_id], table)
                _, next_guest = self.join(initial["table"]["invite"], "Next")
                self.assertEqual(next_guest["you"], 1)

    def test_reset_active_guest_marks_leaving_in_retained_shared_table(self):
        host, initial, table = self.shared()
        guest, _ = self.join(initial["table"]["invite"])
        self.next_hand(host, table)
        status, solo, _ = self.request("POST", "/api/reset", sid=guest)
        self.assertEqual(status, 200)
        self.assertFalse(solo["table"]["shared"])
        view = self.request("GET", "/api/state", sid=host)[1]
        self.assertTrue(view["players"][1]["leaving"])
        self.next_hand(host, table)
        self.assertEqual(table.players[1]["kind"], "bot")

    def test_expired_pending_guest_releases_seat_without_dropping_table(self):
        host, initial, table = self.shared()
        guest, _ = self.join(initial["table"]["invite"])
        self.now += 7199
        self.assertEqual(self.request("GET", "/api/state", sid=host)[0], 200)
        self.now += 2
        self.request("GET", "/healthz")
        self.assertNotIn(guest, server.SESSIONS)
        self.assertFalse(table.closed)
        _, replacement = self.join(initial["table"]["invite"], "Replacement")
        self.assertEqual(replacement["you"], 1)

    def test_lru_evicted_pending_guest_releases_seat(self):
        host, initial, table = self.shared()
        guest, _ = self.join(initial["table"]["invite"])
        self.request("GET", "/api/state", sid=host)
        with patch.object(server, "MAX_SESSIONS", 2):
            self.solo()
        self.assertNotIn(guest, server.SESSIONS)
        self.assertFalse(table.closed)
        _, replacement = self.join(initial["table"]["invite"], "Replacement")
        self.assertEqual(replacement["you"], 1)

    def test_join_wakes_old_pending_poll_onto_new_binding(self):
        _, shared, target = self.shared()
        guest, old_view = self.solo()
        old = server.TABLES[server.SESSIONS[guest].table_id]
        entered = threading.Event()
        result, errors = [], []
        original_wait = old.changed.wait

        def wait(timeout):
            entered.set()
            return original_wait(timeout)

        def poll():
            try:
                result.append(self.request("GET", f"/api/state?after={old_view['version']}", sid=guest))
            except Exception as exc:
                errors.append(exc)

        with patch.object(old.changed, "wait", side_effect=wait):
            worker = threading.Thread(target=poll, daemon=True)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                self.join(shared["table"]["invite"], sid=guest)
                worker.join(2)
                self.assertFalse(worker.is_alive())
            finally:
                if worker.is_alive():
                    old.close()
                    target.close()
                    worker.join(2)
        self.assertEqual(errors, [])
        self.assertEqual(result[0][0], 200)
        self.assertEqual(result[0][1]["table"], shared["table"])
        self.assertEqual(result[0][1]["you"], 1)
        self.assertTrue(result[0][1]["pending"])
        self.assertTrue(all(not player["cards"] for player in result[0][1]["players"]))


if __name__ == "__main__":
    unittest.main()
