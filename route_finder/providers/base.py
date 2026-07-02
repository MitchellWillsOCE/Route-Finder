from __future__ import annotations

from route_finder.models import RouteOption, SearchRequest


class RouteProvider:
    name: str

    def search(self, request: SearchRequest, client) -> list[RouteOption]:
        raise NotImplementedError
