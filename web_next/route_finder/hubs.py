from __future__ import annotations

from route_finder.geocode import haversine_km

# Major intercity hubs (lat, lon) used when direct routing to small towns fails.
HUB_COORDINATES: dict[str, tuple[float, float]] = {
    "Amsterdam": (52.3791, 4.9003),
    "Rotterdam": (51.9244, 4.4777),
    "Brussels": (50.8353, 4.3355),
    "Paris": (48.8566, 2.3522),
    "London": (51.5074, -0.1278),
    "Berlin": (52.5200, 13.4050),
    "Munich": (48.1351, 11.5820),
    "Frankfurt": (50.1109, 8.6821),
    "Cologne": (50.9375, 6.9603),
    "Hamburg": (53.5511, 9.9937),
    "Vienna": (48.2082, 16.3738),
    "Prague": (50.0755, 14.4378),
    "Budapest": (47.4979, 19.0402),
    "Warsaw": (52.2297, 21.0122),
    "Copenhagen": (55.6761, 12.5683),
    "Stockholm": (59.3293, 18.0686),
    "Oslo": (59.9139, 10.7522),
    "Zurich": (47.3769, 8.5417),
    "Milan": (45.4642, 9.1900),
    "Rome": (41.9028, 12.4964),
    "Naples": (40.8518, 14.2681),
    "Florence": (43.7696, 11.2558),
    "Venice": (45.4408, 12.3155),
    "Verona": (45.4384, 10.9916),
    "Vicenza": (45.5455, 11.5354),
    "Padua": (45.4064, 11.8768),
    "Bologna": (44.4949, 11.3426),
    "Turin": (45.0703, 7.6869),
    "Genoa": (44.4056, 8.9463),
    "Barcelona": (41.3874, 2.1686),
    "Madrid": (40.4168, -3.7038),
    "Lisbon": (38.7223, -9.1393),
    "Dublin": (53.3498, -6.2603),
    "Edinburgh": (55.9533, -3.1883),
    "Manchester": (53.4808, -2.2426),
    "Birmingham": (52.4862, -1.8904),
    "Lyon": (45.7640, 4.8357),
    "Marseille": (43.2965, 5.3698),
    "Nice": (43.7102, 7.2620),
    "Luxembourg": (49.6116, 6.1319),
    "Antwerp": (51.2194, 4.4025),
    "Ghent": (51.0543, 3.7174),
    "Bruges": (51.2093, 3.2247),
    "Innsbruck": (47.2692, 11.4041),
    "Salzburg": (47.8095, 13.0550),
    "Graz": (47.0707, 15.4395),
    "Krakow": (50.0647, 19.9450),
    "Düsseldorf": (51.2200, 6.7940),
    "Cologne": (50.9375, 6.9603),
}


# Rail station coordinates for the final local leg from a hub.
HUB_STATION_COORDINATES: dict[str, tuple[float, float]] = {
    "Amsterdam": (52.3791, 4.9003),
    "Brussels": (50.8353, 4.3364),
    "Paris": (48.8768, 2.3592),
    "Munich": (48.1402, 11.5583),
    "Frankfurt": (50.1070, 8.6638),
    "Milan": (45.4845, 9.2026),
    "Venice": (45.4414, 12.3210),
    "Verona": (45.4289, 10.9828),
    "Vicenza": (45.5413, 11.5402),
    "Padua": (45.4166, 11.8824),
    "Bologna": (44.5058, 11.3416),
    "Vienna": (48.1850, 16.3729),
    "Zurich": (47.3782, 8.5402),
    "Düsseldorf": (51.2200, 6.7940),
    "Cologne": (50.9430, 6.9587),
    "Treviso": (45.6664, 12.2453),
    "Eindhoven": (51.4431, 5.4803),
    "Rotterdam": (51.9244, 4.4700),
}


def hub_station_coords(
    hub_name: str,
    *,
    fallback: tuple[float, float] | None = None,
) -> tuple[float, float]:
    return (
        HUB_STATION_COORDINATES.get(hub_name)
        or HUB_COORDINATES.get(hub_name)
        or fallback
        or (0.0, 0.0)
    )


def nearest_hubs(
    lat: float,
    lon: float,
    *,
    limit: int = 3,
    max_km: float = 120.0,
    exclude_name: str | None = None,
) -> list[tuple[str, float, float, float]]:
    """Return (name, lat, lon, distance_km) sorted nearest-first."""
    exclude = (exclude_name or "").strip().lower()
    ranked: list[tuple[str, float, float, float]] = []
    for name, (hub_lat, hub_lon) in HUB_COORDINATES.items():
        if name.lower() == exclude:
            continue
        dist = haversine_km(lat, lon, hub_lat, hub_lon)
        if dist <= max_km:
            ranked.append((name, hub_lat, hub_lon, dist))
    ranked.sort(key=lambda item: item[3])
    return ranked[:limit]


def nearest_flix_hub(
    lat: float,
    lon: float,
    client,
    *,
    limit: int = 5,
) -> str | None:
    """Pick the closest major city that FlixBus recognises."""
    for name, _, _, _ in nearest_hubs(lat, lon, limit=limit, max_km=200.0):
        try:
            response = client.get(
                "https://global.api.flixbus.com/search/autocomplete/cities",
                params={"q": name, "locale": "en"},
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://shop.flixbus.com/",
                },
                timeout=15,
            )
            if response.status_code == 200 and response.json():
                first = response.json()[0]
                if _normalize_flix_name(first.get("name", "")) == _normalize_flix_name(name):
                    return name
                if name.lower() in first.get("name", "").lower():
                    return name
        except Exception:
            continue
    return None


def _normalize_flix_name(name: str) -> str:
    return name.strip().lower().split(",")[0].strip()
