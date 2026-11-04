"""Viewer isolation and deterministic server-side turn scheduling."""
from copy import deepcopy
import threading
import unittest
from unittest.mock import patch

from poker_lab.game import BOT_DELAY, FAST_BOT_DELAY, PLAYERS, Table


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def seats(*humans):
    players = deepcopy(PLAYERS)
    for seat, player in enumerate(players):
        player["kind"] = "human" if seat in humans else "bot"
        player["style"] = "" if seat in humans else player["style"] or "tight"
    return players


class ViewerTests(unittest.TestCase):
    def test_two_humans_have_private_views_replays_nets_and_notes(self):
        players = seats(0, 3)
        players[3]["name"] = "Guest"
        table = Table(seed=5, players=players)
        players[3]["name"] = "changed outside the table"
        original_holes = deepcopy(table.holes)
        for actor, action, amount in (
            (2, "check_call", None), (3, "check_call", None), (4, "fold", None),
            (5, "fold", None), (0, "raise", 6), (1, "check_call", None),
            (2, "fold", None), (3, "fold", None), (0, "check_call", None),
            (1, "raise", 2), (0, "fold", None),
        ):
            for viewer in (0, 3):
                view = table.view(viewer)
                self.assertEqual(view["you"], viewer)
                self.assertEqual(view["players"][3]["name"], "Guest")
                self.assertEqual(view["players"][viewer]["kind"], "human")
                for player in view["players"]:
                    self.assertEqual(player["cards"], original_holes[viewer] if player["id"] == viewer else [])
                self.assertEqual(view["legal"]["call_amount"],
                                 table.legal()["call_amount"] if viewer == actor else 0)
                if viewer != actor:
                    self.assertFalse(any(view["legal"].values()))
            table.act(actor, action, amount)
        self.assertFalse(table.state.status)
        self.assertEqual(table.shown, {})
        self.assertEqual(table.session_net[0], -6)
        self.assertEqual(table.session_net[3], -2)
        stored = deepcopy(table.hands)
        for frame in table.frames:
            self.assertTrue(all(not player["cards"] for player in frame["players"]))
        for viewer in (0, 3):
            replay = table.hand(1, viewer)
            self.assertEqual(set(replay), {"hand_id", "summary", "net", "board", "frames", "notes"})
            self.assertEqual(replay["net"], table.session_net[viewer])
            self.assertEqual(replay["net"], table.history(viewer)[0]["net"])
            self.assertIn(f"净变化 {replay['net'] / 2:g} BB", replay["notes"][0])
            self.assertEqual(replay["frames"][-1]["session_net"], table.session_net[viewer])
            for frame in replay["frames"]:
                self.assertEqual(frame["you"], viewer)
                for player in frame["players"]:
                    self.assertEqual(player["cards"], original_holes[viewer] if player["id"] == viewer else [])
                if frame["current_actor"] != viewer:
                    self.assertFalse(any(frame["legal"].values()))
            replay["frames"][0]["players"][viewer]["cards"].clear()
            replay["notes"].clear()
        self.assertEqual(table.hands, stored)
        before = [table.hand(1, viewer) for viewer in (0, 3)]
        table.new_hand()
        self.assertEqual(before, [table.hand(1, viewer) for viewer in (0, 3)])

    def test_rotated_seats_showdown_and_session_totals(self):
        for dealer in range(6):
            table = Table(seed=dealer, dealer=dealer, players=seats(2, 5))
            original = deepcopy(table.holes)
            while table.state.status:
                table.act(table.actor, "check_call")
            for viewer in (2, 5):
                replay = table.hand(1, viewer)
                self.assertEqual(replay["frames"][0]["players"][viewer]["cards"], original[viewer])
                for player in replay["frames"][0]["players"]:
                    if player["id"] != viewer:
                        self.assertEqual(player["cards"], [])
                for player in replay["frames"][-1]["players"]:
                    expected = original[viewer] if player["id"] == viewer else table.shown.get(player["id"], [])
                    self.assertEqual(player["cards"], expected)
                self.assertEqual(replay["net"], table.state.payoffs[table.indices[viewer]])
                self.assertEqual(table.view(viewer)["session_net"], replay["net"])
            self.assertEqual(sum(table.session_net), 0)
            nets = table.session_net.copy()
            table.new_hand()
            self.assertEqual(table.session_net, nets)


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()

    def table(self, **kwargs):
        return Table(seed=3, clock=self.clock, **kwargs)

    def test_bot_deadline_is_stable_and_one_action_runs_per_due_time(self):
        table = self.table()
        self.assertEqual(table.next_due(), BOT_DELAY)
        self.clock.now = BOT_DELAY - 0.01
        with patch("poker_lab.bots.choose_action", return_value={"action": "check_call"}) as policy:
            self.assertFalse(table.run_due())
            self.assertEqual(table.next_due(), BOT_DELAY)
            policy.assert_not_called()
            self.clock.now = BOT_DELAY
            version = table.version
            self.assertTrue(table.run_due())
            self.assertEqual(table.version, version + 1)
            self.assertEqual(table.next_due(), BOT_DELAY * 2)
            self.assertFalse(table.run_due())
            policy.assert_called_once()

    def test_scheduled_bot_actions_match_direct_policy_and_rng(self):
        from poker_lab.bots import choose_action
        scheduled = self.table(players=seats())
        direct = self.table(players=seats())
        for _ in range(8):
            if not direct.state.status:
                break
            seat = direct.actor
            decision = choose_action(direct.observation(seat), direct.players[seat]["style"], direct.bot_rngs[seat])
            direct.act(seat, decision["action"], decision.get("amount"))
            self.clock.now = scheduled.next_due()
            self.assertTrue(scheduled.run_due())
            self.assertEqual(scheduled.view(0), direct.view(0))
            self.assertEqual(scheduled.bot_rngs[seat].getstate(), direct.bot_rngs[seat].getstate())

    def test_folded_human_accelerates_bots_and_completed_hand_stops(self):
        table = self.table()
        for seat in (2, 3, 4, 5):
            table.act(seat, "fold")
        self.assertIsNone(table.next_due())
        table.act(0, "check_call")
        table.act(1, "check_call")
        table.act(0, "check_call")
        table.act(1, "raise", 2)
        table.act(0, "fold")
        self.assertIsNone(table.next_due())
        # A separate multiway hand leaves several bot decisions after the human folds.
        table = self.table()
        for seat in (2, 3, 4, 5):
            table.act(seat, "check_call")
        table.act(0, "fold")
        self.assertEqual(table.next_due(), FAST_BOT_DELAY)
        with patch("poker_lab.bots.choose_action", return_value={"action": "check_call"}):
            self.clock.now = FAST_BOT_DELAY
            self.assertTrue(table.run_due())
            self.assertEqual(table.next_due(), FAST_BOT_DELAY * 2)

    def test_roles_support_bot_seat_zero_and_no_human_table(self):
        table = self.table(players=seats(2))
        self.assertIsNone(table.next_due())
        table.act(2, "fold")
        self.assertEqual(table.next_due(), FAST_BOT_DELAY)
        table = self.table(players=seats())
        with patch("poker_lab.bots.choose_action", return_value={"action": "fold"}):
            for _ in range(5):
                self.clock.now = table.next_due()
                self.assertTrue(table.run_due())
        self.assertFalse(table.state.status)
        self.assertIsNone(table.next_due())
        self.assertIn(0, [a["player"] for a in table.actions])
        self.assertEqual(table.hand_id, 1)

    def test_all_in_human_still_uses_normal_bot_pace(self):
        table = self.table(stacks=[2, 200, 200, 200, 200, 200])
        table.act(2, "check_call")
        for seat in (3, 4, 5):
            table.act(seat, "fold")
        table.act(0, "check_call")
        table.act(1, "check_call")
        self.assertEqual(table.observation(table.actor)["all_in"], [0])
        self.assertEqual(table.next_due(), BOT_DELAY)

    def test_human_timer_folds_facing_a_bet_and_checks_when_free(self):
        table = self.table(players=seats(*range(6)), turn_seconds=10)
        self.clock.now = 9
        self.assertFalse(table.run_due())
        self.clock.now = 10
        self.assertTrue(table.run_due())
        self.assertEqual(table.actions[-1]["kind"], "fold")
        self.assertEqual(table.actions[-1]["player"], 2)
        self.assertEqual(table.next_due(), 20)
        for seat in (3, 4, 5, 0):
            table.act(seat, "check_call")
        self.assertTrue(table.legal()["can_check"])
        self.clock.now = 20
        self.assertTrue(table.run_due())
        self.assertEqual(table.actions[-1]["player"], 1)
        self.assertEqual(table.actions[-1]["kind"], "check_call")
        self.assertEqual(table.actions[-1]["amount"], 0)

    def test_thinking_releases_table_lock_and_stale_result_preserves_rng(self):
        table = self.table()
        self.clock.now = BOT_DELAY
        entered, release = threading.Event(), threading.Event()
        result, errors = [], []
        rng_before = table.bot_rngs[2].getstate()

        def think(observation, style, rng):
            rng.random()
            entered.set()
            if not release.wait(2):
                raise AssertionError("Test did not release policy")
            return {"action": "fold"}

        def run():
            try:
                result.append(table.run_due())
            except Exception as error:
                errors.append(error)

        with patch("poker_lab.bots.choose_action", side_effect=think):
            worker = threading.Thread(target=run)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(table.lock.acquire(timeout=1))
                try:
                    self.assertFalse(table.run_due())  # The same version is already being computed.
                    table.act(2, "check_call")
                finally:
                    table.lock.release()
            finally:
                release.set()
                worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result, [False])
        self.assertEqual(table.bot_rngs[2].getstate(), rng_before)
        self.assertEqual([a["kind"] for a in table.actions], ["check_call"])

    def test_closed_table_discards_inflight_policy(self):
        table = self.table()
        self.clock.now = BOT_DELAY

        def think(*args):
            table.close()
            return {"action": "fold"}

        with patch("poker_lab.bots.choose_action", side_effect=think):
            self.assertFalse(table.run_due())
        self.assertEqual(table.actions, [])
        self.assertIsNone(table.next_due())
        with self.assertRaises(ValueError):
            table.new_hand()


if __name__ == "__main__":
    unittest.main()
