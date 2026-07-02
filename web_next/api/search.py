from __future__ import annotations

import json
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from api.search_core import run_search


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        try:
            qs = parse_qs(urlparse(self.path).query)
            from_ = qs.get("from", [""])[0].strip()
            to = qs.get("to", [""])[0].strip()
            date = qs.get("date", [""])[0].strip() or None
            flex_raw = qs.get("flex", ["2"])[0]
            flex = int(flex_raw) if flex_raw.isdigit() else 2

            if not from_ or not to:
                self._json(400, {"error": "Missing from or to"})
                return

            payload = run_search(from_, to, date=date, flex=flex)
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
