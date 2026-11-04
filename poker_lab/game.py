"""Seat-safe adapter around PokerKit. All chip values are integers (2 = 1 BB)."""
from collections import deque
from copy import deepcopy
import hashlib
import random
import secrets
import threading
import time

from pokerkit import Automation as A, Deck, Mode, NoLimitTexasHoldem

from .errors import GameError
from .opponents import OpponentStats

ENGINE_VERSION = "pokerkit-0.7.4/adapter-1"
HAND_HISTORY_LIMIT = 20
BOT_DELAY = 0.85
FAST_BOT_DELAY = 0.2
AUTO_DEAL_SECONDS = 5
PLAYERS = [
    dict(kind="human", name="你", name_en="You", style="", avatar="你", color="#b7874c"),
    dict(kind="bot", name="阿岚", name_en="A-Lan", style="tight", avatar="岚", color="#78988c"),
    dict(kind="bot", name="小满", name_en="Xiaoman", style="calling", avatar="满", color="#cf9e77"),
    dict(kind="bot", name="Leo", name_en="Leo", style="bold", avatar="L", color="#8a8bb1"),
    dict(kind="bot", name="知夏", name_en="Zhixia", style="tight", avatar="夏", color="#b3949e"),
    dict(kind="bot", name="老周", name_en="Lao Zhou", style="calling", avatar="周", color="#8199ab"),
]
AUTOMATIONS = (A.ANTE_POSTING, A.BET_COLLECTION, A.BLIND_OR_STRADDLE_POSTING,
               A.RUNOUT_COUNT_SELECTION, A.HOLE_CARDS_SHOWING_OR_MUCKING,
               A.HAND_KILLING, A.CHIPS_PUSHING, A.CHIPS_PULLING)
STREETS = ["preflop", "flop", "turn", "river"]
POSITIONS = ["SB", "BB", "UTG", "HJ", "CO", "BTN"]


def derived_seed(seed, label):
    return int.from_bytes(hashlib.sha256(f"{seed}:{label}".encode()).digest(), "big")


