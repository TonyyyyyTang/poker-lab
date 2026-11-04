# Architecture

Status: local implementation with public solo hosting configuration prepared, 4 November 2026. The design below includes later extensions, identified as proposals.

## Implemented slice

- `poker_lab/game.py`: PokerKit 0.7.4 adapter; fixed physical seats mapped to rotating engine positions; 2 integer units per BB; independently seeded dealing and policy streams; filtered seat observations; immutable public replay frames; recent hand history.
- `poker_lab/opponents.py`: per-table opponent statistics (entry, raising, folding to bets, aggression, shown river bluffs) counted from completed hands' public records, with Beta-prior estimates.
- `poker_lab/bots.py`: three configured heuristic policies, adjusted by those statistics according to each personality's trust and adaptation rate, using position, preflop selection, public aggression, approximate random-range showdown share and explicit biases. No external model calls.
- `poker_lab/server.py`: standard-library HTTP server bound to loopback by default, with `HOST`/`PORT` overrides for hosting, opaque per-browser session cookies (Secure behind HTTPS), versioned actions, serialised state changes, and an explicit static-file allowlist.
- `web/`: native HTML, CSS and JavaScript for the six-seat table, actions and post-hand replay. No frontend toolchain is required.
- `tests/`: adapter boundary tests and conditional policy comparisons.

Sessions and each session's last 20 completed hands are held in process memory. The server keeps at most 100 sessions, evicting the least recently used when full. Sessions idle for more than two hours are removed on API requests or health checks. Reloading a page resumes via its cookie; restarting the service clears them. No database is used. Render's free-service configuration is prepared but has not been deployed. Replay is visual history, not a branchable simulator yet. A deterministic seed and action trace exist inside each Table for verification, but are not sent through the public API.

PokerKit is MIT licensed and was selected after checking its documented full betting/settlement model. Its API is pinned and tested at 0.7.4. Each browser session is a solo table; multiplayer is a later phase.

## Core flow

```text
Player UI / Bot policy
        |
        v
Action validation -> Rules engine -> State transition -> Event log
                         |
                         v
                Seat-specific observations
                         |
                         v
               UI, policies and replay
```

The engine has full state. Each participant gets a separately constructed observation with only their own private cards and the information exposed by the rules. Never send a full state to a bot and ask it to ignore hidden fields.

## Small initial modules

### Game engine adapter

Wrap a proven rules engine behind a small interface. Keep betting, dealing, turn order, showdown and settlement here. Chip amounts use exact integer units. Minimum raises, short all-ins, reopened betting and side pots need explicit coverage.

### Observation and action contracts

A seat observation includes public board, visible stacks, current bets, pot information, position, public action history, that seat's hole cards and legal action bounds.

A proposed action identifies a legal action type and, where needed, a total bet amount in integer units. Define clearly whether a quantity means an increment or a street-total commitment. The server validates actions against the current hand and decision version, rejecting stale or illegal requests.

After a hand, information becomes visible only according to the game's showdown/reveal rules. An omniscient diagnostic view is separate and cannot feed live policies or coaching.

### Opponent policy

Each bot maps its observation, private policy state and an isolated random stream to a legal action. Policies must work without a language model.

Personality configuration affects hand selection, aggression, calling thresholds, sizing, uncertainty and risk appetite. Behaviour varies by position, stack depth, street and betting history. Avoid a single context-free aggression number masquerading as a complete policy.

Temporary state can alter specified parameters within bounds. Record the trigger and transition. Do not let a hidden-state update use unrevealed opponent cards or a later outcome.

### Opponent beliefs and memory

Store only observations that the bot legitimately made. Statistics use relevant decision opportunities as denominators and distinguish contexts such as position and street.

Bayesian updates or a small mixture of opponent hypotheses are potential extensions. Public actions and legitimately revealed cards may update beliefs; privileged diagnostic labels may not. Explain how limited samples affect certainty.

### Events and replay

Record actions, public transitions, configuration and engine/policy versions. For local development, keep a separate private trace of deck order, hidden state and RNG information for exact replay. A public hand-history export must redact private traces and unrevealed information by default.

Gameplay, each bot and optional language generation need separate random streams. Changing dialogue must not alter cards or policy decisions. Record LLM responses when used; a seed alone does not make remote model generation deterministic.

### Training and evaluation

Replay a decision from its original observation. Compare legal candidate actions using explicitly approximate range and rollout assumptions. Hand equity alone is not action expected value; include betting responses, future actions and costs where the approximation supports them.

Saved runs should support comparisons across seeds, seats and opponent mixes. Reuse controlled deals where appropriate and report uncertainty. Do not equate realised winnings with skill or generalise dominance against one weak bot to overall strength.

### Optional language layer

LLMs may provide character expression or explain recorded actions. They cannot control card dealing, chip accounting or legal-action validation. Explanations should be grounded in contemporaneous policy diagnostics rather than invented after seeing the result.

Keep provider calls behind a small optional adapter with timeout, budget, logging and a fallback. Live credentials and costs are future setup work, not part of this documentation handoff.

## Technology candidates

Python with PokerKit is a plausible rules/policy backend. A TypeScript browser UI, potentially React, can support a polished table and replay. A thin local API is a possible bridge.

Before choosing this split, check the game library's current license, API and hosting fit. Do not add an API service, database or WebSocket architecture simply to make the project sound sophisticated. The first implementation should use the smallest stack that supports correct play and deployment goals.

OpenSpiel is a research candidate for simplified games and learning methods, not an assumed plug-in solution for strong six-player no-limit agents.

## Product presentation

Lead with the usable table. Use legible card assets, stable player seats and action controls, restrained animation and a clear betting history. Personality should appear through actions and small touches, not long dialogue interruptions. Training views should let users see uncertainty and assumptions without turning play into a dashboard.

Visual theme, names and branding are still open. Avoid generic neon-casino styling or decorative clutter by default. Desktop and mobile framing require actual screenshot checks once implemented.

## Verification gates

- Unique cards, exact settlement and chip conservation, including side pots.
- Correct legal actions, turn order and short all-in handling.
- Hidden-card isolation in policy input, UI responses, exports and optional prompts.
- Same recorded configuration and action sequence reproduces the game state.
- Distinct bot behaviours are demonstrated by conditional action statistics and representative hands.
- Long sessions can advance without stalled turns or invalid actions.
- Decision feedback records its approximation and information set.
- No real-money functionality, live poker assistance, private data or secrets.

The first local version has 17 passing tests, including 100 simulated hands, and desktop/mobile browser checks. Later changes must rerun the relevant checks; these results do not establish optimal playing strength or a production hosting boundary.
