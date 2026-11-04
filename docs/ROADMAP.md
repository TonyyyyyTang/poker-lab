# Roadmap

Updated 4 November 2026. Owner-approved direction; scope constraints are in `AGENTS.md`.

Goal: a website where anyone can play the bots from a link, friends can share a private table without cards or chips, the bots adapt to how people play, and the review shows the quality of each decision.

## Decisions

- Hosting: free tier for now (Render's free web service is the current candidate; it sleeps after 15 idle minutes and restarts in about a minute).
- No accounts. A guest name and an invite link are enough.
- Play money only. Private invite tables and solo play against bots; no public lobby.
- In-memory state is acceptable until persistence is needed. A sleep or redeploy may end a table; the UI says so plainly.

## Phases

| Phase | Outcome | Owner | Status |
|---|---|---|---|
| 0. Public solo table | The current game at a public HTTPS link | Codex | Live at https://poker-lab.onrender.com |
| 1. Server-driven tables | The server runs bot turns and timers; each seat gets its own view; one table can seat several humans | Codex (backend), Claude (client) | Spec: `docs/tasks/server-driven-tables.md` |
| 2. Invite rooms | "Create table" returns a link; friends join with a name; empty seats are bots; live updates over WebSocket; turn timer, sit out, rejoin | Codex (backend), Claude (lobby and seat UI) | Not started |
| 3. Adaptive bots | Bots keep per-opponent statistics from public observations, with Bayesian shrinkage, and shift bluffing, value sizing and calling thresholds; personality sets how fast they adapt | Claude | Done; see `poker_lab/opponents.py` |
| 4. Decision review | Replay shows equity against an estimated range with its standard error, breakeven equity, call/fold EV under a stated simplification, and all-in-adjusted results | Claude | Not started |

Order rationale: Phase 0 gives a shareable link within days. Phase 1 is the structural change everything multiplayer depends on: today the browser asks the server to advance each bot turn, and seat 0 is assumed to be the only human. Phases 3 and 4 live in the bot and analysis code and do not wait for multiplayer.

Phase 1 concurrency follow-up: bot decisions currently run under the server's global `LOCK`. Before supporting many concurrent tables, capture an observation and decision version under the lock, compute the bot decision outside it, then revalidate the version before applying the action under the lock.

## Later candidates

Host settings (blinds, stacks, bot mix), shareable hand links, reactions instead of free chat, a session summary including what each bot learned about you, persistence of hand history, and a push/fold equilibrium trainer.

## Not planned

Real-money features of any kind, a public lobby with strangers, paid model calls, and claims of optimal (GTO) play.
