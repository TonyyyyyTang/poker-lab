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
| 0. Public solo table | The current game at a public HTTPS link | Codex | Spec: `docs/tasks/public-solo-table.md` |
| 1. Server-driven tables | The server runs bot turns and timers; each seat gets its own view; one table can seat several humans | Codex | Not started |
| 2. Invite rooms | "Create table" returns a link; friends join with a name; empty seats are bots; live updates over WebSocket; turn timer, sit out, rejoin | Codex (backend), Claude (lobby and seat UI) | Not started |
| 3. Adaptive bots | Bots keep per-opponent statistics from public observations, with Bayesian shrinkage, and shift bluffing, value sizing and calling thresholds; personality sets how fast they adapt | Claude | Not started; can run alongside 1–2 |
| 4. Decision review | Replay shows equity against an estimated range with its standard error, breakeven equity, call/fold EV under a stated simplification, and all-in-adjusted results | Claude | Not started |

Order rationale: Phase 0 gives a shareable link within days. Phase 1 is the structural change everything multiplayer depends on: today the browser asks the server to advance each bot turn, and seat 0 is assumed to be the only human. Phases 3 and 4 live in the bot and analysis code and do not wait for multiplayer.

## Later candidates

Host settings (blinds, stacks, bot mix), shareable hand links, reactions instead of free chat, a session summary including what each bot learned about you, persistence of hand history, and a push/fold equilibrium trainer.

## Not planned

Real-money features of any kind, a public lobby with strangers, paid model calls, and claims of optimal (GTO) play.
