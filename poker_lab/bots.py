"""Small, intentionally imperfect policies using only a seat's observation.

Postflop samples are against uniformly random hands, not inferred ranges or an
action-EV solver. They are a noisy policy signal; no playing-strength claim is
implied. The caller owns the random stream, independently of dealing cards.
"""

from collections import Counter
from random import Random

from pokerkit import StandardHighHand

POLICY_VERSION = "friends-1.0"
EQUITY_SAMPLES = 32
RANKS = "23456789TJQKA"
DECK = tuple(rank + suit for rank in RANKS for suit in "cdhs")

PROFILES = {
    "tight": {
        "entry": 0.48, "open_raise": 0.88, "call_margin": 0.10,
        "optimism": -0.035, "pair_attachment": 0.0,
        "value_raise": 0.70, "bluff": 0.055, "size": 0.65,
    },
    "calling": {
        "entry": 0.24, "open_raise": 0.12, "call_margin": -0.005,
        "optimism": 0.035, "pair_attachment": 0.16,
        "value_raise": 0.20, "bluff": 0.015, "size": 0.45,
    },
    "bold": {
        "entry": 0.32, "open_raise": 0.82, "call_margin": 0.015,
        "optimism": 0.105, "pair_attachment": 0.065,
        "value_raise": 0.88, "bluff": 0.23, "size": 0.85,
    },
}


def _preflop_strength(hole: list[str]) -> float:
    high, low = sorted((RANKS.index(card[0]) + 2 for card in hole), reverse=True)
    if high == low:
        return 0.45 + (high - 2) / 12 * 0.55
    strength = 0.05 + (high + low - 4) / 24 * 0.60
    strength += 0.10 if hole[0][1] == hole[1][1] else 0
    strength -= max(0, high - low - 1) * 0.022
    strength += 0.055 if high - low == 1 and high >= 7 else 0
    strength += 0.06 if low >= 10 else 0
    strength += 0.04 if high == 14 and low <= 5 else 0
    return min(1.0, max(0.0, strength))


def _random_range_equity(observation: dict, rng: Random) -> float:
    """Estimate showdown share from known cards, including fractional ties."""
    hole, board = observation["hole"], observation["board"]
    remaining = [card for card in DECK if card not in hole and card not in board]
    opponents = min(5, max(1, observation["opponents"]))
    missing = 5 - len(board)
    share = 0.0
    for _ in range(EQUITY_SAMPLES):
        sample = rng.sample(remaining, missing + 2 * opponents)
        runout = "".join(board + sample[:missing])
        hero = StandardHighHand.from_game("".join(hole), runout)
        hands = [hero]
        for seat in range(opponents):
            offset = missing + seat * 2
            hands.append(StandardHighHand.from_game("".join(sample[offset:offset + 2]), runout))
        best = max(hands)
        if hero == best:
            share += 1 / hands.count(best)
    return share / EQUITY_SAMPLES


def _features(observation: dict) -> tuple[bool, bool]:
    hole, board = observation["hole"], observation["board"]
    ranks = [RANKS.index(card[0]) + 2 for card in hole]
    board_ranks = [RANKS.index(card[0]) + 2 for card in board]
    top_pair = max(board_ranks) in ranks or (ranks[0] == ranks[1] and ranks[0] > max(board_ranks))
    # A draw must involve at least one hole card; a four-flush board alone is
    # not a personal flush draw. River draws have no remaining card to arrive.
    suits = Counter(card[1] for card in hole + board)
    flush_draw = any(count == 4 and any(card[1] == suit for card in hole) for suit, count in suits.items())
    unique = set(ranks + board_ranks)
    if 14 in unique:
        unique.add(1)
    straight_draw = any(
        len(unique.intersection(range(low, low + 5))) == 4
        and any(rank in range(low, low + 5) for rank in ranks)
        for low in range(1, 11)
    )
    return top_pair, len(board) < 5 and (flush_draw or straight_draw)


