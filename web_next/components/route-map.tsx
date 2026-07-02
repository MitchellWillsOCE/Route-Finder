"use client";

import { useEffect } from "react";
import L from "leaflet";
import { MapContainer, Marker, Polyline, TileLayer, useMap } from "react-leaflet";

import type { RouteLeg } from "@/components/route-timeline";
import { modeColor, routeMapData } from "@/lib/route-geo";

import "leaflet/dist/leaflet.css";

const icon = L.divIcon({
  className: "",
  html: `<span style="display:block;width:10px;height:10px;border-radius:9999px;background:#f4f6fb;border:2px solid #0b0c10;box-shadow:0 0 0 2px #22c55e"></span>`,
  iconSize: [10, 10],
  iconAnchor: [5, 5],
});

const endpointIcon = L.divIcon({
  className: "",
  html: `<span style="display:block;width:12px;height:12px;border-radius:9999px;background:#22c55e;border:2px solid #f4f6fb"></span>`,
  iconSize: [12, 12],
  iconAnchor: [6, 6],
});

function FitBounds({ legs }: { legs: RouteLeg[] }) {
  const map = useMap();
  const { stops } = routeMapData(legs);

  useEffect(() => {
    if (stops.length < 2) {
      if (stops.length === 1) map.setView([stops[0].lat, stops[0].lon], 8);
      return;
    }
    const bounds = L.latLngBounds(stops.map((s) => [s.lat, s.lon]));
    map.fitBounds(bounds, { padding: [36, 36], maxZoom: 8 });
  }, [legs, map, stops]);

  return null;
}

type Props = {
  legs: RouteLeg[];
  className?: string;
};

export function RouteMap({ legs, className }: Props) {
  const { stops, segments } = routeMapData(legs);

  if (!stops.length) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg border border-border bg-card text-sm text-muted ${className || ""}`}
      >
        Map unavailable for this route
      </div>
    );
  }

  const center: [number, number] = [stops[0].lat, stops[0].lon];

  return (
    <div className={`overflow-hidden rounded-lg border border-border ${className || ""}`}>
      <MapContainer
        center={center}
        zoom={5}
        scrollWheelZoom={false}
        className="h-full w-full min-h-[220px] bg-background"
        style={{ background: "#0b0c10" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        <FitBounds legs={legs} />
        {segments.map((seg, i) => (
          <Polyline
            key={i}
            positions={seg.points}
            pathOptions={{
              color: modeColor(seg.mode),
              weight: seg.mode === "walk" ? 2 : 4,
              opacity: seg.mode === "walk" ? 0.45 : 0.9,
              dashArray: seg.mode === "walk" ? "4 8" : undefined,
            }}
          />
        ))}
        {stops.map((stop, i) => (
          <Marker
            key={`${stop.name}-${i}`}
            position={[stop.lat, stop.lon]}
            icon={i === 0 || i === stops.length - 1 ? endpointIcon : icon}
          >
            {/* Popup for touch users */}
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
