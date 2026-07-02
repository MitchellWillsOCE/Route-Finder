import type { RouteLeg } from "@/components/route-timeline";

export type MapPoint = {
  name: string;
  lat: number;
  lon: number;
};

export type MapSegment = {
  mode: string;
  points: [number, number][];
};

const MODE_COLOR: Record<string, string> = {
  train: "#60a5fa",
  bus: "#fbbf24",
  plane: "#22c55e",
  walk: "#9ca3af",
};

export function modeColor(mode: string): string {
  return MODE_COLOR[mode] || "#e5e7eb";
}

export function routeMapData(legs: RouteLeg[]): {
  stops: MapPoint[];
  segments: MapSegment[];
} {
  const stops: MapPoint[] = [];
  const segments: MapSegment[] = [];

  const addStop = (name: string, lat?: number, lon?: number) => {
    if (lat == null || lon == null) return;
    const last = stops[stops.length - 1];
    if (last && last.lat === lat && last.lon === lon) return;
    stops.push({ name, lat, lon });
  };

  for (const leg of legs) {
    const from: [number, number] | null =
      leg.origin_lat != null && leg.origin_lon != null
        ? [leg.origin_lat, leg.origin_lon]
        : null;
    const to: [number, number] | null =
      leg.dest_lat != null && leg.dest_lon != null
        ? [leg.dest_lat, leg.dest_lon]
        : null;

    if (from) addStop(leg.origin, from[0], from[1]);
    if (to) addStop(leg.destination, to[0], to[1]);

    if (from && to && leg.mode !== "walk") {
      segments.push({ mode: leg.mode, points: [from, to] });
    } else if (from && to && leg.mode === "walk") {
      segments.push({ mode: "walk", points: [from, to] });
    }
  }

  return { stops, segments };
}
