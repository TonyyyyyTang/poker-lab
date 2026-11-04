"""HTTP sessions, long polling and server-driven tables. PokerKit is authoritative."""
from collections import OrderedDict
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import threading
import time
import unicodedata
from urllib.parse import parse_qs, urlsplit

from .game import HAND_HISTORY_LIMIT, PLAYERS, Table

ROOT = Path(__file__).resolve().parent.parent
MAX_SESSIONS = 100
SESSION_IDLE_SECONDS = 2 * 60 * 60
LONG_POLL_SECONDS = 25
REGISTRY_LOCK = threading.RLock()
WAKE = threading.Event()


@dataclass
class Session:
    table_id: str
    seat: int
    last_seen: float
    active: bool = True


SESSIONS: OrderedDict[str, Session] = OrderedDict()
TABLES: dict[str, Table] = {}


def _retire_binding(session):
    """Registry helpers hold REGISTRY_LOCK; never acquire it while holding a table lock."""
    table = TABLES[session.table_id]
    with table.changed:
        session.active = False
        remaining = [s for s in SESSIONS.values() if s.table_id == session.table_id]
        if not remaining:
            del TABLES[session.table_id]
            table.close()
        else:
            if not table.closed and not any(s.seat == session.seat for s in remaining):
                table.leave(session.seat)
            # A reset/eviction must also wake polls on a table still used by other seats.
            table.changed.notify_all()
    WAKE.set()


def _drop_session(sid):
    _retire_binding(SESSIONS.pop(sid))


def _expire_sessions(now):
    while SESSIONS:
        sid, session = next(iter(SESSIONS.items()))
        if now - session.last_seen <= SESSION_IDLE_SECONDS:
            break
        _drop_session(sid)


def _register_table(table):
    if table.closed:
        raise ValueError("牌桌已关闭。")
    for table_id, registered in TABLES.items():
        if registered is table:
            return table_id
    table_id = secrets.token_urlsafe(24)
    while table_id in TABLES or table_id == table.invite:
        table_id = secrets.token_urlsafe(24)
    table.wake = WAKE.set
    TABLES[table_id] = table
    return table_id


def _store_session(sid, table_id, seat=0):
    # Callers expire sessions before selecting/reserving a destination table.
    now = time.monotonic()
    table = TABLES[table_id]
    if type(seat) is not int or not 0 <= seat < 6 or table.closed or not table.has_human(seat):
        raise ValueError("会话必须对应一个玩家座位。")
    previous = SESSIONS.get(sid)
    session = Session(table_id, seat, now)
    SESSIONS[sid] = session
    SESSIONS.move_to_end(sid)
    if previous is not None:
        _retire_binding(previous)
    while len(SESSIONS) > MAX_SESSIONS:
        _drop_session(next(iter(SESSIONS)))
    WAKE.set()
    return session


def guest_name(value):
    if not isinstance(value, str) or any(unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in value):
        raise ValueError("名字须为 1–12 个字符，不能包含控制字符。")
    name = value.strip()
    if not 1 <= len(name) <= 12:
        raise ValueError("名字须为 1–12 个字符，不能包含控制字符。")
    return name


