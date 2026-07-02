from __future__ import annotations

import argparse
import sys
from datetime import datetime

from rich.console import Console
from rich.prompt import Confirm, Prompt

from route_finder.display import (
    print_detailed_itineraries,
    print_efficiency_legend,
    print_header,
    print_sources,
    print_summary_table,
)
from route_finder.models import SearchRequest
from route_finder.places import LocationValidationError
from route_finder.search import search_routes

console = Console()


class InlineStatusProgress:
    def __init__(self, status) -> None:
        self._status = status

    def update(self, message: str) -> None:
        self._status.update(f"[cyan]{message}[/cyan]")

    def done(self, message: str, found: int = 0) -> None:
        pass


def _parse_date(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"Invalid date '{value}'. Use YYYY-MM-DD or DD/MM/YYYY."
    )


def _print_location_error(exc: LocationValidationError) -> None:
    console.print(f"[red]Location error:[/red] {exc.message}")
    if exc.suggestions:
        console.print("[yellow]Suggestions:[/yellow] " + ", ".join(exc.suggestions))


def _prompt_location(label: str, default: str) -> str:
    while True:
        value = Prompt.ask(label, default=default)
        if value.strip():
            return value.strip()
        console.print("[red]Please enter a location.[/red]")


def _prompt_interactive() -> SearchRequest | None:
    print_header()
    console.print("[bold]Enter your trip details[/bold] (press Enter for examples)\n")

    while True:
        origin = _prompt_location("Start location", "Paris")
        destination = _prompt_location("Destination", "Amsterdam")
        date_str = Prompt.ask(
            "Ideal departure date",
            default=(datetime.now().replace(day=15)).strftime("%Y-%m-%d"),
        )
        flexibility = Prompt.ask("Date flexibility (days either side)", default="3")

        try:
            ideal = _parse_date(date_str)
            flex = int(flexibility)
        except (argparse.ArgumentTypeError, ValueError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            continue

        request = SearchRequest(
            origin=origin,
            destination=destination,
            ideal_departure=ideal,
            flexibility_days=flex,
        )

        try:
            with console.status("[cyan]Checking locations...[/cyan]", spinner="dots"):
                from route_finder.places import validate_trip_locations
                import httpx
                from route_finder.config import CONFIG

                with httpx.Client(timeout=CONFIG.request_timeout) as client:
                    start, end, note = validate_trip_locations(
                        request.origin, request.destination, client
                    )
            request.origin = start.name
            request.destination = end.name
            if note:
                console.print(f"[dim]{note}[/dim]")
            if start.spelling_corrected or end.spelling_corrected:
                console.print(
                    f"[dim]Using: {start.name} -> {end.name}[/dim]\n"
                )
            return request
        except LocationValidationError as exc:
            _print_location_error(exc)
            if not Confirm.ask("Try different locations?", default=True):
                return None
            console.print()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find efficient European routes by time vs cost.",
    )
    parser.add_argument("--from", dest="origin", help="Start location (city or station)")
    parser.add_argument("--to", dest="destination", help="Destination")
    parser.add_argument(
        "--date",
        type=_parse_date,
        help="Ideal departure date (YYYY-MM-DD or DD/MM/YYYY)",
    )
    parser.add_argument(
        "--flex",
        type=int,
        default=3,
        help="Days of flexibility either side of ideal date (default: 3)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show detailed itineraries for all routes, not just top 3",
    )
    parser.add_argument(
        "--no-legend",
        action="store_true",
        help="Hide efficiency scoring explanation",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force mock data instead of live providers",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Run interactive prompts (default if no --from/--to given)",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    interactive = args.interactive or (not args.origin and not args.destination)

    if interactive:
        request = _prompt_interactive()
        if request is None:
            return 1
    else:
        if not args.origin or not args.destination or not args.date:
            parser.error("--from, --to, and --date are required in non-interactive mode")
        request = SearchRequest(
            origin=args.origin,
            destination=args.destination,
            ideal_departure=args.date,
            flexibility_days=args.flex,
        )
        print_header()

    try:
        with console.status("[cyan]Searching...[/cyan]", spinner="dots") as status:
            if args.mock:
                from route_finder.mock_data import generate_mock_routes

                result = generate_mock_routes(request)
            else:
                progress = InlineStatusProgress(status)
                result = search_routes(request, progress=progress)
    except LocationValidationError as exc:
        _print_location_error(exc)
        return 1

    console.print("[green]Done.[/green] Search complete.\n")

    print_summary_table(result)

    top_n = len(result.routes) if args.all else 3
    print_detailed_itineraries(result, top_n=top_n)
    print_sources(result)

    if not args.no_legend:
        print_efficiency_legend()

    if interactive and Confirm.ask("Run another search?", default=False):
        return run([])

    return 0


def main() -> None:
    raise SystemExit(run())
