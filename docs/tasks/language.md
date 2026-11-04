# Task: Chinese and English, chosen by the player

Backend: Codex, branch `codex/language-data`, based on `codex/invite-tables`. Client: Claude, branch `claude/language`, based on `claude/invite-client`. Each reviews the other; the owner merges all four branches and pushes once.

## Goal

A 中 / EN switch in the top bar sets the whole interface to one language, remembered on the device and defaulting to the browser's language. Today the page mixes English labels with Chinese text, and the server writes Chinese sentences into the data, so the browser cannot render anything else.

## Principle

The server sends language-neutral data: codes, seat numbers and amounts. The browser owns every word the player reads. Server error bodies keep a short English `error` for logs and as a fallback.

## Server changes (Codex)

1. **Errors.** Every non-2xx JSON body is `{"code": ..., "error": ...}`. Codes:

   | Code | When |
   |---|---|
   | `expired` | Session or table gone (401) |
   | `not_found` | Unknown endpoint or static path |
   | `hand_not_found` | Hand not finished or outside the last 20 |
   | `invite_not_found` | Unknown or closed invite code |
   | `table_full` | No bot seat left to take |
   | `bad_name` | Guest name fails validation |
   | `bad_request` | Malformed JSON, oversized body, bad `after` or `version` |
   | `stale` | Version mismatch: the table changed first |
   | `not_your_turn` | Seat is not the actor, or the hand is over |
   | `illegal_action` | Fold/check/raise not allowed, amount out of range, unknown action |
   | `hand_in_progress` | Next hand requested before the current one ends |
   | `not_seated` | Pending, departed or bot-controlled seat tried to act |
   | `forbidden_origin` | Cross-site POST |
   | `server_error` | Unexpected exception (500) |

2. **Actions.** Each entry in `actions` is `{player, kind, amount, street, all_in}` with `kind` in `fold`, `check_call`, `raise`. `amount` keeps today's meaning (street total for a raise, chips added for a call). Drop `text`.
3. **Last action per seat.** `players[i].last_action` is `null` or `{kind, amount, all_in}` with `kind` in `small_blind`, `big_blind`, `fold`, `check`, `call`, `raise`. Drop the Chinese label.
4. **Hand result.** Replace `summary` with `winners: [{seat, amount, name, name_en}]` (amounts are positive payoffs; an empty list means nobody won chips) and add `rebuys: [seat]` for seats topped up at the start of the current hand. Every winner entry in views, replay frames, history and hand replies carries the names that seat had when the hand ended. These historical names remain unchanged when a new occupant takes the seat at a later deal. History entries carry `winners` instead of `summary`.
5. **Review notes.** `notes` becomes a list of objects:
   - `{"kind": "result", "actions": n, "net": units}`
   - `{"kind": "pot_odds", "street": s, "call": units, "eligible": units, "required": percent}` (`required` rounded to one decimal)
   - `{"kind": "visibility"}`
6. **Names.** Each player has `name_en` beside `name`: 阿岚 A-Lan, 小满 Xiaoman, Leo Leo, 知夏 Zhixia, 老周 Lao Zhou, 阿禾 A-He, and the solo player's default 你 → You. For guests `name_en` equals the name they typed.

Replay frames and history use the same shapes. No other JSON changes.

## Client changes (Claude)

- One string table per language (`zh`, `en`) for every visible string, including the static page, dialogs, countdowns, error codes and the composed texts above (action log, seat labels, winners, rebuys, notes).
- A 中 / EN switch in the top bar; the choice is stored in `localStorage` (with a safe fallback) and sets `<html lang>`.
- Bot names follow the chosen language; guest names are shown as typed.

## Acceptance checks

- Server tests updated for the new shapes; new tests cover each error code at its trigger, `last_action` for blinds, calls, raises and all-ins, `winners` and `rebuys`, structured notes, and that no Chinese text remains in any JSON response (a test can scan responses for CJK characters other than player names).
- With all four branches merged: every screen (table, actions, hand end, replay, history, invite, join, away, errors) shows only the chosen language, on desktop and phone, and switching language mid-hand re-renders without a reload.

## Out of scope

Server-side language negotiation, translating names typed by players, and any other language.
