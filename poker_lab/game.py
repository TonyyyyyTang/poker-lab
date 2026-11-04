"""Seat-safe adapter around PokerKit. All chip values are integers (2 = 1 BB)."""
from collections import deque
from copy import deepcopy
import hashlib
import random
import secrets

from pokerkit import Automation as A, Deck, Mode, NoLimitTexasHoldem

from .opponents import OpponentStats

ENGINE_VERSION = "pokerkit-0.7.4/adapter-1"
HAND_HISTORY_LIMIT = 20
PLAYERS = [
    dict(name="你", style="", avatar="你", color="#b7874c"),
    dict(name="阿岚", style="tight", avatar="岚", color="#78988c"),
    dict(name="小满", style="calling", avatar="满", color="#cf9e77"),
    dict(name="Leo", style="bold", avatar="L", color="#8a8bb1"),
    dict(name="知夏", style="tight", avatar="夏", color="#b3949e"),
    dict(name="老周", style="calling", avatar="周", color="#8199ab"),
]
AUTOMATIONS = (A.ANTE_POSTING, A.BET_COLLECTION, A.BLIND_OR_STRADDLE_POSTING,
               A.RUNOUT_COUNT_SELECTION, A.HOLE_CARDS_SHOWING_OR_MUCKING,
               A.HAND_KILLING, A.CHIPS_PUSHING, A.CHIPS_PULLING)
STREETS = ["preflop", "flop", "turn", "river"]
POSITIONS = ["SB", "BB", "UTG", "HJ", "CO", "BTN"]


def derived_seed(seed, label):
    return int.from_bytes(hashlib.sha256(f"{seed}:{label}".encode()).digest(), "big")


def bb(amount):
    return f"{amount / 2:g} BB"


