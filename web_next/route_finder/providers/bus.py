from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from route_finder import booking_urls
from route_finder.config import CONFIG
from route_finder.geocode import geocode, geocode_station
from route_finder.hubs import hub_station_coords, nearest_flix_hub
from route_finder.models import JourneyLeg, RouteOption, SearchRequest, TransportMode
from route_finder.providers.base import RouteProvider
from route_finder.providers.motis_client import itinerary_to_legs, merge_routes, plan_itineraries
from route_finder.workers import map_parallel, worker_count

FLIX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://shop.flixbus.com/",
}


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _flix_city_id(client: httpx.Client, query: str) -> dict:
    from route_finder.place_resolver import flix_city_cached

    city = flix_city_cached(client, query)
    if city:
        return city
    response = client.get(
        "https://global.api.flixbus.com/search/autocomplete/cities",
        params={"q": query, "locale": "en"},
        headers=FLIX_HEADERS,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        raise ValueError(f"No FlixBus city found for: {query}")
    return results[0]


def _search_date_strings(request: SearchRequest) -> list[str]:
    base = request.ideal_departure.date()
    dates: list[str] = []
    for offset in range(-request.flexibility_days, request.flexibility_days + 1):
        day = base + timedelta(days=offset)
        if day >= datetime.now().date():
            dates.append(day.strftime("%d.%m.%Y"))
    return dates or [base.strftime("%d.%m.%Y")]


class BusProvider(RouteProvider):
    name = "FlixBus API"

    def search(self, request: SearchRequest, client: httpx.Client) -> list[RouteOption]:
        try:
            from_city = _flix_city_id(client, request.origin)
        except ValueError:
            return []

        try:
            to_city = _flix_city_id(client, request.destination)
            options = self._search_flix(from_city, to_city, request, client)
            if options:
                return options
        except ValueError:
            pass

        return self._search_via_hub(from_city, request, client)

    def _search_flix(
        self,
        from_city: dict,
        to_city: dict,
        request: SearchRequest,
        client: httpx.Client,
    ) -> list[RouteOption]:
        options: list[RouteOption] = []
        seen: set[str] = set()
        dates = _search_date_strings(request)

        def _fetch_day(date_str: str) -> list:
            params = {
                "search_by": "cities",
                "from_city_id": from_city["id"],
                "to_city_id": to_city["id"],
                "departure_date": date_str,
                "products": '{"adult":1}',
                "locale": "en",
                "currency": "EUR",
            }
            with httpx.Client(timeout=CONFIG.request_timeout) as thread_client:
                response = thread_client.get(
                    "https://global.api.flixbus.com/search/service/v4/search",
                    params=params,
                    headers=FLIX_HEADERS,
                    timeout=CONFIG.request_timeout,
                )
                if response.status_code != 200:
                    return []
                return response.json().get("trips", [])

        for trip_days in map_parallel(dates, _fetch_day, max_workers=worker_count()):
            for trip_day in trip_days:
                for result in trip_day.get("results", {}).values():
                    if result.get("status") != "available":
                        continue
                    uid = result.get("uid", "")
                    if uid in seen:
                        continue
                    seen.add(uid)

                    depart = _parse_iso(result["departure"]["date"])
                    arrive = _parse_iso(result["arrival"]["date"])
                    duration = result.get("duration", {})
                    duration_min = int(duration.get("hours", 0)) * 60 + int(
                        duration.get("minutes", 0)
                    )
                    price = float(result["price"]["total_with_platform_fee"])

                    transfer = result.get("transfer_type_key", "direct")
                    legs: list[JourneyLeg] = []
                    for idx, leg_data in enumerate(result.get("legs", []), start=1):
                        leg_depart = _parse_iso(leg_data["departure"]["date"])
                        leg_arrive = _parse_iso(leg_data["arrival"]["date"])
                        leg_duration = int((leg_arrive - leg_depart).total_seconds() / 60)
                        leg_count = max(len(result.get("legs", [])), 1)
                        leg_origin = leg_data.get("departure", {}).get(
                            "name", from_city["name"]
                        )
                        leg_destination = leg_data.get("arrival", {}).get(
                            "name", to_city["name"]
                        )
                        legs.append(
                            JourneyLeg(
                                mode=TransportMode.BUS,
                                origin=leg_origin,
                                destination=leg_destination,
                                depart=leg_depart,
                                arrive=leg_arrive,
                                duration_minutes=leg_duration,
                                cost_eur=price / leg_count,
                                operator="FlixBus",
                                booking_url=booking_urls.flixbus(
                                    from_city["name"], to_city["name"], leg_depart
                                ),
                                notes=transfer if idx == 1 else "",
                            )
                        )

                    if not legs:
                        legs = [
                            JourneyLeg(
                                mode=TransportMode.BUS,
                                origin=from_city["name"],
                                destination=to_city["name"],
                                depart=depart,
                                arrive=arrive,
                                duration_minutes=duration_min,
                                cost_eur=price,
                                operator="FlixBus",
                                booking_url=booking_urls.flixbus(
                                    from_city["name"], to_city["name"], depart
                                ),
                                notes=transfer,
                            )
                        ]

                    options.append(
                        RouteOption(
                            legs=legs,
                            label="",
                            efficiency_score=0.0,
                            data_source="FlixBus API (live)",
                            price_verified=True,
                        )
                    )

        options.sort(key=lambda r: (r.total_cost_eur, r.total_duration_minutes))
        return options[:3]

    def _search_via_hub(
        self,
        from_city: dict,
        request: SearchRequest,
        client: httpx.Client,
    ) -> list[RouteOption]:
        destination = geocode(request.destination, client)
        dest_station = geocode_station(request.destination, client)
        hub_name = nearest_flix_hub(dest_station.lat, dest_station.lon, client)
        if not hub_name:
            return []

        try:
            hub_city = _flix_city_id(client, hub_name)
        except ValueError:
            return []

        hub_station_lat, hub_station_lon = hub_station_coords(hub_name)
        bus_options = self._search_flix(from_city, hub_city, request, client)
        if not bus_options:
            return []

        combined: list[RouteOption] = []
        seen: set[str] = set()

        for bus_route in bus_options[:2]:
            bus_arrive = bus_route.legs[-1].arrive
            local_depart = bus_arrive + timedelta(minutes=30)
            local_itineraries = plan_itineraries(
                client,
                hub_station_lat,
                hub_station_lon,
                dest_station.lat,
                dest_station.lon,
                local_depart,
            )[:1]
            if not local_itineraries:
                continue

            local_legs = itinerary_to_legs(
                local_itineraries[0],
                request,
                origin_label=hub_name,
                destination_label=request.destination,
                booking_origin=hub_name,
            )
            if not local_legs:
                continue

            local_route = RouteOption(
                legs=local_legs,
                label="",
                efficiency_score=0.0,
                data_source="Transitous / MOTIS (final leg)",
                price_verified=False,
            )
            merged = merge_routes(
                bus_route,
                local_route,
                hub_name=hub_name,
                final_destination=request.destination,
                data_source="FlixBus + local rail/bus (live)",
            )
            if not merged:
                continue

            key = "|".join(
                f"{leg.depart.isoformat()}-{leg.origin}-{leg.destination}"
                for leg in merged.legs
            )
            if key in seen:
                continue
            seen.add(key)
            combined.append(merged)

        combined.sort(key=lambda r: (r.total_cost_eur, r.total_duration_minutes))
        return combined[:3]
