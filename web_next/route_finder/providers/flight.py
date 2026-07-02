from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from route_finder import booking_urls
from route_finder.config import CONFIG
from route_finder.flight_estimates import (
    estimate_flight_confidence,
    estimate_flight_duration,
    estimate_flight_fare,
    historic_confidence_value,
)
from route_finder.models import JourneyLeg, RouteOption, SearchRequest, TransportMode
from route_finder.providers.base import RouteProvider


class _AmadeusClient:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self._token: str | None = None

    def _ensure_token(self) -> str:
        if self._token:
            return self._token
        response = self._client.post(
            "https://test.api.amadeus.com/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": CONFIG.amadeus_client_id,
                "client_secret": CONFIG.amadeus_client_secret,
            },
            timeout=CONFIG.request_timeout,
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]
        return self._token

    def search_flights(
        self, origin_code: str, destination_code: str, depart: datetime
    ) -> list[dict]:
        token = self._ensure_token()
        response = self._client.get(
            "https://test.api.amadeus.com/v2/shopping/flight-offers",
            params={
                "originLocationCode": origin_code,
                "destinationLocationCode": destination_code,
                "departureDate": depart.strftime("%Y-%m-%d"),
                "adults": 1,
                "max": 5,
                "currencyCode": "EUR",
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=CONFIG.request_timeout,
        )
        response.raise_for_status()
        return response.json().get("data", [])


def _search_dates(request: SearchRequest) -> list[datetime]:
    base = request.ideal_departure.replace(hour=8, minute=0, second=0, microsecond=0)
    dates: list[datetime] = []
    for offset in range(-request.flexibility_days, request.flexibility_days + 1):
        candidate = base + timedelta(days=offset)
        if candidate.date() >= datetime.now().date():
            dates.append(candidate)
    return dates or [base]


def _parse_duration(iso_duration: str) -> int:
    # PT2H30M
    hours = minutes = 0
    body = iso_duration.replace("PT", "")
    if "H" in body:
        hours_part, body = body.split("H", 1)
        hours = int(hours_part or 0)
    if "M" in body:
        minutes = int(body.replace("M", "") or 0)
    return hours * 60 + minutes


class FlightProvider(RouteProvider):
    name = "Flight fare model"

    def search(self, request: SearchRequest, client: httpx.Client) -> list[RouteOption]:
        del client
        if CONFIG.amadeus_client_id and CONFIG.amadeus_client_secret:
            routes = self._search_amadeus(request, client)
            if routes:
                return routes

        if CONFIG.use_playwright_flights:
            routes = self._search_skyscanner(request)
            if routes:
                return routes

        return self._search_estimated(request)

    def _search_amadeus(
        self, request: SearchRequest, client: httpx.Client
    ) -> list[RouteOption]:
        amadeus = _AmadeusClient(client)
        origin_code = booking_urls._iata(request.origin)
        destination_code = booking_urls._iata(request.destination)
        options: list[RouteOption] = []

        for depart in _search_dates(request):
            try:
                offers = amadeus.search_flights(origin_code, destination_code, depart)
            except Exception:
                continue

            for offer in offers:
                price = float(offer["price"]["grandTotal"])
                itineraries = offer.get("itineraries", [])
                if not itineraries:
                    continue

                legs: list[JourneyLeg] = []
                for itinerary in itineraries:
                    for segment in itinerary.get("segments", []):
                        leg_depart = datetime.fromisoformat(
                            segment["departure"]["at"][:19]
                        )
                        leg_arrive = datetime.fromisoformat(
                            segment["arrival"]["at"][:19]
                        )
                        duration_min = _parse_duration(segment.get("duration", "PT0M"))
                        carrier_code = (segment.get("carrierCode") or "").strip()
                        flight_number = str(segment.get("number") or "").strip()
                        service_id = f"{carrier_code} {flight_number}".strip() if flight_number else carrier_code
                        legs.append(
                            JourneyLeg(
                                mode=TransportMode.PLANE,
                                origin=segment["departure"].get("iataCode", origin_code),
                                destination=segment["arrival"].get("iataCode", destination_code),
                                depart=leg_depart,
                                arrive=leg_arrive,
                                duration_minutes=duration_min,
                                cost_eur=price / max(len(itineraries), 1),
                                operator=carrier_code or "Airline",
                                booking_url=booking_urls.skyscanner_flights(
                                    request.origin, request.destination, leg_depart
                                ),
                                service_id=service_id,
                            )
                        )

                if legs:
                    options.append(
                        RouteOption(
                            legs=legs,
                            label="",
                            efficiency_score=0.0,
                            data_source="Amadeus Flight API (live)",
                            price_verified=True,
                        )
                    )

        options.sort(key=lambda r: (r.total_cost_eur, r.total_duration_minutes))
        return options[:5]

    def _search_skyscanner(self, request: SearchRequest) -> list[RouteOption]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return []

        import re

        depart = request.ideal_departure
        url = booking_urls.skyscanner_flights(request.origin, request.destination, depart)
        options: list[RouteOption] = []

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=120000)
                page.wait_for_timeout(12000)
                text = page.inner_text("body")
                browser.close()
        except Exception:
            return []

        prices = re.findall(r"(?:EUR|€)\s*([\d,.]+)", text)
        if not prices:
            return []

        price = float(prices[0].replace(",", ""))
        leg_depart = depart.replace(hour=9, minute=0, second=0, microsecond=0)
        leg_arrive = leg_depart + timedelta(hours=2)
        options.append(
            RouteOption(
                legs=[
                    JourneyLeg(
                        mode=TransportMode.PLANE,
                        origin=f"{request.origin} airport",
                        destination=f"{request.destination} airport",
                        depart=leg_depart,
                        arrive=leg_arrive,
                        duration_minutes=120,
                        cost_eur=price,
                        operator="Skyscanner result",
                        booking_url=url,
                        notes="Verify departure times on Skyscanner",
                    )
                ],
                label="",
                efficiency_score=0.0,
                data_source="Skyscanner scrape (live price)",
                price_verified=True,
            )
        )
        return options

    def _search_estimated(self, request: SearchRequest) -> list[RouteOption]:
        origin_code = booking_urls._iata(request.origin)
        destination_code = booking_urls._iata(request.destination)
        confidence = estimate_flight_confidence(request.origin, request.destination)
        historic_conf = historic_confidence_value(confidence)
        duration_min = estimate_flight_duration(request.origin, request.destination)
        if duration_min is None:
            duration_min = 120

        options: list[RouteOption] = []
        for depart in _search_dates(request):
            price = estimate_flight_fare(request.origin, request.destination, depart)
            if price is None:
                continue
            leg_depart = depart.replace(hour=9, minute=0, second=0, microsecond=0)
            options.append(
                RouteOption(
                    legs=[
                        JourneyLeg(
                            mode=TransportMode.PLANE,
                            origin=f"{request.origin} ({origin_code})",
                            destination=f"{request.destination} ({destination_code})",
                            depart=leg_depart,
                            arrive=leg_depart + timedelta(minutes=duration_min),
                            duration_minutes=duration_min,
                            cost_eur=price,
                            operator="Airline (est.)",
                            booking_url=booking_urls.skyscanner_flights(
                                request.origin, request.destination, leg_depart
                            ),
                            notes=f"~{duration_min // 60}h{duration_min % 60:02d} block; verify on Skyscanner",
                        )
                    ],
                    label="",
                    efficiency_score=0.0,
                    data_source=f"Flight fare model ({confidence})",
                    price_verified=False,
                    price_estimated=True,
                    historic_confidence=historic_conf,
                )
            )

        options.sort(key=lambda r: (r.total_cost_eur, r.total_duration_minutes))
        seen_days: set[str] = set()
        unique: list[RouteOption] = []
        for route in options:
            day = route.legs[0].depart.date().isoformat()
            if day in seen_days:
                continue
            seen_days.add(day)
            unique.append(route)
        return unique[:5]
