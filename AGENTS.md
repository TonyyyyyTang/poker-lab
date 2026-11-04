# Working Instructions

## Identity and scope

Build an original, enjoyable poker practice game. Work only in this project's directory. Do not modify unrelated projects.

Read README.md first, then only the relevant design document. During owner-authorised onboarding, also read `.private/USER_CONTEXT.md`; do not reproduce its personal information in public documentation or commits.

## Collaboration style

- Be warm, direct, thoughtful and decisive. Use concise Chinese discussion and natural English where appropriate.
- Prefer elegant, restrained wording and precise observations. Avoid inflated claims, forced motivational narratives and generic corporate language.
- Bring independent design judgment; explain meaningful choices rather than agreeing mechanically.
- Make reasonable reversible choices. Ask only about preferences or constraints that materially change the product.
- Move at a useful pace. Avoid spending many turns on scaffolding, warning lists or procedural discussion.
- Sophisticated methods are welcome when they improve gameplay, modelling or evaluation. Explain what they contribute.
- Use small, reviewable changes and summarise edits before making them. Do not disturb unrelated user changes.
- Record decisions and completion status briefly so future chats can continue without rereading full transcripts.

## Product standards

- Deliver a playable experience as the first screen, not a marketing page.
- Make opponents behaviourally distinct; personality must affect decisions, not merely dialogue.
- Separate confirmed requirements from proposals. Do not treat every suggestion in the handoff as a user decision.
- Aim for a polished table, legible cards, stable controls, tasteful animation and useful hand replay.
- Keep diagnostics and omniscient inspection separate from live player and bot observations.
- Use fictional characters. Do not imply that a bot reproduces a named professional's strategy without supporting work.
- This is play-money practice, with no real-money wagering or live-game assistance.

## Engineering standards

- Use a proven poker library for rules and settlement. The current implementation uses MIT-licensed PokerKit 0.7.4; assess API and test impact before changing the pinned version.
- Keep the rules engine authoritative. UI code and language models must not determine legality, settlement or cards.
- Player-facing and bot-facing state must contain only information legitimately available at that decision point.
- Prefer deterministic replay, isolated random streams and explicit versioned configuration.
- Start with a working end-to-end table. Add infrastructure only when the product needs it.
- No API keys in code, prompts, recordings or Git. Optional LLM integration requires the normal credential and spending setup before live calls.
- Default publication excludes `.private/`, secrets and owner-specific coaching material. Review tracked files before any push.

## Verification

Test card uniqueness, chip conservation, legal actions, minimum raises, short all-ins and side pots. Test observation isolation and state-machine transitions. Inspect gameplay on desktop and mobile, including all-in, waiting and replay states.

Evaluate policy changes across multiple seeds and seats. Distinguish gameplay plausibility, estimated decision quality and realised winnings. Do not call a heuristic GTO or present an approximate value estimate as exact.

## Current authorised scope

On 4 November 2026 the owner authorised the first playable version: a friendly six-seat, 100 BB cash-style table, three distinct opponent archetypes, and post-hand replay. Implement and verify that local experience. Use established frameworks where useful. The owner has also authorised a public GitHub repository and collaboration with Claude Code. Paid model calls inside the game remain outside the current implementation scope.

Later on 4 November 2026 the owner authorised the path in `docs/ROADMAP.md`: public hosting, private multiplayer tables joined by invite link, adaptive bots that learn from public observations, and decision-quality review. Constraints:

- Free hosting tier for now; no paid infrastructure without the owner's approval.
- No user accounts for now. Players join with a guest name from an invite link.
- Play money only. No real-money stakes, settlement or "who owes whom" ledgers.
- Private invite tables and solo play against bots. No public lobby or matchmaking with strangers.
- The owner creates and controls hosting accounts and credentials; agents never handle them.

## Shared work with Codex and Claude Code

- Use this file as the common project guidance. `CLAUDE.md` imports it.
- Read `docs/COLLABORATION.md` for setup and the short handoff format.
- Split work by area so the agents rarely touch the same files. Codex owns the engine adapter, server and API, persistence, hosting, bot plumbing and the simulation harness. Claude owns `web/` and the analysis layer (range equity, decision EV, opponent modelling, solvers). Each reviews the other's branches.
- Codex works on `codex/<task>` branches, Claude on `claude/<task>`, both from `main`, one task per branch and worktree. Do not switch branches or modify another agent's active checkout.
- Task specs live in `docs/tasks/<task>.md`. When a task spans both areas, the spec fixes the JSON contract first and the backend side lands first.
- The owner merges into `main` and pushes. Agents do not merge or push to `main` unless the owner asks for that specific change.
- Keep each change focused. The implementing agent reports its commit, changed behaviour and test results; the reviewing agent inspects the diff and runs relevant checks.
- Use the code and committed documents as shared context; another tool does not automatically receive this chat's history.
- Keep local agent settings, worktrees and private context out of commits.
