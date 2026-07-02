from __future__ import annotations

import re
from datetime import datetime, timedelta

from route_finder.airports import Airport
from route_finder.config import CONFIG
from route_finder.flight_estimates import (
    estimate_flight_confidence,
    estimate_flight_duration,
    estimate_flight_fare,
    historic_confidence_value,
)
from route_finder.models import JourneyLeg, RouteOption, SearchRequest, TransportMode
from route_finder.workers import map_parallel, worker_count

_PRICE_RE = re.compile(r"(?:EUR|€|from)\s*([\d]{1,4}[.,]\d{2})", re.IGNORECASE)


def _skyscanner_url(dep: Airport, arr: Airport, depart: datetime) -> str:
    yymmdd = depart.strftime("%y%m%d")
    return (
        "https://www.skyscanner.net/transport/flights/"
        f"{dep.skyscanner_code}/{arr.skyscanner_code}/{yymmdd}/"
    )


def _estimated_flight_route(
    dep: Airport,
    arr: Airport,
    earliest_depart: datetime,
) -> RouteOption:
    """Priced flight estimate from historic route data and booking window."""
    duration_min = estimate_flight_duration(dep.city, arr.city)
    if duration_min is None:
        duration_min = 120
    price = estimate_flight_fare(dep.city, arr.city, earliest_depart)
    confidence = estimate_flight_confidence(dep.city, arr.city)
    historic_conf = historic_confidence_value(confidence)
    leg_depart = earliest_depart
    url = _skyscanner_url(dep, arr, earliest_depart)
    return RouteOption(
        legs=[
            JourneyLeg(
                mode=TransportMode.PLANE,
                origin=f"{dep.city} ({dep.iata})",
                destination=f"{arr.city} ({arr.iata})",
                depart=leg_depart,
                arrive=leg_depart + timedelta(minutes=duration_min),
                duration_minutes=duration_min,
                cost_eur=price or 0.0,
                operator="Airline (est.)",
                booking_url=url,
                notes=f"{dep.iata} -> {arr.iata}; ~{duration_min}m block",
            )
        ],
        label="",
        efficiency_score=0.0,
        data_source=f"Flight fare model ({confidence})",
        price_verified=False,
        price_estimated=price is not None,
        historic_confidence=historic_conf,
    )


def _flight_from_scrape(
    dep: Airport,
    arr: Airport,
    earliest: datetime,
    text: str,
) -> RouteOption | None:
    price = None
    for raw in _PRICE_RE.findall(text):
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            continue
        if 5.0 <= value <= 5000.0:
            price = value
            break
    duration_min = estimate_flight_duration(dep.city, arr.city) or 120
    leg_depart = earliest
    url = _skyscanner_url(dep, arr, earliest)
    if price is None:
        return None
    return RouteOption(
        legs=[
            JourneyLeg(
                mode=TransportMode.PLANE,
                origin=f"{dep.city} ({dep.iata})",
                destination=f"{arr.city} ({arr.iata})",
                depart=leg_depart,
                arrive=leg_depart + timedelta(minutes=duration_min),
                duration_minutes=duration_min,
                cost_eur=price,
                operator="Skyscanner",
                booking_url=url,
                notes=f"{dep.iata} -> {arr.iata}",
            )
        ],
        label="",
        efficiency_score=0.0,
        data_source="Skyscanner scrape (live price)",
        price_verified=True,
    )


def _scrape_one_pair(
    item: tuple[Airport, Airport, datetime],
) -> tuple[tuple[str, str], RouteOption]:
    dep, arr, earliest = item
    key = (dep.iata, arr.iata)
    if not CONFIG.use_playwright_flights:
        return key, _estimated_flight_route(dep, arr, earliest)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return key, _estimated_flight_route(dep, arr, earliest)

    url = _skyscanner_url(dep, arr, earliest)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            text = page.inner_text("body")
            browser.close()
        flight = _flight_from_scrape(dep, arr, earliest, text)
        return key, flight or _estimated_flight_route(dep, arr, earliest)
    except Exception:
        return key, _estimated_flight_route(dep, arr, earliest)


def scrape_airport_flights_batch(
    pairs: list[tuple[Airport, Airport, datetime]],
    request: SearchRequest,
) -> dict[tuple[str, str], RouteOption]:
    del request
    if not pairs:
        return {}

    flight_workers = min(4, worker_count(), len(pairs))
    scraped = map_parallel(pairs, _scrape_one_pair, max_workers=flight_workers)
    return dict(scraped)
