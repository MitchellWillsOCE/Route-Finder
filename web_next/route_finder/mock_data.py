from __future__ import annotations

from datetime import datetime, timedelta

from route_finder import booking_urls
from route_finder.models import JourneyLeg, RouteOption, SearchRequest, SearchResult, TransportMode


def _leg(
    mode: TransportMode,
    origin: str,
    destination: str,
    base: datetime,
    offset_hours: float,
    duration_min: int,
    cost: float,
    operator: str,
    url: str,
    notes: str = "",
    service_id: str = "",
) -> JourneyLeg:
    depart = base + timedelta(hours=offset_hours)
    arrive = depart + timedelta(minutes=duration_min)
    return JourneyLeg(
        mode=mode,
        origin=origin,
        destination=destination,
        depart=depart,
        arrive=arrive,
        duration_minutes=duration_min,
        cost_eur=cost,
        operator=operator,
        booking_url=url,
        service_id=service_id,
        notes=notes,
    )


def generate_mock_routes(request: SearchRequest) -> SearchResult:
    """Return plausible mock routes for any European city pair."""
    base = request.ideal_departure.replace(hour=8, minute=0, second=0, microsecond=0)
    o = request.origin
    d = request.destination

    train_depart = base
    flight_depart = base + timedelta(hours=0, minutes=45)
    bus_leg2_depart = base + timedelta(hours=4, minutes=30)
    scenic_leg2_depart = base + timedelta(hours=3)

    routes = [
        RouteOption(
            label="Best balance",
            efficiency_score=91.2,
            data_source="Train API (aggregated)",
            price_verified=True,
            legs=[
                _leg(
                    TransportMode.TRAIN,
                    f"{o} central station",
                    f"{d} central station",
                    base,
                    0,
                    195,
                    89.0,
                    "Eurostar / SNCF / DB",
                    booking_urls.trainline(o, d, train_depart),
                    "Direct high-speed; seat reservation included",
                    service_id="THA 9324",
                ),
            ],
        ),
        RouteOption(
            label="Fastest",
            efficiency_score=78.5,
            data_source="Skyscanner scrape",
            legs=[
                _leg(
                    TransportMode.WALK,
                    o,
                    f"{o} airport",
                    base,
                    0,
                    45,
                    0.0,
                    "n/a",
                    booking_urls.google_maps_transit(o, f"{o} airport"),
                    "Metro + walk",
                ),
                _leg(
                    TransportMode.PLANE,
                    f"{o} airport",
                    f"{d} airport",
                    base,
                    0.75,
                    95,
                    124.0,
                    "Ryanair",
                    booking_urls.ryanair(o, d, flight_depart),
                    "Hand luggage only at quoted price",
                    service_id="FR 1234",
                ),
                _leg(
                    TransportMode.BUS,
                    f"{d} airport",
                    f"{d} city centre",
                    base,
                    3.5,
                    35,
                    6.5,
                    "FlixBus Airport Shuttle",
                    booking_urls.flixbus(f"{d} airport", f"{d} city centre", flight_depart + timedelta(hours=1, minutes=10)),
                ),
            ],
        ),
        RouteOption(
            label="Cheapest",
            efficiency_score=72.8,
            data_source="Official operator sites",
            legs=[
                _leg(
                    TransportMode.BUS,
                    f"{o} bus station",
                    "Brussels South",
                    base,
                    0,
                    240,
                    22.0,
                    "FlixBus",
                    booking_urls.flixbus(o, "Brussels", base),
                ),
                _leg(
                    TransportMode.BUS,
                    "Brussels South",
                    f"{d} bus station",
                    base,
                    4.5,
                    180,
                    18.0,
                    "FlixBus",
                    booking_urls.flixbus("Brussels", d, bus_leg2_depart),
                    "45 min layover",
                ),
            ],
        ),
        RouteOption(
            label="Scenic / regional",
            efficiency_score=65.0,
            data_source="National rail websites",
            legs=[
                _leg(
                    TransportMode.TRAIN,
                    f"{o}",
                    "Cologne Hbf",
                    base,
                    0,
                    150,
                    45.0,
                    "Deutsche Bahn",
                    booking_urls.bahn(o, "Cologne", base),
                ),
                _leg(
                    TransportMode.TRAIN,
                    "Cologne Hbf",
                    f"{d}",
                    base,
                    3.0,
                    165,
                    38.0,
                    "NS International",
                    booking_urls.ns_international("Cologne", d, scenic_leg2_depart),
                    "flexible ticket +EUR 20",
                ),
            ],
        ),
        RouteOption(
            label="Walk only (reference)",
            efficiency_score=5.0,
            data_source="OpenStreetMap routing",
            legs=[
                _leg(
                    TransportMode.WALK,
                    o,
                    d,
                    base,
                    0,
                    72 * 60,
                    0.0,
                    "n/a",
                    booking_urls.google_maps_walk(o, d),
                    "Not practical; shown for comparison",
                ),
            ],
        ),
    ]

    flex = request.flexibility_days
    window_start = (base - timedelta(days=flex)).strftime("%a %d %b")
    window_end = (base + timedelta(days=flex)).strftime("%a %d %b")

    return SearchResult(
        request=request,
        routes=sorted(routes, key=lambda r: r.efficiency_score, reverse=True),
        searched_sources=[
            "Train APIs (Trainline, DB, SNCF)",
            "Skyscanner (flight search scrape)",
            "FlixBus / BlaBlaBus official sites",
            "OpenStreetMap (walking reference)",
        ],
        price_note=(
            f"Prices sampled around {base.strftime('%a %d %b %Y')}. "
            f"Searching +/-{flex} days ({window_start} - {window_end}); "
            "cheaper options may exist on adjacent dates."
        ),
    )
