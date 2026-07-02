from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime

# Typical one-way fares (EUR) observed ~30 days before departure.
# Sources: Omio/operator averages across 2023–2025 for standard/2nd class.
# Keys use alphabetical place order (naples, rome) — lookups normalize via _route_key.
_HISTORIC_TRAIN_EUR: dict[tuple[str, str], float] = {
    # Benelux
    ("amsterdam", "antwerp"): 18.0,
    ("amsterdam", "brussels"): 29.0,
    ("amsterdam", "cologne"): 38.0,
    ("amsterdam", "dusseldorf"): 32.0,
    ("amsterdam", "eindhoven"): 14.0,
    ("amsterdam", "frankfurt"): 42.0,
    ("amsterdam", "hamburg"): 36.0,
    ("amsterdam", "london"): 68.0,
    ("amsterdam", "maastricht"): 26.0,
    ("amsterdam", "munich"): 89.0,
    ("amsterdam", "paris"): 40.0,
    ("amsterdam", "rotterdam"): 16.0,
    ("amsterdam", "the hague"): 12.0,
    ("amsterdam", "treviso"): 88.0,
    ("amsterdam", "utrecht"): 11.0,
    ("amsterdam", "venice"): 98.0,
    ("amsterdam", "vienna"): 72.0,
    ("antwerp", "brussels"): 12.0,
    ("brussels", "cologne"): 24.0,
    ("brussels", "liege"): 18.0,
    ("brussels", "lille"): 22.0,
    ("brussels", "london"): 55.0,
    ("brussels", "luxembourg"): 24.0,
    ("brussels", "paris"): 29.0,
    ("liege", "paris"): 38.0,
    ("lille", "london"): 42.0,
    ("lille", "paris"): 18.0,
    ("maastricht", "brussels"): 22.0,
    ("rotterdam", "antwerp"): 14.0,
    # UK / Channel
    ("edinburgh", "london"): 55.0,
    ("london", "amsterdam"): 52.0,
    ("london", "berlin"): 78.0,
    ("london", "brussels"): 48.0,
    ("london", "paris"): 65.0,
    # France
    ("bordeaux", "paris"): 38.0,
    ("lyon", "marseille"): 28.0,
    ("lyon", "nice"): 42.0,
    ("lyon", "paris"): 32.0,
    ("marseille", "nice"): 22.0,
    ("marseille", "paris"): 52.0,
    ("montpellier", "paris"): 48.0,
    ("nantes", "paris"): 32.0,
    ("nice", "paris"): 62.0,
    ("paris", "strasbourg"): 28.0,
    ("paris", "toulouse"): 42.0,
    # Germany
    ("berlin", "dresden"): 22.0,
    ("berlin", "frankfurt"): 42.0,
    ("berlin", "hamburg"): 22.0,
    ("berlin", "leipzig"): 18.0,
    ("berlin", "munich"): 55.0,
    ("berlin", "nuremberg"): 38.0,
    ("berlin", "prague"): 32.0,
    ("cologne", "dusseldorf"): 12.0,
    ("cologne", "frankfurt"): 18.0,
    ("cologne", "munich"): 52.0,
    ("cologne", "venice"): 78.0,
    ("dresden", "prague"): 24.0,
    ("dusseldorf", "munich"): 58.0,
    ("dusseldorf", "treviso"): 68.0,
    ("dusseldorf", "venice"): 72.0,
    ("frankfurt", "munich"): 38.0,
    ("frankfurt", "nuremberg"): 28.0,
    ("frankfurt", "paris"): 48.0,
    ("frankfurt", "stuttgart"): 22.0,
    ("hamburg", "munich"): 48.0,
    ("leipzig", "munich"): 52.0,
    ("munich", "nuremberg"): 18.0,
    ("munich", "salzburg"): 24.0,
    ("munich", "stuttgart"): 32.0,
    ("nuremberg", "prague"): 32.0,
    # DACH / Alps
    ("basel", "zurich"): 22.0,
    ("bern", "zurich"): 28.0,
    ("geneva", "lyon"): 32.0,
    ("geneva", "paris"): 52.0,
    ("geneva", "zurich"): 38.0,
    ("innsbruck", "munich"): 28.0,
    ("innsbruck", "vienna"): 38.0,
    ("munich", "vienna"): 42.0,
    ("munich", "zurich"): 36.0,
    ("salzburg", "vienna"): 22.0,
    ("zurich", "milan"): 32.0,
    # Italy
    ("bologna", "florence"): 18.0,
    ("bologna", "milan"): 28.0,
    ("bologna", "rome"): 32.0,
    ("bologna", "venice"): 24.0,
    ("florence", "milan"): 32.0,
    ("florence", "naples"): 42.0,
    ("florence", "rome"): 24.0,
    ("florence", "venice"): 28.0,
    ("genoa", "milan"): 18.0,
    ("milan", "naples"): 58.0,
    ("milan", "nice"): 38.0,
    ("milan", "rome"): 45.0,
    ("milan", "turin"): 16.0,
    ("milan", "venice"): 28.0,
    ("milan", "verona"): 14.0,
    ("naples", "rome"): 22.0,
    ("naples", "venice"): 48.0,
    ("padova", "bassano del grappa"): 6.0,
    ("padova", "venice"): 7.0,
    ("rome", "turin"): 48.0,
    ("rome", "venice"): 45.0,
    ("treviso", "venice"): 5.0,
    ("turin", "paris"): 62.0,
    ("verona", "bassano del grappa"): 8.0,
    ("verona", "venice"): 9.0,
    ("verona", "vicenza"): 6.0,
    ("vicenza", "bassano del grappa"): 6.0,
    # Iberia
    ("barcelona", "madrid"): 35.0,
    ("barcelona", "paris"): 68.0,
    ("barcelona", "valencia"): 28.0,
    ("lisbon", "madrid"): 48.0,
    ("madrid", "seville"): 32.0,
    ("madrid", "valencia"): 28.0,
    ("malaga", "madrid"): 42.0,
    ("porto", "barcelona"): 38.0,
    # Central / Eastern Europe
    ("berlin", "warsaw"): 38.0,
    ("bratislava", "vienna"): 14.0,
    ("brno", "prague"): 12.0,
    ("budapest", "prague"): 32.0,
    ("budapest", "vienna"): 19.0,
    ("budapest", "warsaw"): 42.0,
    ("krakow", "berlin"): 48.0,
    ("krakow", "prague"): 38.0,
    ("krakow", "warsaw"): 22.0,
    ("krakow", "vienna"): 32.0,
    ("ljubljana", "vienna"): 28.0,
    ("prague", "vienna"): 16.0,
    ("vienna", "venice"): 48.0,
    ("vienna", "warsaw"): 38.0,
    ("warsaw", "gdansk"): 22.0,
    ("zagreb", "ljubljana"): 14.0,
    ("zagreb", "vienna"): 38.0,
    # Nordics
    ("copenhagen", "hamburg"): 38.0,
    ("copenhagen", "oslo"): 52.0,
    ("copenhagen", "stockholm"): 48.0,
    ("gothenburg", "oslo"): 32.0,
    ("gothenburg", "stockholm"): 28.0,
    ("helsinki", "stockholm"): 58.0,
    ("oslo", "stockholm"): 42.0,
    # Cross-border highlights (long haul)
    ("amsterdam", "berlin"): 48.0,
    ("amsterdam", "rome"): 95.0,
    ("barcelona", "lyon"): 52.0,
    ("barcelona", "milan"): 72.0,
    ("berlin", "vienna"): 48.0,
    ("budapest", "munich"): 52.0,
    ("lyon", "milan"): 42.0,
    ("milan", "munich"): 48.0,
    ("milan", "zurich"): 32.0,
    ("munich", "venice"): 42.0,
    ("paris", "barcelona"): 68.0,
    ("paris", "berlin"): 78.0,
    ("paris", "milan"): 58.0,
    ("paris", "munich"): 72.0,
    ("paris", "zurich"): 48.0,
    ("rome", "munich"): 68.0,
    ("vienna", "zurich"): 52.0,
}

