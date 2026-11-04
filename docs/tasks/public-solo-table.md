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

The owner creates the Render account, connects the GitHub repository, and approves the first deploy. Agents never handle hosting credentials.

## Out of scope

Multiplayer, WebSockets, persistence, accounts, rate limiting, custom domain, and any change to game rules, bots or the web UI.
