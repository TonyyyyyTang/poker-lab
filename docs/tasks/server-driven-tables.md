# Task: server-driven tables (Roadmap phase 1)

Backend: Codex, branch `codex/server-driven-tables`. Client: Claude, branch `claude/live-client`, built against the contract below. Each reviews the other.

## Goal

The server runs the game: bot turns, pacing and (optionally) turn timers happen on the server, and any seat can be human. Solo play looks and feels the same as today. Nothing multiplayer is exposed yet; invite links and names are phase 2. This phase removes the structural reasons that the code only works for one human in seat 0.

## Why

Today the browser drives the game: it calls `POST /api/step` every 850 ms to make the next bot act, and `game.py` assumes seat 0 is the only human (snapshot cards and legal actions, session net, hand net, review notes, replay frames that embed seat 0's cards, `step_bot`). With two humans at a table, both browsers would race to step bots and each would see the other's cards in replay.

## Required behaviour

### 1. Seats and per-viewer views (`game.py`)

- A table has a seat configuration: for each of the six seats, `kind` (`"human"` or `"bot"`), `name`, and `style` for bots. The current `PLAYERS` list becomes the default solo configuration (seat 0 human, seats 1–5 the existing bots).
- Replace `snapshot()` with `view(seat)`: the viewer's own hole cards plus cards revealed at showdown; `legal` populated only when `seat` is the actor; net and session totals for that seat.
- Store replay frames as public frames (no hole cards except revealed ones). When a seat requests a hand, return the frames with that seat's own hole cards added to every frame. Review notes are computed for the requesting seat.
- Track session net and per-hand net for every seat, not only seat 0.

### 2. Server-side bot driving

- Bots act on the server after a delay: `BOT_DELAY = 0.85` seconds, matching today's pace.
- When no human remains in the hand (all human seats have folded, or none is seated), bots act every `FAST_BOT_DELAY = 0.2` seconds. This removes today's ~7 s wait after you fold.
- The scheduling decision is a pure, testable method on the table (for example, given `now`, return the next due time or run every bot action that is due). A single background thread (or `threading.Timer` chain) only calls it. Tests drive it with an injected clock and must not sleep.
- Bot thinking runs outside any global lock. Read the observation under the table's lock, release it, compute `choose_action`, re-acquire, and apply only if the table version is unchanged.
- Replace the single global `LOCK` with one lock per table plus a small lock for the session and table registries. The current global lock is noted as a Phase 1 concern in `docs/ARCHITECTURE.md`.

### 3. Turn timer (mechanism only)

- A table setting `turn_seconds`, `None` by default (solo tables keep no timer).
- When it is set and a human seat does not act in time, the server checks if checking is free, otherwise folds. Covered by tests with an injected clock. No UI in this phase.

### 4. Sessions and tables

- A session maps a browser to `(table_id, seat)`. Tables live in their own registry so a table can later hold several sessions.
- `POST /api/session` creates a solo table (default configuration) with this browser in seat 0, exactly as today. `POST /api/reset` replaces it with a fresh solo table.
- Keep today's limits: at most 100 sessions with LRU eviction and a 2-hour idle expiry. A table is dropped once no session refers to it, and its bot schedule stops.
- `POST /api/next` (deal the next hand) is accepted from any human seated at the table. Automatic dealing is phase 2.
- Test, without new endpoints: seat two humans at one table programmatically, play a hand where both act, and confirm each view and each replay contains only that seat's own hole cards.

### 5. Updates to the browser: long polling

- `GET /api/state?after=<version>` returns the viewer's view immediately if the table version is greater than `after`, otherwise waits until it changes or 25 seconds pass, then returns the current view. `GET /api/state` with no `after` returns immediately.
- Waiting requests block on a per-table `threading.Condition`, not by polling in a loop.
- `POST /api/step` is removed.

## JSON contract

The view keeps every field of today's snapshot, with these changes:

| Field | Change |
|---|---|
| `you` | New. The viewer's seat index. |
| `players[i].kind` | New. `"human"` or `"bot"`. |
| `players[i].cards` | The viewer's own cards, revealed cards, otherwise `[]`. |
| `legal` | Populated only when `current_actor == you`; otherwise the existing all-false shape. |
| `session_net` | The viewer's own session net. |
| `players[i].net` | Unchanged meaning (each seat's net for a completed hand). |

`/api/history` and `/api/hand/<id>` return the same shapes as today, with `net`, notes and own hole cards for the requesting seat.

Endpoints after this phase: `POST /api/session`, `POST /api/reset`, `POST /api/action`, `POST /api/next`, `GET /api/state[?after=N]`, `GET /api/history`, `GET /api/hand/<id>`, `GET /healthz`.

## Client (Claude, in parallel)

`claude/live-client` replaces the 850 ms `/api/step` timer in `web/app.js` with a long-poll loop on `GET /api/state?after=<version>`, uses `you` instead of assuming seat 0, pauses polling while the tab is hidden (an open tab's polls count as traffic and would keep the free server from sleeping), and restarts after errors and when the tab becomes visible. No visual change.

## Merge order

The two branches only work together. The owner merges `codex/server-driven-tables`, then `claude/live-client`, and pushes once, so the live site never runs one without the other.

## Acceptance checks

- All existing tests pass, updated where they used `snapshot()` or `step_bot`.
- New tests: per-seat views and replays never contain another seat's unrevealed cards (two humans at one table); bot scheduling with an injected clock, including the fast pace once no human remains in the hand; stale bot decisions are discarded when the version changed during thinking; the turn timer checks or folds; long-poll returns immediately on a newer version and after the timeout otherwise; tables are dropped with their last session.
- With both branches merged, local play is unchanged: a full hand, replay, history, next hand, reset, reload resumes the session, desktop and phone.
- After folding, the rest of the hand finishes in about 2 seconds rather than about 7.

## Out of scope

Invite links, guest names, joining a table, WebSockets, lobby or seat UI, a turn-timer UI, persistence, automatic dealing, and any change to bot policy.

## Backend handoff — 4 November 2026

Implemented on `codex/server-driven-tables`. `Table(players=...)` accepts six human/bot seat configurations; `view(seat)`, `history(seat)` and `hand(hand_id, seat)` project the specified JSON contract. Stored replay frames are public, with original hole cards kept separately and only the viewer's cards added to responses. Nets and notes are per seat. Sessions bind to table IDs and human seats; removing the last binding closes the table and wakes its polls.

`Table(clock=..., turn_seconds=...)` supports deterministic deadline tests; `run_due()` performs one due action. The server starts one background driver in `main`. Policy computation uses detached observations and RNG copies outside both locks, and stale results leave the live RNG unchanged. Long polls use the per-table condition with a 25-second timeout; reset and expiry also wake them. `/api/step` returns 404. `web/`, bot policies and dependencies are unchanged.

Verification: all 56 tests pass on Python 3.13.2, including two-human privacy, replay/net/notes, rotated seats, fake-clock pacing and timeouts, stale thinking, session eviction, reset during a long poll and the exact response keys. Local HTTP smoke checks on port 18766 passed a complete hand, long-poll bot updates, history, replay, next hand, reset and cookie-based resume. The sampled post-fold hand completed in 3.24 seconds; unit tests verify the required 0.2-second per-action pace, with total duration depending on the number of actions. The temporary server was stopped after verification.

Pending: combined desktop/phone checks with `claude/live-client`. The owner merges the backend, then the client, and pushes once. No deployment was performed.