_HISTORIC_BUS_EUR: dict[tuple[str, str], float] = {
    ("amsterdam", "berlin"): 28.0,
    ("amsterdam", "brussels"): 12.0,
    ("amsterdam", "cologne"): 15.0,
    ("amsterdam", "dusseldorf"): 14.0,
    ("amsterdam", "hamburg"): 22.0,
    ("amsterdam", "london"): 32.0,
    ("amsterdam", "munich"): 38.0,
    ("amsterdam", "paris"): 25.0,
    ("amsterdam", "prague"): 32.0,
    ("amsterdam", "rotterdam"): 8.0,
    ("amsterdam", "vienna"): 35.0,
    ("barcelona", "madrid"): 18.0,
    ("barcelona", "paris"): 38.0,
    ("berlin", "munich"): 22.0,
    ("berlin", "prague"): 18.0,
    ("berlin", "vienna"): 28.0,
    ("berlin", "warsaw"): 22.0,
    ("brussels", "paris"): 15.0,
    ("budapest", "vienna"): 12.0,
    ("cologne", "frankfurt"): 10.0,
    ("florence", "rome"): 14.0,
    ("krakow", "warsaw"): 10.0,
    ("london", "paris"): 28.0,
    ("lyon", "paris"): 14.0,
    ("milan", "rome"): 16.0,
    ("milan", "venice"): 12.0,
    ("munich", "vienna"): 14.0,
    ("naples", "rome"): 12.0,
    ("naples", "venice"): 28.0,
    ("paris", "milan"): 32.0,
    ("prague", "vienna"): 12.0,
    ("rome", "venice"): 22.0,
}

