from __future__ import annotations

from datetime import date, datetime

from route_finder.historic_fares import (
    _BASELINE_DAYS_AHEAD,
    _CITY_COORDS,
    _coords,
    _haversine_km,
    _route_key,
    booking_window_multiplier,
    days_until_departure,
)

# Typical one-way economy fares (EUR) ~30 days before departure.
# Sources: Skyscanner / airline averages 2023–2025, one adult, cabin bag.
_HISTORIC_FLIGHT_EUR: dict[tuple[str, str], float] = {
    ("amsterdam", "barcelona"): 72.0,
    ("amsterdam", "berlin"): 58.0,
    ("amsterdam", "brussels"): 95.0,
    ("amsterdam", "budapest"): 68.0,
    ("amsterdam", "copenhagen"): 62.0,
    ("amsterdam", "dublin"): 55.0,
    ("amsterdam", "edinburgh"): 72.0,
    ("amsterdam", "frankfurt"): 78.0,
    ("amsterdam", "london"): 62.0,
    ("amsterdam", "madrid"): 88.0,
    ("amsterdam", "milan"): 72.0,
    ("amsterdam", "munich"): 82.0,
    ("amsterdam", "naples"): 92.0,
    ("amsterdam", "paris"): 68.0,
    ("amsterdam", "prague"): 65.0,
    ("amsterdam", "rome"): 78.0,
    ("amsterdam", "stockholm"): 85.0,
    ("amsterdam", "vienna"): 75.0,
    ("amsterdam", "warsaw"): 58.0,
    ("amsterdam", "zurich"): 88.0,
    ("barcelona", "london"): 48.0,
    ("barcelona", "madrid"): 42.0,
    ("barcelona", "paris"): 52.0,
    ("barcelona", "rome"): 58.0,
    ("berlin", "barcelona"): 72.0,
    ("berlin", "london"): 58.0,
    ("berlin", "munich"): 48.0,
    ("berlin", "paris"): 62.0,
    ("berlin", "prague"): 55.0,
    ("berlin", "rome"): 68.0,
    ("berlin", "vienna"): 52.0,
    ("berlin", "warsaw"): 45.0,
    ("bologna", "london"): 62.0,
    ("brussels", "barcelona"): 68.0,
    ("brussels", "london"): 72.0,
    ("brussels", "madrid"): 78.0,
    ("brussels", "rome"): 72.0,
    ("budapest", "london"): 65.0,
    ("copenhagen", "london"): 58.0,
    ("copenhagen", "paris"): 62.0,
    ("dublin", "london"): 38.0,
    ("dublin", "paris"): 72.0,
    ("dusseldorf", "munich"): 55.0,
    ("edinburgh", "london"): 42.0,
    ("florence", "london"): 78.0,
    ("frankfurt", "london"): 58.0,
    ("frankfurt", "madrid"): 72.0,
    ("frankfurt", "rome"): 68.0,
    ("geneva", "london"): 72.0,
    ("lisbon", "london"): 62.0,
    ("lisbon", "madrid"): 38.0,
    ("lisbon", "paris"): 58.0,
    ("london", "madrid"): 52.0,
    ("london", "milan"): 48.0,
    ("london", "munich"): 58.0,
    ("london", "nice"): 62.0,
    ("london", "paris"): 55.0,
    ("london", "rome"): 52.0,
    ("london", "vienna"): 62.0,
    ("lyon", "paris"): 58.0,
    ("madrid", "paris"): 48.0,
    ("madrid", "rome"): 52.0,
    ("marseille", "paris"): 62.0,
    ("milan", "naples"): 48.0,
    ("milan", "paris"): 52.0,
    ("milan", "rome"): 42.0,
    ("milan", "vienna"): 58.0,
    ("munich", "rome"): 62.0,
    ("munich", "vienna"): 55.0,
    ("naples", "paris"): 68.0,
    ("naples", "rome"): 48.0,
    ("nice", "paris"): 58.0,
    ("paris", "rome"): 48.0,
    ("paris", "vienna"): 62.0,
    ("prague", "vienna"): 48.0,
    ("rome", "vienna"): 55.0,
    ("venice", "naples"): 58.0,
    ("venice", "rome"): 48.0,
    ("vienna", "warsaw"): 42.0,
    ("zurich", "london"): 62.0,
    ("zurich", "paris"): 72.0,
    ("zurich", "rome"): 68.0,
}

