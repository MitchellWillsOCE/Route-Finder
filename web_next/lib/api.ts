export function apiBase(): string {
  const explicit = process.env.NEXT_PUBLIC_ROUTE_FINDER_API?.replace(/\/$/, "");
  if (explicit) return explicit;

  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host !== "localhost" && host !== "127.0.0.1") {
      return "";
    }
  }

  return "http://127.0.0.1:8001";
}

export type PlaceSuggestion = {
  name: string;
  lat: number;
  lon: number;
};

const FALLBACK_CITIES = [
  "Amsterdam", "Athens", "Barcelona", "Berlin", "Birmingham", "Bologna", "Brussels",
  "Budapest", "Copenhagen", "Dublin", "Florence", "Frankfurt", "Geneva", "Hamburg",
  "Krakow", "Lisbon", "London", "Lyon", "Madrid", "Manchester", "Milan", "Munich",
  "Naples", "Nice", "Oslo", "Paris", "Porto", "Prague", "Rome", "Rotterdam",
  "Stockholm", "Vienna", "Venice", "Warsaw", "Zurich", "Antwerp", "Bruges",
  "Cologne", "Edinburgh", "Glasgow", "Marseille", "Seville", "Valencia", "Verona",
];

export async function fetchPlaces(query: string): Promise<PlaceSuggestion[]> {
  const q = query.trim();

  if (!q) {
    return FALLBACK_CITIES.slice(0, 8).map((name) => ({ name, lat: 0, lon: 0 }));
  }

  try {
    const res = await fetch(
      `${apiBase()}/api/places?q=${encodeURIComponent(q)}&limit=8`,
      { cache: "no-store" },
    );
    if (res.ok) {
      const data = (await res.json()) as { places: PlaceSuggestion[] };
      if (data.places?.length) return data.places;
    }
  } catch {
    // fall through to local list
  }

  const lower = q.toLowerCase();
  return FALLBACK_CITIES.filter((c) => c.toLowerCase().includes(lower))
    .slice(0, 8)
    .map((name) => ({ name, lat: 0, lon: 0 }));
}
