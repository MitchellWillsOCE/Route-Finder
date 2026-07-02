from __future__ import annotations

from urllib.parse import urlparse

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from route_finder.models import RouteOption, SearchResult, TransportMode
from route_finder.route_summary import mode_breakdown, route_via_hubs

console = Console()

MODE_ICONS = {
    TransportMode.WALK: "[walk]",
    TransportMode.BUS: "[bus]",
    TransportMode.TRAIN: "[train]",
    TransportMode.PLANE: "[plane]",
}

# Short station walks are shown as thin connectors, not full legs.
_WALK_CONNECTOR_MAX_MIN = 15


def _format_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    hours, mins = divmod(minutes, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h {mins}m"
    return f"{hours}h {mins}m"


def _format_modes(route: RouteOption) -> str:
    return " -> ".join(f"{MODE_ICONS[m]} {m.value}" for m in route.modes_used)


def _format_modes_compact(route: RouteOption) -> str:
    """Summary modes without cluttering short station walks."""
    main_modes = [m for m in route.modes_used if m != TransportMode.WALK]
    if not main_modes:
        return f"{MODE_ICONS[TransportMode.WALK]} walk"
    label = " -> ".join(f"{MODE_ICONS[m]} {m.value}" for m in main_modes)
    has_station_walk = any(
        leg.mode == TransportMode.WALK and leg.duration_minutes <= _WALK_CONNECTOR_MAX_MIN
        for leg in route.legs
    )
    if has_station_walk:
        label += " [dim](+ station access)[/dim]"
    return label


def _short_place(name: str) -> str:
    text = name.strip()
    if "(" in text:
        text = text.split("(")[0].strip()
    if "," in text:
        text = text.split(",")[0].strip()
    return text


def _format_stop(label: str, place: str, when: str) -> str:
    return f"  {label:<7} [bold]{_short_place(place)}[/bold]  [dim]{when}[/dim]"


def _format_leg_connector(route: RouteOption, leg) -> list[str]:
    lines: list[str] = []
    if leg.mode == TransportMode.WALK:
        if leg.duration_minutes <= _WALK_CONNECTOR_MAX_MIN:
            lines.append(
                f"          [dim]|  walk {_format_duration(leg.duration_minutes)}[/dim]"
            )
        else:
            lines.append(
                f"          {MODE_ICONS[leg.mode]}  [bold]walk[/bold]  -  "
                f"{_format_duration(leg.duration_minutes)}"
            )
        return lines

    icon = MODE_ICONS[leg.mode]
    details = [_format_duration(leg.duration_minutes)]
    if leg.operator and leg.operator.lower() not in ("n/a", "-"):
        details.append(leg.operator)
    if leg.service_id:
        details.append(leg.service_id)
    details.append(_format_leg_cost(route, leg.cost_eur, leg.mode))
    lines.append(
        f"          {icon}  [bold]{leg.mode.value}[/bold]  -  {' - '.join(details)}"
    )
    if leg.notes:
        lines.append(f"          [dim]   {leg.notes}[/dim]")
    if leg.booking_url:
        label = _short_booking_label(leg.booking_url, leg.operator)
        if leg.mode in (TransportMode.TRAIN, TransportMode.BUS):
            lines.append(
                f"          [dim]   [/dim]Check fare: [link={leg.booking_url}]{label}[/link]"
            )
        else:
            lines.append(
                f"          [dim]   [/dim]Book: [link={leg.booking_url}]{label}[/link]"
            )
    return lines


def _format_timeline(route: RouteOption) -> list[str]:
    if not route.legs:
        return []

    lines: list[str] = []
    first = route.legs[0]
    lines.append(_format_stop("Depart", first.origin, _format_datetime(first.depart)))

    for index, leg in enumerate(route.legs):
        lines.extend(_format_leg_connector(route, leg))
        is_last = index == len(route.legs) - 1
        if is_last:
            lines.append(
                _format_stop("Arrive", leg.destination, _format_datetime(leg.arrive))
            )
        else:
            lines.append(
                f"        > [bold]{_short_place(leg.destination)}[/bold]  "
                f"[dim]{_format_datetime(leg.arrive)}[/dim]"
            )

    return lines


def _format_datetime(dt) -> str:
    return dt.strftime("%a %d %b, %H:%M")


def _format_leg_header(leg) -> str:
    icon = MODE_ICONS[leg.mode]
    header = f"{icon} [bold]{leg.mode.value.upper()}[/bold] | {leg.operator}"
    if leg.service_id:
        header += f" | {leg.service_id}"
    return header


_DOMAIN_LABELS = {
    "int.bahn.de": "Deutsche Bahn",
    "thetrainline.com": "Deutsche Bahn",
    "bahn.de": "Deutsche Bahn",
    "shop.flixbus.com": "FlixBus",
    "global.flixbus.com": "FlixBus",
    "google.com": "Google Maps",
    "skyscanner.net": "Skyscanner",
    "ryanair.com": "Ryanair",
    "omio.com": "Omio",
}


def _short_booking_label(url: str, operator: str) -> str:
    domain = urlparse(url).netloc.removeprefix("www.")
    if domain in _DOMAIN_LABELS:
        return _DOMAIN_LABELS[domain]
    if operator and operator not in ("n/a", "-"):
        short_ops = operator.split(" / ")[0].strip()
        if len(short_ops) <= 24:
            return short_ops
    return domain


def print_header() -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]Europe Route Finder[/bold cyan]\n"
            "[dim]Compare time vs cost across bus, train, plane & walk[/dim]",
            border_style="cyan",
        )
    )
    console.print()


