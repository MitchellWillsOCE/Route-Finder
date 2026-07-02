from __future__ import annotations

import math
from dataclasses import dataclass

import httpx

from route_finder.config import CONFIG
from route_finder.places import ResolvedPlace, resolve_place


@dataclass(frozen=True)
class GeoPlace:
    name: str
    lat: float
    lon: float
    display_name: str


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geocode(query: str, client: httpx.Client | None = None) -> GeoPlace:
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=CONFIG.request_timeout)

    try:
        return resolve_place(query, client).to_geo()
    finally:
        if own_client:
            client.close()


def geocode_station(query: str, client: httpx.Client) -> GeoPlace:
    """Prefer rail station coordinates for timetable routing."""
    base = query.strip().split(",")[0]
    for suffix in (" railway station", " train station"):
        try:
            place = geocode(f"{base}{suffix}", client)
            if abs(place.lat) > 0.01:
                return place
        except Exception:
            continue
    return geocode(query, client)

