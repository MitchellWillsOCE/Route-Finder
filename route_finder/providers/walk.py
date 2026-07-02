from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from route_finder import booking_urls
from route_finder.config import CONFIG
from route_finder.geocode import GeoPlace, geocode, haversine_km
from route_finder.models import JourneyLeg, RouteOption, SearchRequest, TransportMode
from route_finder.providers.base import RouteProvider


class WalkProvider(RouteProvider):
    name = "OpenStreetMap / OSRM"

    def search(self, request: SearchRequest, client: httpx.Client) -> list[RouteOption]:
        origin = geocode(request.origin, client)
        destination = geocode(request.destination, client)
        distance_km = haversine_km(origin.lat, origin.lon, destination.lat, destination.lon)

        try:
            response = client.get(
                "http://router.project-osrm.org/route/v1/foot/"
                f"{origin.lon},{origin.lat};{destination.lon},{destination.lat}",
                params={"overview": "false"},
                timeout=CONFIG.request_timeout,
            )
            response.raise_for_status()
            route = response.json()["routes"][0]
            distance_km = route["distance"] / 1000
        except Exception:
            pass

        duration_min = int((distance_km / CONFIG.walking_speed_kmh) * 60)
        depart = request.ideal_departure.replace(hour=8, minute=0, second=0, microsecond=0)
        arrive = depart + timedelta(minutes=duration_min)

        notes = f"Approx {distance_km:.0f} km on foot"
        if distance_km > CONFIG.max_walk_km:
            notes += "; impractical for most travellers (shown for comparison)"

        leg = JourneyLeg(
            mode=TransportMode.WALK,
            origin=origin.name,
            destination=destination.name,
            depart=depart,
            arrive=arrive,
            duration_minutes=duration_min,
            cost_eur=0.0,
            operator="n/a",
            booking_url=booking_urls.google_maps_walk(origin.name, destination.name),
            notes=notes,
        )
        return [
            RouteOption(
                legs=[leg],
                label="Walk only (reference)",
                efficiency_score=0.0,
                data_source="OpenStreetMap / OSRM (live)",
                price_verified=True,
            )
        ]