# Approximate city-centre coordinates for distance fallback (lat, lon).
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "aachen": (50.7753, 6.0839),
    "alicante": (38.3452, -0.4810),
    "amsterdam": (52.3676, 4.9041),
    "antwerp": (51.2194, 4.4025),
    "athens": (37.9838, 23.7275),
    "barcelona": (41.3874, 2.1686),
    "basel": (47.5596, 7.5886),
    "bassano del grappa": (45.7667, 11.7333),
    "belgrade": (44.7866, 20.4489),
    "berlin": (52.5200, 13.4050),
    "bern": (46.9480, 7.4474),
    "bilbao": (43.2630, -2.9350),
    "birmingham": (52.4862, -1.8904),
    "bologna": (44.4949, 11.3426),
    "bordeaux": (44.8378, -0.5792),
    "bratislava": (48.1486, 17.1077),
    "brno": (49.1951, 16.6068),
    "bruges": (51.2093, 3.2247),
    "brussels": (50.8503, 4.3517),
    "bucharest": (44.4268, 26.1025),
    "budapest": (47.4979, 19.0402),
    "cologne": (50.9375, 6.9603),
    "copenhagen": (55.6761, 12.5683),
    "dresden": (51.0504, 13.7373),
    "dublin": (53.3498, -6.2603),
    "dusseldorf": (51.2277, 6.7735),
    "edinburgh": (55.9533, -3.1883),
    "eindhoven": (51.4416, 5.4697),
    "florence": (43.7696, 11.2558),
    "frankfurt": (50.1109, 8.6821),
    "gdansk": (54.3520, 18.6466),
    "geneva": (46.2044, 6.1432),
    "genoa": (44.4056, 8.9463),
    "ghent": (51.0543, 3.7174),
    "glasgow": (55.8642, -4.2518),
    "gothenburg": (57.7089, 11.9746),
    "graz": (47.0707, 15.4395),
    "hamburg": (53.5511, 9.9937),
    "heidelberg": (49.3988, 8.6724),
    "helsinki": (60.1699, 24.9384),
    "innsbruck": (47.2692, 11.4041),
    "krakow": (50.0647, 19.9450),
    "leipzig": (51.3397, 12.3731),
    "liege": (50.6326, 5.5797),
    "lille": (50.6292, 3.0573),
    "lisbon": (38.7223, -9.1393),
    "ljubljana": (46.0569, 14.5058),
    "london": (51.5074, -0.1278),
    "luxembourg": (49.6116, 6.1319),
    "lyon": (45.7640, 4.8357),
    "madrid": (40.4168, -3.7038),
    "malaga": (36.7213, -4.4214),
    "manchester": (53.4808, -2.2426),
    "marseille": (43.2965, 5.3698),
    "milan": (45.4642, 9.1900),
    "montpellier": (43.6108, 3.8767),
    "munich": (48.1351, 11.5820),
    "naples": (40.8518, 14.2681),
    "napoli": (40.8518, 14.2681),
    "nantes": (47.2184, -1.5536),
    "nice": (43.7102, 7.2620),
    "nuremberg": (49.4521, 11.0767),
    "oslo": (59.9139, 10.7522),
    "padova": (45.4064, 11.8768),
    "paris": (48.8566, 2.3522),
    "porto": (41.1579, -8.6291),
    "poznan": (52.4064, 16.9252),
    "prague": (50.0755, 14.4378),
    "rome": (41.9028, 12.4964),
    "rotterdam": (51.9244, 4.4777),
    "salzburg": (47.8095, 13.0550),
    "seville": (37.3891, -5.9845),
    "sofia": (42.6977, 23.3219),
    "stockholm": (59.3293, 18.0686),
    "strasbourg": (48.5734, 7.7521),
    "stuttgart": (48.7758, 9.1829),
    "the hague": (52.0705, 4.3007),
    "toulouse": (43.6047, 1.4442),
    "treviso": (45.6669, 12.2430),
    "turin": (45.0703, 7.6869),
    "utrecht": (52.0907, 5.1214),
    "valencia": (39.4699, -0.3763),
    "venice": (45.4408, 12.3155),
    "verona": (45.4384, 10.9916),
    "vicenza": (45.5455, 11.5353),
    "vienna": (48.2082, 16.3738),
    "warsaw": (52.2297, 21.0122),
    "wroclaw": (51.1079, 17.0385),
    "zagreb": (45.8150, 15.9819),
    "zurich": (47.3769, 8.5417),
    "maastricht": (50.8514, 5.6910),
}

