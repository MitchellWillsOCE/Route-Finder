from __future__ import annotations

from route_finder.connections import count_transfers
from route_finder.models import RouteOption
from route_finder.pricing import apply_route_pricing_meta, departure_day_penalty

# Scoring exponents: time is weighted more heavily than cost so a route that
# is ~2x faster is not beaten solely for being ~1.5x more expensive.
_TIME_EXPONENT = 0.68
_COST_EXPONENT = 0.22


def _is_impractical_walk(route: RouteOption) -> bool:
    return (
        len(route.legs) == 1
        and route.legs[0].mode.value == "walk"
        and "impractical" in (route.legs[0].notes or "").lower()
    )


def assign_labels(routes: list[RouteOption]) -> None:
    if not routes:
        return

    practical = [r for r in routes if not _is_impractical_walk(r)]
    pool = practical or routes

    fastest = min(pool, key=lambda r: r.total_duration_minutes)
    cheapest = min(
        (r for r in pool if r.price_verified or r.price_estimated),
        key=lambda r: r.total_cost_eur,
        default=min(pool, key=lambda r: r.total_cost_eur),
    )
    best = max(practical or routes, key=lambda r: r.efficiency_score)

    for route in routes:
        if route is best:
            route.label = "Best balance"
        elif route is fastest:
            route.label = "Fastest"
        elif route is cheapest:
            route.label = "Cheapest"
        elif not route.label:
            route.label = "Alternative"


def score_routes(
    routes: list[RouteOption],
    *,
    ideal_departure=None,
) -> list[RouteOption]:
    if not routes:
        return routes

    positive_costs = [
        r.total_cost_eur
        for r in routes
        if (r.price_verified or r.price_estimated) and r.total_cost_eur > 0
    ]
    min_cost = min(positive_costs) if positive_costs else 1.0
    min_duration = min(r.total_duration_minutes for r in routes)
    ideal = ideal_departure or routes[0].legs[0].depart

    for route in routes:
        apply_route_pricing_meta(route)

        if _is_impractical_walk(route):
            route.efficiency_score = 0.0
            continue

        time_factor = min_duration / max(route.total_duration_minutes, 1)
        if not route.price_verified and not route.price_estimated:
            cost_factor = 0.7
        elif route.total_cost_eur <= 0:
            cost_factor = 0.7
        else:
            cost_factor = min_cost / route.total_cost_eur

        # Mild boost when a route is dramatically faster (e.g. 5h train vs 10h bus).
        duration_ratio = min_duration / max(route.total_duration_minutes, 1)
        if duration_ratio >= 0.99:
            speed_bonus = 1.0
        elif duration_ratio >= 0.55:
            speed_bonus = 1.0 + 0.12 * (duration_ratio - 0.55) / 0.44
        else:
            speed_bonus = 0.92

        confidence_weight = 0.55 + 0.45 * route.price_confidence
        transfer_factor = 0.93 ** count_transfers(route)
        date_factor = departure_day_penalty(route, ideal)

        route.efficiency_score = round(
            100
            * (time_factor**_TIME_EXPONENT)
            * (cost_factor**_COST_EXPONENT)
            * confidence_weight
            * transfer_factor
            * date_factor
            * speed_bonus,
            1,
        )

    ranked = sorted(routes, key=lambda r: r.efficiency_score, reverse=True)
    return ranked


def diversify_ranked_routes(
    ranked: list[RouteOption],
    *,
    limit: int = 8,
) -> list[RouteOption]:
    """Keep top routes while ensuring bus, train, and flight each appear when available."""
    if not ranked:
        return ranked

    from collections import defaultdict

    from route_finder.route_summary import route_category

    caps = {
        "flight": 3,
        "train": 2,
        "bus": 2,
        "intermodal": 2,
        "walk": 1,
        "other": 2,
    }
    picked: list[RouteOption] = []
    picked_ids: set[int] = set()
    counts: dict[str, int] = defaultdict(int)

    def can_take(route: RouteOption) -> bool:
        return counts[route_category(route)] < caps.get(route_category(route), 2)

    def take(route: RouteOption) -> None:
        if id(route) in picked_ids or len(picked) >= limit or not can_take(route):
            return
        picked.append(route)
        picked_ids.add(id(route))
        counts[route_category(route)] += 1

    by_category: dict[str, list[RouteOption]] = {}
    for route in ranked:
        by_category.setdefault(route_category(route), []).append(route)

    for category in ("flight", "train", "bus", "intermodal"):
        pool = by_category.get(category, [])
        if pool:
            take(max(pool, key=lambda r: r.efficiency_score))

    for route in ranked:
        take(route)

    picked.sort(key=lambda r: r.efficiency_score, reverse=True)
    assign_labels(picked)
    return picked[:limit]
