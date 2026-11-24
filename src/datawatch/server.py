"""Local web server for the dashboard. Binds to 127.0.0.1 only.

Defences (see docs/security.md): Host-header allowlist (DNS rebinding), strict CSP with no inline code, same-origin
checks + a per-run token on every write, JSON-only bodies with a size cap, validated input, no stack traces.
"""
import hmac
import json
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import autostart
from .app import App

if getattr(sys, "frozen", False):
    WEB = Path(sys._MEIPASS) / "datawatch" / "web"
else:
    WEB = Path(__file__).parent / "web"

STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'")
MAX_BODY = 4096


def make_handler(app: App, port: int, token: str, on_quit):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    cache = {}                                                 # static files are read once

    class Handler(BaseHTTPRequestHandler):
        server_version = "datawatch"
        sys_version = ""

        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype, nocache=True):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

        def _host_ok(self):
            return self.headers.get("Host", "") in hosts

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "forbidden"})
            path = self.path.split("?", 1)[0]
            if path in STATIC:
                name, ctype = STATIC[path]
                try:
                    if name not in cache:
                        cache[name] = (WEB / name).read_bytes()
                    return self._send(200, cache[name], ctype)
                except OSError:
                    return self._json(404, {"error": "not found"})
            if path == "/api/state":
                try:
                    st = app.state()
                    st["token"] = token
                    return self._json(200, st)
                except Exception:
                    return self._json(500, {"error": "internal error"})
            self._json(404, {"error": "not found"})

        def _drain(self):
            """Read (and drop) a small request body so an early refusal doesn't reset the connection."""
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if 0 < n <= MAX_BODY:
                    self.rfile.read(n)
            except (ValueError, OSError):
                pass

        def do_POST(self):
            if not self._host_ok():
                self._drain()
                return self._json(403, {"error": "forbidden"})
            origin = self.headers.get("Origin")
            if (origin is not None and origin not in origins) or self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
                self._drain()
                return self._json(403, {"error": "forbidden"})
            if not hmac.compare_digest(self.headers.get("X-DW-Token", ""), token):
                self._drain()
                return self._json(403, {"error": "forbidden"})
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._drain()
                return self._json(415, {"error": "json only"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = -1
            if not 0 <= n <= MAX_BODY:
                return self._json(413, {"error": "body too large"})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json(400, {"error": "bad json"})
            path = self.path.split("?", 1)[0]
            try:
                if path == "/api/settings":
                    return self._json(200, {"settings": app.update_settings(body)})
                if path == "/api/apps/refresh":
                    app.refresh_apps()
                    return self._json(200, {"started": True})
                if path == "/api/autostart":
                    en = body.get("enabled") if isinstance(body, dict) else None
                    if not isinstance(en, bool):
                        raise ValueError("enabled must be true or false")
                    autostart.set_enabled(en)
                    return self._json(200, {"autostart": autostart.is_enabled()})
                if path == "/api/quit":
                    self._json(200, {"bye": True})
                    threading.Thread(target=on_quit, daemon=True).start()
                    return
            except ValueError as e:
                return self._json(400, {"error": str(e)[:200]})
            except Exception:
                return self._json(500, {"error": "internal error"})
            self._json(404, {"error": "not found"})

    return Handler


def serve(app: App, port: int):
    token = secrets.token_urlsafe(32)
    holder = {}
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, port, token, lambda: (app.stop.set(), holder["s"].shutdown())))
    holder["s"] = srv
    return srv