_TRAIN_EUR_PER_KM = 0.11
_TRAIN_MIN_EUR = 12.0
_BUS_EUR_PER_KM = 0.055
_BUS_MIN_EUR = 8.0
_BASELINE_DAYS_AHEAD = 30
_VIA_HUBS = (
    "amsterdam",
    "barcelona",
    "berlin",
    "brussels",
    "cologne",
    "frankfurt",
    "lyon",
    "madrid",
    "milan",
    "munich",
    "paris",
    "rome",
    "vienna",
    "zurich",
)


def _normalize_place(name: str) -> str:
    text = name.strip().lower()
    if "(" in text:
        text = text.split("(")[0].strip()
    if "," in text:
        text = text.split(",")[0].strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for suffix in (
        " centraal",
        " central",
        " hbf",
        " hl n",
        " hlavni nadrazi",
        " airport",
        " flughafen",
        " station",
    ):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


# Station / local names mapped to canonical city keys used in fare tables.
_PLACE_ALIASES: dict[str, str] = {
    "antwerpen": "antwerp",
    "antwerpen centraal": "antwerp",
    "barcelona sants": "barcelona",
    "barcelona estacio de franca": "barcelona",
    "basel sbb": "basel",
    "bologna centrale": "bologna",
    "bordeaux saint jean": "bordeaux",
    "bratislava hlavna stanica": "bratislava",
    "brussel": "brussels",
    "brussels midi": "brussels",
    "brussels south": "brussels",
    "brussels zuid": "brussels",
    "bruxelles": "brussels",
    "bruxelles midi": "brussels",
    "bruxelles central": "brussels",
    "budapest keleti": "budapest",
    "copenhagen central": "copenhagen",
    "kobenhavn h": "copenhagen",
    "den haag": "the hague",
    "den haag centraal": "the hague",
    "dusseldorf": "dusseldorf",
    "dusseldorf hbf": "dusseldorf",
    "florenz": "florence",
    "firenze": "florence",
    "firenze santa maria novella": "florence",
    "frankfurt main hbf": "frankfurt",
    "frankfurt hbf": "frankfurt",
    "geneve": "geneva",
    "geneve cff": "geneva",
    "genova": "genoa",
    "genova piazza principe": "genoa",
    "hamburg hbf": "hamburg",
    "hannover hbf": "hannover",
    "innsbruck hbf": "innsbruck",
    "krakow glowny": "krakow",
    "krakow main": "krakow",
    "koln": "cologne",
    "koln hbf": "cologne",
    "koeln": "cologne",
    "koeln hbf": "cologne",
    "lisboa": "lisbon",
    "lisboa oriente": "lisbon",
    "lisboa santa apolonia": "lisbon",
    "ljubljana": "ljubljana",
    "lyon part dieu": "lyon",
    "lyon perrache": "lyon",
    "madrid atocha": "madrid",
    "madrid chamartin": "madrid",
    "malaga maria zambrano": "malaga",
    "marseille saint charles": "marseille",
    "milano": "milan",
    "milano centrale": "milan",
    "milano rogoredo": "milan",
    "munchen": "munich",
    "munchen hbf": "munich",
    "muenchen": "munich",
    "muenchen hbf": "munich",
    "münchen": "munich",
    "münchen hbf": "munich",
    "napoli": "naples",
    "napoli centrale": "naples",
    "nice ville": "nice",
    "nurnberg": "nuremberg",
    "nurnberg hbf": "nuremberg",
    "nuremberg hbf": "nuremberg",
    "oslo s": "oslo",
    "padova": "padova",
    "paris gare de lyon": "paris",
    "paris gare du nord": "paris",
    "paris gare de l est": "paris",
    "paris montparnasse": "paris",
    "paris nord": "paris",
    "porto campanha": "porto",
    "praha": "prague",
    "praha hlavni nadrazi": "prague",
    "roma": "rome",
    "roma termini": "rome",
    "roma tiburtina": "rome",
    "rotterdam centraal": "rotterdam",
    "salzburg hbf": "salzburg",
    "sevilla": "seville",
    "sevilla santa justa": "seville",
    "stockholm central": "stockholm",
    "stockholms centralstation": "stockholm",
    "stuttgart hbf": "stuttgart",
    "the hague": "the hague",
    "torino": "turin",
    "torino porta nuova": "turin",
    "toulouse matabiau": "toulouse",
    "utrecht centraal": "utrecht",
    "valencia joaquin sorolla": "valencia",
    "venezia": "venice",
    "venezia mestre": "venice",
    "venezia santa lucia": "venice",
    "verona porta nuova": "verona",
    "vicenza": "vicenza",
    "warszawa": "warsaw",
    "warszawa centralna": "warsaw",
    "wien": "vienna",
    "wien hbf": "vienna",
    "wroclaw glowny": "wroclaw",
    "zagreb glavni kolodvor": "zagreb",
    "zurich hb": "zurich",
    "zurich hbf": "zurich",
    "zurich main station": "zurich",
}