class Table:
    def __init__(self, seed=None, stacks=None, dealer=5):
        self.seed = secrets.randbits(128) if seed is None else seed
        self.stacks = list(stacks or [200] * 6)
        self.dealer = (dealer - 1) % 6
        self.hand_id = 0
        self.version = 0
        self.session_net = 0
        self.hands = []
        self.opponent_stats = OpponentStats()
        self.new_hand()

    def new_hand(self):
        if self.hand_id and self.state.status:
            raise ValueError("这手牌还没结束。")
        rebuys = []
        for seat, amount in enumerate(self.stacks):
            if amount < 2:
                self.stacks[seat] = 200
                rebuys.append(PLAYERS[seat]["name"])
        self.hand_id += 1
        self.version += 1
        self.dealer = (self.dealer + 1) % 6
        self.seats = [(self.dealer + 1 + i) % 6 for i in range(6)]
        self.indices = {seat: index for index, seat in enumerate(self.seats)}
        self.start_stacks = self.stacks.copy()
        self.state = NoLimitTexasHoldem.create_state(
            AUTOMATIONS, True, 0, (1, 2), 2,
            tuple(self.stacks[seat] for seat in self.seats), 6, mode=Mode.CASH_GAME)
        deck = list(Deck.STANDARD)
        random.Random(derived_seed(self.seed, f"deck:{self.hand_id}")).shuffle(deck)
        self.state.deck_cards = deque(deck)
        self.bot_rngs = {seat: random.Random(derived_seed(self.seed, f"policy:{self.hand_id}:{seat}"))
                         for seat in range(6)}
        while self.state.can_deal_hole():
            self.state.deal_hole()
        self.holes = {seat: [repr(c) for c in self.state.hole_cards[i]]
                      for i, seat in enumerate(self.seats)}
        self.folded = set()
        self.shown = {}
        self.actions = []
        self.frames = []
        self.last_actions = {seat: "" for seat in range(6)}
        self.last_actions[self.seats[0]] = "小盲 " + bb(1)
        self.last_actions[self.seats[1]] = "大盲 " + bb(2)
        self.summary = "、".join(rebuys) + " 已补充至 100 BB。" if rebuys else ""
        self.action_trace = []
        self._saved = False
        self._record()

    @property
    def actor(self):
        i = self.state.actor_index
        return self.seats[i] if i is not None else None

    def legal(self):
        s = self.state
        if s.actor_index is None:
            return dict(can_fold=False, can_check=False, call_amount=0, can_raise=False,
                        min_raise_to=0, max_raise_to=0)
        return dict(can_fold=bool(s.checking_or_calling_amount) and s.can_fold(), can_check=s.checking_or_calling_amount == 0,
                    call_amount=s.checking_or_calling_amount or 0,
                    can_raise=s.can_complete_bet_or_raise_to(),
                    min_raise_to=s.min_completion_betting_or_raising_to_amount or 0,
                    max_raise_to=s.max_completion_betting_or_raising_to_amount or 0)

    def _board(self):
        return [repr(cards[0]) for cards in self.state.board_cards]

    def observation(self, seat):
        """The ONLY input passed to a policy; no table or engine reference escapes."""
        i = self.indices[seat]
        call = self.legal()["call_amount"]
        contributions = [self.start_stacks[p] - self.state.stacks[self.indices[p]] for p in range(6)]
        cap = contributions[seat] + call
        eligible = sum(min(cap, committed + (call if p == seat else 0))
                       for p, committed in enumerate(contributions))
        return dict(seat=seat, street=STREETS[self.state.street_index or 0],
                    hole=self.holes[seat].copy(), board=self._board(),
                    pot=self.state.total_pot_amount, stack=self.state.stacks[i],
                    bet=self.state.bets[i], big_blind=2,
                    position=POSITIONS[i],
                    opponents=sum(self.state.statuses) - 1,
                    eligible_pot_after_call=eligible,
                    legal=self.legal(), history=deepcopy(self.actions),
                    all_in=[p for p in range(6) if self.state.stacks[self.indices[p]] == 0 and p not in self.folded],
                    reads=self.opponent_stats.snapshot())

    def snapshot(self):
        s = self.state
        complete = not s.status
        players = []
        for seat, player in enumerate(PLAYERS):
            i = self.indices[seat]
            # Style is a public character trait. No policy diagnostics or hidden cards.
            cards = self.holes[seat] if seat == 0 else self.shown.get(seat, [])
            players.append(dict(id=seat, **player, stack=s.stacks[i], bet=s.bets[i],
                                in_hand=seat not in self.folded,
                                all_in=s.stacks[i] == 0 and seat not in self.folded,
                                cards=cards.copy(), last_action=self.last_actions[seat],
                                position=POSITIONS[i],
                                net=s.payoffs[i] if complete else 0))
        pot = s.total_pot_amount
        if complete:
            pot = sum(sum(op.amounts) for op in s.operations if type(op).__name__ == "ChipsPushing")
        return dict(hand_id=self.hand_id, version=self.version, complete=complete,
                    street="showdown" if complete else STREETS[s.street_index or 0],
                    board=self._board(), pot=pot, current_actor=self.actor,
                    dealer=self.dealer, big_blind=2, players=players,
                    legal=self.legal() if self.actor == 0 else dict(can_fold=False, can_check=False,
                        call_amount=0, can_raise=False, min_raise_to=0, max_raise_to=0),
                    actions=deepcopy(self.actions), summary=self.summary,
                    session_net=self.session_net)

    def _record(self):
        self.frames.append(self.snapshot())

    def act(self, seat, action, amount=None, version=None):
        if version is not None and version != self.version:
            raise ValueError("牌局已更新，请按当前局面操作。")
        if not self.state.status or seat != self.actor:
            raise ValueError("现在还没轮到这个座位。")
        s = self.state
        street = STREETS[s.street_index or 0]
        old_count = len(s.operations)
        old_bet = s.bets[self.indices[seat]]
        if action == "fold":
            if not self.legal()["can_fold"]:
                raise ValueError("当前不能弃牌。")
            s.fold()
            self.folded.add(seat)
            label, contribution = "弃牌", 0
        elif action == "check_call":
            contribution = s.checking_or_calling_amount or 0
            if not s.can_check_or_call():
                raise ValueError("当前不能过牌或跟注。")
            s.check_or_call()
            label = "过牌" if contribution == 0 else "跟注 " + bb(contribution)
        elif action == "raise":
            if type(amount) is not int or not s.can_complete_bet_or_raise_to(amount):
                raise ValueError("下注额不在当前允许范围内。")
            s.complete_bet_or_raise_to(amount)
            contribution = amount - old_bet
            label = "加注至 " + bb(amount)
        else:
            raise ValueError("未知操作。")
        if s.stacks[self.indices[seat]] == 0 and seat not in self.folded:
            label += " · 全下"
        self.last_actions[seat] = label
        self.actions.append(dict(player=seat, kind=action, amount=amount or contribution,
                                 street=street, text=f"{PLAYERS[seat]['name']} · {label}"))
        self.action_trace.append(dict(seat=seat, action=action, amount=amount))
        self.version += 1
        self._collect_reveals(old_count)
        self._record()
        self._advance()
        return self.snapshot()

    def _collect_reveals(self, start):
        for op in self.state.operations[start:]:
            if type(op).__name__ == "HoleCardsShowingOrMucking" and op.hole_cards:
                self.shown[self.seats[op.player_index]] = [repr(c) for c in op.hole_cards]

    def _advance(self):
        s = self.state
        while s.status and s.actor_index is None:
            start = len(s.operations)
            if s.can_burn_card():
                s.burn_card()
            elif s.can_deal_board():
                s.deal_board()
                self._collect_reveals(start)
                self._record()
            else:
                raise RuntimeError("Rules engine stopped at an unhandled transition")
            self._collect_reveals(start)
        if not s.status and not self._saved:
            self.stacks = [s.stacks[self.indices[seat]] for seat in range(6)]
            self.session_net += s.payoffs[self.indices[0]]
            winners = [f"{PLAYERS[seat]['name']} +{bb(s.payoffs[i])}"
                       for i, seat in enumerate(self.seats) if s.payoffs[i] > 0]
            self.summary = "，".join(winners) or "平分底池"
            self.opponent_stats.update(self._public_record())
            self._record()
            notes = self._review_notes()
            self.hands.append(dict(hand_id=self.hand_id, frames=deepcopy(self.frames),
                                   summary=self.summary, notes=notes,
                                   net=s.payoffs[self.indices[0]], board=self._board()))
            self.hands = self.hands[-HAND_HISTORY_LIMIT:]
            self._saved = True

    def _public_record(self):
        """What every seat saw this hand: no unrevealed cards."""
        return dict(positions={seat: POSITIONS[i] for i, seat in enumerate(self.seats)},
                    actions=[dict(player=a["player"], kind=a["kind"], street=a["street"]) for a in self.actions],
                    shown=deepcopy(self.shown), board=self._board())

    def _review_notes(self):
        hero = [a for a in self.actions if a["player"] == 0]
        notes = [f"本手你行动 {len(hero)} 次，净变化 {bb(self.state.payoffs[self.indices[0]])}。结果本身不代表决策质量。"]
        for frame in self.frames:
            if frame["current_actor"] == 0 and frame["legal"]["call_amount"] > 0:
                cost = frame["legal"]["call_amount"]
                contributions = [self.start_stacks[p["id"]] - p["stack"] for p in frame["players"]]
                cap = contributions[0] + cost
                eligible = sum(min(cap, committed + (cost if seat == 0 else 0))
                               for seat, committed in enumerate(contributions))
                required = cost / eligible * 100
                notes.append(f"{dict(preflop='翻牌前', flop='翻牌', turn='转牌', river='河牌').get(frame['street'], '')}的一次决定：跟注 {bb(cost)}，跟注后可争夺底池 {bb(eligible)}；若之后不再下注，需要约 {required:.1f}% 的胜率才能打平。这不是完整行动 EV。")
                break
        notes.append("逐步回看只显示当时可见的信息；对手在实际亮牌后才公开底牌，弃牌与盖牌仍然保密。")
        return notes

    def step_bot(self, version=None):
        if version is not None and version != self.version:
            raise ValueError("牌局已更新。")
        seat = self.actor
        if seat is None or seat == 0:
            return self.snapshot()
        from .bots import choose_action
        decision = choose_action(self.observation(seat), PLAYERS[seat]["style"], self.bot_rngs[seat])
        return self.act(seat, decision["action"], decision.get("amount"), version)
