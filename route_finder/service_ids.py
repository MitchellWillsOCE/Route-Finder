from __future__ import annotations


def motis_service_id(leg_data: dict) -> str:
    display = (leg_data.get("displayName") or "").strip()
    route_short = (leg_data.get("routeShortName") or "").strip()
    trip_short = (leg_data.get("tripShortName") or "").strip()

    if display:
        if trip_short and trip_short not in display:
            return f"{display} {trip_short}"
        return display
    if route_short and trip_short and trip_short not in route_short:
        return f"{route_short} {trip_short}"
    return route_short or trip_short


def hafas_service_id(leg_data: dict) -> str:
    line = leg_data.get("line") or {}
    name = (line.get("name") or "").strip()
    if name:
        return name

    product = (line.get("productName") or line.get("product") or "").strip()
    fahrt_nr = str(line.get("fahrtNr") or "").strip()
    if product and fahrt_nr:
        return f"{product} {fahrt_nr}"
    return product or fahrt_nr


def navitia_service_id(section: dict) -> str:
    info = section.get("display_informations") or {}
    code = (info.get("code") or "").strip()
    trip = (info.get("trip_short_name") or "").strip()
    headsign = (info.get("headsign") or "").strip()

    if code and trip:
        return f"{code} {trip}"
    if code and headsign:
        return f"{code} {headsign}"
    return code or trip or headsign
