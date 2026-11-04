"""Opponent statistics come only from public records, and bots adjust in the right direction."""
import random
import unittest
from collections import Counter

from poker_lab.bots import choose_action
from poker_lab.game import Table
from poker_lab.opponents import OpponentStats, estimate

POSITIONS = {0: "SB", 1: "BB", 2: "UTG", 3: "HJ", 4: "CO", 5: "BTN"}


def act(player, kind, street):
    return {"player": player, "kind": kind, "street": street}


def reads(**stats):
    """Fresh reads with seat 0's counts replaced."""
    value = OpponentStats().snapshot()
    value[0].update(stats)
    return value


FOLDED = [act(seat, "fold", "preflop") for seat in (1, 3, 4, 5)]


def flop_spot(r):
    """Seat 2 on the button with air, heads-up against seat 0, checked to."""
    return dict(seat=2, street="flop", hole=["2c", "7d"], board=["Ks", "Qh", "9s"], pot=12, stack=190, bet=0,
                big_blind=2, position="BTN", opponents=1, history=FOLDED, all_in=[], reads=r,
                legal=dict(can_fold=False, can_check=True, call_amount=0, can_raise=True,
                           min_raise_to=2, max_raise_to=190))


def river_spot(r):
    """Seat 2 with second pair facing a pot-sized river bet from seat 0."""
    return dict(seat=2, street="river", hole=["Jc", "9d"], board=["Qs", "Jd", "5c", "4h", "2s"], pot=40, stack=150,
                bet=0, big_blind=2, position="BTN", opponents=1, history=FOLDED + [act(0, "raise", "river")],
                all_in=[], reads=r, legal=dict(can_fold=True, can_check=False, call_amount=40, can_raise=True,
                                    min_raise_to=80, max_raise_to=150))


def actions(spot, style, n=200):
    return Counter(choose_action(spot, style, random.Random(seed))["action"] for seed in range(n))


class OpponentStatsTests(unittest.TestCase):
    def test_counts_use_decision_opportunities(self):
        stats = OpponentStats()
        stats.update(dict(positions=POSITIONS, board=["Qs", "Jd", "9c", "5h", "3s"],
                          shown={4: ["7c", "2d"], 2: ["Ah", "Kh"]}, actions=[
            act(2, "raise", "preflop"), act(3, "fold", "preflop"), act(4, "check_call", "preflop"),
            act(5, "fold", "preflop"), act(0, "fold", "preflop"), act(1, "check_call", "preflop"),
            act(1, "check_call", "flop"), act(2, "raise", "flop"), act(4, "check_call", "flop"), act(1, "fold", "flop"),
            act(2, "check_call", "turn"), act(4, "raise", "turn"), act(2, "check_call", "turn"),
            act(2, "check_call", "river"), act(4, "raise", "river"), act(2, "check_call", "river"),
        ]))
        c = stats.counts
        self.assertEqual(c[1], dict(vpip=[1, 1], pfr=[0, 1], fold_to_bet=[1, 1], aggression=[0, 0], river_bluff=[0, 0]))
        self.assertEqual(c[2], dict(vpip=[1, 1], pfr=[1, 1], fold_to_bet=[0, 2], aggression=[1, 3], river_bluff=[0, 0]))
        # Seat 4 bet the river with seven-high and was called: an observed bluff.
        self.assertEqual(c[4], dict(vpip=[1, 1], pfr=[0, 1], fold_to_bet=[0, 1], aggression=[2, 3], river_bluff=[1, 1]))
        self.assertEqual(c[0]["vpip"], [0, 1])

    def test_unraised_big_blind_check_is_not_voluntary(self):
        stats = OpponentStats()
        stats.update(dict(positions=POSITIONS, board=[], shown={}, actions=[
            act(2, "check_call", "preflop"), *[act(s, "fold", "preflop") for s in (3, 4, 5, 0)],
            act(1, "check_call", "preflop")]))
        self.assertEqual(stats.counts[1]["vpip"], [0, 1])
        self.assertEqual(stats.counts[2]["vpip"], [1, 1])

    def test_no_data_returns_prior_and_trust_slows_learning(self):
        self.assertEqual(estimate([0, 0], "fold_to_bet", 12), 0.30)
        quick, slow = estimate([140, 200], "fold_to_bet", 12), estimate([140, 200], "fold_to_bet", 60)
        self.assertGreater(quick, slow)
        self.assertGreater(slow, 0.30)

    def test_table_learns_only_public_information(self):
        def play(seed):
            """Everyone limps; the first flop actor bets and the rest fold, so no cards are shown."""
            table = Table(seed=seed)
            while table.state.status:
                legal = table.legal()
                if table.view(0)["street"] == "preflop":
                    table.act(table.actor, "check_call")
                elif legal["can_check"]:
                    table.act(table.actor, "raise", legal["min_raise_to"])
                else:
                    table.act(table.actor, "fold")
            return table
        first, second = play(1), play(2)
        self.assertNotEqual(first.holes, second.holes)
        self.assertEqual(first._public_record()["shown"], {})
        self.assertEqual(first.opponent_stats.counts, second.opponent_stats.counts)
        self.assertNotEqual(first.opponent_stats.counts, OpponentStats().counts)
        first.new_hand()
        observation = first.observation(first.actor)
        observation["reads"][0]["vpip"][0] = 99
        self.assertNotEqual(first.opponent_stats.counts[0]["vpip"][0], 99)


class AdaptationTests(unittest.TestCase):
    def test_bluff_more_against_folders_and_less_against_callers(self):
        prior = actions(flop_spot(reads()), "bold")["raise"]
        folder = actions(flop_spot(reads(fold_to_bet=[140, 200])), "bold")["raise"]
        station = actions(flop_spot(reads(fold_to_bet=[10, 200])), "bold")["raise"]
        self.assertGreater(folder, prior * 2)
        self.assertLess(station, prior * 0.6)

    def test_call_lighter_against_a_shown_bluffer(self):
        prior = actions(river_spot(reads()), "tight")["fold"]
        bluffer = actions(river_spot(reads(river_bluff=[30, 40], aggression=[60, 100])), "tight")["fold"]
        self.assertLess(bluffer, prior * 0.5)

    def test_bet_any_two_cards_when_fold_equity_beats_the_price(self):
        prior = actions(flop_spot(reads()), "tight")["raise"]
        folder = actions(flop_spot(reads(fold_to_bet=[140, 200])), "tight")["raise"]
        self.assertLess(prior, 20)
        self.assertGreater(folder, 80)

    def test_no_fold_equity_bonus_when_an_opponent_is_all_in(self):
        # Three-way flop against two heavy folders. With seat 1 all-in the main pot must reach
        # showdown, so the folding history earns no extra bluffs.
        folders = reads(fold_to_bet=[190, 200])
        folders[1]["fold_to_bet"] = [190, 200]
        history = [act(s, "fold", "preflop") for s in (3, 4, 5)]
        live = flop_spot(folders) | dict(history=history, opponents=2, all_in=[])
        all_in = live | dict(all_in=[1])
        baseline = flop_spot(reads()) | dict(history=history, opponents=2, all_in=[1])
        self.assertGreater(actions(live, "tight")["raise"], 80)
        self.assertLessEqual(actions(all_in, "tight")["raise"], actions(baseline, "tight")["raise"])

    def test_calling_style_adapts_least(self):
        def gain(style):
            prior = actions(flop_spot(reads()), style)["raise"]
            return actions(flop_spot(reads(fold_to_bet=[140, 200])), style)["raise"] - prior
        self.assertLess(gain("calling"), 0.4 * gain("tight"))


if __name__ == "__main__":
    unittest.main()