class Table:
    def __init__(self, seed=None, stacks=None, dealer=5, players=None,
                 turn_seconds=None, clock=None, version=0, shared=False, invite=None):
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.clock = clock or time.monotonic
        self.closed = False
        self.wake = lambda: None
        self._thinking_version = None
        self.due_at = None
        self.shared = shared
        self.invite = invite if shared else None
        self.pending = {}
        self.timeouts = [0] * 6
        self.first_hand = [1] * 6
        self.players = deepcopy(PLAYERS)
        if players is not None:
            if len(players) != 6:
                raise ValueError("A table must have six seats.")
            for default, configured in zip(self.players, players):
                default.update(configured)
        for player in self.players:
            if player["kind"] not in ("human", "bot") or not isinstance(player["name"], str):
                raise ValueError("Invalid seat configuration.")
            if player["kind"] == "human":
                player["style"] = ""
                if players is not None:
                    player["name_en"] = player["name"]
            elif player["style"] not in ("tight", "calling", "bold"):
                raise ValueError("Unknown bot style.")
            player.update(away=False, leaving=False)
        # Seat zero starts human, so it needs a regular of its own when vacated.
        self.bots = deepcopy(PLAYERS)
        self.bots[0].update(kind="bot", name="阿禾", name_en="A-He", style="tight", avatar="禾")
        for seat, player in enumerate(self.players):
            if player["kind"] == "bot":
                self.bots[seat] = deepcopy(player)
        if turn_seconds is not None and turn_seconds <= 0:
            raise ValueError("Turn duration must be positive.")
        self.turn_seconds = 30 if shared else turn_seconds
        self.seed = secrets.randbits(128) if seed is None else seed
        self.stacks = list(stacks or [200] * 6)
        self.dealer = (dealer - 1) % 6
        self.hand_id = 0
        self.version = version
        self.session_net = [0] * 6
        self.hands = []
        self.opponent_stats = OpponentStats()
        self.new_hand()

    def has_human(self, seat):
        with self.lock:
            return seat in self.pending or (self.players[seat]["kind"] == "human"
                                            and not self.players[seat]["leaving"])

    def _notify(self):
        self.changed.notify_all()
        self.wake()

    def _unattended(self):
        # Pending guests are present and need this hand to finish before taking a seat.
        return self.shared and not self.pending and not any(
            p["kind"] == "human" and not p["away"] and not p["leaving"]
            for p in self.players)

    def join(self, name):
        """Reserve a bot seat; its current hand still belongs to the bot."""
        with self.changed:
            if self.closed or not self.shared:
                raise GameError("expired")
            seat = next((seat for seat, player in enumerate(self.players)
                         if player["kind"] == "bot" and seat not in self.pending), None)
            if seat is None:
                raise GameError("table_full")
            names = {p["name"] for p in self.players if p["kind"] == "human"}
            names.update(p["name"] for p in self.pending.values())
            base, suffix = name, 2
            while name in names:
                name = f"{base} {suffix}"
                suffix += 1
            player = deepcopy(self.players[seat])
            player.update(kind="human", name=name, name_en=name, style="", avatar=name[0], away=False, leaving=False)
            self.pending[seat] = player
            self.version += 1
            if self.due_at is None:
                self._schedule_next()
            else:
                self._notify()
            return seat

    def leave(self, seat):
        with self.changed:
            if seat in self.pending:
                del self.pending[seat]
            elif self.players[seat]["kind"] == "human" and not self.players[seat]["leaving"]:
                self.players[seat]["leaving"] = True
            else:
                return
            self.version += 1
            if self._unattended() or (seat == self.actor and self.players[seat]["leaving"]):
                self._schedule_next()
            else:
                self._notify()

    def back(self, seat):
        with self.changed:
            if self.closed:
                raise GameError("expired")
            if seat in self.pending or not self.has_human(seat):
                raise GameError("not_seated")
            was_away = self.players[seat]["away"]
            self.players[seat]["away"] = False
            self.timeouts[seat] = 0
            self.version += 1
            if self.due_at is None or (was_away and seat == self.actor):
                self._schedule_next()
            else:
                self._notify()
            return self.view(seat)

    def _change_occupants(self):
        """Apply ownership changes only between hands, after old reads are recorded."""
        for seat, player in enumerate(self.players):
            replacement = self.pending.pop(seat, None)
            if replacement is None and player["leaving"]:
                replacement = deepcopy(self.bots[seat])
            if replacement is None:
                continue
            replacement.update(away=False, leaving=False)
            self.players[seat] = replacement
            self.stacks[seat] = 200
            self.session_net[seat] = 0
            self.timeouts[seat] = 0
            self.first_hand[seat] = self.hand_id + 1
            self.opponent_stats.counts[seat] = {stat: [0, 0] for stat in self.opponent_stats.counts[seat]}

    def new_hand(self):
        with self.changed:
            if self.closed:
                raise GameError("expired")
            self._new_hand()
            self._schedule_next()

    def _new_hand(self):
        if self.hand_id and self.state.status:
            raise GameError("hand_in_progress")
        self._change_occupants()
        self.rebuys = []
        for seat, amount in enumerate(self.stacks):
            if amount < 2:
                self.stacks[seat] = 200
                self.rebuys.append(seat)
        self.hand_id += 1
        self.version += 1
        self._decision_version = self.version
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
        self.last_actions = {seat: None for seat in range(6)}
        for index, kind in enumerate(("small_blind", "big_blind")):
            self.last_actions[self.seats[index]] = dict(
                kind=kind, amount=self.state.bets[index], all_in=self.state.stacks[index] == 0)
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
        with self.lock:
            return self._observation(seat)

    def _observation(self, seat):
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

    def _public_frame(self):
        s = self.state
        complete = not s.status
        players = []
        for seat, player in enumerate(self.players):
            i = self.indices[seat]
            # Style is a public character trait. No policy diagnostics or hidden cards.
            cards = self.shown.get(seat, [])
            players.append(dict(id=seat, **player, stack=s.stacks[i], bet=s.bets[i],
                                in_hand=seat not in self.folded,
                                all_in=s.stacks[i] == 0 and seat not in self.folded,
                                cards=cards.copy(), last_action=deepcopy(self.last_actions[seat]),
                                position=POSITIONS[i],
                                net=s.payoffs[i] if complete else 0))
        pot = s.total_pot_amount
        if complete:
            pot = sum(sum(op.amounts) for op in s.operations if type(op).__name__ == "ChipsPushing")
        return dict(hand_id=self.hand_id, version=self.version, complete=complete,
                    street="showdown" if complete else STREETS[s.street_index or 0],
                    board=self._board(), pot=pot, current_actor=self.actor,
                    dealer=self.dealer, big_blind=2, players=players,
                    legal=self.legal(), actions=deepcopy(self.actions),
                    winners=self._winners(), rebuys=self.rebuys.copy(),
                    session_net=self.session_net.copy())

    def _winners(self):
        if self.state.status:
            return []
        return [dict(seat=seat, amount=self.state.payoffs[i])
                for i, seat in enumerate(self.seats) if self.state.payoffs[i] > 0]

    @staticmethod
    def _project(frame, seat, hole, pending=False):
        view = deepcopy(frame)
        view["you"] = seat
        view["pending"] = pending
        if not pending:
            view["players"][seat]["cards"] = hole.copy()
        view["session_net"] = 0 if pending else frame["session_net"][seat]
        if pending or frame["current_actor"] != seat:
            view["legal"] = dict(can_fold=False, can_check=False, call_amount=0,
                                 can_raise=False, min_raise_to=0, max_raise_to=0)
        return view

    def view(self, seat):
        with self.lock:
            view = self._project(self._public_frame(), seat, self.holes[seat], seat in self.pending)
            remaining = None if self.due_at is None else max(0, self.due_at - self.clock())
            view.update(table=dict(shared=self.shared, invite=self.invite),
                        turn_remaining=remaining if self.shared and self.actor is not None
                        and self.players[self.actor]["kind"] == "human" else None,
                        next_hand_in=remaining if self.shared and not self.state.status else None)
            return view

    def history(self, seat):
        with self.lock:
            if seat in self.pending:
                return []
            return [dict(hand_id=h["hand_id"], winners=deepcopy(h["winners"]),
                         rebuys=h["rebuys"].copy(), net=h["nets"][seat], board=h["board"].copy())
                    for h in reversed(self.hands)
                    if h["hand_id"] >= self.first_hand[seat]]

    def hand(self, hand_id, seat):
        with self.lock:
            if seat in self.pending or hand_id < self.first_hand[seat]:
                return None
            hand = next((h for h in self.hands if h["hand_id"] == hand_id), None)
            if hand is None:
                return None
            return dict(hand_id=hand_id, winners=deepcopy(hand["winners"]),
                        rebuys=hand["rebuys"].copy(), net=hand["nets"][seat],
                        board=hand["board"].copy(), notes=self._review_notes(hand, seat),
                        frames=[self._project(f, seat, hand["holes"][seat]) for f in hand["frames"]])

    def _record(self):
        self.frames.append(self._public_frame())

    def act(self, seat, action, amount=None, version=None):
        with self.changed:
            if self.closed:
                raise GameError("expired")
            self._act(seat, action, amount, version)
            self._schedule_next()
            return self.view(seat)

    def _act(self, seat, action, amount=None, version=None, automatic=False):
        # Seat metadata can change while the same decision remains on screen.
        # Any version from this decision is valid; prior/future decisions are not.
        if version is not None:
            if type(version) is not int or version < 0:
                raise GameError("bad_request")
            if not self._decision_version <= version <= self.version:
                raise GameError("stale")
        if not self.state.status or seat != self.actor:
            raise GameError("not_your_turn")
        s = self.state
        street = STREETS[s.street_index or 0]
        old_count = len(s.operations)
        old_bet = s.bets[self.indices[seat]]
        old_stack = s.stacks[self.indices[seat]]
        if action == "fold":
            if not self.legal()["can_fold"]:
                raise GameError("illegal_action")
            s.fold()
            self.folded.add(seat)
            kind, contribution = "fold", 0
        elif action == "check_call":
            contribution = s.checking_or_calling_amount or 0
            if not s.can_check_or_call():
                raise GameError("illegal_action")
            s.check_or_call()
            kind = "check" if contribution == 0 else "call"
        elif action == "raise":
            if type(amount) is not int or not s.can_complete_bet_or_raise_to(amount):
                raise GameError("illegal_action")
            s.complete_bet_or_raise_to(amount)
            contribution = amount - old_bet
            kind = "raise"
        else:
            raise GameError("illegal_action")
        if not automatic and self.players[seat]["kind"] == "human" and not self.players[seat]["leaving"]:
            self.players[seat]["away"] = False
            self.timeouts[seat] = 0
        all_in = action != "fold" and contribution == old_stack
        action_amount = amount if action == "raise" else contribution
        self.last_actions[seat] = dict(kind=kind, amount=action_amount, all_in=all_in)
        self.actions.append(dict(player=seat, kind=action, amount=action_amount,
                                 street=street, all_in=all_in))
        self.action_trace.append(dict(seat=seat, action=action, amount=amount))
        self.version += 1
        self._decision_version = self.version
        self._collect_reveals(old_count)
        self._record()
        self._advance()

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
            for seat in range(6):
                self.session_net[seat] += s.payoffs[self.indices[seat]]
            self.opponent_stats.update(self._public_record())
            self._record()
            self.hands.append(dict(hand_id=self.hand_id, frames=deepcopy(self.frames),
                                   winners=self._winners(), rebuys=self.rebuys.copy(),
                                   start_stacks=self.start_stacks.copy(),
                                   holes=deepcopy(self.holes),
                                   nets=[s.payoffs[self.indices[p]] for p in range(6)], board=self._board()))
            self.hands = self.hands[-HAND_HISTORY_LIMIT:]
            self._saved = True

    def _public_record(self):
        """What every seat saw this hand: no unrevealed cards."""
        return dict(positions={seat: POSITIONS[i] for i, seat in enumerate(self.seats)},
                    actions=[dict(player=a["player"], kind=a["kind"], street=a["street"]) for a in self.actions],
                    shown=deepcopy(self.shown), board=self._board())

    def _review_notes(self, hand, seat):
        hero = [a for a in hand["frames"][-1]["actions"] if a["player"] == seat]
        notes = [dict(kind="result", actions=len(hero), net=hand["nets"][seat])]
        for frame in hand["frames"]:
            if frame["current_actor"] == seat and frame["legal"]["call_amount"] > 0:
                cost = frame["legal"]["call_amount"]
                contributions = [hand["start_stacks"][p["id"]] - p["stack"] for p in frame["players"]]
                cap = contributions[seat] + cost
                eligible = sum(min(cap, committed + (cost if p == seat else 0))
                               for p, committed in enumerate(contributions))
                required = cost / eligible * 100
                notes.append(dict(kind="pot_odds", street=frame["street"], call=cost,
                                  eligible=eligible, required=round(required, 1)))
                break
        notes.append(dict(kind="visibility"))
        return notes

    def _schedule_next(self):
        """Anchor the next deadline once per transition; inspecting it never delays play."""
        actor = self.actor
        if self.closed or self._unattended():
            delay = None
        elif actor is None:
            delay = AUTO_DEAL_SECONDS if self.shared and not self.state.status else None
        elif self.players[actor]["kind"] == "human":
            delay = 0 if self.players[actor]["away"] or self.players[actor]["leaving"] else self.turn_seconds
        else:
            human_remains = any(p["kind"] == "human" and seat not in self.folded
                                for seat, p in enumerate(self.players))
            delay = BOT_DELAY if human_remains else FAST_BOT_DELAY
        self.due_at = None if delay is None else self.clock() + delay
        self._notify()

    def next_due(self):
        with self.lock:
            return None if self.closed else self.due_at

    def close(self):
        with self.changed:
            self.closed = True
            self.due_at = None
            self.changed.notify_all()
            self.wake()

    def run_due(self, now=None):
        """Run at most one due action; clock injection makes pacing testable without sleep.

        The policy receives a detached observation and RNG. Neither table nor registry
        locks may be held by the caller while this method computes the decision.
        """
        with self.lock:
            now = self.clock() if now is None else now
            if self.closed or self.due_at is None or now < self.due_at:
                return False
            if not self.state.status:
                self.new_hand()
                return True
            seat, version = self.actor, self.version
            if self.players[seat]["kind"] == "human":
                player = self.players[seat]
                if not player["leaving"] and not player["away"]:
                    self.timeouts[seat] += 1
                    player["away"] = self.timeouts[seat] >= 2
                self._act(seat, "check_call" if self.legal()["can_check"] else "fold",
                          version=version, automatic=True)
                self._schedule_next()
                return True
            if self._thinking_version == version:
                return False
            self._thinking_version = version
            observation = self.observation(seat)
            style = self.players[seat]["style"]
            rng = random.Random(0)
            rng.setstate(self.bot_rngs[seat].getstate())
        try:
            from .bots import choose_action
            decision = choose_action(observation, style, rng)
            with self.lock:
                if self.closed or self.version != version:
                    return False
                self.act(seat, decision["action"], decision.get("amount"), version)
                self.bot_rngs[seat].setstate(rng.getstate())
                return True
        except Exception:
            with self.lock:
                if not self.closed and self.version == version:
                    self.due_at = self.clock() + BOT_DELAY
            raise
        finally:
            with self.lock:
                if self._thinking_version == version:
                    self._thinking_version = None
