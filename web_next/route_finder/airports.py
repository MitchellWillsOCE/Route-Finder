from __future__ import annotations

from dataclasses import dataclass

from route_finder.geocode import haversine_km


@dataclass(frozen=True)
class Airport:
    iata: str
    name: str
    city: str
    lat: float
    lon: float
    skyscanner_code: str


# Major European airports used for intermodal routing (no route-specific bias).
EUROPEAN_AIRPORTS: tuple[Airport, ...] = (
    Airport("AMS", "Amsterdam Schiphol", "Amsterdam", 52.3105, 4.7683, "amst"),
    Airport("RTM", "Rotterdam The Hague", "Rotterdam", 51.9569, 4.4372, "rtm"),
    Airport("EIN", "Eindhoven", "Eindhoven", 51.4501, 5.3744, "einh"),
    Airport("BRU", "Brussels", "Brussels", 50.9014, 4.4844, "brus"),
    Airport("DUS", "Düsseldorf", "Düsseldorf", 51.2895, 6.7668, "duss"),
    Airport("CGN", "Cologne Bonn", "Cologne", 50.8659, 7.1427, "cgn"),
    Airport("FRA", "Frankfurt", "Frankfurt", 50.0379, 8.5622, "fran"),
    Airport("HAM", "Hamburg", "Hamburg", 53.6304, 9.9882, "hamb"),
    Airport("MUC", "Munich", "Munich", 48.3538, 11.7861, "munc"),
    Airport("BER", "Berlin Brandenburg", "Berlin", 52.3667, 13.5033, "berl"),
    Airport("CDG", "Paris CDG", "Paris", 49.0097, 2.5479, "pari"),
    Airport("ORY", "Paris Orly", "Paris", 48.7262, 2.3652, "pari"),
    Airport("LHR", "London Heathrow", "London", 51.4700, -0.4543, "lond"),
    Airport("STN", "London Stansted", "London", 51.8860, 0.2389, "lond"),
    Airport("VCE", "Venice Marco Polo", "Venice", 45.5053, 12.3519, "veni"),
    Airport("TSF", "Treviso", "Treviso", 45.6484, 12.1944, "trvs"),
    Airport("VRN", "Verona", "Verona", 45.3957, 10.8885, "vrn"),
    Airport("BGY", "Milan Bergamo", "Milan", 45.6736, 9.7042, "mila"),
    Airport("MXP", "Milan Malpensa", "Milan", 45.6306, 8.7281, "mila"),
    Airport("LIN", "Milan Linate", "Milan", 45.4451, 9.2767, "mila"),
    Airport("BLQ", "Bologna", "Bologna", 44.5354, 11.2887, "blq"),
    Airport("FCO", "Rome Fiumicino", "Rome", 41.8003, 12.2389, "rome"),
    Airport("NAP", "Naples", "Naples", 40.8860, 14.2908, "napl"),
    Airport("BCN", "Barcelona", "Barcelona", 41.2971, 2.0785, "bcn"),
    Airport("MAD", "Madrid", "Madrid", 40.4983, -3.5676, "madr"),
    Airport("LIS", "Lisbon", "Lisbon", 38.7756, -9.1354, "lisb"),
    Airport("VIE", "Vienna", "Vienna", 48.1103, 16.5697, "vien"),
    Airport("ZRH", "Zurich", "Zurich", 47.4647, 8.5492, "zuri"),
    Airport("PRG", "Prague", "Prague", 50.1008, 14.2600, "prag"),
    Airport("BUD", "Budapest", "Budapest", 47.4298, 19.2611, "budp"),
    Airport("CPH", "Copenhagen", "Copenhagen", 55.6180, 12.6508, "cope"),
)


def airports_near(
    lat: float,
    lon: float,
    *,
    max_km: float,
    limit: int,
    exclude_iata: str | None = None,
) -> list[tuple[Airport, float]]:
    ranked: list[tuple[Airport, float]] = []
    for airport in EUROPEAN_AIRPORTS:
        if exclude_iata and airport.iata == exclude_iata:
            continue
        dist = haversine_km(lat, lon, airport.lat, airport.lon)
        if dist <= max_km:
            ranked.append((airport, dist))
    ranked.sort(key=lambda item: item[1])
    return ranked[:limit]


def departure_airport_candidates(
    origin_lat: float,
    origin_lon: float,
    *,
    max_km: float = 400.0,
    limit: int = 8,
) -> list[Airport]:
    return [ap for ap, _ in airports_near(origin_lat, origin_lon, max_km=max_km, limit=limit)]


def arrival_airport_candidates(
    dest_lat: float,
    dest_lon: float,
    *,
    max_km: float = 150.0,
    limit: int = 5,
) -> list[Airport]:
    return [ap for ap, _ in airports_near(dest_lat, dest_lon, max_km=max_km, limit=limit)]


def rank_airport_pairs(
    departures: list[Airport],
    arrivals: list[Airport],
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    *,
    limit: int = 10,
) -> list[tuple[Airport, Airport]]:
    """Rank pairs; farther departure airports are tried first (often cheaper flight hubs)."""
    pairs: list[tuple[Airport, Airport, float]] = []
    for dep in departures:
        dep_dist = haversine_km(origin_lat, origin_lon, dep.lat, dep.lon)
        for arr in arrivals:
            if dep.iata == arr.iata:
                continue
            arr_dist = haversine_km(dest_lat, dest_lon, arr.lat, arr.lon)
            # Prefer farther departure hubs (train+flight) over origin's home airport.
            score = arr_dist - dep_dist * 0.35
            pairs.append((dep, arr, score))
    pairs.sort(key=lambda item: item[2])
    return [(dep, arr) for dep, arr, _ in pairs[:limit]]