def _raise(observation: dict, profile: dict, rng: Random, reason: str) -> dict:
    legal = observation["legal"]
    current = observation["bet"] + legal["call_amount"]
    if observation["street"] == "preflop":
        target = max(3 * observation["big_blind"], current * (2.5 if current > observation["big_blind"] else 3))
    else:
        fraction = profile["size"] * rng.uniform(0.85, 1.15)
        target = current + (observation["pot"] + legal["call_amount"]) * fraction
    amount = max(legal["min_raise_to"], min(legal["max_raise_to"], round(target)))
    return {"action": "raise", "amount": int(amount), "reason": reason}


def choose_action(observation: dict, archetype: str, rng: Random) -> dict:
    """Choose a legal action. Amounts are integer street-total commitments."""
    profile = PROFILES[archetype]
    legal = observation["legal"]
    call = legal["call_amount"]
    free = legal["can_check"]
    late = observation["position"] in {"CO", "BTN"}
    can_raise = bool(legal["can_raise"] and legal["min_raise_to"] is not None and legal["max_raise_to"] is not None)

    if observation["street"] == "preflop":
        strength = _preflop_strength(observation["hole"])
        price_bb = call / observation["big_blind"]
        pressure = min(0.34, 0.045 * max(0, price_bb - 1) ** 0.65)
        position = -0.055 if late else (0.035 if observation["position"] in {"UTG", "HJ"} else 0)
        threshold = profile["entry"] + position + pressure
        playable = strength + rng.uniform(-0.045, 0.045) >= threshold
        if not playable and not free and legal["can_fold"]:
            return {"action": "fold", "reason": "这手牌不值得以当前价格入池"}
        raise_rate = profile["open_raise"]
        if price_bb > 2:
            raise_rate *= max(0.10, strength - 0.35)
        if archetype == "calling" and strength > 0.83:
            raise_rate += 0.34
        if can_raise and playable and rng.random() < raise_rate:
            return _raise(observation, profile, rng, "用主动下注争取位置与底池" if archetype == "bold" else "在自己的入池范围内下注")
        return {"action": "check_call", "reason": "先看下一张牌" if archetype == "calling" else "控制投入，继续这手牌"}

    equity = _random_range_equity(observation, rng)
    top_pair, draw = _features(observation)
    perceived = equity + profile["optimism"] + rng.uniform(-0.025, 0.025)
    if top_pair:
        perceived += profile["pair_attachment"]
    if draw and archetype == "bold":
        perceived += 0.06
    street_raises = sum(
        event.get("kind") == "raise" and event.get("street") == observation["street"]
        for event in observation.get("history", [])
    )
    # Public aggression matters to the disciplined opponent; the bold one
    # tends to retain its original read. This is a bias, not hidden knowledge.
    if archetype == "tight":
        perceived -= min(0.09, street_raises * 0.03)
    pot_odds = call / max(1, observation.get("eligible_pot_after_call", observation["pot"] + call))
    required = pot_odds + profile["call_margin"]
    if archetype == "tight" and call > observation["pot"] / 2:
        required += 0.055
    if not free and legal["can_fold"] and perceived < required:
        return {"action": "fold", "reason": "继续投入的价格超过了对这手牌的判断"}

    multiway = max(1, observation["opponents"])
    value_threshold = max(0.48, 1 / (multiway + 1) + 0.15)
    value_raise = perceived > value_threshold and rng.random() < profile["value_raise"]
    # Bluff more often with a draw, in position, and against fewer players.
    bluff_rate = profile["bluff"] * (1.5 if draw else 0.45) * (1.2 if late else 0.8) / multiway
    bluff_raise = (free or call <= observation["pot"] / 3) and rng.random() < bluff_rate
    if can_raise and (value_raise or bluff_raise):
        return _raise(observation, profile, rng, "借听牌向对手施压" if bluff_raise and draw else "下注争取价值或主动权")
    return {"action": "check_call", "reason": "仍然相信这手顶对" if top_pair and archetype == "calling" else "以当前价格继续，观察后续行动"}
