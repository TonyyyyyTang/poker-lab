"""Opponent statistics built only from completed hands' public records.

Every seat sees the same public record (actions and showdown reveals), so one
ledger per table serves all bots. Counts are [hits, opportunities] so that each
rate has its own denominator; bots.py turns them into Beta-posterior estimates
with a personality-specific prior strength.

River bluffs are only observed when a river bet reaches showdown, so that rate
is conditional on being called; bluffs that won uncontested stay unseen.
"""

from pokerkit import StandardHighHand

# Population priors: what a bot assumes about a player it has not seen.
PRIORS = {"vpip": 0.35, "pfr": 0.18, "fold_to_bet": 0.30, "aggression": 0.45, "river_bluff": 0.25}


def estimate(counts: list[int], stat: str, strength: float) -> float:
    """Posterior mean of a Beta prior worth `strength` hands, after counts = [hits, n].

    Written as prior + correction so that no data returns the prior exactly.
    """
    hits, n = counts
    return PRIORS[stat] + (hits - n * PRIORS[stat]) / (n + strength)


def _weak_showdown(hole: list[str], board: list[str]) -> bool:
    """High card, or hole cards that do not improve on the board alone."""
    hand = StandardHighHand.from_game("".join(hole), "".join(board))
    board_only = StandardHighHand.from_game("".join(board[:2]), "".join(board[2:]))
    return hand.entry.label.name == "HIGH_CARD" or hand <= board_only


class OpponentStats:
    def __init__(self, seats: int = 6):
        self.counts = {seat: {stat: [0, 0] for stat in PRIORS} for seat in range(seats)}

    def snapshot(self) -> dict:
        return {seat: {stat: list(c) for stat, c in stats.items()} for seat, stats in self.counts.items()}

    def update(self, record: dict) -> None:
        """Add one completed hand: positions, public actions, revealed cards and board."""
        acted, entered, raised_pre = set(), set(), set()
        preflop_raised = False
        street_raised = set()
        for action in record["actions"]:
            seat, kind, street = action["player"], action["kind"], action["street"]
            stats = self.counts[seat]
            if street == "preflop":
                acted.add(seat)
                # The big blind's unraised check is not voluntary; every other call is.
                if kind == "raise" or (kind == "check_call" and (record["positions"][seat] != "BB" or preflop_raised)):
                    entered.add(seat)
                if kind == "raise":
                    raised_pre.add(seat)
                    preflop_raised = True
                continue
            facing = street in street_raised
            if facing:
                stats["fold_to_bet"][1] += 1
                stats["fold_to_bet"][0] += kind == "fold"
            if kind == "raise" or (facing and kind == "check_call"):
                stats["aggression"][1] += 1
                stats["aggression"][0] += kind == "raise"
            if kind == "raise":
                street_raised.add(street)
        for seat in acted:
            self.counts[seat]["vpip"][1] += 1
            self.counts[seat]["vpip"][0] += seat in entered
            self.counts[seat]["pfr"][1] += 1
            self.counts[seat]["pfr"][0] += seat in raised_pre
        river_bettors = {a["player"] for a in record["actions"] if a["street"] == "river" and a["kind"] == "raise"}
        for seat in river_bettors & record["shown"].keys():
            stats = self.counts[seat]["river_bluff"]
            stats[1] += 1
            stats[0] += _weak_showdown(record["shown"][seat], record["board"])
