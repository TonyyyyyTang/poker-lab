@AGENTS.md

# Poker Lab — Claude Code notes

Shared rules live in `AGENTS.md` (Codex reads that file, not this one). This file adds Claude's role and working notes.

## Goal
A playable six-max no-limit hold'em practice table against fictional, behaviourally
distinct bots, growing into a clear demonstration of decisions under uncertainty:
equity, expected value, Bayesian opponent reads and tractable game-theoretic solutions.
Play money only.

## Structure
- `poker_lab/game.py` — `Table`: PokerKit 0.7.4 adapter. Dealing (seeded per hand),
  legal actions, settlement, seat observations, replay frames, last 20 hands.
  Integer chips, 2 units = 1 BB. Any seat can be human; the server runs bot turns,
  turn timers and (on shared tables) automatic dealing.
- `poker_lab/bots.py` — `choose_action(observation, style, rng)`; profiles `tight`,
  `calling`, `bold`. Preflop strength score vs position/price threshold; postflop
  32-sample Monte Carlo equity vs random hands plus style biases, shifted by
  opponent reads.
- `poker_lab/opponents.py` — per-table public opponent statistics with Beta priors;
  updated from each completed hand's public record, passed to bots as `reads`.
- `poker_lab/server.py` — stdlib HTTP; `HOST`/`PORT` from the environment (127.0.0.1:8765
  locally); in-memory cookie sessions (at most 100, 2 h idle expiry); JSON API under `/api/`.
- `web/` — buildless HTML/CSS/JS; long-polls `GET /api/state?after=<version>` while visible;
  invite links are `/t/<code>`.
- `tests/` — unittest: engine edge cases, observation isolation, determinism,
  policy differences, server versioning.

## Status (4 Nov 2026)
Working: full hand loop, five bots on three profiles that adapt to public opponent
statistics, time-correct replay, 38 tests. Live at https://poker-lab.onrender.com (Render free tier,
redeploys on push to `main`).
Known gaps: bot equity is vs random hands (noisy, range-blind); bot reasons and
policy/engine versions are discarded; per-hand action traces are not stored;
review gives one pot-odds note per hand; replay repeats the final step;
no persistence.

## Run
    python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python -m poker_lab.server            # http://127.0.0.1:8765
    .venv/bin/python -m unittest discover -s tests -v

## Code style
- Minimal and direct. Build what the feature needs; no speculative abstractions,
  aliases or fallbacks for inputs that cannot occur.
- No defensive bloat: trust internal contracts (PokerKit bounds, server version
  checks). Validate only at the HTTP boundary.
- Comment only non-obvious reasons. State a limitation once, where it applies.
- Keep files diff-friendly: one rule/statement per line, no minified CSS,
  no 1,000-character template literals.
- PokerKit decides legality and settlement. Bots and UI see only observations.
- Label estimates as estimates and report sample size or standard error.

## Working with Codex
Split by area, so the two agents rarely touch the same files:
- **Claude:** `web/` (table, controls, replay and review presentation) and the
  analysis layer — range equity, decision EV, Bayesian reads, small solvers —
  where the maths and how it is explained must both be right. Also task specs
  and reviews of Codex branches.
- **Codex:** engine adapter, server and API, persistence, bot plumbing, and the
  simulation/evaluation harness. Also reviews Claude branches.

Process:
- Codex works on `codex/<task>`, Claude on `claude/<task>`, both from `main`,
  one task per branch and worktree. Never edit the other agent's active branch.
- Specs go in `docs/tasks/<task>.md`: goal, required behaviour, acceptance checks,
  likely files, out of scope. When a task spans both areas, the spec fixes the JSON
  contract first; the backend side lands first.
- Review: read `git diff main...<branch>`, run the tests plus targeted probes,
  check the spec's acceptance items and the code style above, then report findings
  with file:line and a verdict (ready to merge / changes needed).
- The owner merges. Neither agent merges or pushes to `main`.
