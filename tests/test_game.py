"""Integration checks for the PokerKit adapter, independent of bot policy code."""
from collections import deque
from copy import deepcopy
import random
import unittest

from pokerkit import Card, Deck, Mode, NoLimitTexasHoldem

from poker_lab.game import AUTOMATIONS, Table


def finish_by_calling(table):
    for _ in range(200):
        if not table.state.status:
            return
        if table.actor is None:
            raise AssertionError("Live hand has no actor after automatic advancement")
        table.act(table.actor, "check_call")
    raise AssertionError("Hand did not finish within 200 actions")


def rigged_table(stacks):
    """Give seats 2/3/4 AA/KK/QQ and a dry board for exact side-pot checks."""
    table = Table(seed=51, stacks=stacks)
    state = NoLimitTexasHoldem.create_state(
        AUTOMATIONS, True, 0, (1, 2), 2, tuple(stacks), 6, mode=Mode.CASH_GAME
    )
    hands = ["5s6s", "JsTs", "AhAd", "KhKd", "QhQd", "8h8d"]
    used = set(Card.parse("".join(hands)))
    # Burn, flop, burn, turn, burn, river.
    runout = list(Card.parse("2h2c3d4h3h7s4c9c"))
    remainder = [c for c in Deck.STANDARD if c not in used and c not in runout]
    state.deck_cards = deque([*Card.parse("".join(hands)), *runout, *remainder])
    for index, cards in enumerate(hands):
        state.deal_hole(cards, index)
    table.state = state
    table.holes = {seat: [repr(c) for c in state.hole_cards[index]]
                   for index, seat in enumerate(table.seats)}
    table.frames = []
    table._record()
    return table


