from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from route_finder.models import SearchRequest, TransportMode
from route_finder.route_summary import mode_breakdown, route_via_hubs
from route_finder.search import search_routes

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "web" / "templates"
STATIC_DIR = BASE_DIR / "web" / "static"

app = FastAPI(title="Europe Route Finder")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from uuid import uuid4


@dataclass
class JobState:
    status: str  # pending | done | error
    message: str
    created_at: datetime
    query: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


_jobs: dict[str, JobState] = {}
_jobs_lock = Lock()
_pool = ThreadPoolExecutor(max_workers=4)

class _JobProgress:
    def __init__(self, job_id: str) -> None:
        self._job_id = job_id

    def update(self, message: str) -> None:
        with _jobs_lock:
            job = _jobs.get(self._job_id)
            if not job or job.status != "pending":
                return
            job.message = message

    def done(self, message: str, found: int = 0) -> None:
        self.update(message)


def _parse_date(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError("Invalid date. Use YYYY-MM-DD or DD/MM/YYYY.")


def _format_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    hours, mins = divmod(minutes, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h {mins}m"
    return f"{hours}h {mins}m"


def _route_to_view(route, *, origin: str, destination: str) -> dict[str, Any]:
    via = route_via_hubs(route, origin, destination)
    breakdown = mode_breakdown(route)
    by_mode = []
    for mode in (TransportMode.TRAIN, TransportMode.BUS, TransportMode.PLANE):
        item = breakdown.get(mode)
        if not item:
            continue
        by_mode.append(
            {
                "mode": mode.value,
                "duration": _format_duration(item.duration_minutes),
                "cost_eur": round(item.cost_eur, 2),
                "has_cost": item.cost_eur > 0,
            }
        )
    legs = [
        {
            "mode": leg.mode.value,
            "origin": leg.origin,
            "destination": leg.destination,
            "depart": leg.depart.strftime("%a %d %b %H:%M"),
            "arrive": leg.arrive.strftime("%a %d %b %H:%M"),
            "duration": _format_duration(leg.duration_minutes),
            "operator": leg.operator,
            "service_id": leg.service_id,
            "cost_eur": round(leg.cost_eur, 2),
            "booking_url": leg.booking_url,
            "notes": leg.notes,
        }
        for leg in route.legs
    ]
    return {
        "label": route.label,
        "efficiency_score": route.efficiency_score,
        "duration": _format_duration(route.total_duration_minutes),
        "total_cost_eur": round(route.total_cost_eur, 2),
        "cost_is_estimated": bool(route.price_estimated and not route.price_verified),
        "modes": [m.value for m in route.modes_used if m.value != "walk"],
        "via": via,
        "by_mode": by_mode,
        "data_source": route.data_source,
        "legs": legs,
    }

def _run_search(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "pending"
        job.message = "Searching providers..."

    try:
        origin = str(job.query["origin"])
        destination = str(job.query["destination"])
        date_raw = str(job.query["date"])
        flex = int(job.query["flex"])

        with _jobs_lock:
            job = _jobs.get(job_id)
            if job and job.status == "pending":
                job.message = "Checking locations..."

        depart = _parse_date(date_raw)
        req = SearchRequest(
            origin=origin,
            destination=destination,
            ideal_departure=depart,
            flexibility_days=flex,
        )
        progress = _JobProgress(job_id)
        result = search_routes(req, progress=progress)
        view_routes = [
            _route_to_view(r, origin=req.origin, destination=req.destination)
            for r in result.routes
        ]
        payload = {
            "query": {
                "origin": req.origin,
                "destination": req.destination,
                "date": date_raw,
                "flex": flex,
            },
            "routes": view_routes,
            "price_note": result.price_note,
            "searched_sources": result.searched_sources,
        }
        with _jobs_lock:
            job = _jobs.get(job_id)
            if not job:
                return
            job.status = "done"
            job.message = "Done"
            job.result = payload
    except Exception as exc:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if not job:
                return
            job.status = "error"
            job.message = "Search failed"
            job.error = str(exc)


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "defaults": {
                "origin": "Amsterdam",
                "destination": "Naples",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "flex": 2,
            },
        },
    )


@app.post("/search")
def search(
    request: Request,
    origin: str = Form(...),
    destination: str = Form(...),
    date: str = Form(...),
    flex: int = Form(3),
) -> RedirectResponse:
    job_id = uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = JobState(
            status="pending",
            message="Queued...",
            created_at=datetime.now(),
            query={
                "origin": origin.strip() or "Amsterdam",
                "destination": destination.strip() or "Naples",
                "date": date.strip(),
                "flex": int(flex),
            },
        )
    _pool.submit(_run_search, job_id)
    return RedirectResponse(url=f"/results/{job_id}", status_code=303)


@app.get("/api/job/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return {"status": "error", "message": "Unknown job", "error": "Unknown job"}
        return {
            "status": job.status,
            "message": job.message,
            "error": job.error,
        }

@app.get("/api/search")
def api_search(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    date: str | None = None,
    flex: int = 2,
) -> dict[str, Any]:  # noqa: A002
    """
    Minimal API for the shadcn/Next UI.
    Returns only the core route fields (no data notes).
    """
    date_raw = date or datetime.now().strftime("%Y-%m-%d")
    depart = _parse_date(date_raw)
    req = SearchRequest(
        origin=from_,
        destination=to,
        ideal_departure=depart,
        flexibility_days=int(flex),
    )
    result = search_routes(req)
    routes = [
        {
            "label": r.label,
            "duration": _format_duration(r.total_duration_minutes),
            "total_cost_eur": round(r.total_cost_eur, 2),
            "cost_is_estimated": bool(r.price_estimated and not r.price_verified),
            "via": route_via_hubs(r, req.origin, req.destination),
            "by_mode": [
                {
                    "mode": m["mode"],
                    "duration": m["duration"],
                    "cost_eur": m["cost_eur"],
                    "has_cost": m["has_cost"],
                }
                for m in _route_to_view(r, origin=req.origin, destination=req.destination)[
                    "by_mode"
                ]
            ],
        }
        for r in result.routes
    ]
    return {"routes": routes}


@app.get("/results", response_class=HTMLResponse)
def results_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(url="/", status_code=303)


@app.get("/results/{job_id}", response_class=HTMLResponse)
def results_job(request: Request, job_id: str) -> HTMLResponse:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return templates.TemplateResponse(
                request,
                "results.html",
                {
                    "request": request,
                    "query": {"origin": "", "destination": "", "date": "", "flex": 0},
                    "routes": [],
                    "price_note": "",
                    "searched_sources": [],
                    "error": "Unknown search job. Please start a new search.",
                    "loading": False,
                    "job_id": job_id,
                },
            )
        if job.status != "done":
            return templates.TemplateResponse(
                request,
                "results.html",
                {
                    "request": request,
                    "query": job.query,
                    "routes": [],
                    "price_note": "",
                    "searched_sources": [],
                    "error": job.error,
                    "loading": True,
                    "job_id": job_id,
                },
            )
        assert job.result is not None
        payload = job.result

    return templates.TemplateResponse(
        request,
        "results.html",
        {
            "request": request,
            "query": payload["query"],
            "routes": payload["routes"],
            "price_note": payload["price_note"],
            "searched_sources": payload["searched_sources"],
            "error": None,
            "loading": False,
            "job_id": job_id,
        },
    )

