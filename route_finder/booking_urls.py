from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from urllib.parse import quote

import httpx

# Skyscanner city codes (lowercase, 4-letter where applicable)
_SKYSCANNER_CITY: dict[str, str] = {
    "paris": "pari",
    "amsterdam": "amst",
    "london": "lond",
    "berlin": "berl",
    "brussels": "brus",
    "cologne": "cgn",
    "madrid": "madr",
    "rome": "rome",
    "barcelona": "bcn",
    "naples": "napl",
    "vienna": "vien",
    "prague": "prag",
    "budapest": "budp",
    "dublin": "dubl",
    "lisbon": "lisb",
    "milan": "mila",
    "zurich": "zuri",
    "frankfurt": "fran",
    "hamburg": "hamb",
    "warsaw": "wars",
    "dusseldorf": "duss",
    "venice": "veni",
    "treviso": "trvs",
    "verona": "vrn",
    "bologna": "blq",
    "rotterdam": "rtm",
    "eindhoven": "einh",
}

# IATA airport codes for direct airline booking links
_AIRPORT_IATA: dict[str, str] = {
    "paris": "PAR",
    "amsterdam": "AMS",
    "london": "LON",
    "berlin": "BER",
    "brussels": "BRU",
    "cologne": "CGN",
    "madrid": "MAD",
    "rome": "ROM",
    "barcelona": "BCN",
    "naples": "NAP",
    "vienna": "VIE",
    "prague": "PRG",
    "budapest": "BUD",
    "dublin": "DUB",
    "lisbon": "LIS",
    "milan": "MIL",
    "zurich": "ZRH",
    "frankfurt": "FRA",
    "hamburg": "HAM",
    "warsaw": "WAW",
    "dusseldorf": "DUS",
    "venice": "VCE",
    "treviso": "TSF",
    "verona": "VRN",
    "bologna": "BLQ",
    "rotterdam": "RTM",
    "eindhoven": "EIN",
}


def _slug(city: str) -> str:
    return city.strip().lower().split(",")[0].split("(")[0].strip()


def _skyscanner_code(city: str) -> str:
    key = _slug(city)
    return _SKYSCANNER_CITY.get(key, key[:4].ljust(4, "x")[:4])


def _iata(city: str) -> str:
    key = _slug(city)
    return _AIRPORT_IATA.get(key, key[:3].upper().ljust(3, "X")[:3])


