"""Invite-seat ownership, private views and clock-driven shared-table lifecycle."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from poker_lab.game import AUTO_DEAL_SECONDS, PLAYERS, Table


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class InviteTableTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()

    def table(self, **kwargs):
        return Table(seed=9, clock=self.clock, shared=True, invite="test-invite", **kwargs)

    def finish(self, table):
        while table.state.status:
            table.act(table.actor, "check_call")

    def to_actor(self, table, seat):
        while table.actor != seat:
            self.assertTrue(table.state.status)
            table.act(table.actor, "check_call")

    def timeout(self, table):
        self.clock.now = table.next_due()
        self.assertTrue(table.run_due())

    def join_and_deal(self, table, name="Guest"):
        seat = table.join(name)
        self.finish(table)
        table.new_hand()
        return seat

    def test_pending_seat_is_public_and_owns_no_old_hand(self):
        table = self.table()
        self.finish(table)
        previous = deepcopy(table.hand(1, 1))
        table.new_hand()
        bot = deepcopy(table.players[1])
        deadline = table.next_due()
        seat = table.join("Guest")
        self.assertEqual(seat, 1)
        self.assertEqual(table.players[seat], bot)
        self.assertEqual(table.next_due(), deadline)
        self.assertTrue(table.has_human(seat))
        view = table.view(seat)
        self.assertEqual(view["table"], {"shared": True, "invite": "test-invite"})
        self.assertTrue(view["pending"])
        self.assertEqual(view["session_net"], 0)
        self.assertEqual(view["players"][seat]["cards"], [])
        self.assertFalse(any(view["legal"].values()))
        self.assertEqual(table.history(seat), [])
        self.assertIsNone(table.hand(1, seat))
        self.to_actor(table, seat)
        self.assertEqual(table.view(seat)["players"][seat]["cards"], [])
        self.assertFalse(any(table.view(seat)["legal"].values()))
        self.finish(table)
        # Public showdown reveals are allowed, but do not unlock a bot's replay.
        self.assertEqual(table.view(seat)["players"][seat]["cards"], table.shown.get(seat, []))
        self.assertIsNone(table.hand(2, seat))
        self.assertEqual(table.history(seat), [])
        table.new_hand()
        self.assertFalse(table.view(seat)["pending"])
        self.assertEqual(table.players[seat]["name"], "Guest")
        self.assertEqual(table.players[seat]["kind"], "human")
        self.assertEqual(table.start_stacks[seat], 200)
        self.assertEqual(table.session_net[seat], 0)
        self.assertEqual(table.view(seat)["players"][seat]["cards"], table.holes[seat])
        self.assertIsNone(table.hand(1, seat))
        self.assertIsNone(table.hand(2, seat))
        self.finish(table)
        self.assertEqual([h["hand_id"] for h in table.history(seat)], [3])
        replay = table.hand(3, seat)
        for frame in replay["frames"]:
            self.assertEqual(frame["players"][seat]["cards"], table.holes[seat])
        self.assertEqual([h["hand_id"] for h in table.history(0)], [3, 2, 1])
        self.assertEqual(previous["frames"][0]["players"][1]["cards"], table.hands[0]["holes"][1])

    def test_pending_names_are_unique_and_consume_all_available_seats(self):
        table = self.table()
        for seat in range(1, 6):
            self.assertEqual(table.join("你"), seat)
            self.assertEqual(table.pending[seat]["name"], f"你 {seat + 1}")
        with self.assertRaisesRegex(ValueError, "这张桌已经坐满了。"):
            table.join("another")
        table.leave(2)
        self.assertFalse(table.has_human(2))
        self.assertEqual(table.join("你"), 2)
        self.assertEqual(table.pending[2]["name"], "你 3")

    def test_join_after_hand_end_does_not_reveal_bot_or_delay_next_deal(self):
        table = self.table()
        # Folding all but one leaves everyone's cards unrevealed.
        while table.state.status:
            table.act(table.actor, "fold")
        deadline = table.next_due()
        self.clock.now += 2
        seat = table.join("Later")
        self.assertEqual(table.next_due(), deadline)
        self.assertTrue(table.view(seat)["pending"])
        self.assertEqual(table.view(seat)["players"][seat]["cards"], [])
        self.assertEqual(table.view(seat)["next_hand_in"], 3)
        self.assertIsNone(table.hand(1, seat))

    def test_leaving_player_checks_or_folds_then_returns_to_original_bot(self):
        for check in (False, True):
            with self.subTest(check=check):
                table = self.table()
                seat = self.join_and_deal(table)
                self.to_actor(table, seat)
                if not check:
                    # Seat 1 is the small blind in hand 2, facing the big blind.
                    self.assertFalse(table.legal()["can_check"])
                else:
                    self.to_actor(table, 2)
                    table.act(2, "check_call")
                    self.to_actor(table, seat)
                    self.assertTrue(table.legal()["can_check"])
                table.leave(seat)
                self.assertTrue(table.players[seat]["leaving"])
                self.assertFalse(table.has_human(seat))
                self.assertEqual(table.next_due(), self.clock.now)
                self.assertTrue(table.run_due())
                self.assertEqual(table.actions[-1]["player"], seat)
                self.assertEqual(table.actions[-1]["kind"], "check_call" if check else "fold")
                self.finish(table)
                table.new_hand()
                self.assertEqual(table.start_stacks[seat], 200)
                self.assertEqual(table.players[seat]["name"], PLAYERS[seat]["name"])
                self.assertEqual(table.players[seat]["style"], PLAYERS[seat]["style"])
                self.assertFalse(table.players[seat]["leaving"])
                self.assertFalse(table.players[seat]["away"])
                self.assertEqual(table.history(seat), [])

    def test_leaving_other_seat_does_not_reset_current_turn_deadline(self):
        table = self.table()
        seat = self.join_and_deal(table)
        self.to_actor(table, 0)
        deadline = table.next_due()
        self.clock.now += 8
        table.leave(seat)
        self.assertEqual(table.next_due(), deadline)
        self.assertEqual(table.view(0)["turn_remaining"], 22)
        self.assertEqual(table.join("Replacement"), 2)  # Leaving human still occupies seat 1.

    def test_two_timeouts_mark_away_and_next_turn_is_immediate(self):
        players = deepcopy(PLAYERS)
        for player in players:
            player["kind"] = "human"
        table = self.table(players=players)
        self.to_actor(table, 1)  # Big blind can check without folding out.
        self.assertEqual(table.view(0)["turn_remaining"], 30)
        self.timeout(table)
        self.assertEqual(table.timeouts[1], 1)
        self.assertFalse(table.players[1]["away"])
        self.to_actor(table, 1)
        self.timeout(table)
        self.assertEqual(table.timeouts[1], 2)
        self.assertTrue(table.players[1]["away"])
        self.to_actor(table, 1)
        self.assertEqual(table.next_due(), self.clock.now)
        self.assertEqual(table.view(0)["turn_remaining"], 0)
        self.assertTrue(table.run_due())
        self.assertTrue(table.players[1]["away"])
        self.assertEqual(table.actions[-1]["kind"], "check_call")
        self.to_actor(table, 1)
        with self.assertRaises(ValueError):
            table.act(1, "raise", 0)
        self.assertTrue(table.players[1]["away"])
        table.act(1, "check_call")
        self.assertFalse(table.players[1]["away"])
        self.assertEqual(table.timeouts[1], 0)

    def test_manual_action_breaks_timeout_streak_and_back_preserves_other_timer(self):
        players = deepcopy(PLAYERS)
        for player in players:
            player["kind"] = "human"
        table = self.table(players=players)
        self.to_actor(table, 1)
        self.timeout(table)
        self.to_actor(table, 1)
        table.act(1, "check_call")
        self.assertEqual(table.timeouts[1], 0)
        self.to_actor(table, 1)
        self.timeout(table)
        self.assertFalse(table.players[1]["away"])
        table.players[1]["away"] = True
        deadline = table.next_due()
        self.clock.now += 4
        table.back(1)
        self.assertEqual(table.next_due(), deadline)
        self.assertFalse(table.players[1]["away"])
        self.assertEqual(table.timeouts[1], 0)
        self.to_actor(table, 1)
        table.players[1]["away"] = True
        with table.changed:
            table._schedule_next()
        self.assertEqual(table.next_due(), self.clock.now)
        table.back(1)
        self.assertEqual(table.next_due(), self.clock.now + 30)
        deadline = table.next_due()
        self.clock.now += 5
        table.back(1)
        self.assertEqual(table.next_due(), deadline)

    def test_automatic_deal_is_only_for_shared_tables_after_five_seconds(self):
        for shared in (True, False):
            table = Table(seed=1, clock=self.clock, shared=shared, invite="test")
            self.finish(table)
            self.assertIsNone(table.view(0)["turn_remaining"])
            if shared:
                self.assertEqual(table.view(0)["next_hand_in"], AUTO_DEAL_SECONDS)
                self.clock.now += AUTO_DEAL_SECONDS - .01
                self.assertFalse(table.run_due())
                self.clock.now += .01
                self.assertTrue(table.run_due())
                self.assertEqual(table.hand_id, 2)
                self.assertIsNone(table.view(0)["next_hand_in"])
            else:
                self.assertIsNone(table.next_due())
                self.assertIsNone(table.view(0)["next_hand_in"])
                self.assertEqual(table.view(0)["table"], {"shared": False, "invite": None})
                self.clock.now += 500
                self.assertFalse(table.run_due())
                self.assertEqual(table.hand_id, 1)

    def test_each_occupant_change_resets_only_its_reads_net_and_history(self):
        table = self.table()
        self.finish(table)
        seat = table.join("First")
        before = table.opponent_stats.snapshot()
        self.assertTrue(any(count[1] for count in before[seat].values()))
        table.new_hand()
        self.assertTrue(all(count == [0, 0] for count in table.opponent_stats.counts[seat].values()))
        self.assertEqual(table.opponent_stats.counts[0], before[0])
        self.finish(table)
        self.assertEqual(len(table.history(seat)), 1)
        table.leave(seat)
        table.new_hand()
        self.assertEqual(table.session_net[seat], 0)
        self.assertEqual(table.history(seat), [])
        self.assertTrue(all(count == [0, 0] for count in table.opponent_stats.counts[seat].values()))
        self.assertEqual(table.join("Second"), seat)
        self.finish(table)
        self.assertTrue(any(count[1] for count in table.opponent_stats.counts[seat].values()))
        table.new_hand()
        self.assertEqual(table.players[seat]["name"], "Second")
        self.assertEqual(table.session_net[seat], 0)
        self.assertEqual(table.history(seat), [])
        self.assertTrue(all(count == [0, 0] for count in table.opponent_stats.counts[seat].values()))
        for hand_id in (1, 2, 3):
            self.assertIsNone(table.hand(hand_id, seat))
            self.assertIsNotNone(table.hand(hand_id, 0))

    def test_pending_bot_still_acts_and_a_join_invalidates_inflight_policy(self):
        table = self.table()
        self.clock.now = table.next_due()

        def think(*args):
            table.join("Guest")
            return {"action": "check_call"}

        with patch("poker_lab.bots.choose_action", side_effect=think):
            self.assertFalse(table.run_due())
        self.assertEqual(table.actions, [])
        with patch("poker_lab.bots.choose_action", return_value={"action": "check_call"}):
            self.assertTrue(table.run_due())
            self.to_actor(table, 1)
            self.clock.now = table.next_due()
            self.assertTrue(table.run_due())
        self.assertEqual(table.actions[-1]["player"], 1)
        self.assertEqual(table.players[1]["kind"], "bot")
        self.assertTrue(table.view(1)["pending"])
        self.assertEqual(table.view(1)["players"][1]["cards"], [])

    def test_timeout_streak_survives_deals_and_owner_seat_gets_a_bot(self):
        table = self.table()
        for hand in range(2):
            self.to_actor(table, 0)
            self.timeout(table)
            self.assertIn(0, table.folded)
            self.assertEqual(table.timeouts[0], hand + 1)
            self.assertEqual(table.players[0]["away"], hand == 1)
            self.finish(table)
            table.new_hand()
        self.to_actor(table, 0)
        self.assertEqual(table.next_due(), self.clock.now)
        table.leave(0)
        self.assertTrue(table.run_due())
        self.finish(table)
        table.new_hand()
        self.assertEqual(table.players[0]["kind"], "bot")
        self.assertEqual(table.players[0]["name"], "阿禾")
        self.assertEqual(table.players[0]["style"], "tight")
        self.assertFalse(table.players[0]["away"])
        self.assertFalse(table.players[0]["leaving"])
        self.assertEqual(table.start_stacks[0], 200)
        self.assertEqual(table.join("New owner"), 0)


if __name__ == "__main__":
    unittest.main()
