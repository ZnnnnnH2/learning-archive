"""Dependency-free local HTTP control console and projection page."""

from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .service import TournamentService


def serve(service: TournamentService, host: str, port: int) -> None:
    assets = Path(__file__).with_name("web")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, content: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers(); self.wfile.write(content)

        def _json(self, value: object, status: int = 200) -> None:
            self._send(json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

        def do_GET(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            if route == "/api/state":
                return self._json(service.store.state())
            if route.startswith("/api/replay/"):
                try:
                    return self._json(service.replay(int(route.rsplit("/", 1)[1])))
                except (ValueError, KeyError, RuntimeError) as error:
                    return self._json({"error": str(error)}, 404)
            names = {"/": "index.html", "/display": "display.html", "/app.js": "app.js", "/style.css": "style.css"}
            name = names.get(route)
            if not name:
                return self._json({"error": "not found"}, 404)
            content_type = "text/html; charset=utf-8" if name.endswith("html") else "text/css; charset=utf-8" if name.endswith("css") else "application/javascript; charset=utf-8"
            return self._send((assets / name).read_bytes(), content_type)

        def do_POST(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            if route.startswith("/api/run-game/"):
                try:
                    game_id = int(route.rsplit("/", 1)[1])
                    threading.Thread(target=service.run_game, args=(game_id,), daemon=True).start()
                    return self._json({"started": game_id}, HTTPStatus.ACCEPTED)
                except ValueError:
                    return self._json({"error": "invalid game id"}, 400)
            if route == "/api/advance-knockout":
                try:
                    return self._json({"result": service.advance_knockout()})
                except RuntimeError as error:
                    return self._json({"error": str(error)}, 409)
            return self._json({"error": "not found"}, 404)

        def log_message(self, *_: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"operator: http://{host}:{port}/\nprojection: http://{host}:{port}/display", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
