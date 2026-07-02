from __future__ import annotations

import re
from dataclasses import dataclass

from route_finder.airports import EUROPEAN_AIRPORTS
from route_finder.historic_fares import canonical_place
from route_finder.hubs import HUB_COORDINATES
from route_finder.models import RouteOption, TransportMode

_IATA_RE = re.compile(r"\(([A-Z]{3})\)")
_VIA_NOTE_RE = re.compile(
    r"(?:via|transfer at|leg via)\s+([A-Za-zÀ-ÿ'\- ]+)", re.I
)

_HUB_CANONICAL: dict[str, str] = {
    canonical_place(name): name for name in HUB_COORDINATES
}
_IATA_TO_CITY: dict[str, str] = {ap.iata: ap.city for ap in EUROPEAN_AIRPORTS}


@dataclass(frozen=True)
class ModeBreakdown:
    duration_minutes: int
    cost_eur: float
    has_priced_leg: bool


def _hub_label(canonical: str) -> str | None:
    if canonical in _HUB_CANONICAL:
        return _HUB_CANONICAL[canonical]
    return None


def _place_hub(place: str) -> str | None:
    if not place or place.lower() in ("n/a", "a", "b"):
        return None
    match = _IATA_RE.search(place)
    if match:
        city = _IATA_TO_CITY.get(match.group(1))
        if city:
            return city
    canonical = canonical_place(place)
    hub = _hub_label(canonical)
    if hub:
        return hub
    for name in HUB_COORDINATES:
        if name.lower() in place.lower():
            return name
    return None


def _hubs_from_notes(route: RouteOption) -> list[str]:
    found: list[str] = []
    for leg in route.legs:
        if not leg.notes:
            continue
        for match in _VIA_NOTE_RE.finditer(leg.notes):
            hub = _place_hub(match.group(1).strip())
            if hub:
                found.append(hub)
    return found


def route_via_hubs(route: RouteOption, origin: str, destination: str) -> list[str]:
    """Major cities/hubs touched between origin and destination."""
    origin_hub = _place_hub(origin) or canonical_place(origin)
    dest_hub = _place_hub(destination) or canonical_place(destination)
    skip = {origin_hub, dest_hub, canonical_place(origin), canonical_place(destination)}

    hubs: list[str] = []
    seen: set[str] = set()

    def add(name: str | None) -> None:
        if not name:
            return
        key = canonical_place(name)
        if key in skip:
            return
        label = _hub_label(key)
        if not label:
            for ap in EUROPEAN_AIRPORTS:
                if ap.city.lower() == key:
                    label = ap.city
                    break
        if not label:
            return
        if key in seen:
            return
        seen.add(key)
        hubs.append(label)

    for leg in route.legs:
        if leg.mode == TransportMode.WALK:
            continue
        add(_place_hub(leg.origin))
        add(_place_hub(leg.destination))

    for hub in _hubs_from_notes(route):
        add(hub)

    return hubs


def mode_breakdown(route: RouteOption) -> dict[TransportMode, ModeBreakdown]:
    totals: dict[TransportMode, ModeBreakdown] = {}
    for leg in route.legs:
        if leg.mode == TransportMode.WALK:
            continue
        current = totals.get(leg.mode)
        duration = leg.duration_minutes
        cost = leg.cost_eur
        priced = leg.cost_eur > 0
        if current is None:
            totals[leg.mode] = ModeBreakdown(duration, cost, priced)
        else:
            totals[leg.mode] = ModeBreakdown(
                current.duration_minutes + duration,
                current.cost_eur + cost,
                current.has_priced_leg or priced,
            )
    return totals


def suggest_stopovers(route: RouteOption, origin: str, destination: str) -> list[dict[str, str]]:
    """
    Suggest convenient stopover hubs along this route.

    Heuristic rules:
    - Prefer major hubs that appear as transfer points (layover >= ~45m).
    - For very long trips, also suggest a midpoint hub for an overnight stop.
    """
    hubs = route_via_hubs(route, origin, destination)
    if not hubs:
        return []

    # Compute layovers at major transfer points (ignoring short walks).
    transfers: list[tuple[str, int]] = []
    for prev, nxt in zip(route.legs, route.legs[1:]):
        if prev.mode == TransportMode.WALK:
            continue
        if nxt.mode == TransportMode.WALK and nxt.duration_minutes <= 15:
            continue
        gap_min = int((nxt.depart - prev.arrive).total_seconds() / 60)
        if gap_min < 0:
            continue
        point = prev.destination
        hub = _place_hub(point)
        if hub and hub in hubs:
            transfers.append((hub, gap_min))

    suggestions: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(city: str, reason: str) -> None:
        if city in seen:
            return
        seen.add(city)
        suggestions.append({"city": city, "reason": reason})

    for hub, gap in sorted(transfers, key=lambda x: -x[1]):
        if gap >= 45:
            add(hub, f"Easy stopover (transfer ~{gap}m)")

    # Midpoint/overnight suggestion for long trips.
    total = route.total_duration_minutes
    if total >= 10 * 60:
        target = total // 2
        elapsed = 0
        best: tuple[str, int] | None = None
        for leg in route.legs:
            if leg.mode == TransportMode.WALK:
                continue
            elapsed += max(leg.duration_minutes, 0)
            hub = _place_hub(leg.destination)
            if hub and hub in hubs:
                delta = abs(elapsed - target)
                if best is None or delta < best[1]:
                    best = (hub, delta)
        if best:
            add(best[0], "Convenient midpoint stop")

    return suggestions[:3]


def route_category(route: RouteOption) -> str:
    modes = {leg.mode for leg in route.legs if leg.mode != TransportMode.WALK}
    has_plane = TransportMode.PLANE in modes
    has_train = TransportMode.TRAIN in modes
    has_bus = TransportMode.BUS in modes
    if has_plane and (has_train or has_bus):
        return "intermodal"
    if has_plane:
        return "flight"
    if has_train and has_bus:
        breakdown = mode_breakdown(route)
        train_min = breakdown.get(TransportMode.TRAIN, ModeBreakdown(0, 0, False)).duration_minutes
        bus_min = breakdown.get(TransportMode.BUS, ModeBreakdown(0, 0, False)).duration_minutes
        return "train" if train_min >= bus_min else "bus"
    if has_train:
        return "train"
    if has_bus:
        return "bus"
    if TransportMode.WALK in modes:
        return "walk"
    return "other"