def _format_cost(route: RouteOption) -> str:
    total = route.total_cost_eur
    if total <= 0:
        if any(
            leg.mode in (TransportMode.TRAIN, TransportMode.BUS) for leg in route.legs
        ):
            return "Check Omio for fare"
        return "Free"
    if route.price_estimated and not route.price_verified:
        return f"~EUR {total:.2f} (est.)"
    if route.price_estimated and route.price_verified:
        return f"~EUR {total:.2f} (part est.)"
    if not route.price_verified:
        return f"~EUR {total:.2f} (est.)"
    return f"EUR {total:.2f}"


def _format_leg_cost(route: RouteOption, leg_cost: float, leg_mode: TransportMode) -> str:
    if leg_mode == TransportMode.WALK:
        return "Free"
    if route.price_estimated and leg_cost > 0:
        return f"~EUR {leg_cost:.2f} (estimated)"
    if leg_cost > 0 and route.price_verified:
        return f"EUR {leg_cost:.2f}"
    if leg_mode in (TransportMode.TRAIN, TransportMode.BUS):
        return "Check Omio for live fare"
    if leg_cost == 0:
        return "Free"
    return f"EUR {leg_cost:.2f}"


def _format_via_hubs(route: RouteOption, origin: str, destination: str) -> str:
    hubs = route_via_hubs(route, origin, destination)
    if not hubs:
        return "-"
    return " -> ".join(hubs)


def _format_mode_breakdown(route: RouteOption) -> str:
    parts: list[str] = []
    breakdown = mode_breakdown(route)
    for mode in (
        TransportMode.TRAIN,
        TransportMode.BUS,
        TransportMode.PLANE,
    ):
        summary = breakdown.get(mode)
        if not summary:
            continue
        icon = MODE_ICONS[mode]
        time_str = _format_duration(summary.duration_minutes)
        if summary.cost_eur > 0:
            if route.price_estimated and not route.price_verified:
                cost_str = f"~EUR {summary.cost_eur:.0f}"
            elif route.price_estimated:
                cost_str = f"~EUR {summary.cost_eur:.0f}"
            else:
                cost_str = f"EUR {summary.cost_eur:.0f}"
        elif mode in (TransportMode.TRAIN, TransportMode.BUS):
            cost_str = "fare TBC"
        else:
            cost_str = "EUR 0"
        parts.append(f"{icon} {time_str} {cost_str}")
    return " · ".join(parts) if parts else "-"


def print_summary_table(result: SearchResult) -> None:
    table = Table(
        title="Route comparison (ranked by efficiency)",
        show_lines=True,
        header_style="bold",
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Label", min_width=12)
    table.add_column("Modes", min_width=14)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Total cost", justify="right", min_width=12)
    table.add_column("By mode (time / cost)", min_width=28)
    table.add_column("Via hubs", min_width=16)
    table.add_column("Score", justify="right", style="bold green", width=7)

    req = result.request
    for i, route in enumerate(result.routes, 1):
        table.add_row(
            str(i),
            route.label,
            _format_modes_compact(route),
            _format_duration(route.total_duration_minutes),
            _format_cost(route),
            _format_mode_breakdown(route),
            _format_via_hubs(route, req.origin, req.destination),
            f"{route.efficiency_score:.0f}",
        )

    console.print(table)
    console.print()


def print_detailed_itineraries(result: SearchResult, top_n: int = 3) -> None:
    req = result.request
    console.print(
        Panel(
            f"[bold]{req.origin}[/bold] -> [bold]{req.destination}[/bold]\n"
            f"Ideal departure: [cyan]{req.ideal_departure.strftime('%a %d %b %Y')}[/cyan] "
            f"(+/-{req.flexibility_days} days)\n"
            f"[dim]{result.price_note}[/dim]",
            title="Search",
            border_style="blue",
        )
    )
    console.print()

    for i, route in enumerate(result.routes[:top_n], 1):
        lines: list[str] = []
        lines.append(
            f"[bold]#{i} - {route.label}[/bold]  "
            f"[green]Score {route.efficiency_score:.0f}/100[/green]  "
            f"[dim]({route.data_source})[/dim]"
        )
        lines.append(
            f"Total: {_format_duration(route.total_duration_minutes)} | "
            f"{_format_cost(route)} | {_format_modes_compact(route)}"
        )
        via = _format_via_hubs(route, req.origin, req.destination)
        if via != "-":
            lines.append(f"Via: [cyan]{via}[/cyan]")
        breakdown = _format_mode_breakdown(route)
        if breakdown != "-":
            lines.append(f"By mode: {breakdown}")
        lines.append(f"[dim]{route.data_source}[/dim]")
        lines.append("")
        lines.extend(_format_timeline(route))

        console.print(Panel("\n".join(lines).rstrip(), border_style="green" if i == 1 else "dim"))
        console.print()

    if len(result.routes) > top_n:
        console.print(
            f"[dim]Showing top {top_n} of {len(result.routes)} routes. "
            "Use --all to see every option.[/dim]\n"
        )


def print_sources(result: SearchResult) -> None:
    sources = "\n".join(f"  - {s}" for s in result.searched_sources)
    console.print(Panel(sources, title="Data sources queried", border_style="dim"))
    console.print()


def print_efficiency_legend() -> None:
    legend = Text()
    legend.append("Efficiency score ", style="bold")
    legend.append(
        "balances journey time and total cost (0-100, higher is better). "
        "Weights favour routes that are neither extremely slow nor expensive."
    )
    console.print(Panel(legend, title="How scoring works", border_style="dim"))
    console.print()
