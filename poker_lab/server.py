"""Solo-table HTTP app. PokerKit remains authoritative."""
from collections import OrderedDict
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

from .game import HAND_HISTORY_LIMIT, Table

ROOT = Path(__file__).resolve().parent.parent
MAX_SESSIONS = 100
SESSION_IDLE_SECONDS = 2 * 60 * 60
LOCK = threading.RLock()


@dataclass
class Session:
    table: Table
    last_seen: float


SESSIONS: OrderedDict[str, Session] = OrderedDict()


def _expire_sessions(now):
    """Remove the expired LRU prefix. Session helpers run with LOCK held."""
    while SESSIONS:
        sid, session = next(iter(SESSIONS.items()))
        if now - session.last_seen <= SESSION_IDLE_SECONDS:
            break
        del SESSIONS[sid]


def _get_session_table(sid):
    now = time.monotonic()
    _expire_sessions(now)
    session = SESSIONS.get(sid)
    if session is None:
        return None
    session.last_seen = now
    SESSIONS.move_to_end(sid)
    return session.table


def _store_session(sid, table):
    now = time.monotonic()
    _expire_sessions(now)
    SESSIONS[sid] = Session(table, now)
    SESSIONS.move_to_end(sid)
    while len(SESSIONS) > MAX_SESSIONS:
        SESSIONS.popitem(last=False)


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

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            with LOCK:
                _expire_sessions(time.monotonic())
            return self.reply(200, {"ok": True})
        if path.startswith("/api/"):
            with LOCK:
                table = _get_session_table(self.session_id())
                if table is None:
                    return self.reply(401, {"error": "牌桌已过期或服务已重启，请重新连接开始新的一场。"})
                if path == "/api/state":
                    return self.reply(200, table.snapshot())
                if path == "/api/history":
                    return self.reply(200, {"hands": [{k: h[k] for k in ("hand_id", "summary", "net", "board")}
                                                     for h in reversed(table.hands)]})
                if path.startswith("/api/hand/"):
                    try:
                        hand_id = int(path.rsplit("/", 1)[-1])
                    except ValueError:
                        return self.reply(404, {"error": "找不到这手牌。"})
                    hand = next((h for h in table.hands if h["hand_id"] == hand_id), None)
                    return self.reply(200, hand) if hand else self.reply(404, {"error": f"这手牌尚未结束或已不在最近 {HAND_HISTORY_LIMIT} 手中。"})
                return self.reply(404, {"error": "接口不存在。"})
        # An explicit allowlist keeps private files and source code off the web server.
        files = {"/": "index.html", "/index.html": "index.html", "/style.css": "style.css", "/app.js": "app.js"}
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
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 4096:
                raise ValueError("请求过大。")
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("请求格式错误。")
        except (ValueError, json.JSONDecodeError):
            return self.reply(400, {"error": "请求格式错误。"})
        path = urlsplit(self.path).path
        with LOCK:
            sid = self.session_id()
            table = _get_session_table(sid)
            if path == "/api/session":
                if table is None:
                    sid = secrets.token_urlsafe(32)
                    table = Table()
                    _store_session(sid, table)
                return self.reply(200, table.snapshot(), cookie=sid)
            if table is None:
                return self.reply(401, {"error": "牌桌已过期或服务已重启，请重新连接开始新的一场。"})
            try:
                if path == "/api/reset":
                    previous_version = table.version
                    table = Table()
                    _store_session(sid, table)
                    table.version = previous_version + 1
                    table.frames = [table.snapshot()]
                    return self.reply(200, table.snapshot())
                version = payload.get("version")
                if type(version) is not int or version != table.version:
                    raise ValueError("牌局已更新，请重试当前操作。")
                if path == "/api/action":
                    result = table.act(0, payload.get("action"), payload.get("amount"), version)
                elif path == "/api/step":
                    result = table.step_bot(version)
                elif path == "/api/next":
                    table.new_hand()
                    result = table.snapshot()
                else:
                    return self.reply(404, {"error": "接口不存在。"})
                return self.reply(200, result)
            except ValueError as exc:
                return self.reply(409, {"error": str(exc)})
            except Exception:
                import traceback
                traceback.print_exc()
                return self.reply(500, {"error": "牌局遇到错误，请刷新后重试。"})


def main():
    parser = argparse.ArgumentParser(description="Start the Poker Lab table")
    parser.add_argument("--port", type=int, default=os.environ.get("PORT", "8765"))
    args = parser.parse_args()
    host = os.environ.get("HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, args.port), Handler)
    print(f"Poker Lab · http://{host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
