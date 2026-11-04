# Task: public solo table (Roadmap phase 0)

Owner: Codex, branch `codex/public-solo-table`. Reviewer: Claude.

## Goal

The current solo game (one human, five bots) is playable at a public HTTPS URL on Render's free tier. Gameplay does not change. Local play keeps working exactly as today.

## Required behaviour

1. **Binding.** The server reads `HOST` (default `127.0.0.1`) and `PORT` (default `8765`) from the environment; `--port` still works locally. Render sets `PORT` and needs `HOST=0.0.0.0`.
2. **Origin check behind HTTPS.** `server.py` currently accepts a POST only when `Origin == "http://" + Host`. Behind Render's proxy the browser sends `https://…`, so every action would be rejected with 403. Compare the origin's host and port with the `Host` header instead, and accept either scheme.
3. **Cookie.** Add `Secure` to the session cookie when the request arrived over HTTPS (`X-Forwarded-Proto: https`). Keep `HttpOnly; SameSite=Strict`.
4. **Memory bounds.** One session holds about 12 MB after 100 hands (measured with `tracemalloc`: frames are deep-copied snapshots), and the free instance has 512 MB.
   - Keep the last 20 completed hands per session (currently 100).
   - Cap live sessions at 100. When full, evict the least recently used one.
   - Drop sessions idle for more than 2 hours.
   - Make the three limits module constants, not configuration layers.
5. **Restart recovery.** When the instance sleeps or redeploys, sessions vanish. A returning browser gets 401, the existing error banner appears, and "重新连接" starts a fresh table. Confirm this works; change the banner text only if it is misleading.
6. **Health check.** `GET /healthz` returns 200 with a tiny body and no session.
7. **Deployment config.** Add a `render.yaml` (Python web service, free plan, `pip install -r requirements.txt`, start `python -m poker_lab.server`, `HOST=0.0.0.0`, health check `/healthz`) and pin the Python version Render should use.
8. **Docs.** Update README: the public URL once it exists, "last 20 hands", and a short note that a sleeping free instance takes about a minute to wake and resets tables.

## Acceptance checks

- Existing tests pass. New tests cover: the origin check (same host over http and https accepted, foreign origin rejected), the `Secure` flag with and without `X-Forwarded-Proto`, LRU eviction at the cap, idle expiry, the 20-hand history limit, and `/healthz`.
- Local run unchanged: `.venv/bin/python -m poker_lab.server` serves on `127.0.0.1:8765`.
- On the deployed URL: play a full hand, open the replay, and start the next hand, on desktop and on a phone.
- After a manual redeploy, the open page recovers through "重新连接".

## Owner steps

The owner controls the Render account and all hosting credentials. Agents never handle hosting credentials.

1. Create the Render account, connect the GitHub repository, and approve the first deploy using `render.yaml` on the free plan. The configuration installs `requirements.txt`, starts `python -m poker_lab.server`, sets `HOST=0.0.0.0`, uses Render's `PORT`, and checks `/healthz`. `.python-version` pins Python 3.13.2.
2. Verify the public HTTPS URL and add it to README.
3. On desktop and phone, play a complete hand, open its replay, and start the next hand.
4. With a page open, manually redeploy; trigger another request and verify **重新连接** starts a fresh table.

## Out of scope

Multiplayer, WebSockets, persistence, accounts, rate limiting, custom domain, and any change to game rules, bots or the web UI.

## Implementation handoff — 4 November 2026

Implemented on `codex/public-solo-table`: environment binding, HTTP/HTTPS origin checks, proxy-aware Secure cookies, 20-hand history, 100-session LRU with two-hour idle expiry, `/healthz`, and Render free-service configuration pinned to Python 3.13.2. The 401 message now explains that reconnecting starts a fresh table; the existing web UI and JSON shapes are unchanged.

Verification: all 29 unit tests pass on Python 3.13.2. Local browser checks on port 18765 passed for completing a hand, opening and advancing replay, and dealing the next hand. Restarting that test server with the page open produced the session-loss banner on the next action; **重新连接** cleared it and started hand 1 with fresh stacks. Default binding and environment/CLI overrides are covered by server-construction tests; the existing local server on port 8765 was left running.

Pending owner steps: deployment, adding the public HTTPS URL, desktop/phone checks on that URL, and reconnect after a Render redeploy. No deployment or hosting credential access was performed.

Review follow-up: merged `main` with adaptive bots, keeping both the opponent-model and hosting descriptions in the architecture document. Simplified Origin validation to HTTP/HTTPS host-and-port comparison and moved the owner checklist here from README. The combined suite passes all 36 tests. The global-lock bot-computation follow-up is recorded under Phase 1 in the roadmap.