def bind_session(sid, path, payload):
    """Atomically reserve a seat and replace a cookie's binding; return detached JSON.

    Only registry operations acquire multiple table locks, always after REGISTRY_LOCK.
    Holding the source lock until replacement prevents its last action from producing
    a newer response than the destination's first view.
    """
    with REGISTRY_LOCK:
        now = time.monotonic()
        _expire_sessions(now)
        session = SESSIONS.get(sid)
        if session is not None and TABLES[session.table_id].closed:
            _drop_session(sid)
            session = None
        if session is None and path in ("/api/reset", "/api/leave"):
            return 401, {"error": "牌桌已过期或服务已重启，请重新连接开始新的一场。"}, None
        source = TABLES[session.table_id] if session else None
        with source.lock if source else nullcontext():
            if session:
                session.last_seen = now
                SESSIONS.move_to_end(sid)
            if path == "/api/session" and session:
                return 200, source.view(session.seat), sid
            if path == "/api/join":
                code = payload.get("code")
                target = next((t for t in TABLES.values()
                               if t.shared and t.invite == code and not t.closed), None)
                if target is None:
                    return 404, {"error": "找不到这张牌桌，邀请链接可能已过期。"}, None
                if source is target:
                    return 200, target.view(session.seat), None
                try:
                    name = guest_name(payload.get("name"))
                except ValueError as exc:
                    return 400, {"error": str(exc)}, None
                with target.changed:
                    try:
                        seat = target.join(name)
                    except ValueError as exc:
                        return 409, {"error": str(exc)}, None
                    # Versions must stay monotonic for this browser across table switches.
                    if source:
                        target.version = max(target.version, source.version + 1)
                    cookie = None if session else secrets.token_urlsafe(32)
                    _store_session(sid if session else cookie, _register_table(target), seat)
                    target.changed.notify_all()
                    return 200, target.view(seat), cookie
            options = {"version": source.version if source else 0}
            if path == "/api/tables":
                try:
                    name = guest_name(payload.get("name"))
                except ValueError as exc:
                    return 400, {"error": str(exc)}, None
                invite = secrets.token_urlsafe(8)
                while invite in TABLES or any(t.invite == invite for t in TABLES.values()):
                    invite = secrets.token_urlsafe(8)
                players = deepcopy(PLAYERS)
                players[0].update(name=name, avatar=name[0])
                options.update(shared=True, invite=invite, players=players)
            fresh = Table(**options)
            cookie = None if session else secrets.token_urlsafe(32)
            _store_session(sid if session else cookie, _register_table(fresh))
            return 200, fresh.view(0), cookie


def _resolve_session(sid):
    with REGISTRY_LOCK:
        now = time.monotonic()
        _expire_sessions(now)
        session = SESSIONS.get(sid)
        if session is None:
            return None
        if TABLES[session.table_id].closed:
            _drop_session(sid)
            return None
        session.last_seen = now
        SESSIONS.move_to_end(sid)
        return session, TABLES[session.table_id]


def drive_tables():
    """One scheduler pass; policy computation happens after releasing the registry lock."""
    with REGISTRY_LOCK:
        _expire_sessions(time.monotonic())
        tables = list(TABLES.values())
    for table in tables:
        try:
            table.run_due()
        except Exception:
            import traceback
            traceback.print_exc()
    with REGISTRY_LOCK:
        deadlines = [s.last_seen + SESSION_IDLE_SECONDS + 0.001 for s in SESSIONS.values()]
        tables = list(TABLES.values())
    deadlines.extend(due for table in tables if (due := table.next_due()) is not None)
    return max(0, min(deadlines) - time.monotonic()) if deadlines else None


def run_scheduler(stop):
    while not stop.is_set():
        WAKE.clear()
        delay = drive_tables()
        if not stop.is_set():
            WAKE.wait(delay)


