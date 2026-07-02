from __future__ import annotations

import json
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from api.bootstrap import ensure_imports


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        try:
            ensure_imports()
            from route_finder.places import search_places

            qs = parse_qs(urlparse(self.path).query)
            query = qs.get("q", [""])[0]
            limit_raw = qs.get("limit", ["8"])[0]
            limit = int(limit_raw) if limit_raw.isdigit() else 8
            limit = min(max(limit, 1), 20)

            payload = {"places": search_places(query, limit=limit)}
            self._json(200, payload)
        except Exception as exc:
            traceback.print_exc()
            self._json(500, {"error": str(exc)})

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
