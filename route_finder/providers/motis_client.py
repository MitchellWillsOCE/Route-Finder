from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from route_finder import booking_urls
from route_finder.config import CONFIG
from route_finder.models import JourneyLeg, RouteOption, SearchRequest, TransportMode
from route_finder.service_ids import motis_service_id

TRANSITOUS_URL = "https://api.transitous.org/api/v5/plan"

RAIL_MODES = {
    "HIGHSPEED_RAIL",
    "LONG_DISTANCE",
    "NIGHT_RAIL",
    "REGIONAL_RAIL",
    "SUBURBAN",
    "RAIL",
    "METRO",
    "TRAM",
}


def parse_motis_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def motis_mode(mode: str) -> TransportMode:
    upper = mode.upper()
    if upper in ("WALK", "FOOT"):
        return TransportMode.WALK
    if upper == "BUS":
        return TransportMode.BUS
    if upper in RAIL_MODES:
        return TransportMode.TRAIN
    return TransportMode.TRAIN


def plan_itineraries(
    client: httpx.Client,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    depart: datetime,
    *,
    max_transfers: int = 4,
) -> list[dict]:
    tz_offset = depart.strftime("%z")
    if tz_offset:
        tz_offset = f"{tz_offset[:3]}:{tz_offset[3:]}"
    else:
        tz_offset = "+02:00"
    time_str = depart.strftime(f"%Y-%m-%dT%H:%M:%S{tz_offset}")

    response = client.get(
        TRANSITOUS_URL,
        params={
            "fromPlace": f"{from_lat},{from_lon}",
            "toPlace": f"{to_lat},{to_lon}",
            "time": time_str,
            "arriveBy": "false",
            "maxTransfers": str(max_transfers),
            "transitModes": "RAIL,BUS,WALK",
        },
        headers={"User-Agent": CONFIG.nominatim_user_agent},
        timeout=CONFIG.request_timeout,
    )
    if response.status_code != 200:
        return []

    itineraries = response.json().get("itineraries", [])
    itineraries.sort(
        key=lambda it: (
            0 if any(leg.get("mode") == "HIGHSPEED_RAIL" for leg in it.get("legs", [])) else 1,
            it.get("transfers", 99),
            it.get("duration", 99999),
        )
    )
    return itineraries


def itinerary_to_legs(
    itinerary: dict,
    request: SearchRequest,
    *,
    origin_label: str | None = None,
    destination_label: str | None = None,
    booking_origin: str | None = None,
    booking_destination: str | None = None,
) -> list[JourneyLeg]:
    origin_label = origin_label or request.origin
    destination_label = destination_label or request.destination
    book_o = booking_origin or request.origin
    book_d = booking_destination or request.destination

    trip_depart = parse_motis_time(itinerary["startTime"])
    trip_book_url = booking_urls.train_booking(book_o, book_d, trip_depart)
    train_booking_set = False
    legs: list[JourneyLeg] = []

    for leg_data in itinerary.get("legs", []):
        mode_name = leg_data.get("mode", "RAIL")
        if mode_name.upper() in ("CAR", "BIKE"):
            continue

        leg_depart = parse_motis_time(leg_data["startTime"])
        leg_arrive = parse_motis_time(leg_data["endTime"])
        duration_min = int(leg_data.get("duration", 0) / 60)
        from_name = leg_data.get("from", {}).get("name", origin_label)
        to_name = leg_data.get("to", {}).get("name", destination_label)
        if from_name in ("START", "END"):
            from_name = origin_label if from_name == "START" else from_name
        if to_name in ("START", "END"):
            to_name = destination_label if to_name == "END" else to_name

        operator = (
            leg_data.get("agencyName")
            or (leg_data.get("route") or {}).get("agencyName")
            or mode_name.replace("_", " ").title()
        )
        service_id = (
            motis_service_id(leg_data) if motis_mode(mode_name) != TransportMode.WALK else ""
        )

        if motis_mode(mode_name) == TransportMode.WALK:
            booking = booking_urls.google_maps_walk(from_name, to_name)
        elif not train_booking_set:
            booking = trip_book_url
            train_booking_set = True
        else:
            booking = ""

        legs.append(
            JourneyLeg(
                mode=motis_mode(mode_name),
                origin=from_name,
                destination=to_name,
                depart=leg_depart,
                arrive=leg_arrive,
                duration_minutes=duration_min,
                cost_eur=0.0,
                operator=operator,
                booking_url=booking,
                service_id=service_id,
            )
        )
    return legs


def itinerary_to_route(
    itinerary: dict,
    request: SearchRequest,
    *,
    data_source: str,
    origin_label: str | None = None,
    destination_label: str | None = None,
    booking_origin: str | None = None,
    booking_destination: str | None = None,
    hub_note: str = "",
) -> RouteOption | None:
    legs = itinerary_to_legs(
        itinerary,
        request,
        origin_label=origin_label,
        destination_label=destination_label,
        booking_origin=booking_origin,
        booking_destination=booking_destination,
    )
    if not legs or not any(leg.mode == TransportMode.TRAIN for leg in legs):
        return None
    if hub_note and legs:
        legs[0].notes = hub_note
    return RouteOption(
        legs=legs,
        label="",
        efficiency_score=0.0,
        data_source=data_source,
        price_verified=False,
    )


def merge_routes(
    first: RouteOption,
    second: RouteOption,
    *,
    hub_name: str,
    final_destination: str,
    data_source: str,
    min_connection_minutes: int = 20,
) -> RouteOption | None:
    if not first.legs or not second.legs:
        return None

    first_arrive = first.legs[-1].arrive
    second_depart = second.legs[0].depart
    if second_depart < first_arrive + timedelta(minutes=min_connection_minutes):
        return None

    combined_legs = list(first.legs)
    if combined_legs[-1].destination.lower() != second.legs[0].origin.lower():
        combined_legs.append(
            JourneyLeg(
                mode=TransportMode.WALK,
                origin=combined_legs[-1].destination,
                destination=second.legs[0].origin,
                depart=first_arrive,
                arrive=second_depart,
                duration_minutes=max(
                    int((second_depart - first_arrive).total_seconds() / 60), 5
                ),
                cost_eur=0.0,
                operator="n/a",
                booking_url=booking_urls.google_maps_walk(
                    combined_legs[-1].destination, second.legs[0].origin
                ),
                notes=f"Transfer at {hub_name}",
            )
        )
    combined_legs.extend(second.legs)
    combined_legs[-1].destination = final_destination

    return RouteOption(
        legs=combined_legs,
        label="",
        efficiency_score=0.0,
        data_source=data_source,
        price_verified=first.price_verified or second.price_verified,
    )
