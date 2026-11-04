"""Language-neutral public data, including replay and action-time all-in flags."""
from copy import deepcopy
import re
import unittest

from poker_lab.game import PLAYERS, Table


def finish(table):
    while table.state.status:
        table.act(table.actor, "check_call")


class LanguageDataTests(unittest.TestCase):
    def assert_language_neutral(self, value):
        if isinstance(value, dict):
            player = {"id", "name", "name_en", "kind"} <= value.keys()
            winner = {"seat", "amount", "name", "name_en"} == value.keys()
            self.assertNotIn("summary", value)
            self.assertNotIn("text", value)
            for key, child in value.items():
                if player and key in ("name", "name_en", "avatar"):
                    continue
                if winner and key in ("name", "name_en"):
                    continue
                self.assert_language_neutral(child)
        elif isinstance(value, list):
            for child in value:
                self.assert_language_neutral(child)
        elif isinstance(value, str):
            self.assertIsNone(re.search(r"[\u3400-\u9fff]", value), value)

    def test_action_and_last_action_contract_for_blinds_calls_checks_raises_and_folds(self):
        table = Table(seed=1)
        initial = table.view(0)
        self.assertEqual(initial["players"][0]["last_action"],
                         {"kind": "small_blind", "amount": 1, "all_in": False})
        self.assertEqual(initial["players"][1]["last_action"],
                         {"kind": "big_blind", "amount": 2, "all_in": False})
        self.assertTrue(all(p["last_action"] is None for p in initial["players"][2:]))
        for seat, action, amount, kind, expected in (
            (2, "raise", 8, "raise", 8),
            (3, "check_call", None, "call", 8),
            (4, "fold", None, "fold", 0),
            (5, "fold", None, "fold", 0),
            (0, "check_call", None, "call", 7),
            (1, "check_call", None, "call", 6),
            (0, "check_call", None, "check", 0),
        ):
            street = table.view(0)["street"]
            table.act(seat, action, amount)
            view = table.view(0)
            self.assertEqual(view["actions"][-1], {
                "player": seat, "kind": action, "amount": expected,
                "street": street, "all_in": False})
            self.assertEqual(view["players"][seat]["last_action"],
                             {"kind": kind, "amount": expected, "all_in": False})
        # Captured frames retain their own structured last actions.
        self.assertEqual(table.frames[0]["players"][0]["last_action"],
                         {"kind": "small_blind", "amount": 1, "all_in": False})

    def test_all_in_blind_raise_and_final_winning_call(self):
        blind = Table(seed=1, stacks=[200, 2, 200, 200, 200, 200])
        self.assertEqual(blind.view(0)["players"][1]["last_action"],
                         {"kind": "big_blind", "amount": 2, "all_in": True})
        table = Table(seed=1)
        for seat in (2, 3, 4, 5):
            table.act(seat, "fold")
        while table.state.street_index != 3:
            table.act(table.actor, "check_call")
        table.act(0, "raise", 198)
        self.assertEqual(table.view(0)["players"][0]["last_action"],
                         {"kind": "raise", "amount": 198, "all_in": True})
        table.act(1, "check_call")
        self.assertFalse(table.state.status)
        # PokerKit pays the winner immediately, so his post-call stack is nonzero.
        self.assertEqual(table.stacks[1], 400)
        self.assertEqual(table.actions[-1], {"player": 1, "kind": "check_call", "amount": 198,
                                            "street": "river", "all_in": True})
        self.assertEqual(table.view(0)["players"][1]["last_action"],
                         {"kind": "call", "amount": 198, "all_in": True})
        winners = [{"seat": 1, "amount": 200, "name": "阿岚", "name_en": "A-Lan"}]
        self.assertEqual(table.view(0)["winners"], winners)
        for frame in table.hand(1, 0)["frames"]:
            if frame["complete"]:
                self.assertEqual(frame["winners"], winners)

    def test_results_rebuys_and_notes_have_the_same_shapes_in_history_and_replay(self):
        table = Table(seed=4, stacks=[0, 200, 1, 200, 200, 200])
        self.assertEqual(table.view(0)["rebuys"], [0, 2])
        self.assertEqual(table.view(0)["winners"], [])
        finish(table)
        view, hand, history = table.view(0), table.hand(1, 0), table.history(0)[0]
        expected = [{"seat": seat, "amount": table.state.payoffs[i],
                     "name": table.players[seat]["name"], "name_en": table.players[seat]["name_en"]}
                    for i, seat in enumerate(table.seats) if table.state.payoffs[i] > 0]
        for result in (view, hand, history):
            self.assertEqual(result["winners"], expected)
            self.assertEqual(result["rebuys"], [0, 2])
            self.assert_language_neutral(result)
        self.assertEqual(hand["notes"][0], {
            "kind": "result", "actions": sum(a["player"] == 0 for a in table.actions),
            "net": table.session_net[0]})
        self.assertEqual(hand["notes"][-1], {"kind": "visibility"})
        odds = hand["notes"][1]
        self.assertEqual(set(odds), {"kind", "street", "call", "eligible", "required"})
        self.assertEqual(odds["required"], round(odds["call"] / odds["eligible"] * 100, 1))
        for frame in hand["frames"]:
            self.assertEqual(frame["rebuys"], [0, 2])
        table.new_hand()
        self.assertEqual(table.view(0)["rebuys"], [])
        self.assertEqual(table.view(0)["winners"], [])
        self.assertEqual(table.hand(1, 0), hand)

    def test_structured_response_fields_do_not_alias_live_or_saved_data(self):
        table = Table(seed=1, stacks=[0, 200, 200, 200, 200, 200])
        view = table.view(0)
        view["players"][0]["last_action"]["amount"] = 999
        view["rebuys"].clear()
        self.assertEqual(table.view(0)["players"][0]["last_action"]["amount"], 1)
        self.assertEqual(table.view(0)["rebuys"], [0])
        finish(table)
        saved = deepcopy(table.hands)
        for data in (table.view(0), table.history(0)[0], table.hand(1, 0)):
            data["winners"][0]["amount"] = 999
            data["winners"][0]["name"] = "changed"
            data["winners"][0]["name_en"] = "changed"
            data["rebuys"].clear()
        replay = table.hand(1, 0)
        replay["notes"][0]["net"] = 999
        replay["frames"][-1]["players"][0]["last_action"]["amount"] = 999
        replay["frames"][-1]["winners"].clear()
        self.assertEqual(table.hands, saved)

    def test_winner_names_survive_bot_and_human_replacement(self):
        table = Table(seed=1, shared=True, invite="example")
        for seat in (2, 3, 4, 5):
            table.act(seat, "fold")
        while table.state.street_index != 3:
            table.act(table.actor, "check_call")
        table.act(0, "raise", 198)
        table.act(1, "check_call")
        bot_winners = deepcopy(table.view(0)["winners"])
        self.assertEqual(bot_winners, [{"seat": 1, "amount": 200, "name": "阿岚", "name_en": "A-Lan"}])
        seat = table.join("朋友")
        self.assertEqual(seat, 1)
        table.new_hand()
        self.assertEqual(table.players[seat]["name"], "朋友")
        self.assertEqual(table.history(0)[0]["winners"], bot_winners)
        self.assertEqual(table.hand(1, 0)["winners"], bot_winners)
        while table.actor != seat:
            table.act(table.actor, "fold")
        table.act(seat, "raise", 4)
        table.act(table.actor, "fold")
        self.assertFalse(table.state.status)
        human_winners = deepcopy(table.view(0)["winners"])
        self.assertEqual(human_winners[0]["name"], "朋友")
        self.assertEqual(human_winners[0]["name_en"], "朋友")
        table.leave(seat)
        table.new_hand()
        self.assertEqual(table.players[seat]["name_en"], "A-Lan")
        self.assertEqual([h["winners"] for h in table.history(0)], [human_winners, bot_winners])
        for hand_id, winners in ((1, bot_winners), (2, human_winners)):
            hand = table.hand(hand_id, 0)
            self.assertEqual(hand["winners"], winners)
            for frame in hand["frames"]:
                self.assertEqual(frame["winners"], winners if frame["complete"] else [])
            self.assert_language_neutral(hand)

    def test_english_bot_names_and_guest_names_survive_ownership_changes(self):
        players = deepcopy(PLAYERS)
        players[0]["name"] = "朋友"
        table = Table(seed=1, players=players, shared=True, invite="example")
        self.assertEqual([p["name_en"] for p in table.view(0)["players"]],
                         ["朋友", "A-Lan", "Xiaoman", "Leo", "Zhixia", "Lao Zhou"])
        guest = table.join("朋友")
        finish(table)
        table.new_hand()
        self.assertEqual(table.view(guest)["players"][guest]["name"], "朋友 2")
        self.assertEqual(table.view(guest)["players"][guest]["name_en"], "朋友 2")
        table.leave(0)
        table.leave(guest)
        finish(table)
        table.new_hand()
        self.assertEqual(table.players[0]["name_en"], "A-He")
        self.assertEqual(table.players[guest]["name_en"], "A-Lan")
        self.assert_language_neutral(table.view(guest))

    def test_solo_placeholder_is_translated_but_a_typed_chinese_name_is_not(self):
        solo = Table(seed=1)
        self.assertEqual(solo.players[0]["name"], "你")
        self.assertEqual(solo.players[0]["name_en"], "You")
        players = deepcopy(PLAYERS)
        players[0]["name"] = "你"
        shared = Table(seed=1, players=players, shared=True, invite="example")
        self.assertEqual(shared.players[0]["name_en"], "你")
        guest = shared.join("小王")
        finish(shared)
        shared.new_hand()
        self.assertEqual(shared.players[guest]["name_en"], "小王")


if __name__ == "__main__":
    unittest.main()
