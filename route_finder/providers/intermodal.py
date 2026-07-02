from __future__ import annotations

import httpx

from route_finder.graph_router import GraphRouter
from route_finder.models import RouteOption, SearchRequest
from route_finder.place_resolver import TripEndpoints, resolve_trip
from route_finder.providers.base import RouteProvider


class IntermodalProvider(RouteProvider):
    name = "Intermodal (train + flight)"

    def search(self, request: SearchRequest, client: httpx.Client) -> list[RouteOption]:
        endpoints = resolve_trip(request.origin, request.destination, client)
        return GraphRouter().search(request, client, endpoints)