def same_origin_host(origin, host):
    """Compare authorities, allowing TLS termination before this HTTP server."""
    try:
        source = urlsplit(origin)
        target = urlsplit("//" + (host or ""))
        if source.scheme not in ("http", "https"):
            return False
        if not source.hostname or not target.hostname:
            return False
        default_port = 443 if source.scheme == "https" else 80
        return (source.hostname, source.port if source.port is not None else default_port) == (
            target.hostname, target.port if target.port is not None else default_port)
    except ValueError:
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Keep cookies, request bodies and hidden cards out of logs.
        if args and str(args[1] if len(args) > 1 else "").startswith("5"):
            super().log_message(fmt, *args)

    def reply(self, status, data, cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").strip().lower() == "https" else ""
            self.send_header("Set-Cookie", f"poker_session={cookie}; HttpOnly; SameSite=Strict; Path=/{secure}")
        self.end_headers()
        self.wfile.write(body)

    def session_id(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            return None
        return cookie["poker_session"].value if "poker_session" in cookie else None

    def session_expired(self):
        return self.reply(401, {"error": "牌桌已过期或服务已重启，请重新连接开始新的一场。"})

    def do_GET(self):
        url = urlsplit(self.path)
        path = url.path
        if path == "/healthz":
            with REGISTRY_LOCK:
                _expire_sessions(time.monotonic())
            return self.reply(200, {"ok": True})
        if path.startswith("/api/"):
            if path not in ("/api/state", "/api/history") and not path.startswith("/api/hand/"):
                return self.reply(404, {"error": "接口不存在。"})
            after = None
            try:
                values = parse_qs(url.query, keep_blank_values=True).get("after")
                if path == "/api/state" and values is not None:
                    if len(values) != 1:
                        raise ValueError
                    after = int(values[0])
                    if after < 0:
                        raise ValueError
            except ValueError:
                return self.reply(400, {"error": "版本号格式错误。"})
            while True:
                binding = _resolve_session(self.session_id())
                if binding is None:
                    return self.session_expired()
                session, table = binding
                with table.changed:
                    if not session.active or table.closed:
                        continue
                    if path == "/api/state":
                        if after is not None:
                            table.changed.wait_for(
                                lambda: table.version > after or not session.active or table.closed,
                                timeout=LONG_POLL_SECONDS)
                        if not session.active or table.closed:
                            continue
                        status, body = 200, table.view(session.seat)
                    elif path == "/api/history":
                        status, body = 200, {"hands": table.history(session.seat)}
                    else:
                        try:
                            hand_id = int(path.rsplit("/", 1)[-1])
                        except ValueError:
                            status, body = 404, {"error": "找不到这手牌。"}
                        else:
                            hand = table.hand(hand_id, session.seat)
                            status, body = (200, hand) if hand else (404, {
                                "error": f"这手牌尚未结束或已不在最近 {HAND_HISTORY_LIMIT} 手中。"})
                # Never hold a table or registry lock while writing to a slow browser.
                return self.reply(status, body)
        # An explicit allowlist keeps private files and source code off the web server.
        files = {"/": "index.html", "/index.html": "index.html", "/style.css": "style.css", "/app.js": "app.js"}
        if re.fullmatch(r"/t/[A-Za-z0-9_-]+", path):
            files[path] = "index.html"
        if path not in files:
            return self.reply(404, {"error": "Not found"})
        file = ROOT / "web" / files[path]
        if not file.exists():
            return self.reply(503, {"error": "界面仍在准备中。"})
        content = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin is not None and not same_origin_host(origin, self.headers.get("Host")):
            return self.reply(403, {"error": "仅接受当前站点牌桌的操作。"})
        path = urlsplit(self.path).path
        if path not in ("/api/session", "/api/reset", "/api/action", "/api/next",
                        "/api/tables", "/api/join", "/api/leave", "/api/back"):
            return self.reply(404, {"error": "接口不存在。"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 4096:
                raise ValueError("请求过大。")
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("请求格式错误。")
        except (ValueError, json.JSONDecodeError):
            return self.reply(400, {"error": "请求格式错误。"})
        sid = self.session_id()
        if path in ("/api/session", "/api/reset", "/api/tables", "/api/join", "/api/leave"):
            status, body, cookie = bind_session(sid, path, payload)
            return self.reply(status, body, cookie=cookie)
        binding = _resolve_session(sid)
        if binding is None:
            return self.session_expired()
        session, table = binding
        with table.lock:
            if not session.active or table.closed:
                status, body = 401, {"error": "牌桌已过期或服务已重启，请重新连接开始新的一场。"}
            else:
                try:
                    if not table.has_human(session.seat) or session.seat in table.pending:
                        raise ValueError("此座位由对手控制。")
                    if path == "/api/back":
                        table.back(session.seat)
                    else:
                        version = payload.get("version")
                        if type(version) is not int:
                            raise ValueError("牌局已更新，请重试当前操作。")
                        if path == "/api/action":
                            table.act(session.seat, payload.get("action"), payload.get("amount"), version)
                        else:
                            if version != table.version:
                                raise ValueError("牌局已更新，请重试当前操作。")
                            table.new_hand()
                    status, body = 200, table.view(session.seat)
                except ValueError as exc:
                    status, body = 409, {"error": str(exc)}
                except Exception:
                    import traceback
                    traceback.print_exc()
                    status, body = 500, {"error": "牌局遇到错误，请刷新后重试。"}
        return self.reply(status, body)


def main():
    parser = argparse.ArgumentParser(description="Start the Poker Lab table")
    parser.add_argument("--port", type=int, default=os.environ.get("PORT", "8765"))
    args = parser.parse_args()
    host = os.environ.get("HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, args.port), Handler)
    print(f"Poker Lab · http://{host}:{args.port}", flush=True)
    stop = threading.Event()
    worker = threading.Thread(target=run_scheduler, args=(stop,), name="table-driver", daemon=True)
    worker.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        WAKE.set()
        worker.join()
        with REGISTRY_LOCK:
            for sid in list(SESSIONS):
                _drop_session(sid)
        server.server_close()


if __name__ == "__main__":
    main()