# Typical block times (minutes) gate-to-gate including taxi; direct flights.
_HISTORIC_FLIGHT_MINUTES: dict[tuple[str, str], int] = {
    ("amsterdam", "barcelona"): 135,
    ("amsterdam", "berlin"): 75,
    ("amsterdam", "brussels"): 55,
    ("amsterdam", "budapest"): 140,
    ("amsterdam", "copenhagen"): 90,
    ("amsterdam", "dublin"): 95,
    ("amsterdam", "edinburgh"): 95,
    ("amsterdam", "frankfurt"): 70,
    ("amsterdam", "london"): 75,
    ("amsterdam", "madrid"): 165,
    ("amsterdam", "milan"): 115,
    ("amsterdam", "munich"): 95,
    ("amsterdam", "naples"): 155,
    ("amsterdam", "paris"): 80,
    ("amsterdam", "prague"): 95,
    ("amsterdam", "rome"): 145,
    ("amsterdam", "stockholm"): 115,
    ("amsterdam", "vienna"): 110,
    ("amsterdam", "warsaw"): 115,
    ("amsterdam", "zurich"): 95,
    ("barcelona", "london"): 150,
    ("barcelona", "madrid"): 75,
    ("barcelona", "paris"): 115,
    ("barcelona", "rome"): 120,
    ("berlin", "barcelona"): 165,
    ("berlin", "london"): 120,
    ("berlin", "munich"): 70,
    ("berlin", "paris"): 110,
    ("berlin", "prague"): 65,
    ("berlin", "rome"): 150,
    ("berlin", "vienna"): 85,
    ("berlin", "warsaw"): 75,
    ("brussels", "barcelona"): 130,
    ("brussels", "london"): 70,
    ("brussels", "madrid"): 155,
    ("brussels", "rome"): 140,
    ("dublin", "london"): 70,
    ("dublin", "paris"): 105,
    ("edinburgh", "london"): 75,
    ("lisbon", "london"): 165,
    ("lisbon", "madrid"): 75,
    ("lisbon", "paris"): 150,
    ("london", "madrid"): 150,
    ("london", "milan"): 130,
    ("london", "munich"): 115,
    ("london", "nice"): 135,
    ("london", "paris"): 80,
    ("london", "rome"): 150,
    ("london", "vienna"): 140,
    ("lyon", "paris"): 70,
    ("madrid", "paris"): 130,
    ("madrid", "rome"): 150,
    ("milan", "naples"): 85,
    ("milan", "paris"): 90,
    ("milan", "rome"): 80,
    ("munich", "rome"): 105,
    ("munich", "vienna"): 65,
    ("naples", "paris"): 145,
    ("naples", "rome"): 70,
    ("paris", "rome"): 130,
    ("paris", "vienna"): 120,
    ("venice", "naples"): 90,
    ("venice", "rome"): 75,
    ("zurich", "london"): 110,
    ("zurich", "paris"): 80,
    ("zurich", "rome"): 105,
}

_FLIGHT_VIA_HUBS = (
    "amsterdam",
    "barcelona",
    "brussels",
    "frankfurt",
    "london",
    "madrid",
    "milan",
    "munich",
    "paris",
    "rome",
    "vienna",
    "zurich",
)

_FLIGHT_EUR_PER_KM = 0.085
_FLIGHT_MIN_EUR = 28.0
_FLIGHT_MIN_MINUTES = 55
_FLIGHT_MAX_MINUTES = 240