class TableTests(unittest.TestCase):
    def assert_conserved(self, table):
        self.assertEqual(sum(table.state.stacks) + table.state.total_pot_amount,
                         sum(table.start_stacks))

    def assert_unique_cards(self, table):
        cards = [card for hand in table.holes.values() for card in hand]
        cards.extend(table.snapshot()["board"])
        self.assertEqual(len(cards), len(set(cards)))

    def test_six_seat_order_blinds_and_button_rotation(self):
        table = Table(seed=3)
        self.assertEqual(table.dealer, 5)
        self.assertEqual(table.state.bets, [1, 2, 0, 0, 0, 0])
        self.assertEqual(table.actor, 2)
        order = []
        for _ in range(6):
            order.append(table.actor)
            table.act(table.actor, "check_call")
        self.assertEqual(order, [2, 3, 4, 5, 0, 1])
        self.assertEqual(table.snapshot()["street"], "flop")
        self.assertEqual(table.actor, 0)
        finish_by_calling(table)
        closing_stacks = table.stacks.copy()
        table.new_hand()
        self.assertEqual(table.dealer, 0)
        self.assertEqual(table.seats, [1, 2, 3, 4, 5, 0])
        self.assertEqual(table.actor, 3)
        self.assertEqual(table.start_stacks,
                         [200 if value < 2 else value for value in closing_stacks])

    def test_illegal_and_stale_requests_do_not_mutate(self):
        table = Table(seed=4)
        invalid = [
            (1, "check_call", None, table.version),
            (2, "check_call", None, table.version - 1),
            (2, "raise", 3, table.version),
            (2, "raise", 201, table.version),
            (2, "raise", 4.0, table.version),
            (2, "raise", True, table.version),
            (2, "unknown", None, table.version),
        ]
        for seat, action, amount, version in invalid:
            with self.subTest(action=action, amount=amount, seat=seat, version=version):
                before = deepcopy((table.snapshot(), table.frames, table.action_trace,
                                   table.state.operations))
                with self.assertRaises(ValueError):
                    table.act(seat, action, amount, version)
                self.assertEqual(before, (table.snapshot(), table.frames, table.action_trace,
                                          table.state.operations))
        with self.assertRaises(ValueError):
            table.new_hand()

    def test_raise_bounds_are_street_total_and_full_raise_updates_minimum(self):
        table = Table(seed=4)
        self.assertEqual(table.legal()["min_raise_to"], 4)
        table.act(2, "raise", 10)
        self.assertEqual(table.legal()["min_raise_to"], 18)
        self.assertEqual(table.legal()["call_amount"], 10)
        table.act(3, "raise", 18)
        self.assertEqual(table.legal()["min_raise_to"], 26)
        self.assert_conserved(table)

    def test_short_all_in_does_not_reopen_prior_actor(self):
        table = Table(seed=4, stacks=[200, 200, 200, 15, 200, 200])
        table.act(2, "raise", 10)
        table.act(3, "raise", 15)
        for seat in [4, 5, 0, 1]:
            table.act(seat, "check_call")
        self.assertEqual(table.actor, 2)
        self.assertEqual(table.legal()["call_amount"], 5)
        self.assertFalse(table.legal()["can_raise"])
        before = table.snapshot()
        with self.assertRaises(ValueError):
            table.act(2, "raise", 23)
        self.assertEqual(before, table.snapshot())
        table.act(2, "check_call")
        self.assertEqual(table.snapshot()["street"], "flop")
        finish_by_calling(table)
        self.assert_conserved(table)

    def test_side_pots_all_in_runout_and_uncalled_refund(self):
        table = rigged_table([200, 200, 20, 50, 100, 200])
        table.act(2, "raise", 20)
        table.act(3, "raise", 50)
        table.act(4, "raise", 100)
        for seat in [5, 0, 1]:
            table.act(seat, "fold")
        self.assertFalse(table.state.status)
        self.assertEqual(table.snapshot()["board"], ["2c", "3d", "4h", "7s", "9c"])
        self.assertEqual(table.stacks, [199, 198, 63, 60, 50, 200])
        self.assertEqual([p["net"] for p in table.snapshot()["players"]],
                         [-1, -2, 43, 10, -50, 0])
        self.assertEqual(len(table.hands), 1)
        self.assertTrue(table.hands[0]["frames"][-1]["complete"])
        self.assert_conserved(table)
        self.assert_unique_cards(table)

    def test_hidden_cards_and_replay_do_not_leak_folded_hands(self):
        table = Table(seed=5)
        original_holes = deepcopy(table.holes)
        for seat in range(6):
            observation = table.observation(seat)
            self.assertEqual(observation["hole"], original_holes[seat])
            self.assertNotIn("holes", observation)
            self.assertNotIn("deck", observation)
            observation["hole"].clear()
            observation["history"].append({"text": "mutated"})
            self.assertEqual(table.holes, original_holes)
            self.assertEqual(table.actions, [])
        first_frame = deepcopy(table.frames[0])
        self.assertEqual(first_frame["players"][0]["cards"], original_holes[0])
        self.assertTrue(all(not p["cards"] for p in first_frame["players"][1:]))
        for seat in [2, 3, 4, 5, 0]:
            table.act(seat, "fold")
        self.assertFalse(table.state.status)
        self.assertEqual(table.snapshot()["players"][0]["cards"], original_holes[0])
        self.assertEqual(table.frames[0], first_frame)
        for frame in table.hands[0]["frames"]:
            for seat in [2, 3, 4, 5]:
                self.assertEqual(frame["players"][seat]["cards"], [])
            for action in frame["actions"]:
                self.assertFalse({"hole", "holes", "cards", "deck"} & action.keys())

    def test_short_stack_review_excludes_unwinnable_side_pot(self):
        table = Table(seed=4, stacks=[20, 200, 200, 200, 200, 200])
        table.act(2, "raise", 100)
        table.act(3, "check_call")
        table.act(4, "fold")
        table.act(5, "fold")
        self.assertEqual(table.actor, 0)
        self.assertEqual(table.legal()["call_amount"], 19)
        self.assertEqual(table.observation(0)["eligible_pot_after_call"], 62)
        table.act(0, "check_call")
        finish_by_calling(table)
        notes = " ".join(table.hands[-1]["notes"])
        self.assertIn("30.6%", notes)  # 19 / (20 + 20 + 20 + dead big blind 2)
        self.assertNotIn("8.6%", notes)

    def test_same_seed_and_actions_replay_exactly_with_isolated_policy_rng(self):
        first, second = Table(seed=912), Table(seed=912)
        rng = random.Random(9)
        for _ in range(5):
            for _ in range(200):
                self.assertEqual(first.snapshot(), second.snapshot())
                if not first.state.status:
                    break
                seat = first.actor
                legal = first.legal()
                action, amount = "check_call", None
                if legal["can_raise"] and rng.random() < .15:
                    action, amount = "raise", legal["min_raise_to"]
                elif legal["can_fold"] and rng.random() < .2:
                    action = "fold"
                first.act(seat, action, amount)
                # Policy randomness must not influence deal order or another seat.
                for _ in range(11):
                    first.bot_rngs[seat].random()
                second.act(seat, action, amount)
            else:
                self.fail("Hand stalled during deterministic replay")
            self.assertEqual(first.hands, second.hands)
            first.new_hand()
            second.new_hand()

    def test_one_hundred_random_legal_hands_conserve_chips_and_unique_cards(self):
        rng = random.Random(119)
        for seed in range(10):
            table = Table(seed=seed, dealer=seed % 6)
            for hand in range(10):
                with self.subTest(seed=seed, hand=hand):
                    for _ in range(200):
                        self.assert_conserved(table)
                        self.assert_unique_cards(table)
                        if not table.state.status:
                            break
                        self.assertIsNotNone(table.actor)
                        legal = table.legal()
                        roll = rng.random()
                        if roll < .18 and legal["can_raise"]:
                            low, high = legal["min_raise_to"], legal["max_raise_to"]
                            amount = rng.choice([low, high, rng.randint(low, high)])
                            table.act(table.actor, "raise", amount)
                        elif roll < .38 and legal["can_fold"]:
                            table.act(table.actor, "fold")
                        else:
                            table.act(table.actor, "check_call")
                    else:
                        self.fail("Hand did not complete within 200 actions")
                    self.assertTrue(table.snapshot()["complete"])
                    self.assertEqual(sum(p["net"] for p in table.snapshot()["players"]), 0)
                    self.assertEqual(len(table.hands), hand + 1)
                    if hand < 9:
                        table.new_hand()


if __name__ == "__main__":
    unittest.main()
