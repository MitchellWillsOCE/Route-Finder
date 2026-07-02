from __future__ import annotations

import unittest
from datetime import datetime

from route_finder.connections import (
    count_transfers,
    min_connection_minutes,
    validate_route,
)
from route_finder.flight_estimates import (
    estimate_flight_fare,
    estimate_flight_duration,
    flight_booking_window_multiplier,
)
from route_finder.historic_fares import canonical_place, estimate_fare
from route_finder.models import JourneyLeg, RouteOption, SearchRequest, TransportMode
from route_finder.pricing import apply_route_pricing_meta
from route_finder.scoring import diversify_ranked_routes, score_routes
from route_finder.route_summary import route_via_hubs, route_category, mode_breakdown
from route_finder.train_fares import enrich_route_prices


class CoreTests(unittest.TestCase):
    def test_canonical_brussels_station(self) -> None:
        self.assertEqual(canonical_place("Bruxelles-Midi"), "brussels")

    def test_amsterdam_brussels_fare_estimate(self) -> None:
        depart = datetime(2026, 7, 15, 8, 0)
        price = estimate_fare("Amsterdam Centraal", "Bruxelles-Midi", depart)
        self.assertIsNotNone(price)
        assert price is not None
        self.assertGreater(price, 20)
        self.assertLess(price, 60)

    def test_major_routes_use_historic_not_distance_only(self) -> None:
        depart = datetime(2026, 7, 15, 8, 0)
        from route_finder.historic_fares import estimate_confidence

        pairs = [
            ("Venice", "Naples"),
            ("Paris", "Milan"),
            ("Berlin", "Prague"),
            ("Barcelona", "Madrid"),
            ("Munich", "Vienna"),
            ("Florence", "Rome"),
            ("Copenhagen", "Stockholm"),
            ("Lisbon", "Madrid"),
        ]
        for origin, dest in pairs:
            with self.subTest(origin=origin, dest=dest):
                price = estimate_fare(origin, dest, depart)
                confidence = estimate_confidence(origin, dest, "train")
                self.assertIsNotNone(price, f"missing fare for {origin}->{dest}")
                self.assertIn(
                    confidence,
                    ("historic route average", "historic via-hub estimate"),
                    f"{origin}->{dest} fell back to {confidence}",
                )

    def test_amsterdam_naples_flight_estimate(self) -> None:
        depart = datetime(2026, 7, 15, 9, 0)
        price = estimate_flight_fare("Amsterdam", "Naples", depart)
        duration = estimate_flight_duration("Amsterdam", "Naples")
        self.assertIsNotNone(price)
        self.assertIsNotNone(duration)
        assert price is not None
        assert duration is not None
        self.assertGreater(price, 60)
        self.assertLess(price, 180)
        self.assertGreater(duration, 120)
        self.assertLess(duration, 200)

    def test_flight_fare_rises_closer_to_departure(self) -> None:
        far = datetime(2026, 10, 15, 9, 0)
        near = datetime(2026, 7, 2, 9, 0)
        far_price = estimate_flight_fare("Amsterdam", "Naples", far)
        near_price = estimate_flight_fare("Amsterdam", "Naples", near)
        self.assertIsNotNone(far_price)
        self.assertIsNotNone(near_price)
        assert far_price is not None and near_price is not None
        self.assertGreater(near_price, far_price)
        self.assertGreater(
            flight_booking_window_multiplier(3),
            flight_booking_window_multiplier(60),
        )

    def test_enrich_train_route_sets_estimate(self) -> None:
        depart = datetime(2026, 7, 15, 8, 0)
        route = RouteOption(
            legs=[
                JourneyLeg(
                    mode=TransportMode.TRAIN,
                    origin="Amsterdam Centraal",
                    destination="Bruxelles-Midi",
                    depart=depart,
                    arrive=depart.replace(hour=10, minute=26),
                    duration_minutes=146,
                    cost_eur=0.0,
                    operator="Eurostar",
                    booking_url="",
                )
            ],
            label="",
            efficiency_score=0.0,
            data_source="MOTIS test",
            price_verified=False,
        )
        request = SearchRequest("Amsterdam", "Brussels", depart, 3)
        enrich_route_prices(route, request)
        self.assertTrue(route.price_estimated)
        self.assertGreater(route.total_cost_eur, 0)

    def test_route_via_hubs_from_train_legs(self) -> None:
        depart = datetime(2026, 7, 15, 8, 0)
        route = RouteOption(
            legs=[
                JourneyLeg(
                    mode=TransportMode.TRAIN,
                    origin="Amsterdam Centraal",
                    destination="Zurich HB",
                    depart=depart,
                    arrive=depart.replace(hour=12),
                    duration_minutes=240,
                    cost_eur=0,
                    operator="SBB",
                    booking_url="",
                ),
                JourneyLeg(
                    mode=TransportMode.TRAIN,
                    origin="Zurich HB",
                    destination="Milano Centrale",
                    depart=depart.replace(hour=13),
                    arrive=depart.replace(hour=16),
                    duration_minutes=180,
                    cost_eur=0,
                    operator="SBB",
                    booking_url="",
                ),
                JourneyLeg(
                    mode=TransportMode.TRAIN,
                    origin="Milano Centrale",
                    destination="Napoli Centrale",
                    depart=depart.replace(hour=17),
                    arrive=depart.replace(hour=21),
                    duration_minutes=240,
                    cost_eur=0,
                    operator="Trenitalia",
                    booking_url="",
                ),
            ],
            label="",
            efficiency_score=0.0,
            data_source="test",
        )
        hubs = route_via_hubs(route, "Amsterdam", "Naples")
        self.assertIn("Zurich", hubs)
        self.assertIn("Milan", hubs)

    def test_diversify_includes_bus_train_and_flight(self) -> None:
        depart = datetime(2026, 7, 15, 8, 0)
        flight = RouteOption(
            legs=[
                JourneyLeg(
                    mode=TransportMode.PLANE,
                    origin="AMS",
                    destination="NAP",
                    depart=depart,
                    arrive=depart.replace(hour=11),
                    duration_minutes=155,
                    cost_eur=118,
                    operator="x",
                    booking_url="",
                )
            ],
            label="",
            efficiency_score=0.0,
            data_source="flight",
            price_estimated=True,
        )
        train = RouteOption(
            legs=[
                JourneyLeg(
                    mode=TransportMode.TRAIN,
                    origin="Amsterdam",
                    destination="Naples",
                    depart=depart,
                    arrive=depart.replace(hour=22),
                    duration_minutes=840,
                    cost_eur=180,
                    operator="t",
                    booking_url="",
                )
            ],
            label="",
            efficiency_score=0.0,
            data_source="train",
            price_estimated=True,
        )
        bus = RouteOption(
            legs=[
                JourneyLeg(
                    mode=TransportMode.BUS,
                    origin="Amsterdam",
                    destination="Naples",
                    depart=depart,
                    arrive=depart.replace(day=depart.day + 1),
                    duration_minutes=2050,
                    cost_eur=125,
                    operator="FlixBus",
                    booking_url="",
                )
            ],
            label="",
            efficiency_score=0.0,
            data_source="bus",
            price_verified=True,
        )
        ranked = score_routes([flight, flight, flight, flight, bus, train])
        diverse = diversify_ranked_routes(ranked, limit=8)
        categories = {route_category(r) for r in diverse}
        self.assertIn("flight", categories)
        self.assertIn("train", categories)
        self.assertIn("bus", categories)

    def test_mode_breakdown_splits_costs(self) -> None:
        depart = datetime(2026, 7, 15, 8, 0)
        route = RouteOption(
            legs=[
                JourneyLeg(
                    mode=TransportMode.BUS,
                    origin="A",
                    destination="B",
                    depart=depart,
                    arrive=depart.replace(hour=10),
                    duration_minutes=600,
                    cost_eur=80,
                    operator="b",
                    booking_url="",
                ),
                JourneyLeg(
                    mode=TransportMode.TRAIN,
                    origin="B",
                    destination="C",
                    depart=depart.replace(hour=11),
                    arrive=depart.replace(hour=15),
                    duration_minutes=240,
                    cost_eur=40,
                    operator="t",
                    booking_url="",
                ),
            ],
            label="",
            efficiency_score=0.0,
            data_source="test",
        )
        breakdown = mode_breakdown(route)
        self.assertEqual(breakdown[TransportMode.BUS].duration_minutes, 600)
        self.assertEqual(breakdown[TransportMode.TRAIN].cost_eur, 40)

    def test_connection_buffers(self) -> None:
        self.assertGreaterEqual(
            min_connection_minutes(TransportMode.TRAIN, TransportMode.PLANE), 60
        )

    def test_validate_rejects_impossible_connection(self) -> None:
        depart = datetime(2026, 7, 15, 8, 0)
        route = RouteOption(
            legs=[
                JourneyLeg(
                    mode=TransportMode.TRAIN,
                    origin="A",
                    destination="B",
                    depart=depart,
                    arrive=depart.replace(hour=9),
                    duration_minutes=60,
                    cost_eur=10,
                    operator="x",
                    booking_url="",
                ),
                JourneyLeg(
                    mode=TransportMode.PLANE,
                    origin="B",
                    destination="C",
                    depart=depart.replace(hour=9, minute=5),
                    arrive=depart.replace(hour=11),
                    duration_minutes=115,
                    cost_eur=50,
                    operator="y",
                    booking_url="",
                ),
            ],
            label="",
            efficiency_score=0.0,
            data_source="test",
        )
        self.assertFalse(validate_route(route))

    def test_count_transfers_ignores_short_walks(self) -> None:
        depart = datetime(2026, 7, 15, 8, 0)
        route = RouteOption(
            legs=[
                JourneyLeg(
                    mode=TransportMode.WALK,
                    origin="A",
                    destination="B",
                    depart=depart,
                    arrive=depart.replace(minute=10),
                    duration_minutes=10,
                    cost_eur=0,
                    operator="w",
                    booking_url="",
                ),
                JourneyLeg(
                    mode=TransportMode.TRAIN,
                    origin="B",
                    destination="C",
                    depart=depart.replace(minute=10),
                    arrive=depart.replace(hour=2),
                    duration_minutes=110,
                    cost_eur=30,
                    operator="t",
                    booking_url="",
                ),
            ],
            label="",
            efficiency_score=0.0,
            data_source="test",
        )
        self.assertEqual(count_transfers(route), 0)

    def test_scoring_applies_price_confidence(self) -> None:
        depart = datetime(2026, 7, 15, 8, 0)
        bus = RouteOption(
            legs=[
                JourneyLeg(
                    mode=TransportMode.BUS,
                    origin="Amsterdam",
                    destination="Brussels",
                    depart=depart,
                    arrive=depart.replace(hour=11),
                    duration_minutes=180,
                    cost_eur=12.0,
                    operator="FlixBus",
                    booking_url="",
                )
            ],
            label="",
            efficiency_score=0.0,
            data_source="FlixBus API (live)",
            price_verified=True,
        )
        apply_route_pricing_meta(bus)
        self.assertGreaterEqual(bus.price_confidence, 0.9)


if __name__ == "__main__":
    unittest.main()
