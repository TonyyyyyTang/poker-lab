# Project Brief

Updated: 4 November 2026.

## Product

Poker Lab is a Texas hold'em practice game with the atmosphere of a friendly home game. The central experience is to observe recognisable, imperfect opponents, develop a view of their tendencies and adjust your decisions.

The first playable version uses six-max no-limit hold'em, 100 BB cash-style starting stacks, 0.5/1 BB blinds, no rake, five fictional regulars and post-hand review. Two opponents use a tight/aggressive policy, two a loose/calling-heavy policy, and one an aggressive/overconfident policy. Stacks carry across hands; players below 1 BB replenish to 100 BB.

The local implementation uses PokerKit 0.7.4, a small Python service and a buildless browser interface. It supports complete legal betting and settlement, chronological hand replay and a limited pot-odds observation. These are heuristic opponents; no optimal strategy or measured playing strength is claimed.

## Behavioural direction

Opponents should make interpretable choices rather than arbitrary random mistakes. Existing policy differences include hand selection, position sensitivity, calling thresholds, aggression, sizing and optimistic hand evaluation.

Further modelling ideas include:

- Persistent biases, such as attachment to top pair or optimistic draw evaluation.
- Temporary fatigue, urgency, tilt or caution triggered by public outcomes.
- Memory of revealed bluffs, public betting patterns and prior confrontations.
- Different quality of range estimates and uncertainty.

These are exploratory game models, not validated psychological models. Bots now learn public statistics about each player within a table session (`poker_lab/opponents.py`); temporary states and memory across sessions have not been implemented.

## Possible next experiences

- Hide style labels and let players form and revise reads.
- Configure deep stacks, loose tables or other practice scenarios.
- Save history across sessions and branch from a past decision.
- Reveal behaviour summaries with supporting examples after a session.
- Give approximate decision feedback based on information available at the time.
- Let opponents adapt to one another and the player using public evidence.

These extensions remain proposals. The first playable table and its current controls should stay understandable and enjoyable as depth is added.

## Growth path

1. Refine the playable table, distinct policies and replay.
2. Add temporary states and public-history memory.
3. Develop scenarios and approximate decision comparisons.
4. Study opponent inference and adaptation through controlled experiments.
5. Optionally add character expression grounded in recorded decisions.

The game should remain playable without external model calls. Formal game-theoretic learning should begin with tractable simplified games before making claims about full multiplayer no-limit hold'em.

## Success

A player wants to return. A friend can recognise differences between opponents. A technical reader can trace an action to the policy's legitimate observation and random stream. Demonstrations and research claims are supported by saved runs.

## Public references

- [PokerKit documentation](https://pokerkit.readthedocs.io/en/stable/)
- [OpenSpiel](https://github.com/google-deepmind/open_spiel), a possible research environment for simplified games
