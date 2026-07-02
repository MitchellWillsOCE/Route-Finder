from __future__ import annotations

from datetime import timedelta

from route_finder import booking_urls
from route_finder.connections import min_connection_minutes, validate_route
from route_finder.models import JourneyLeg, RouteOption, TransportMode
from route_finder.providers.motis_client import merge_routes


def transfer_leg(
    origin: str,
    destination: str,
    depart,
    duration_minutes: int,
    *,
    notes: str = "",
) -> JourneyLeg:
    arrive = depart + timedelta(minutes=duration_minutes)
    return JourneyLeg(
        mode=TransportMode.WALK,
        origin=origin,
        destination=destination,
        depart=depart,
        arrive=arrive,
        duration_minutes=duration_minutes,
        cost_eur=0.0,
        operator="n/a",
        booking_url=booking_urls.google_maps_transit(origin, destination),
        notes=notes or "Transfer",
    )


def single_leg_route(leg: JourneyLeg, *, data_source: str, price_verified: bool = False) -> RouteOption:
    return RouteOption(
        legs=[leg],
        label="",
        efficiency_score=0.0,
        data_source=data_source,
        price_verified=price_verified,
    )


def chain_routes(
    segments: list[RouteOption],
    *,
    hubs: list[str],
    final_destination: str,
    data_source: str,
) -> RouteOption | None:
    if not segments:
        return None

    result = segments[0]
    for index, segment in enumerate(segments[1:], start=1):
        hub = hubs[index - 1] if index - 1 < len(hubs) else ""
        is_last = index == len(segments) - 1
        merged = merge_routes(
            result,
            segment,
            hub_name=hub,
            final_destination=final_destination if is_last else segment.legs[-1].destination,
            data_source=data_source,
            min_connection_minutes=min_connection_minutes(
                result.legs[-1].mode, segment.legs[0].mode
            ),
        )
        if not merged or not validate_route(merged):
            return None
        result = merged
    result.data_source = data_source
    return result


def build_airport_composites(
    flight_routes: list[RouteOption],
    bus_routes: list[RouteOption],
    origin: str,
    destination: str,
) -> list[RouteOption]:
    """Combine flight routes with airport transfer buses when available."""
    if not flight_routes:
        return []

    composites: list[RouteOption] = []
    for flight in flight_routes[:3]:
        flight_leg = next((leg for leg in flight.legs if leg.mode == TransportMode.PLANE), None)
        if not flight_leg:
            continue

        transfer_out = JourneyLeg(
            mode=TransportMode.WALK,
            origin=origin,
            destination=flight_leg.origin,
            depart=flight_leg.depart - timedelta(minutes=45),
            arrive=flight_leg.depart,
            duration_minutes=45,
            cost_eur=0.0,
            operator="n/a",
            booking_url=booking_urls.google_maps_transit(origin, flight_leg.origin),
            notes="Airport access (metro/walk estimate)",
        )

        transfer_in = JourneyLeg(
            mode=TransportMode.BUS,
            origin=flight_leg.destination,
            destination=destination,
            depart=flight_leg.arrive,
            arrive=flight_leg.arrive + timedelta(minutes=35),
            duration_minutes=35,
            cost_eur=6.5,
            operator="Airport shuttle (estimate)",
            booking_url=booking_urls.flixbus(
                flight_leg.destination, destination, flight_leg.arrive
            ),
            notes="Check FlixBus/local shuttle availability",
        )

        for bus in bus_routes:
            if "airport" in bus.legs[0].origin.lower() or "airport" in bus.legs[-1].destination.lower():
                transfer_in = bus.legs[-1]
                break

        composites.append(
            RouteOption(
                legs=[transfer_out, flight_leg, transfer_in],
                label="",
                efficiency_score=0.0,
                data_source="Flight + airport transfer",
            )
        )

    return composites
