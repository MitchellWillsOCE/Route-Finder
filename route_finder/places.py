from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches

import httpx

from route_finder.config import CONFIG
from route_finder.european_cities import MAJOR_EUROPEAN_CITIES

EUROPE_COUNTRY_CODES = (
    "ad al at ba be bg by ch cy cz de dk ee es fi fr gb gr hr hu ie is it "
    "li lt lu lv mc md me mk mt nl no pl pt ro rs se si sk sm ua va xk"
).split()

_FLIX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://shop.flixbus.com/",
}


@dataclass(frozen=True)
class ResolvedPlace:
    input_query: str
    name: str
    lat: float
    lon: float
    display_name: str
    country_code: str
    spelling_corrected: bool = False

    def to_geo(self):
        from route_finder.geocode import GeoPlace

        return GeoPlace(
            name=self.name,
            lat=self.lat,
            lon=self.lon,
            display_name=self.display_name,
        )


class LocationValidationError(Exception):
    def __init__(self, query: str, message: str, suggestions: list[str] | None = None):
        self.query = query
        self.message = message
        self.suggestions = suggestions or []
        super().__init__(message)


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _short_name(display_name: str) -> str:
    return display_name.split(",")[0].strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _nominatim_search(client: httpx.Client, query: str, limit: int = 5) -> list[dict]:
    response = client.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": query,
            "format": "json",
            "limit": limit,
            "addressdetails": 1,
            "countrycodes": ",".join(EUROPE_COUNTRY_CODES),
        },
        headers={"User-Agent": CONFIG.nominatim_user_agent},
        timeout=CONFIG.request_timeout,
    )
    response.raise_for_status()
    return response.json()


def _flix_suggestions(client: httpx.Client, query: str, limit: int = 5) -> list[str]:
    try:
        response = client.get(
            "https://global.api.flixbus.com/search/autocomplete/cities",
            params={"q": query, "locale": "en"},
            headers=_FLIX_HEADERS,
            timeout=CONFIG.request_timeout,
        )
        if response.status_code != 200:
            return []
        return [item["name"] for item in response.json()[:limit]]
    except Exception:
        return []


def _resolve_candidate(query: str, item: dict, *, force_corrected: bool = False) -> ResolvedPlace:
    display = item.get("display_name", query)
    address = item.get("address", {}) or {}
    country = (address.get("country_code") or "").lower()
    name = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or _short_name(display)
    )
    similarity = _similarity(query, name)
    corrected = force_corrected or (
        similarity < 0.82 and _normalize(query) != _normalize(name)
    )
    return ResolvedPlace(
        input_query=query,
        name=name,
        lat=float(item["lat"]),
        lon=float(item["lon"]),
        display_name=display,
        country_code=country,
        spelling_corrected=corrected,
    )


def _best_nominatim_match(query: str, results: list[dict]) -> ResolvedPlace:
    ranked = sorted(
        results,
        key=lambda item: (
            _similarity(query, _short_name(item.get("display_name", ""))),
            float(item.get("importance", 0)),
        ),
        reverse=True,
    )
    return _resolve_candidate(query, ranked[0])


def resolve_place(query: str, client: httpx.Client) -> ResolvedPlace:
    query = query.strip()
    if not query:
        raise LocationValidationError(
            query=query,
            message="Location cannot be empty.",
            suggestions=[],
        )

    results = _nominatim_search(client, query)
    flix_matches = _flix_suggestions(client, query, limit=5)

    if not results:
        fuzzy = get_close_matches(query, MAJOR_EUROPEAN_CITIES, n=1, cutoff=0.75)
        if fuzzy:
            corrected_results = _nominatim_search(client, fuzzy[0])
            if corrected_results:
                place = _best_nominatim_match(fuzzy[0], corrected_results)
                return ResolvedPlace(
                    input_query=query,
                    name=fuzzy[0],
                    lat=place.lat,
                    lon=place.lon,
                    display_name=place.display_name,
                    country_code=place.country_code,
                    spelling_corrected=True,
                )

        hint = ""
        if flix_matches:
            hint = f" Did you mean: {', '.join(flix_matches)}?"
        suggestions = list(
            dict.fromkeys(
                get_close_matches(query, MAJOR_EUROPEAN_CITIES, n=3, cutoff=0.6) + flix_matches
            )
        )
        raise LocationValidationError(
            query=query,
            message=f"'{query}' was not found in Europe.{hint}",
            suggestions=suggestions,
        )

    best = _best_nominatim_match(query, results)
    query_sim = _similarity(query, best.name)

    if query_sim < 0.82:
        fuzzy = get_close_matches(query, MAJOR_EUROPEAN_CITIES, n=1, cutoff=0.75)
        for match_name in fuzzy:
            corrected_results = _nominatim_search(client, match_name)
            if corrected_results:
                place = _best_nominatim_match(match_name, corrected_results)
                return ResolvedPlace(
                    input_query=query,
                    name=match_name,
                    lat=place.lat,
                    lon=place.lon,
                    display_name=place.display_name,
                    country_code=place.country_code,
                    spelling_corrected=True,
                )

        for flix_name in flix_matches:
            if _similarity(query, flix_name) >= 0.72:
                corrected_results = _nominatim_search(client, flix_name)
                if corrected_results:
                    place = _best_nominatim_match(query, corrected_results)
                    return ResolvedPlace(
                        input_query=query,
                        name=flix_name,
                        lat=place.lat,
                        lon=place.lon,
                        display_name=place.display_name,
                        country_code=place.country_code,
                        spelling_corrected=True,
                    )

    if query_sim < 0.55:
        suggestions = list(
            dict.fromkeys(
                [_short_name(r["display_name"]) for r in results[:3]] + flix_matches
            )
        )
        raise LocationValidationError(
            query=query,
            message=(
                f"'{query}' is unclear. Closest match: {best.name} ({best.country_code.upper()})."
            ),
            suggestions=suggestions,
        )

    if best.country_code and best.country_code not in EUROPE_COUNTRY_CODES:
        raise LocationValidationError(
            query=query,
            message=f"'{query}' resolved outside Europe ({best.display_name}).",
            suggestions=[_short_name(r["display_name"]) for r in results[:3]],
        )

    return best


def validate_trip_locations(
    origin: str,
    destination: str,
    client: httpx.Client,
) -> tuple[ResolvedPlace, ResolvedPlace, str | None]:
    try:
        start = resolve_place(origin, client)
    except LocationValidationError:
        raise

    try:
        end = resolve_place(destination, client)
    except LocationValidationError:
        raise

    if _similarity(start.name, end.name) > 0.92 and _similarity(
        start.display_name, end.display_name
    ) > 0.85:
        raise LocationValidationError(
            query=destination,
            message=f"Origin and destination look the same ({start.name}).",
            suggestions=[],
        )

    notes: list[str] = []
    if start.spelling_corrected:
        notes.append(f"Start -> {start.name}, {start.country_code.upper()}")
    if end.spelling_corrected:
        notes.append(f"Destination -> {end.name}, {end.country_code.upper()}")

    note = None
    if notes:
        note = "Resolved spellings: " + "; ".join(notes)

    return start, end, note