def flight_booking_window_multiplier(days_ahead: int) -> float:
    """Flight fares rise faster than rail as departure approaches."""
    if days_ahead >= 90:
        return 0.78
    if days_ahead >= 60:
        return 0.86
    if days_ahead >= 45:
        return 0.93
    if days_ahead >= _BASELINE_DAYS_AHEAD:
        return 1.0
    if days_ahead >= 21:
        return 1.14
    if days_ahead >= 14:
        return 1.28
    if days_ahead >= 7:
        return 1.52
    if days_ahead >= 3:
        return 1.72
    if days_ahead >= 1:
        return 1.92
    return 2.1


def _lookup_table(
    origin: str,
    destination: str,
    table: dict[tuple[str, str], float | int],
) -> float | int | None:
    return table.get(_route_key(origin, destination))


def _distance_fare_eur(origin: str, destination: str) -> float | None:
    a = _coords(origin)
    b = _coords(destination)
    if not a or not b:
        return None
    km = _haversine_km(a, b)
    return max(_FLIGHT_MIN_EUR, km * _FLIGHT_EUR_PER_KM)


def _distance_minutes(origin: str, destination: str) -> int | None:
    a = _coords(origin)
    b = _coords(destination)
    if not a or not b:
        return None
    km = _haversine_km(a, b)
    block = int(km * 0.75 + 45)
    return max(_FLIGHT_MIN_MINUTES, min(_FLIGHT_MAX_MINUTES, block))


def _via_hub_fare(origin: str, destination: str) -> float | None:
    best: float | None = None
    for hub in _FLIGHT_VIA_HUBS:
        leg1 = _lookup_table(origin, hub, _HISTORIC_FLIGHT_EUR)
        leg2 = _lookup_table(hub, destination, _HISTORIC_FLIGHT_EUR)
        if leg1 is None or leg2 is None:
            continue
        total = float(leg1) + float(leg2) * 0.92
        if best is None or total < best:
            best = total
    return best


def _via_hub_minutes(origin: str, destination: str) -> int | None:
    best: int | None = None
    for hub in _FLIGHT_VIA_HUBS:
        leg1 = _lookup_table(origin, hub, _HISTORIC_FLIGHT_MINUTES)
        leg2 = _lookup_table(hub, destination, _HISTORIC_FLIGHT_MINUTES)
        if leg1 is None or leg2 is None:
            continue
        layover = 75
        total = int(leg1) + layover + int(leg2)
        if best is None or total < best:
            best = total
    return best


def _adjust_for_departure(base: float, depart: datetime) -> float:
    days = days_until_departure(depart)
    baseline_adj = flight_booking_window_multiplier(days) / flight_booking_window_multiplier(
        _BASELINE_DAYS_AHEAD
    )
    return round(base * baseline_adj, 2)


def estimate_flight_fare(
    origin: str,
    destination: str,
    depart: datetime,
) -> float | None:
    base = _lookup_table(origin, destination, _HISTORIC_FLIGHT_EUR)
    if base is None:
        base = _via_hub_fare(origin, destination)
    if base is None:
        base = _distance_fare_eur(origin, destination)
    if base is None:
        return None
    return _adjust_for_departure(float(base), depart)


def estimate_flight_duration(
    origin: str,
    destination: str,
) -> int | None:
    minutes = _lookup_table(origin, destination, _HISTORIC_FLIGHT_MINUTES)
    if minutes is not None:
        return int(minutes)
    via = _via_hub_minutes(origin, destination)
    if via is not None:
        return via
    return _distance_minutes(origin, destination)


def estimate_flight_confidence(origin: str, destination: str) -> str:
    if _lookup_table(origin, destination, _HISTORIC_FLIGHT_EUR) is not None:
        return "historic route average"
    if _via_hub_fare(origin, destination) is not None:
        return "historic via-hub estimate"
    if _coords(origin) and _coords(destination):
        return "distance-based estimate"
    return "rough estimate"


def historic_confidence_value(confidence: str) -> float:
    return {
        "historic route average": 0.72,
        "historic via-hub estimate": 0.62,
        "distance-based estimate": 0.52,
        "rough estimate": 0.42,
    }.get(confidence, 0.6)