def canonical_place(name: str) -> str:
    return _canonical_place(name)


def _canonical_place(name: str) -> str:
    normalized = _normalize_place(name)
    if normalized in _PLACE_ALIASES:
        return _PLACE_ALIASES[normalized]
    if normalized in _CITY_COORDS:
        return normalized
    for alias in sorted(_PLACE_ALIASES, key=len, reverse=True):
        if normalized.startswith(alias) or f" {alias} " in f" {normalized} ":
            return _PLACE_ALIASES[alias]
    for city in sorted(_CITY_COORDS, key=len, reverse=True):
        if normalized.startswith(city) or city in normalized.split():
            return city
    return normalized


def _route_key(origin: str, destination: str) -> tuple[str, str]:
    a = _canonical_place(origin)
    b = _canonical_place(destination)
    return (a, b) if a <= b else (b, a)


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _coords(place: str) -> tuple[float, float] | None:
    key = _canonical_place(place)
    if key in _CITY_COORDS:
        return _CITY_COORDS[key]
    for city, coords in _CITY_COORDS.items():
        if city in key or key in city:
            return coords
    return None


def days_until_departure(depart: datetime, *, today: date | None = None) -> int:
    ref = today or date.today()
    return max((depart.date() - ref).days, 0)


def booking_window_multiplier(days_ahead: int) -> float:
    """Fare uplift as departure approaches (vs ~30-day baseline)."""
    if days_ahead >= 90:
        return 0.85
    if days_ahead >= 60:
        return 0.92
    if days_ahead >= 45:
        return 0.96
    if days_ahead >= _BASELINE_DAYS_AHEAD:
        return 1.0
    if days_ahead >= 21:
        return 1.08
    if days_ahead >= 14:
        return 1.18
    if days_ahead >= 7:
        return 1.32
    if days_ahead >= 3:
        return 1.48
    if days_ahead >= 1:
        return 1.62
    return 1.75


