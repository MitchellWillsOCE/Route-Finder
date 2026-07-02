from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

import httpx

from route_finder import booking_urls
from route_finder.config import CONFIG
from route_finder.geocode import geocode, geocode_station
from route_finder.hubs import hub_station_coords, nearest_hubs
from route_finder.models import JourneyLeg, RouteOption, SearchRequest, TransportMode
from route_finder.providers.base import RouteProvider
from route_finder.providers.motis_client import (
    itinerary_to_route,
    merge_routes,
    plan_itineraries,
)
from route_finder.service_ids import hafas_service_id, navitia_service_id
from route_finder.workers import map_parallel, worker_count

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


class TrainProvider(RouteProvider):
    name = "Transitous / MOTIS"

    HAFAS_MIRRORS = (
        "https://v6.db.transport.rest",
        "https://v5.db.transport.rest",
    )

    def search(
        self,
        request: SearchRequest,
        client: httpx.Client,
        on_progress: Callable[[str], None] | None = None,
    ) -> list[RouteOption]:
        notify = on_progress or (lambda _msg: None)

        notify("Rail timetables...")
        motis_routes = self._search_motis(request, client)
        if motis_routes:
            return motis_routes

        notify("Rail (HAFAS)...")
        hafas_routes = self._search_hafas(request, client, notify)
        if hafas_routes:
            return hafas_routes

        notify("Trying Navitia...")
        navitia_routes = self._navitia_fallback(request, client)
        return navitia_routes

    def _search_motis(self, request: SearchRequest, client: httpx.Client) -> list[RouteOption]:
        origin = geocode(request.origin, client)
        destination = geocode(request.destination, client)
        options = self._motis_routes_for_coords(
            request, client, origin.lat, origin.lon, destination.lat, destination.lon
        )
        if options:
            return options

        dest_station = geocode_station(request.destination, client)
        if (dest_station.lat, dest_station.lon) != (destination.lat, destination.lon):
            options = self._motis_routes_for_coords(
                request,
                client,
                origin.lat,
                origin.lon,
                dest_station.lat,
                dest_station.lon,
            )
            if options:
                return options

        return self._search_via_hubs(request, client, origin, destination, dest_station)

    def _motis_routes_for_coords(
        self,
        request: SearchRequest,
        client: httpx.Client,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        *,
        data_source: str = "Transitous / MOTIS (live timetable)",
        hub_note: str = "",
    ) -> list[RouteOption]:
        options: list[RouteOption] = []
        seen: set[str] = set()

        base = request.ideal_departure.replace(hour=8, minute=0, second=0, microsecond=0)
        offsets = [
            offset
            for offset in range(-request.flexibility_days, request.flexibility_days + 1)
            if (base + timedelta(days=offset)).date() >= datetime.now().date()
        ]

        def _fetch_day(offset: int) -> list[dict]:
            with httpx.Client(timeout=CONFIG.request_timeout) as thread_client:
                depart = base + timedelta(days=offset)
                return plan_itineraries(
                    thread_client, from_lat, from_lon, to_lat, to_lon, depart
                )[:4]

        for itineraries in map_parallel(offsets, _fetch_day, max_workers=worker_count()):
            if not itineraries:
                continue
            for itinerary in itineraries:
                route = itinerary_to_route(
                    itinerary,
                    request,
                    data_source=data_source,
                    hub_note=hub_note,
                )
                if not route:
                    continue
                key = "|".join(
                    f"{leg.depart.isoformat()}-{leg.origin}-{leg.destination}"
                    for leg in route.legs
                )
                if key in seen:
                    continue
                seen.add(key)
                options.append(route)

        options.sort(key=lambda r: r.total_duration_minutes)
        return options[:4]

    def _search_via_hubs(
        self,
        request: SearchRequest,
        client: httpx.Client,
        origin,
        destination,
        dest_station,
    ) -> list[RouteOption]:
        hubs = nearest_hubs(
            destination.lat,
            destination.lon,
            limit=2,
            max_km=100.0,
            exclude_name=destination.name,
        )
        if not hubs:
            return []

        options: list[RouteOption] = []
        seen: set[str] = set()
        depart = request.ideal_departure.replace(hour=8, minute=0, second=0, microsecond=0)
        if depart.date() < datetime.now().date():
            depart = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        for hub_name, hub_lat, hub_lon, _ in hubs:
            long_legs = plan_itineraries(
                client, origin.lat, origin.lon, hub_lat, hub_lon, depart
            )[:1]
            if not long_legs:
                continue

            long_it = long_legs[0]
            long_route = itinerary_to_route(
                long_it,
                request,
                data_source="Transitous / MOTIS via hub (live timetable)",
                destination_label=hub_name,
                booking_destination=hub_name,
                hub_note=f"Long-distance leg via {hub_name}",
            )
            if not long_route:
                continue

            local_depart = long_route.legs[-1].arrive + timedelta(minutes=25)
            hub_station_lat, hub_station_lon = hub_station_coords(hub_name)
            local_legs = plan_itineraries(
                client,
                hub_station_lat,
                hub_station_lon,
                dest_station.lat,
                dest_station.lon,
                local_depart,
            )[:1]
            if not local_legs:
                continue

            local_route = itinerary_to_route(
                local_legs[0],
                request,
                data_source="Transitous / MOTIS via hub (live timetable)",
                origin_label=hub_name,
                destination_label=request.destination,
                booking_origin=hub_name,
            )
            if not local_route:
                continue

            combined = merge_routes(
                long_route,
                local_route,
                hub_name=hub_name,
                final_destination=request.destination,
                data_source="Transitous / MOTIS via hub (live timetable)",
            )
            if not combined:
                continue

            key = "|".join(
                f"{leg.depart.isoformat()}-{leg.origin}-{leg.destination}"
                for leg in combined.legs
            )
            if key in seen:
                continue
            seen.add(key)
            options.append(combined)

        options.sort(key=lambda r: r.total_duration_minutes)
        return options[:4]

    def _search_hafas(
        self,
        request: SearchRequest,
        client: httpx.Client,
        notify: Callable[[str], None],
    ) -> list[RouteOption]:
        notify("Rail (HAFAS)...")
        try:
            from_loc = self._resolve_location(client, request.origin)
            to_loc = self._resolve_location(client, request.destination)
        except Exception:
            return []

        options: list[RouteOption] = []
        seen: set[str] = set()

        for depart in [
            request.ideal_departure.replace(hour=8, minute=0, second=0, microsecond=0)
            + timedelta(days=offset)
            for offset in range(-request.flexibility_days, request.flexibility_days + 1)
            if (
                request.ideal_departure.replace(hour=8, minute=0, second=0, microsecond=0)
                + timedelta(days=offset)
            ).date()
            >= datetime.now().date()
        ]:
            try:
                journeys = self._journeys(client, from_loc["id"], to_loc["id"], depart)
            except Exception:
                continue

            for journey in journeys:
                legs_data = journey.get("legs", [])
                if not legs_data:
                    continue

                key = "|".join(
                    f"{leg.get('origin', {}).get('name')}-{leg.get('destination', {}).get('name')}-"
                    f"{leg.get('departure', '')}"
                    for leg in legs_data
                )
                if key in seen:
                    continue
                seen.add(key)

                legs: list[JourneyLeg] = []
                trip_depart = datetime.fromisoformat(legs_data[0]["departure"].split("+")[0])
                trip_book_url = booking_urls.train_booking(
                    request.origin, request.destination, trip_depart
                )
                train_booking_set = False

                for leg_data in legs_data:
                    mode = (
                        TransportMode.WALK
                        if leg_data.get("walking", False)
                        else TransportMode.TRAIN
                    )
                    leg_depart = datetime.fromisoformat(leg_data["departure"].split("+")[0])
                    leg_arrive = datetime.fromisoformat(leg_data["arrival"].split("+")[0])
                    duration_min = int((leg_arrive - leg_depart).total_seconds() / 60)
                    origin_name = leg_data.get("origin", {}).get("name", request.origin)
                    dest_name = leg_data.get("destination", {}).get("name", request.destination)
                    line = leg_data.get("line", {}) or {}
                    operator = line.get("operator", {}).get("name") or line.get("name") or "Rail"
                    service_id = hafas_service_id(leg_data) if mode != TransportMode.WALK else ""

                    if mode == TransportMode.WALK:
                        booking = booking_urls.google_maps_walk(origin_name, dest_name)
                    elif not train_booking_set:
                        booking = trip_book_url
                        train_booking_set = True
                    else:
                        booking = ""

                    legs.append(
                        JourneyLeg(
                            mode=mode,
                            origin=origin_name,
                            destination=dest_name,
                            depart=leg_depart,
                            arrive=leg_arrive,
                            duration_minutes=duration_min,
                            cost_eur=0.0,
                            operator=operator,
                            booking_url=booking,
                            service_id=service_id,
                        )
                    )

                if not legs:
                    continue

                price_hint = journey.get("price", {})
                total_price = 0.0
                price_verified = False
                if isinstance(price_hint, dict) and price_hint.get("amount") is not None:
                    total_price = float(price_hint["amount"])
                    price_verified = True
                    per_leg = total_price / len(legs)
                    for leg in legs:
                        if leg.mode == TransportMode.TRAIN:
                            leg.cost_eur = per_leg

                options.append(
                    RouteOption(
                        legs=legs,
                        label="",
                        efficiency_score=0.0,
                        data_source="HAFAS / DB transport.rest (live)",
                        price_verified=price_verified,
                    )
                )

        options.sort(key=lambda r: r.total_duration_minutes)
        return options[:4]

    def _resolve_location(self, client: httpx.Client, query: str) -> dict:
        last_error: Exception | None = None
        for base in self.HAFAS_MIRRORS:
            try:
                response = client.get(
                    f"{base}/locations",
                    params={"query": query, "results": 5, "language": "en"},
                    timeout=CONFIG.request_timeout,
                )
                response.raise_for_status()
                results = response.json()
                if results:
                    return results[0]
            except Exception as exc:
                last_error = exc
        raise ValueError(f"No train station found for: {query}") from last_error

    def _journeys(
        self, client: httpx.Client, from_id: str, to_id: str, depart: datetime
    ) -> list[dict]:
        last_error: Exception | None = None
        for base in self.HAFAS_MIRRORS:
            try:
                response = client.get(
                    f"{base}/journeys",
                    params={
                        "from": from_id,
                        "to": to_id,
                        "departure": depart.isoformat(),
                        "results": 5,
                        "stopovers": "true",
                        "language": "en",
                    },
                    timeout=CONFIG.request_timeout,
                )
                response.raise_for_status()
                return response.json().get("journeys", [])
            except Exception as exc:
                last_error = exc
        raise RuntimeError("Train journey search failed") from last_error

    def _navitia_fallback(
        self, request: SearchRequest, client: httpx.Client
    ) -> list[RouteOption]:
        if not CONFIG.navitia_api_key:
            return []

        try:
            from_place = client.get(
                "https://api.navitia.io/v1/coverage/sncf/places",
                params={"q": request.origin},
                headers={"Authorization": CONFIG.navitia_api_key},
                timeout=CONFIG.request_timeout,
            ).json()
            to_place = client.get(
                "https://api.navitia.io/v1/coverage/sncf/places",
                params={"q": request.destination},
                headers={"Authorization": CONFIG.navitia_api_key},
                timeout=CONFIG.request_timeout,
            ).json()
            if not from_place.get("places") or not to_place.get("places"):
                return []

            from_id = from_place["places"][0]["id"]
            to_id = to_place["places"][0]["id"]
            depart = request.ideal_departure.strftime("%Y%m%dT%H%M%S")
            response = client.get(
                "https://api.navitia.io/v1/coverage/sncf/journeys",
                params={"from": from_id, "to": to_id, "datetime": depart},
                headers={"Authorization": CONFIG.navitia_api_key},
                timeout=CONFIG.request_timeout,
            )
            response.raise_for_status()
        except Exception:
            return []

        options: list[RouteOption] = []
        for journey in response.json().get("journeys", [])[:4]:
            legs: list[JourneyLeg] = []
            sections = [
                s
                for s in journey.get("sections", [])
                if s.get("type") in ("public_transport", "street_network")
            ]
            if not sections:
                continue

            trip_depart = datetime.fromisoformat(sections[0]["departure_date_time"][:19])
            trip_book_url = booking_urls.train_booking(
                request.origin, request.destination, trip_depart
            )
            train_booking_set = False

            for section in sections:
                mode = (
                    TransportMode.WALK
                    if section.get("type") == "street_network"
                    else TransportMode.TRAIN
                )
                from_name = section.get("from", {}).get("name", request.origin)
                to_name = section.get("to", {}).get("name", request.destination)
                leg_depart = datetime.fromisoformat(section["departure_date_time"][:19])
                leg_arrive = datetime.fromisoformat(section["arrival_date_time"][:19])
                duration_min = int((leg_arrive - leg_depart).total_seconds() / 60)

                if mode == TransportMode.WALK:
                    booking = booking_urls.google_maps_walk(from_name, to_name)
                elif not train_booking_set:
                    booking = trip_book_url
                    train_booking_set = True
                else:
                    booking = ""

                display = section.get("display_informations", {})
                operator = display.get("commercial_mode", "Rail")
                service_id = navitia_service_id(section) if mode != TransportMode.WALK else ""

                legs.append(
                    JourneyLeg(
                        mode=mode,
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
            if legs:
                options.append(
                    RouteOption(
                        legs=legs,
                        label="",
                        efficiency_score=0.0,
                        data_source="Navitia SNCF API (live)",
                        price_verified=False,
                    )
                )
        return options
