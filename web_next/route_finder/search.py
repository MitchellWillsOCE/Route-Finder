from __future__ import annotations

import httpx

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from route_finder.config import CONFIG
from route_finder.connections import filter_valid_routes
from route_finder.mock_data import generate_mock_routes
from route_finder.models import RouteOption, SearchRequest, SearchResult, TransportMode
from route_finder.place_resolver import resolve_trip
from route_finder.places import LocationValidationError, validate_trip_locations
from route_finder.pricing import apply_route_pricing_meta
from route_finder.progress import NullProgress, ProgressCallback
from route_finder.providers.bus import BusProvider
from route_finder.providers.flight import FlightProvider
from route_finder.providers.intermodal import IntermodalProvider
from route_finder.providers.train import TrainProvider
from route_finder.providers.walk import WalkProvider
from route_finder.scoring import diversify_ranked_routes, score_routes
from route_finder.train_fares import enrich_routes
from route_finder.workers import worker_count

PROVIDER_STEPS: list[tuple[str, str]] = [
    ("intermodal", "Train+flight combos"),
    ("bus", "Buses"),
    ("train", "Trains"),
    ("flight", "Flights"),
    ("walk", "Walking"),
]

_PROVIDER_CLASSES = {
    "bus": BusProvider,
    "intermodal": IntermodalProvider,
    "train": TrainProvider,
    "flight": FlightProvider,
    "walk": WalkProvider,
}


def _route_key(route: RouteOption) -> str:
    modes = "-".join(leg.mode.value for leg in route.legs)
    depart_bucket = (
        route.legs[0].depart.strftime("%Y%m%d%H") if route.legs else "na"
    )
    return (
        f"{modes}|{depart_bucket}|{route.total_duration_minutes // 15}|"
        f"{int(route.total_cost_eur)}"
    )


def _dedupe_routes(routes: list[RouteOption]) -> list[RouteOption]:
    seen: set[str] = set()
    unique: list[RouteOption] = []
    for route in routes:
        key = _route_key(route)
        if key in seen:
            continue
        seen.add(key)
        unique.append(route)
    return unique


def _run_provider(
    key: str,
    request: SearchRequest,
    client: httpx.Client,
) -> tuple[list[RouteOption], str | None]:
    try:
        provider_cls = _PROVIDER_CLASSES.get(key)
        if not provider_cls:
            return [], None
        routes = provider_cls().search(request, client)
        return routes, None
    except Exception as exc:
        return [], str(exc)


def _run_provider_threadsafe(
    key: str,
    request: SearchRequest,
) -> tuple[str, list[RouteOption], str | None]:
    with httpx.Client(timeout=CONFIG.request_timeout) as client:
        routes, error = _run_provider(key, request, client)
    return key, routes, error


def _run_providers_parallel(
    request: SearchRequest,
    reporter: ProgressCallback,
) -> tuple[list[RouteOption], list[str]]:
    routes: list[RouteOption] = []
    errors: list[str] = []
    workers = min(worker_count(), len(PROVIDER_STEPS))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_run_provider_threadsafe, key, request): label
            for key, label in PROVIDER_STEPS
        }
        for future in as_completed(futures):
            label = futures[future]
            reporter.update(f"{label}...")
            try:
                key, found, error = future.result()
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                continue
            if found:
                routes.extend(found)
            elif error:
                errors.append(f"{key}: {error}")

    return routes, errors


def search_routes(
    request: SearchRequest,
    progress: ProgressCallback | None = None,
) -> SearchResult:
    reporter = progress or NullProgress()
    location_note: str | None = None

    with httpx.Client(timeout=CONFIG.request_timeout) as client:
        reporter.update("Checking locations...")
        try:
            start, end, location_note = validate_trip_locations(
                request.origin, request.destination, client
            )
        except LocationValidationError:
            raise

        request.origin = start.name
        request.destination = end.name
        resolve_trip(request.origin, request.destination, client)

        reporter.update("Searching providers...")
        routes, errors = _run_providers_parallel(request, reporter)

        reporter.update("Ranking...")
        routes = filter_valid_routes(_dedupe_routes(routes))
        if routes:
            reporter.update("Estimating fares...")
            enrich_routes(routes, request, client)
            for route in routes:
                apply_route_pricing_meta(route)

    if not routes and CONFIG.use_mock_fallback:
        return generate_mock_routes(request)

    ranked = diversify_ranked_routes(
        score_routes(routes, ideal_departure=request.ideal_departure),
        limit=8,
    )
    sources = list(dict.fromkeys(route.data_source for route in ranked))

    has_estimated_fares = any(
        route.price_estimated and route.total_cost_eur > 0 for route in ranked
    )
    has_live_fares = any(
        route.price_verified
        and route.total_cost_eur > 0
        and any(
            leg.mode in (TransportMode.TRAIN, TransportMode.BUS)
            for leg in route.legs
        )
        for route in ranked
    )
    train_fare_note = (
        "Train/bus fares from live APIs where available."
        if has_live_fares
        else "Train times are live."
    )
    if has_estimated_fares:
        train_fare_note += (
            " Other train/bus costs are estimated from historic route data "
            "(adjusted for how close you are to departure); use the Omio links for live prices."
        )
    has_flight_prices = any(
        route.price_verified
        and any(leg.mode == TransportMode.PLANE for leg in route.legs)
        for route in ranked
    )
    has_flight_estimates = any(
        route.price_estimated
        and any(leg.mode == TransportMode.PLANE for leg in route.legs)
        for route in ranked
    )
    if has_flight_prices:
        flight_fare_note = "Flight prices scraped from Skyscanner when available."
    elif has_flight_estimates:
        flight_fare_note = (
            "Flight costs and durations are estimated from historic route data "
            "(adjusted for how close you are to departure); use Skyscanner links for live prices."
        )
    else:
        flight_fare_note = "Flight prices use timetable estimates with Skyscanner booking links."

    flex = request.flexibility_days
    base = request.ideal_departure
    window_start = (base - timedelta(days=flex)).strftime("%a %d %b")
    window_end = (base + timedelta(days=flex)).strftime("%a %d %b")

    price_note = (
        f"Live data around {base.strftime('%a %d %b %Y')}. "
        f"Searched +/-{flex} days ({window_start} - {window_end}). "
        f"Bus fares from FlixBus API when available. {train_fare_note} {flight_fare_note}"
    )
    if location_note:
        price_note = f"{location_note} {price_note}"
    if errors:
        price_note += f" Warnings: {'; '.join(errors[:3])}."
    if not ranked:
        price_note += " No live routes found. Try different dates or locations."

    reporter.update(f"Done - {len(ranked)} route(s)")

    return SearchResult(
        request=request,
        routes=ranked,
        searched_sources=sources or ["No live sources returned results"],
        price_note=price_note,
    )
