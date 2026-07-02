from __future__ import annotations

import httpx

from route_finder import booking_urls
from route_finder.historic_fares import estimate_confidence, estimate_fare
from route_finder.models import RouteOption, SearchRequest, TransportMode

_RAIL_MODES = {TransportMode.TRAIN, TransportMode.BUS}


def _clean_place(name: str) -> str:
    text = name.strip()
    if "(" in text:
        text = text.split("(")[0].strip()
    if "," in text:
        text = text.split(",")[0].strip()
    return text


def _omio_link(leg) -> str:
    mode = "bus" if leg.mode == TransportMode.BUS else "train"
    return booking_urls.omio_search(leg.origin, leg.destination, leg.depart, mode=mode)


def _rail_bus_legs(route: RouteOption) -> list:
    return [leg for leg in route.legs if leg.mode in _RAIL_MODES]


def _unpriced_rail_legs(route: RouteOption) -> list:
    return [
        leg
        for leg in route.legs
        if leg.mode in _RAIL_MODES and leg.cost_eur <= 0 and leg.duration_minutes >= 10
    ]


def _split_price_across_legs(legs: list, total_price: float) -> None:
    if not legs:
        return
    total_minutes = sum(max(leg.duration_minutes, 1) for leg in legs)
    remaining = total_price
    for index, leg in enumerate(legs):
        if index == len(legs) - 1:
            leg.cost_eur = round(remaining, 2)
        else:
            share = total_price * max(leg.duration_minutes, 1) / total_minutes
            leg.cost_eur = round(share, 2)
            remaining -= leg.cost_eur
        leg.booking_url = _omio_link(leg)


def _mark_estimated(route: RouteOption, confidence: str) -> None:
    route.price_estimated = True
    route.historic_confidence = _historic_confidence_value(confidence)
    note = f"historic fare model ({confidence})"
    if note not in route.data_source:
        route.data_source = f"{route.data_source} + {note}"


def _historic_confidence_value(confidence: str) -> float:
    mapping = {
        "historic route average": 0.75,
        "historic via-hub estimate": 0.65,
        "distance-based estimate": 0.55,
        "segment estimates": 0.6,
        "rough estimate": 0.45,
    }
    return mapping.get(confidence, 0.6)


def enrich_route_prices(route: RouteOption, request: SearchRequest) -> None:
    if all(leg.cost_eur > 0 for leg in _rail_bus_legs(route)):
        return

    confidences: list[str] = []
    priced_any = False

    for leg in _unpriced_rail_legs(route):
        mode = "bus" if leg.mode == TransportMode.BUS else "train"
        price = estimate_fare(
            _clean_place(leg.origin),
            _clean_place(leg.destination),
            leg.depart,
            mode=mode,
        )
        if price is None:
            continue
        leg.cost_eur = price
        leg.booking_url = _omio_link(leg)
        priced_any = True
        confidences.append(
            estimate_confidence(leg.origin, leg.destination, mode)
        )

    remaining = _unpriced_rail_legs(route)
    if remaining and not priced_any:
        modes = {leg.mode for leg in route.legs}
        primary_mode = (
            "bus"
            if TransportMode.BUS in modes and TransportMode.TRAIN not in modes
            else "train"
        )
        trip_depart = route.legs[0].depart if route.legs else request.ideal_departure
        trip_price = estimate_fare(
            request.origin,
            request.destination,
            trip_depart,
            mode=primary_mode,
        )
        if trip_price is not None:
            confidence = estimate_confidence(
                request.origin, request.destination, primary_mode
            )
            _split_price_across_legs(remaining, trip_price)
            _mark_estimated(route, confidence)
            priced_any = True

    if priced_any and not route.price_estimated:
        confidence = (
            confidences[0]
            if confidences and len(set(confidences)) == 1
            else "segment estimates"
        )
        _mark_estimated(route, confidence)


def enrich_routes(
    routes: list[RouteOption],
    request: SearchRequest,
    client: httpx.Client,
) -> None:
    del client
    for route in routes:
        enrich_route_prices(route, request)
        _attach_omio_links(route)


def _attach_omio_links(route: RouteOption) -> None:
    for leg in route.legs:
        if leg.mode not in _RAIL_MODES:
            continue
        if leg.booking_url and "omio.com" in leg.booking_url:
            continue
        leg.booking_url = _omio_link(leg)
