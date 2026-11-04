# Task: invite tables (Roadmap phase 2)

Backend: Codex, branch `codex/invite-tables`. Client: Claude, branch `claude/invite-client`, built against the contract below. Each reviews the other; the owner merges both and pushes once.

## Goal

From the solo table, a player creates a shared table and gets a link. Friends open the link, type a guest name and take a seat; seats nobody has taken are played by the bots. Turns have a timer, players who drift away stop holding up the table, and anyone can leave and come back. Solo play stays the first screen and is unchanged.

## Decisions

- **Long polling, no WebSockets.** Phase 1's `GET /api/state?after=` already delivers each change within one round trip. A table has at most six players and about one change per second. WebSockets would add a dependency and a second connection path without a visible gain. Revisit only if latency becomes a real complaint.
- **No accounts.** A browser's session cookie is its identity. A guest name is display text only.
- **The invite link is the only key.** Anyone holding it can join. No public lobby, no table list.
- **Play money only.** Every human who takes a seat starts with 100 BB; there is no buy-in, ledger or settlement.

## Required behaviour

### 1. Shared tables

- `POST /api/tables` with `{name}` creates a shared table with the caller in seat 0 under that guest name and bots in seats 1–5, using the existing bot names and styles. The name is required and validated exactly like `/api/join`: trim, require 1–12 characters, reject control characters. Invalid names return 400 without changing the current binding. It replaces the caller's current binding (a solo table with no other session is dropped, as with reset).
- Each shared table has an invite code: `secrets.token_urlsafe(8)`, unguessable, distinct from the internal table id.
- Shared tables use `turn_seconds = 30` and deal the next hand automatically `AUTO_DEAL_SECONDS = 5` after a hand ends; any seated human may deal sooner with `POST /api/next`. Solo tables keep no timer and manual dealing.
- When no human is active (every seated human is away or leaving, with no pending joiners), pause scheduled play, human timers and automatic dealing. Returning with `/api/back` or a valid action resumes play. A pending join also resumes scheduling so the newcomer can reach the next deal. Resumption starts a fresh deadline; unrelated join/leave/back events do not extend an existing turn.
- Actions retain the existing `{version, action, amount?}` payload. Accept a version from the start of the current decision through the current table version: join/leave/back notifications do not invalidate a still-current action. A completed action or new deal starts a new decision boundary; earlier, future and replayed action versions are rejected. `/api/next` still requires the current version.

### 2. Joining

- `GET /t/<code>` serves the same `index.html` (add the path to the static allowlist; no other change to static serving).
- `POST /api/join` with `{code, name}`:
  - Validate the name at this boundary: strip it, require 1–12 characters, reject control characters. If another seated human uses the same name, append ` 2`, ` 3` and so on.
  - Take the lowest-numbered seat currently played by a bot. If none is left, return 409 "这张桌已经坐满了。".
  - If the session is already seated at this table, return its current view (reopening the link is not a second join).
  - An unknown code returns 404.
- **Joining mid-hand.** The bot keeps playing that seat until the hand ends. The joiner is *pending*: their view shows only public information, with no hole cards for that seat, and no legal actions. At the next deal the seat becomes human with a fresh 100 BB stack.

### 3. Leaving and coming back

- `POST /api/leave`: the seat returns to its original bot at the next deal, with 100 BB. If the human is in a live hand, they are folded when their turn comes (fold if facing a bet, otherwise check). The session is moved to a fresh solo table and the response is that table's view.
- **Away.** A human who times out twice in a row is marked away. While away, their turns are taken immediately (check if free, otherwise fold), without waiting for the timer. Any action from them, or `POST /api/back`, clears it.
- Rejoining after a reload is not a new join: the cookie still maps to the seat.

### 4. Seat ownership resets

When a seat changes occupant (bot to human, human to bot, or one human to another), reset that seat's session net, per-hand history entries for the new occupant, and its `OpponentStats` counts. The bots must not carry reads about one person over to someone else in the same chair.

### 5. Isolation

Pending, away and departed players see exactly what a seated player would see about other seats: never another seat's unrevealed cards, including the cards of the bot still playing the joiner's seat. Replays and history requested by a seat cover only hands played by that seat's current occupant.

## JSON contract

View additions (all other fields unchanged):

| Field | Meaning |
|---|---|
| `table.shared` | `true` for invite tables, `false` for solo. |
| `table.invite` | The invite code on shared tables, otherwise `null`. The client builds the link as `<origin>/t/<code>`. |
| `pending` | `true` while the viewer waits for the next deal to take their seat. |
| `players[i].away` | `true` when that human is marked away. |
| `players[i].leaving` | `true` when that human has left and the seat returns to its bot at the next deal. |
| `turn_remaining` | Seconds left for the current human actor, or `null` (bots, solo tables, no hand). The client counts down locally from the response time. |
| `next_hand_in` | Seconds until the automatic deal on shared tables, or `null`. |

Endpoints added: `POST /api/tables`, `POST /api/join`, `POST /api/leave`, `POST /api/back`, and `GET /t/<code>` (HTML).

## Client (Claude, in parallel)

- An "邀请朋友" control on the solo table creates a shared table and shows the link with a copy button.
- Opening `/t/<code>` with no seat at that table asks for a guest name, then joins. A pending player sees the table with a "下一手入座" notice.
- A visible countdown for the acting human, away and leaving markers on seats, "我回来了" when away, a leave control, and a countdown before the automatic deal.

## Acceptance checks

- Existing tests pass.
- New tests, with an injected clock where timing matters: create a table and join it through HTTP with two cookies, then play a hand where both humans act; a mid-hand joiner never receives the bot's hole cards for their seat, in live views or replays; the seat becomes human at the next deal with 100 BB; leave folds or checks the departing player and returns the seat to its bot at the next deal; two timeouts mark a player away, away turns resolve immediately, and an action clears away; automatic dealing after 5 seconds on shared tables only; name trimming, length, control characters and duplicate suffixes; unknown code (404) and full table (409); seat changes reset session net, history and opponent statistics for that seat.
- With both branches merged, two browsers (for example a normal and a private window) play several hands together locally and then on Render, on desktop and phone, including a join mid-hand, a timeout, away and back, and a leave.

## Out of scope

Host controls (blinds, stacks, bot mix, removing a player), chat or reactions, spectators who never take a seat, persistence across server restarts, and any change to bot policy.
