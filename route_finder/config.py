from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _default_search_workers() -> int:
    raw = os.getenv("SEARCH_WORKERS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return max(2, min(8, os.cpu_count() or 4))


@dataclass(frozen=True)
class Config:
    nominatim_user_agent: str = os.getenv(
        "NOMINATIM_USER_AGENT", "EuropeRouteFinder/1.0 (route-finder-cli)"
    )
    amadeus_client_id: str = os.getenv("AMADEUS_CLIENT_ID", "")
    amadeus_client_secret: str = os.getenv("AMADEUS_CLIENT_SECRET", "")
    navitia_api_key: str = os.getenv("NAVITIA_API_KEY", "")
    hafas_base_url: str = os.getenv(
        "HAFAS_BASE_URL", "https://v6.db.transport.rest"
    )
    request_timeout: float = float(os.getenv("REQUEST_TIMEOUT", "30"))
    search_workers: int = _default_search_workers()
    graph_max_flight_lookups: int = int(os.getenv("GRAPH_MAX_FLIGHT_LOOKUPS", "12"))
    skip_intermodal_km: float = float(os.getenv("SKIP_INTERMODAL_KM", "250"))
    max_walk_km: float = float(os.getenv("MAX_WALK_KM", "80"))
    walking_speed_kmh: float = float(os.getenv("WALKING_SPEED_KMH", "5"))
    use_playwright_flights: bool = os.getenv("USE_PLAYWRIGHT_FLIGHTS", "").lower() in (
        "1",
        "true",
        "yes",
    )
    use_mock_fallback: bool = os.getenv("USE_MOCK_FALLBACK", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    ns_api_subscription_key: str = os.getenv("NS_API_SUBSCRIPTION_KEY", "")


CONFIG = Config()
