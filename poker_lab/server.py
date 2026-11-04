"""Small local HTTP app. PokerKit remains authoritative; no third-party services."""
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import mimetypes
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit

from .game import Table

ROOT = Path(__file__).resolve().parent.parent
SESSIONS = {}
LOCK = threading.RLock()


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
            self.send_header("Set-Cookie", f"poker_session={cookie}; HttpOnly; SameSite=Strict; Path=/")
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
        if path.startswith("/api/"):
            with LOCK:
                table = SESSIONS.get(self.session_id())
                if table is None:
                    return self.reply(401, {"error": "请重新进入牌桌。"})
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
                    return self.reply(200, hand) if hand else self.reply(404, {"error": "这手牌尚未结束或已不在最近 100 手中。"})
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
        if origin and origin not in (f"http://{self.headers.get('Host')}",):
            return self.reply(403, {"error": "仅接受本地牌桌的操作。"})
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
            table = SESSIONS.get(sid)
            if path == "/api/session":
                if table is None:
                    sid = secrets.token_urlsafe(32)
                    table = SESSIONS[sid] = Table()
                return self.reply(200, table.snapshot(), cookie=sid)
            if table is None:
                return self.reply(401, {"error": "请重新进入牌桌。"})
            try:
                if path == "/api/reset":
                    previous_version = table.version
                    table = SESSIONS[sid] = Table()
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
    parser = argparse.ArgumentParser(description="Start the local Poker Lab table")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Poker Lab · http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
