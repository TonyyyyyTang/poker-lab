# Poker Lab · 德州训练场

A quiet, friendly six-seat hold'em table with opponents whose habits affect how they play.

The first local playable version uses 100 BB starting stacks, 0.5/1 BB blinds, no rake, five fictional opponents, and post-hand replay. Stakes are simulated. PokerKit 0.7.4 handles legal actions and settlement; a small Python server serves the table. No API keys, model calls, Node installation or frontend build are needed.

![Poker Lab table](outputs/poker-lab-preview.jpg)

## Play locally

Requires Python 3.11 or newer. From this project directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m poker_lab.server
```

Open <http://127.0.0.1:8765>. On macOS, `start.command` also starts the table (and installs the requirement on its first run if the virtual environment is absent). Keep its terminal running while playing; Ctrl-C stops it. Use `--port 8766` if the default port is in use.

Play a hand, review it after settlement, then deal the next one. All raise amounts are **the total committed on the current street**, displayed in BB. The dealer moves each hand; stacks carry forward. A stack below 1 BB is replenished to 100 BB before the next hand, with a table notice. Session profit excludes these replenishments.

## The five regulars

- 阿岚 and 知夏 are selective and aggressive, with greater respect for price and public aggression.
- 小满 and 老周 enter more pots, prefer calling, and become attached to top pair.
- Leo applies pressure, bluffs more, and tends to overestimate his hand.

These are deliberately imperfect heuristic policies, not GTO agents. Postflop decisions use a small Monte Carlo estimate against random holdings, together with position, pot odds, draw features and style biases. This is a rough internal signal, not a claim about optimal action value.

## Replay and information boundaries

The browser receives your hole cards and legitimately revealed opponent cards. Bots receive their own cards plus public observations through a separate contract. Neither receives the full deck or other hidden cards. Replay frames preserve what was visible at each point; later showdown information is not backfilled into earlier frames.

The latest 20 completed hands are available in each session. Refreshing the browser resumes its session; restarting the server clears sessions and history. Sessions expire after more than two hours without activity. At most 100 sessions are kept; a new one at that limit replaces the least recently used session. Replay includes a pot-odds observation where applicable, but does not grade decisions by their outcome. Long-term opponent learning and temporary moods remain future work.

## Public solo hosting

The repository includes `render.yaml` for a free Render Python web service and `.python-version` pins Python 3.13.2. The service installs `requirements.txt`, starts `python -m poker_lab.server`, sets `HOST=0.0.0.0`, and uses Render's `PORT`. `GET /healthz` checks availability without creating a table. Locally, `HOST` and `PORT` default to `127.0.0.1` and `8765`; `--port` overrides `PORT`.

Each browser gets its own solo table. Render's free service sleeps after 15 minutes without incoming traffic and takes about a minute to wake. Sleep or redeployment resets in-memory tables and history. An open page reports the lost session on its next request; choose **重新连接** to start a fresh table. See [Render's free-service behaviour](https://render.com/docs/free#spinning-down-on-idle).

There is no public URL yet. The owner creates the Render account, connects the repository, and approves the first deployment; hosting credentials stay outside this project. After deployment, add the verified HTTPS URL here, play a complete hand, open its replay and start the next hand on desktop and phone, then verify **重新连接** after a manual redeploy.

## Verify

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests cover the adapter's legal-action boundaries, short all-ins, side pots, replay visibility, deterministic dealing and chip accounting, plus conditional differences between opponent policies. Card dealing and each bot use separate random streams.

## Project notes

- [Working instructions](AGENTS.md)
- [Product brief](docs/PROJECT_BRIEF.md)
- [Roadmap](docs/ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Working with Codex and Claude Code](docs/COLLABORATION.md)
- [PokerKit](https://github.com/uoftcprg/pokerkit), MIT-licensed rules engine ([documentation](https://pokerkit.readthedocs.io/en/stable/))

Private owner context stays in `.private/` and is excluded from Git and the server's static file allowlist. The project currently runs locally and has no public deployment.
