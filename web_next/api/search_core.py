from __future__ import annotations

from datetime import datetime
from typing import Any

from api.bootstrap import ensure_imports


def run_search(
    from_: str,
    to: str,
    date: str | None = None,
    flex: int = 2,
) -> dict[str, Any]:
    ensure_imports()
    from route_finder.models import SearchRequest
    from route_finder.search import search_routes
    from route_finder.web_app import _parse_date, _route_to_view

    date_raw = date or datetime.now().strftime("%Y-%m-%d")
    depart = _parse_date(date_raw)
    req = SearchRequest(
        origin=from_,
        destination=to,
        ideal_departure=depart,
        flexibility_days=int(flex),
    )
    result = search_routes(req)
    routes = [
        _route_to_view(r, origin=req.origin, destination=req.destination)
        for r in result.routes
    ]
    return {"routes": routes}
