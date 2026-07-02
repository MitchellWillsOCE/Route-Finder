from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from route_finder.airports import (
    Airport,
    arrival_airport_candidates,
    departure_airport_candidates,
)
from route_finder.combiner import chain_routes, single_leg_route, transfer_leg
from route_finder.config import CONFIG
from route_finder.connections import filter_valid_routes, min_connection_minutes
from route_finder.geocode import haversine_km
from route_finder.hubs import hub_station_coords
from route_finder.models import RouteOption, SearchRequest, TransportMode
from route_finder.place_resolver import TripEndpoints
from route_finder.providers.flight_scraper import scrape_airport_flights_batch
from route_finder.historic_fares import canonical_place
from route_finder.providers.motis_client import itinerary_to_route, plan_itineraries
from route_finder.workers import map_parallel, worker_count

DATA_SOURCE = "Graph router (train + flight + train)"
AIRPORT_TRANSFER_MIN = 50
_BEAM_WIDTH = 10


class GraphRouter:
    """Multimodal graph search with pruning and connection validation."""

    def search(
        self,
        request: SearchRequest,
        client: httpx.Client,
        endpoints: TripEndpoints,
    ) -> list[RouteOption]:
        origin = endpoints.origin
        dest_lat, dest_lon = endpoints.destination_station

        if haversine_km(origin.lat, origin.lon, dest_lat, dest_lon) < CONFIG.skip_intermodal_km:
            return []

        dep_airports = departure_airport_candidates(origin.lat, origin.lon, limit=6)
        arr_airports = arrival_airport_candidates(dest_lat, dest_lon, limit=6)
        if not dep_airports or not arr_airports:
            return []

        depart = request.ideal_departure.replace(hour=8, minute=0, second=0, microsecond=0)
        if depart.date() < datetime.now().date():
            depart = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        rail_legs = self._build_rail_legs(client, request, origin, dep_airports, depart)
        if not rail_legs:
            return []

        flight_requests = self._prune_flight_pairs(
            rail_legs, arr_airports, dest_lat, dest_lon, origin.lat, origin.lon
        )
        flights = scrape_airport_flights_batch(flight_requests, request)

        beam: list[RouteOption] = []
        seen: set[str] = set()

        for dep_ap, rail_out, airport_xfer in rail_legs:
            for arr_ap in arr_airports:
                flight = flights.get((dep_ap.iata, arr_ap.iata))
                if not flight:
                    continue

                arr_city = arr_ap.city
                station_lat, station_lon = hub_station_coords(
                    arr_city, fallback=(arr_ap.lat, arr_ap.lon)
                )
                min_flight_buffer = min_connection_minutes(
                    TransportMode.TRAIN, TransportMode.PLANE
                )
                if flight.legs[0].depart < airport_xfer.legs[-1].arrive + timedelta(
                    minutes=min_flight_buffer
                ):
                    continue

                dest_matches = canonical_place(arr_city) == canonical_place(
                    endpoints.destination_label
                )
                if dest_matches:
                    city_xfer = single_leg_route(
                        transfer_leg(
                            f"{arr_ap.name} ({arr_ap.iata})",
                            endpoints.destination_label,
                            flight.legs[-1].arrive,
                            AIRPORT_TRANSFER_MIN,
                            notes=f"Transfer from {arr_ap.iata}",
                        ),
                        data_source=DATA_SOURCE,
                    )
                    combined = chain_routes(
                        [rail_out, airport_xfer, flight, city_xfer],
                        hubs=[dep_ap.city, dep_ap.iata, arr_ap.iata],
                        final_destination=endpoints.destination_label,
                        data_source=DATA_SOURCE,
                    )
                else:
                    station_xfer = single_leg_route(
                        transfer_leg(
                            f"{arr_ap.name} ({arr_ap.iata})",
                            f"{arr_city} station",
                            flight.legs[-1].arrive,
                            AIRPORT_TRANSFER_MIN,
                            notes=f"Transfer from {arr_ap.iata}",
                        ),
                        data_source=DATA_SOURCE,
                    )
                    rail_buffer = min_connection_minutes(
                        TransportMode.PLANE, TransportMode.TRAIN
                    )
                    rail_in_depart = station_xfer.legs[-1].arrive + timedelta(
                        minutes=rail_buffer
                    )
                    rail_in = self._rail_from_city(
                        client,
                        request,
                        arr_city,
                        station_lat,
                        station_lon,
                        dest_lat,
                        dest_lon,
                        endpoints.destination_label,
                        rail_in_depart,
                    )
                    if not rail_in:
                        continue
                    combined = chain_routes(
                        [rail_out, airport_xfer, flight, station_xfer, rail_in],
                        hubs=[dep_ap.city, dep_ap.iata, arr_ap.iata, arr_city],
                        final_destination=endpoints.destination_label,
                        data_source=DATA_SOURCE,
                    )
                if not combined:
                    continue
                if not any(leg.mode == TransportMode.PLANE for leg in combined.legs):
                    continue
                if not any(leg.mode == TransportMode.TRAIN for leg in combined.legs):
                    continue

                key = "|".join(
                    f"{leg.mode.value}-{leg.origin}-{leg.depart.isoformat()}"
                    for leg in combined.legs
                    if leg.mode != TransportMode.WALK
                )
                if key in seen:
                    continue
                seen.add(key)
                beam.append(combined)
                beam.sort(key=lambda r: (r.total_duration_minutes, r.total_cost_eur))
                beam = beam[:_BEAM_WIDTH]

        return filter_valid_routes(beam)

    def _prune_flight_pairs(
        self,
        rail_legs: list,
        arr_airports: list[Airport],
        dest_lat: float,
        dest_lon: float,
        origin_lat: float,
        origin_lon: float,
    ) -> list[tuple[Airport, Airport, datetime]]:
        flight_requests: list[tuple[Airport, Airport, datetime]] = []
        min_flight_buffer = min_connection_minutes(
            TransportMode.TRAIN, TransportMode.PLANE
        )
        for dep_ap, _, airport_xfer in rail_legs:
            earliest_flight = airport_xfer.legs[-1].arrive + timedelta(
                minutes=min_flight_buffer
            )
            for arr_ap in arr_airports:
                flight_requests.append((dep_ap, arr_ap, earliest_flight))

        dep_distance = {
            item[0].iata: haversine_km(origin_lat, origin_lon, item[0].lat, item[0].lon)
            for item in flight_requests
        }
        selected: list[tuple[Airport, Airport, datetime]] = []
        seen_pairs: set[tuple[str, str]] = set()

        for dep_iata in sorted(dep_distance, key=dep_distance.get, reverse=True):
            dep_pairs = [p for p in flight_requests if p[0].iata == dep_iata]
            dep_pairs.sort(
                key=lambda p: haversine_km(dest_lat, dest_lon, p[1].lat, p[1].lon)
            )
            for pair in dep_pairs:
                key = (pair[0].iata, pair[1].iata)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                selected.append(pair)
                break

        for pair in sorted(flight_requests, key=lambda item: -dep_distance[item[0].iata]):
            key = (pair[0].iata, pair[1].iata)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            selected.append(pair)
            if len(selected) >= CONFIG.graph_max_flight_lookups:
                break
        return selected

    def _build_rail_legs(
        self,
        client: httpx.Client,
        request: SearchRequest,
        origin,
        dep_airports: list[Airport],
        depart: datetime,
    ) -> list[tuple[Airport, RouteOption, RouteOption]]:
        def _one(dep_ap: Airport) -> tuple[Airport, RouteOption, RouteOption] | None:
            with httpx.Client(timeout=CONFIG.request_timeout) as thread_client:
                rail_out = self._rail_to_city(thread_client, request, origin, dep_ap, depart)
            if not rail_out:
                return None
            city_arrive = rail_out.legs[-1].arrive
            airport_xfer = single_leg_route(
                transfer_leg(
                    rail_out.legs[-1].destination,
                    f"{dep_ap.name} ({dep_ap.iata})",
                    city_arrive,
                    AIRPORT_TRANSFER_MIN,
                    notes=f"Transfer to {dep_ap.iata}",
                ),
                data_source=DATA_SOURCE,
            )
            return dep_ap, rail_out, airport_xfer

        built = map_parallel(dep_airports, _one, max_workers=worker_count())
        return [item for item in built if item is not None]

    def _rail_to_city(
        self,
        client: httpx.Client,
        request: SearchRequest,
        origin,
        dep_ap: Airport,
        depart: datetime,
    ) -> RouteOption | None:
        station_lat, station_lon = hub_station_coords(
            dep_ap.city, fallback=(dep_ap.lat, dep_ap.lon)
        )
        itineraries = plan_itineraries(
            client, origin.lat, origin.lon, station_lat, station_lon, depart
        )[:1]
        if not itineraries:
            return None
        return itinerary_to_route(
            itineraries[0],
            request,
            data_source=DATA_SOURCE,
            destination_label=dep_ap.city,
            booking_destination=dep_ap.city,
        )

    def _rail_from_city(
        self,
        client: httpx.Client,
        request: SearchRequest,
        arr_city: str,
        station_lat: float,
        station_lon: float,
        dest_lat: float,
        dest_lon: float,
        dest_label: str,
        earliest_depart: datetime,
    ) -> RouteOption | None:
        for offset in range(0, 120, 30):
            query_depart = earliest_depart + timedelta(minutes=offset)
            itineraries = plan_itineraries(
                client, station_lat, station_lon, dest_lat, dest_lon, query_depart
            )[:2]
            for itinerary in itineraries:
                route = itinerary_to_route(
                    itinerary,
                    request,
                    data_source=DATA_SOURCE,
                    origin_label=arr_city,
                    destination_label=dest_label,
                    booking_origin=arr_city,
                )
                if not route:
                    continue
                train_legs = [leg for leg in route.legs if leg.mode == TransportMode.TRAIN]
                if not train_legs or train_legs[0].depart < earliest_depart:
                    continue
                first_train_idx = route.legs.index(train_legs[0])
                return RouteOption(
                    legs=route.legs[first_train_idx:],
                    label=route.label,
                    efficiency_score=route.efficiency_score,
                    data_source=route.data_source,
                    price_verified=route.price_verified,
                )
        return None
