from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TransportMode(str, Enum):
    WALK = "walk"
    BUS = "bus"
    TRAIN = "train"
    PLANE = "plane"


class PriceSource(str, Enum):
    UNKNOWN = "unknown"
    FLIXBUS_API = "flixbus_api"
    SKYSCANNER = "skyscanner"
    HAFAS = "hafas"
    HISTORIC = "historic"
    FREE = "free"


@dataclass
class JourneyLeg:
    mode: TransportMode
    origin: str
    destination: str
    depart: datetime
    arrive: datetime
    duration_minutes: int
    cost_eur: float
    operator: str
    booking_url: str
    service_id: str = ""
    notes: str = ""


@dataclass
class RouteOption:
    legs: list[JourneyLeg]
    label: str  # e.g. "Balanced", "Fastest", "Cheapest"
    efficiency_score: float  # 0-100, higher is better
    data_source: str  # e.g. "SNCF API", "Skyscanner scrape", "Official site"
    price_verified: bool = True  # False when only schedule is live, not fare
    price_estimated: bool = False  # True when cost comes from historic fare model
    price_source: PriceSource = PriceSource.UNKNOWN
    price_confidence: float = 0.0
    historic_confidence: float = 0.65

    @property
    def total_duration_minutes(self) -> int:
        if not self.legs:
            return 0
        return int((self.legs[-1].arrive - self.legs[0].depart).total_seconds() / 60)

    @property
    def total_cost_eur(self) -> float:
        return sum(leg.cost_eur for leg in self.legs)

    @property
    def modes_used(self) -> list[TransportMode]:
        seen: list[TransportMode] = []
        for leg in self.legs:
            if leg.mode not in seen:
                seen.append(leg.mode)
        return seen


@dataclass
class SearchRequest:
    origin: str
    destination: str
    ideal_departure: datetime
    flexibility_days: int = 3


@dataclass
class SearchResult:
    request: SearchRequest
    routes: list[RouteOption] = field(default_factory=list)
    searched_sources: list[str] = field(default_factory=list)
    price_note: str = ""
