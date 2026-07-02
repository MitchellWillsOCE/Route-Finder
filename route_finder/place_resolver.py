from __future__ import annotations

from dataclasses import dataclass

import httpx

from route_finder.cache import FLIX_CITY_CACHE, GEOCODE_CACHE
from route_finder.geocode import geocode_station
from route_finder.historic_fares import canonical_place
from route_finder.hubs import hub_station_coords
from route_finder.places import ResolvedPlace, resolve_place


@dataclass(frozen=True)
class TripEndpoints:
    origin: ResolvedPlace
    destination: ResolvedPlace
    origin_canonical: str
    destination_canonical: str
    origin_station: tuple[float, float]
    destination_station: tuple[float, float]

    @property
    def origin_label(self) -> str:
        return self.origin.name

    @property
    def destination_label(self) -> str:
        return self.destination.name


def _cache_key(prefix: str, query: str) -> str:
    return f"{prefix}:{query.strip().lower()}"


def resolve_place_cached(query: str, client: httpx.Client) -> ResolvedPlace:
    key = _cache_key("geo", query)
    cached = GEOCODE_CACHE.get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    place = resolve_place(query, client)
    GEOCODE_CACHE.set(key, place)
    return place


def station_coords_for(place: ResolvedPlace, client: httpx.Client) -> tuple[float, float]:
    canonical = canonical_place(place.name)
    hub = hub_station_coords(place.name)
    if hub != (0.0, 0.0):
        return hub
    key = _cache_key("station", place.name)
    cached = GEOCODE_CACHE.get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    station = geocode_station(place.name, client)
    coords = (station.lat, station.lon)
    GEOCODE_CACHE.set(key, coords)
    return coords


def resolve_trip(
    origin: str,
    destination: str,
    client: httpx.Client,
) -> TripEndpoints:
    start = resolve_place_cached(origin, client)
    end = resolve_place_cached(destination, client)
    return TripEndpoints(
        origin=start,
        destination=end,
        origin_canonical=canonical_place(start.name),
        destination_canonical=canonical_place(end.name),
        origin_station=station_coords_for(start, client),
        destination_station=station_coords_for(end, client),
    )


def flix_city_cached(client: httpx.Client, query: str) -> dict | None:
    canonical = canonical_place(query)
    key = _cache_key("flix", canonical)
    cached = FLIX_CITY_CACHE.get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://shop.flixbus.com/",
    }
    for term in (query, canonical.replace("_", " ").title()):
        try:
            response = client.get(
                "https://global.api.flixbus.com/search/autocomplete/cities",
                params={"q": term, "locale": "en"},
                headers=headers,
                timeout=15,
            )
            if response.status_code == 200 and response.json():
                city = response.json()[0]
                FLIX_CITY_CACHE.set(key, city)
                return city
        except Exception:
            continue
    return None