def _flix_date(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y")


def _iso_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _iso_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


# Station names recognised by int.bahn.de (Deutsche Bahn international).
_DB_STATIONS: dict[str, str] = {
    "amsterdam": "Amsterdam Centraal",
    "brussels": "Bruxelles Midi",
    "bruxelles": "Bruxelles Midi",
    "paris": "Paris",
    "london": "London",
    "berlin": "Berlin Hbf",
    "cologne": "Köln Hbf",
    "frankfurt": "Frankfurt (Main) Hbf",
    "munich": "München Hbf",
    "vienna": "Wien Hbf",
    "prague": "Praha hl.n.",
    "budapest": "Budapest",
    "zurich": "Zürich HB",
    "milan": "Milano Centrale",
    "rome": "Roma Termini",
    "barcelona": "Barcelona Sants",
    "madrid": "Madrid",
    "copenhagen": "København H",
    "stockholm": "Stockholm Central",
    "oslo": "Oslo S",
    "hamburg": "Hamburg Hbf",
    "rotterdam": "Rotterdam Centraal",
    "antwerp": "Antwerpen-Centraal",
    "lyon": "Lyon Part-Dieu",
    "marseille": "Marseille-St-Charles",
    "bruges": "Brugge",
    "ghent": "Gent-Sint-Pieters",
    "luxembourg": "Luxembourg",
    "warsaw": "Warszawa Centralna",
    "dusseldorf": "Düsseldorf Hbf",
    "venice": "Venezia Santa Lucia",
    "verona": "Verona Porta Nuova",
    "krakow": "Kraków Główny",
    "dublin": "Dublin",
    "edinburgh": "Edinburgh",
    "manchester": "Manchester",
    "birmingham": "Birmingham",
}


def _db_station(city: str) -> str:
    key = _slug(city)
    return _DB_STATIONS.get(key, city.strip())


_DB_ORTS_API = "https://www.bahn.de/web/api/reiseloesung/orte"


@lru_cache(maxsize=128)
def _db_station_ref(city: str) -> str:
    """Resolve a city to a DB station id via the public orts API."""
    search = _db_station(city)
    try:
        response = httpx.get(
            _DB_ORTS_API,
            params={"suchbegriff": search, "typ": "ALL", "limit": 1},
            timeout=8.0,
            headers={"User-Agent": "EuropeRouteFinder/1.0 (route-finder-cli)"},
        )
        if response.status_code == 200:
            results = response.json()
            if results:
                return results[0]["id"]
    except Exception:
        pass
    return f"O={search}"


def db_station_id(city: str) -> str:
    """Public wrapper for DB station id lookup (used by fare search)."""
    return _db_station_ref(city)


def train_booking(origin: str, destination: str, depart: datetime) -> str:
    """Deutsche Bahn international planner with route and date pre-filled."""
    o = quote(_db_station_ref(origin), safe="")
    d = quote(_db_station_ref(destination), safe="")
    when = quote(_iso_datetime(depart), safe="")
    return (
        "https://int.bahn.de/en/buchung/fahrplan/suche"
        f"#soid={o}&zoid={d}&hd={when}&ht=1&r=0&tt=dep"
    )


def trainline(origin: str, destination: str, depart: datetime) -> str:
    """Alias for train_booking (Trainline text URLs are not reliable)."""
    return train_booking(origin, destination, depart)


def bahn(origin: str, destination: str, depart: datetime) -> str:
    return train_booking(origin, destination, depart)


def ns_international(origin: str, destination: str, depart: datetime) -> str:
    o, d = quote(origin), quote(destination)
    date = _iso_date(depart)
    time = depart.strftime("%H:%M")
    return (
        "https://www.ns.nl/en/journeyplanner/#/"
        f"?vertrek={o}&aankomst={d}"
        f"&vertrekdatum={date}&vertrektijdT={quote(time)}"
    )


def skyscanner_flights(origin: str, destination: str, depart: datetime) -> str:
    o_code = _skyscanner_code(origin)
    d_code = _skyscanner_code(destination)
    yymmdd = depart.strftime("%y%m%d")
    return f"https://www.skyscanner.net/transport/flights/{o_code}/{d_code}/{yymmdd}/"


def ryanair(origin: str, destination: str, depart: datetime) -> str:
    o_iata = _iata(origin)
    d_iata = _iata(destination)
    date = _iso_date(depart)
    return (
        "https://www.ryanair.com/gb/en/trip/flights/select"
        f"?adults=1&teens=0&children=0&infants=0"
        f"&dateOut={date}&originIata={o_iata}&destinationIata={d_iata}"
        f"&isConnectedFlight=false&tpAdults=1&tpStartDate={date}"
        f"&tpOriginIata={o_iata}&tpDestinationIata={d_iata}"
    )


def flixbus(origin: str, destination: str, depart: datetime) -> str:
    o, d = quote(origin), quote(destination)
    return (
        "https://shop.flixbus.com/search"
        f"?departureCity={o}&arrivalCity={d}&rideDate={_flix_date(depart)}"
        "&adult=1&_locale=en&features%5Bfeature.enable_distribusion%5D=1"
    )


def google_maps_walk(origin: str, destination: str) -> str:
    o, d = quote(origin), quote(destination)
    return f"https://www.google.com/maps/dir/?api=1&origin={o}&destination={d}&travelmode=walking"


def google_maps_transit(origin: str, destination: str) -> str:
    o, d = quote(origin), quote(destination)
    return f"https://www.google.com/maps/dir/?api=1&origin={o}&destination={d}&travelmode=transit"


def _omio_slug(city: str) -> str:
    text = city.strip().lower().split(",")[0].split("(")[0].strip()
    for old, new in (
        ("ü", "u"),
        ("ö", "o"),
        ("ä", "a"),
        ("ß", "ss"),
        ("é", "e"),
        ("è", "e"),
        ("ô", "o"),
        ("ø", "o"),
        ("ł", "l"),
        ("ń", "n"),
    ):
        text = text.replace(old, new)
    return text.replace(" ", "-").replace("'", "")


def omio_search(
    origin: str,
    destination: str,
    depart: datetime,
    *,
    mode: str = "train",
) -> str:
    """Prefilled Omio results page (train or bus) for live fare lookup."""
    date = _iso_date(depart)
    slug_o = _omio_slug(origin)
    slug_d = _omio_slug(destination)
    segment = "buses" if mode == "bus" else "trains"
    return f"https://www.omio.com/{segment}/{slug_o}/{slug_d}/{date}"
