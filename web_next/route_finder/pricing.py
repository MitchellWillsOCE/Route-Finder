from __future__ import annotations

from datetime import datetime, timedelta

from route_finder.models import JourneyLeg, RouteOption, SearchRequest, TransportMode, PriceSource


def _leg_source(leg: JourneyLeg, route: RouteOption) -> PriceSource:
    if leg.mode == TransportMode.WALK:
        return PriceSource.FREE
    if leg.cost_eur <= 0:
        return PriceSource.UNKNOWN
    if leg.mode == TransportMode.BUS and route.price_verified:
        return PriceSource.FLIXBUS_API
    if leg.mode == TransportMode.PLANE and route.price_verified:
        return PriceSource.SKYSCANNER
    if leg.mode == TransportMode.PLANE and route.price_estimated:
        return PriceSource.HISTORIC
    if route.price_estimated:
        return PriceSource.HISTORIC
    if route.price_verified:
        return PriceSource.HAFAS
    return PriceSource.UNKNOWN


def route_price_confidence(route: RouteOption) -> float:
    if not route.legs:
        return 0.0
    weights: list[float] = []
    for leg in route.legs:
        if leg.mode == TransportMode.WALK:
            continue
        source = _leg_source(leg, route)
        if source == PriceSource.FLIXBUS_API:
            weights.append(0.95)
        elif source == PriceSource.SKYSCANNER:
            weights.append(0.85)
        elif source == PriceSource.HAFAS:
            weights.append(0.8)
        elif source == PriceSource.HISTORIC:
            weights.append(route.historic_confidence)
        elif source == PriceSource.FREE:
            weights.append(1.0)
        else:
            weights.append(0.25)
    if not weights:
        return 0.2
    return round(sum(weights) / len(weights), 2)


def apply_route_pricing_meta(route: RouteOption) -> None:
    route.price_confidence = route_price_confidence(route)
    sources = {_leg_source(leg, route) for leg in route.legs if leg.mode != TransportMode.WALK}
    if PriceSource.FLIXBUS_API in sources:
        route.price_source = PriceSource.FLIXBUS_API
    elif PriceSource.SKYSCANNER in sources and PriceSource.HISTORIC in sources:
        route.price_source = PriceSource.SKYSCANNER
    elif PriceSource.HISTORIC in sources:
        route.price_source = PriceSource.HISTORIC
    elif PriceSource.SKYSCANNER in sources:
        route.price_source = PriceSource.SKYSCANNER
    elif PriceSource.HAFAS in sources:
        route.price_source = PriceSource.HAFAS
    elif not sources or sources == {PriceSource.FREE}:
        route.price_source = PriceSource.FREE
    else:
        route.price_source = PriceSource.UNKNOWN


def departure_day_penalty(route: RouteOption, ideal: datetime) -> float:
    if not route.legs:
        return 1.0
    depart_day = route.legs[0].depart.date()
    ideal_day = ideal.date()
    delta = abs((depart_day - ideal_day).days)
    if delta == 0:
        return 1.0
    if delta == 1:
        return 0.97
    if delta == 2:
        return 0.93
    if delta <= 3:
        return 0.88
    return 0.8
