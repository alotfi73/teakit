"""
teakit.app.server — A thin HTTP shim over :mod:`teakit.app.api`.
================================================================

Standard-library ``http.server`` only. Two routes:

``GET  /``           the interface, and its static assets
``POST /api/<name>`` JSON in, JSON out, straight to :func:`teakit.app.api.dispatch`

Bound to loopback by default and single-threaded per request via
``ThreadingHTTPServer``. This is a local desktop tool. It has no authentication,
no CSRF protection and no rate limiting, and it should not be exposed to a
network — if you need that, put :mod:`teakit.app.api` behind a real framework.
"""

from __future__ import annotations

import json
import mimetypes
import os
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import api

__all__ = ["serve", "make_server", "Handler"]

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BODY = 8 * 1024 * 1024          # a project JSON is small; cap it anyway


class Handler(BaseHTTPRequestHandler):
    server_version = "teakit"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # -- plumbing -------------------------------------------------------
    def log_message(self, fmt, *args):                     # noqa: A003
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def _send(self, code: int, body: bytes, ctype: str,
              extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    # -- routes ---------------------------------------------------------
    def do_GET(self) -> None:                              # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path == "/health":
            return self._json({"ok": True})
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        # allow bare asset names so the page can reference app.css directly
        candidate = path.lstrip("/")
        if candidate and "/" not in candidate and ".." not in candidate:
            return self._static(candidate)
        self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:                             # noqa: N802
        path = self.path.split("?", 1)[0]
        if not path.startswith("/api/"):
            return self._json({"ok": False, "error": "not found"}, 404)
        name = path[len("/api/"):].strip("/")
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > MAX_BODY:
            return self._json({"ok": False, "error": "payload too large"}, 413)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            return self._json({"ok": False, "error": f"bad JSON: {exc}"}, 400)
        if not isinstance(payload, dict):
            return self._json({"ok": False, "error": "payload must be an object"}, 400)
        result = api.dispatch(name, payload)
        self._json(result, 200 if result.get("ok") else 200)

    # -- static ---------------------------------------------------------
    def _static(self, rel: str) -> None:
        rel = rel.replace("\\", "/")
        if ".." in rel or rel.startswith("/"):
            return self._json({"ok": False, "error": "forbidden"}, 403)
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(os.path.abspath(STATIC_DIR)) or not os.path.isfile(full):
            return self._json({"ok": False, "error": f"no such file {rel!r}"}, 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",
                                                  "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            self._send(200, fh.read(), ctype)


def _free_port(host: str, start: int, tries: int = 40) -> int:
    """First free port at or after ``start`` — so a second instance still opens."""
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    raise OSError(f"no free port in {start}-{start + tries}")


def make_server(host: str = "127.0.0.1", port: int = 8765,
                verbose: bool = False) -> ThreadingHTTPServer:
    """Build (but do not start) the server. Useful in tests."""
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.verbose = verbose
    srv.daemon_threads = True
    return srv


def serve(host: str = "127.0.0.1", port: int = 8765,
          open_browser: bool = True, verbose: bool = False) -> None:
    """
    Start the application and block until interrupted.

    If ``port`` is busy the next free one is used, so launching a second study
    in parallel works without arguments.
    """
    from .. import __version__
    port = _free_port(host, port)
    srv = make_server(host, port, verbose)
    url = f"http://{host}:{port}/"
    print(f"teakit {__version__} — techno-economic analysis")
    print(f"  {url}")
    print("  capital: DOE/NETL-2002/1169 + NETL-PUB-22580 | "
          "cash flow: NREL/TP-5100-47764")
    print("  Ctrl-C to stop.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        srv.server_close()


if __name__ == "__main__":  # pragma: no cover
    serve()