def _lookup_historic(
    origin: str,
    destination: str,
    table: dict[tuple[str, str], float],
) -> float | None:
    key = _route_key(origin, destination)
    return table.get(key)


def _distance_estimate(origin: str, destination: str, mode: str) -> float | None:
    a = _coords(origin)
    b = _coords(destination)
    if not a or not b:
        return None
    km = _haversine_km(a, b)
    if mode == "bus":
        return max(_BUS_MIN_EUR, km * _BUS_EUR_PER_KM)
    return max(_TRAIN_MIN_EUR, km * _TRAIN_EUR_PER_KM)


def _via_hub_estimate(
    origin: str,
    destination: str,
    table: dict[tuple[str, str], float],
) -> float | None:
    best: float | None = None
    for hub in _VIA_HUBS:
        leg1 = _lookup_historic(origin, hub, table)
        leg2 = _lookup_historic(hub, destination, table)
        if leg1 is None or leg2 is None:
            continue
        total = (leg1 + leg2) * 0.97
        if best is None or total < best:
            best = total
    return best


def estimate_fare(
    origin: str,
    destination: str,
    depart: datetime,
    *,
    mode: str = "train",
) -> float | None:
    table = _HISTORIC_BUS_EUR if mode == "bus" else _HISTORIC_TRAIN_EUR
    base = _lookup_historic(origin, destination, table)
    if base is None:
        base = _via_hub_estimate(origin, destination, table)
    if base is None:
        base = _distance_estimate(origin, destination, mode)
    if base is None:
        return None

    days = days_until_departure(depart)
    baseline_adj = booking_window_multiplier(days) / booking_window_multiplier(
        _BASELINE_DAYS_AHEAD
    )
    return round(base * baseline_adj, 2)


def estimate_confidence(origin: str, destination: str, mode: str) -> str:
    table = _HISTORIC_BUS_EUR if mode == "bus" else _HISTORIC_TRAIN_EUR
    if _lookup_historic(origin, destination, table) is not None:
        return "historic route average"
    if _via_hub_estimate(origin, destination, table) is not None:
        return "historic via-hub estimate"
    if _coords(origin) and _coords(destination):
        return "distance-based estimate"
    return "rough estimate"
