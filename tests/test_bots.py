import copy
import random
import unittest
from collections import Counter

from poker_lab.bots import DECK, PROFILES, choose_action
from poker_lab.opponents import OpponentStats


def observation(**changes):
    value = {
        "seat": 2, "street": "preflop", "hole": ["7s", "6s"], "board": [],
        "pot": 3, "stack": 200, "bet": 0, "big_blind": 2, "position": "HJ",
        "opponents": 5, "history": [], "reads": OpponentStats().snapshot(),
        "legal": {"can_fold": True, "can_check": False, "call_amount": 2,
                  "can_raise": True, "min_raise_to": 4, "max_raise_to": 200},
    }
    value.update(changes)
    return value


class PolicyTests(unittest.TestCase):
    def test_distinct_entry_and_aggression_across_seats_and_seeds(self):
        counts = {name: Counter() for name in PROFILES}
        for position in ("UTG", "HJ", "CO", "BTN", "SB", "BB"):
            for seed in range(80):
                for style in PROFILES:
                    choice = choose_action(observation(position=position), style, random.Random(seed))
                    counts[style][choice["action"]] += 1
        self.assertGreater(counts["tight"]["fold"], counts["calling"]["fold"] + 150)
        self.assertGreater(counts["bold"]["raise"], counts["calling"]["raise"] + 150)
        self.assertGreater(counts["calling"]["check_call"], counts["bold"]["check_call"] + 150)

    def test_top_pair_attachment_changes_costly_calls(self):
        obs = observation(street="river", hole=["Qs", "2d"], board=["Qc", "Jh", "Ts", "7h", "3h"],
                          pot=80, opponents=2,
                          legal={"can_fold": True, "can_check": False, "call_amount": 60,
                                 "can_raise": False, "min_raise_to": None, "max_raise_to": None})
        counts = {style: Counter(choose_action(obs, style, random.Random(seed))["action"] for seed in range(64))
                  for style in ("tight", "calling")}
        self.assertGreater(counts["calling"]["check_call"], counts["tight"]["check_call"] + 20)

    def test_all_styles_take_free_check_and_keep_legal_raise_bounds(self):
        rng = random.Random(31)
        for street, board_count in (("preflop", 0), ("flop", 3), ("turn", 4), ("river", 5)):
            for seed in range(12):
                cards = rng.sample(DECK, 2 + board_count)
                # Includes the legal short all-in case min == max.
                maximum = 7 if seed % 2 else 100
                minimum = 7 if seed % 2 else 12
                can_raise = seed % 3 != 0
                obs = observation(street=street, hole=cards[:2], board=cards[2:], pot=30, opponents=2,
                                  legal={"can_fold": False, "can_check": True, "call_amount": 0,
                                         "can_raise": can_raise, "min_raise_to": minimum if can_raise else None,
                                         "max_raise_to": maximum if can_raise else None})
                for style in PROFILES:
                    result = choose_action(obs, style, random.Random(seed))
                    self.assertIn(result["action"], {"check_call", "raise"})
                    if result["action"] == "raise":
                        self.assertTrue(can_raise)
                        self.assertIsInstance(result["amount"], int)
                        self.assertLessEqual(result["amount"], maximum)
                        self.assertGreaterEqual(result["amount"], minimum)

    def test_weak_hands_fold_to_large_preflop_price(self):
        obs = observation(hole=["7s", "2d"], pot=100,
                          legal={"can_fold": True, "can_check": False, "call_amount": 80,
                                 "can_raise": True, "min_raise_to": 160, "max_raise_to": 200})
        for style in PROFILES:
            for seed in range(20):
                self.assertEqual(choose_action(obs, style, random.Random(seed))["action"], "fold")

    def test_public_board_tie_is_not_mistaken_for_a_loss(self):
        obs = observation(street="river", hole=["2c", "3d"], board=["As", "Ks", "Qs", "Js", "Ts"],
                          pot=100, opponents=1,
                          legal={"can_fold": True, "can_check": False, "call_amount": 10,
                                 "can_raise": False, "min_raise_to": None, "max_raise_to": None})
        for style in PROFILES:
            self.assertEqual(choose_action(obs, style, random.Random(8))["action"], "check_call")

    def test_observation_not_modified_and_rng_reproducible(self):
        obs = observation(street="flop", hole=["As", "Ks"], board=["Qs", "Js", "2d"], opponents=2)
        original = copy.deepcopy(obs)
        a = choose_action(obs, "bold", random.Random(21))
        b = choose_action(obs, "bold", random.Random(21))
        self.assertEqual(a, b)
        self.assertEqual(obs, original)


if __name__ == "__main__":
    unittest.main()
