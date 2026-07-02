import { Bus, Footprints, Plane, Train } from "lucide-react";

export type RouteLeg = {
  mode: string;
  origin: string;
  destination: string;
  depart: string;
  arrive: string;
  duration: string;
  operator?: string;
  service_id?: string;
  cost_eur: number;
  booking_url?: string;
  notes?: string;
  origin_lat?: number;
  origin_lon?: number;
  dest_lat?: number;
  dest_lon?: number;
};

const WALK_CONNECTOR_MAX_MIN = 15;

function shortPlace(name: string): string {
  let text = name.trim();
  if (text.includes("(")) text = text.split("(")[0].trim();
  if (text.includes(",")) text = text.split(",")[0].trim();
  return text;
}

function durationToMinutes(duration: string): number {
  let total = 0;
  const dayMatch = duration.match(/(\d+)d/);
  const hourMatch = duration.match(/(\d+)h/);
  const minMatch = duration.match(/(\d+)m/);
  if (dayMatch) total += Number(dayMatch[1]) * 24 * 60;
  if (hourMatch) total += Number(hourMatch[1]) * 60;
  if (minMatch) total += Number(minMatch[1]);
  return total;
}

function ModeIcon({ mode }: { mode: string }) {
  const className = "h-3.5 w-3.5 shrink-0";
  switch (mode) {
    case "train":
      return <Train className={className} />;
    case "bus":
      return <Bus className={className} />;
    case "plane":
      return <Plane className={className} />;
    default:
      return <Footprints className={className} />;
  }
}

function bookingLabel(url: string): string {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    const map: Record<string, string> = {
      "skyscanner.net": "Skyscanner",
      "shop.flixbus.com": "FlixBus",
      "global.flixbus.com": "FlixBus",
      "int.bahn.de": "Deutsche Bahn",
      "bahn.de": "Deutsche Bahn",
      "ns.nl": "NS",
      "omio.com": "Omio",
      "ryanair.com": "Ryanair",
    };
    return map[host] || host;
  } catch {
    return "Book";
  }
}

function formatLegCost(cost: number, mode: string): string {
  if (cost > 0) return `EUR ${cost.toFixed(2)}`;
  if (mode === "walk") return "";
  return "fare TBC";
}

export function RouteTimeline({ legs }: { legs: RouteLeg[] }) {
  if (!legs.length) return null;

  const first = legs[0];

  return (
    <div className="mt-2 border-t border-border/60 pt-2">
      <div className="relative pl-4">
        <div className="absolute bottom-1 left-[5px] top-1 w-px bg-border" />

        <div className="relative pb-1.5">
          <div className="absolute -left-4 top-1.5 h-2 w-2 rounded-full bg-foreground" />
          <div className="flex flex-wrap items-baseline gap-x-2 text-xs">
            <span className="w-12 shrink-0 font-medium text-muted">Depart</span>
            <span className="font-medium">{shortPlace(first.origin)}</span>
            <span className="text-muted">{first.depart}</span>
          </div>
        </div>

        {legs.map((leg, index) => {
          const isLast = index === legs.length - 1;
          const isShortWalk =
            leg.mode === "walk" && durationToMinutes(leg.duration) <= WALK_CONNECTOR_MAX_MIN;

          return (
            <div key={index}>
              {isShortWalk ? (
                <div className="relative py-0.5 pl-1 text-xs text-muted">
                  <span className="pl-2">| walk {leg.duration}</span>
                </div>
              ) : (
                <div className="relative py-1">
                  <div className="absolute -left-4 top-2.5 h-2 w-2 rounded-full border border-border bg-card" />
                  <div className="flex items-start gap-2 text-xs">
                    <ModeIcon mode={leg.mode} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-x-1.5">
                        <span className="font-medium capitalize">{leg.mode}</span>
                        <span className="text-muted">·</span>
                        <span>{leg.duration}</span>
                        {leg.operator && leg.operator.toLowerCase() !== "n/a" ? (
                          <>
                            <span className="text-muted">·</span>
                            <span className="text-muted">{leg.operator}</span>
                          </>
                        ) : null}
                        {leg.service_id ? (
                          <>
                            <span className="text-muted">·</span>
                            <span className="text-muted">{leg.service_id}</span>
                          </>
                        ) : null}
                        {formatLegCost(leg.cost_eur, leg.mode) ? (
                          <>
                            <span className="text-muted">·</span>
                            <span>{formatLegCost(leg.cost_eur, leg.mode)}</span>
                          </>
                        ) : null}
                      </div>
                      {leg.notes ? (
                        <div className="mt-0.5 text-muted">{leg.notes}</div>
                      ) : null}
                      {leg.booking_url && leg.mode !== "walk" ? (
                        <a
                          href={leg.booking_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-1 inline-block rounded border border-border bg-background px-2 py-0.5 text-[11px] font-medium text-foreground hover:bg-card"
                        >
                          {leg.mode === "plane" ? "Book" : "Check fare"} on{" "}
                          {bookingLabel(leg.booking_url)}
                        </a>
                      ) : null}
                    </div>
                  </div>
                </div>
              )}

              {isLast ? (
                <div className="relative pb-0.5 pt-1">
                  <div className="absolute -left-4 top-2 h-2 w-2 rounded-full bg-accent" />
                  <div className="flex flex-wrap items-baseline gap-x-2 text-xs">
                    <span className="w-12 shrink-0 font-medium text-muted">Arrive</span>
                    <span className="font-medium">{shortPlace(leg.destination)}</span>
                    <span className="text-muted">{leg.arrive}</span>
                  </div>
                </div>
              ) : (
                <div className="relative py-0.5">
                  <div className="absolute -left-4 top-1.5 h-1.5 w-1.5 rounded-full bg-muted" />
                  <div className="flex flex-wrap items-baseline gap-x-2 pl-0 text-xs">
                    <span className="font-medium">{shortPlace(leg.destination)}</span>
                    <span className="text-muted">{leg.arrive}</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
