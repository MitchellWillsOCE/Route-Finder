from __future__ import annotations

from datetime import timedelta

from route_finder.models import JourneyLeg, RouteOption, TransportMode

# Minimum connection time between consecutive legs (minutes).
_CONNECTION_MINUTES: dict[tuple[TransportMode, TransportMode], int] = {
    (TransportMode.TRAIN, TransportMode.TRAIN): 12,
    (TransportMode.TRAIN, TransportMode.BUS): 15,
    (TransportMode.BUS, TransportMode.TRAIN): 15,
    (TransportMode.BUS, TransportMode.BUS): 10,
    (TransportMode.TRAIN, TransportMode.PLANE): 90,
    (TransportMode.BUS, TransportMode.PLANE): 90,
    (TransportMode.PLANE, TransportMode.TRAIN): 45,
    (TransportMode.PLANE, TransportMode.BUS): 45,
    (TransportMode.PLANE, TransportMode.PLANE): 60,
    (TransportMode.WALK, TransportMode.TRAIN): 5,
    (TransportMode.WALK, TransportMode.BUS): 5,
    (TransportMode.TRAIN, TransportMode.WALK): 5,
    (TransportMode.BUS, TransportMode.WALK): 5,
    (TransportMode.WALK, TransportMode.PLANE): 60,
    (TransportMode.PLANE, TransportMode.WALK): 30,
}

_DEFAULT_CONNECTION_MIN = 20
_MAX_WALK_LEG_MIN = 180


def min_connection_minutes(from_mode: TransportMode, to_mode: TransportMode) -> int:
    if from_mode == TransportMode.WALK and to_mode == TransportMode.WALK:
        return 0
    return _CONNECTION_MINUTES.get((from_mode, to_mode), _DEFAULT_CONNECTION_MIN)


def count_transfers(route: RouteOption) -> int:
    if len(route.legs) < 2:
        return 0
    transfers = 0
    prev = route.legs[0]
    for leg in route.legs[1:]:
        if leg.mode == TransportMode.WALK and leg.duration_minutes <= 15:
            continue
        if prev.mode == TransportMode.WALK and prev.duration_minutes <= 15:
            prev = leg
            continue
        if leg.mode != prev.mode or (
            leg.origin.lower() != prev.destination.lower()
        ):
            transfers += 1
        prev = leg
    return transfers


def legs_are_connected(prev: JourneyLeg, nxt: JourneyLeg) -> bool:
    # Short station-access walks are timed tightly in MOTIS data.
    if prev.mode == TransportMode.WALK and prev.duration_minutes <= 15:
        return nxt.depart >= prev.arrive - timedelta(minutes=2)
    if nxt.mode == TransportMode.WALK and nxt.duration_minutes <= 15:
        return nxt.depart >= prev.arrive - timedelta(minutes=2)
    required = min_connection_minutes(prev.mode, nxt.mode)
    earliest = prev.arrive + timedelta(minutes=required)
    return nxt.depart >= earliest - timedelta(minutes=1)


def validate_route(route: RouteOption) -> bool:
    if not route.legs:
        return False
    for leg in route.legs:
        if leg.mode == TransportMode.WALK and leg.duration_minutes > _MAX_WALK_LEG_MIN:
            return False
    for prev, nxt in zip(route.legs, route.legs[1:]):
        if not legs_are_connected(prev, nxt):
            return False
    return True


def filter_valid_routes(routes: list[RouteOption]) -> list[RouteOption]:
    return [route for route in routes if validate_route(route)]
