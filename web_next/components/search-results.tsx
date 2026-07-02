"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { RouteMap } from "@/components/route-map-dynamic";
import { RouteTimeline, type RouteLeg } from "@/components/route-timeline";
import { SearchForm } from "@/components/search-form";
import { Button } from "@/components/ui/button";
import { apiBase } from "@/lib/api";
import { cn } from "@/lib/utils";

type Route = {
  label: string;
  duration: string;
  total_cost_eur: number;
  cost_is_estimated: boolean;
  via: string[];
  stopovers?: { city: string; reason: string }[];
  by_mode: { mode: string; duration: string; cost_eur: number; has_cost: boolean }[];
  booking_links?: { label: string; url: string; mode: string }[];
  legs?: RouteLeg[];
};

type Props = {
  from: string;
  to: string;
  date: string;
  flex: string;
};

export function SearchResults({ from, to, date, flex }: Props) {
  const [routes, setRoutes] = useState<Route[] | null>(null);
  const [selected, setSelected] = useState(0);
  const [status, setStatus] = useState("Searching routes...");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      setRoutes(null);
      setError(null);
      setStatus("Searching routes...");
      setSelected(0);

      try {
        const params = new URLSearchParams({ from, to, flex });
        if (date) params.set("date", date);

        const res = await fetch(`${apiBase()}/api/search?${params.toString()}`, {
          cache: "no-store",
        });
        const data = (await res.json()) as { routes?: Route[]; error?: string };
        if (!res.ok) {
          throw new Error(data.error || "Search failed");
        }
        if (!cancelled) {
          setRoutes(data.routes || []);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Search failed");
        }
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [from, to, date, flex]);

  const active = routes?.[selected];
  const activeLegs = active?.legs || [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-3 rounded-lg border border-border bg-card p-3 lg:hidden">
        <SearchForm
          compact
          initialFrom={from}
          initialTo={to}
          initialDate={date}
          initialFlex={flex}
        />
      </div>

      {error ? (
        <div className="rounded-lg border border-border bg-card p-4 text-sm">
          <p className="text-foreground">{error}</p>
          <Link href="/" className="mt-3 inline-block">
            <Button type="button">New search</Button>
          </Link>
        </div>
      ) : null}

      {!error && !routes ? (
        <div className="rounded-lg border border-border bg-card p-6 text-center text-sm text-muted">
          <div className="mx-auto mb-3 h-5 w-5 animate-pulse rounded-full bg-muted/40" />
          {status}
        </div>
      ) : null}

      {!error && routes && !routes.length ? (
        <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted">
          No routes found.
        </div>
      ) : null}

      {!error && routes && routes.length > 0 ? (
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
          <div className="sticky top-0 z-20 h-[36vh] min-h-[200px] shrink-0 lg:sticky lg:top-4 lg:h-[calc(100vh-8rem)] lg:w-[42%] lg:min-h-[420px]">
            <RouteMap legs={activeLegs} className="h-full shadow-lg" />
            {active ? (
              <div className="mt-2 rounded-md border border-border bg-card/90 px-3 py-2 text-xs backdrop-blur sm:text-sm">
                <span className="font-semibold">{active.label}</span>
                <span className="mx-1.5 text-muted">·</span>
                <span>{active.duration}</span>
                {active.total_cost_eur > 0 ? (
                  <>
                    <span className="mx-1.5 text-muted">·</span>
                    <span>
                      {active.cost_is_estimated ? "~" : ""}EUR {active.total_cost_eur.toFixed(2)}
                    </span>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="min-w-0 flex-1 space-y-2 pb-4">
            <p className="text-xs text-muted lg:hidden">Tap a route to view on map</p>
            {routes.map((r, idx) => {
              const isActive = idx === selected;
              return (
                <article
                  key={idx}
                  className={cn(
                    "rounded-lg border px-3 py-2.5 transition-colors sm:px-4",
                    isActive
                      ? "border-accent bg-card ring-1 ring-accent/40"
                      : "border-border bg-card hover:border-foreground/20",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => setSelected(idx)}
                    className="flex w-full items-start justify-between gap-2 text-left"
                  >
                    <div className="min-w-0 flex-1">
                      <h2 className="text-sm font-semibold leading-snug">{r.label}</h2>
                      {r.via?.length ? (
                        <p className="mt-0.5 text-xs text-muted">
                          Via {r.via.join(" → ")}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-1 text-sm tabular-nums">
                      <div className="text-right">
                        <div className="font-semibold">{r.duration}</div>
                        <div className="text-xs text-muted">
                          {r.total_cost_eur > 0
                            ? `${r.cost_is_estimated ? "~" : ""}EUR ${r.total_cost_eur.toFixed(0)}`
                            : "TBC"}
                        </div>
                      </div>
                      <ChevronRight
                        className={cn("h-4 w-4 text-muted", isActive && "text-accent")}
                      />
                    </div>
                  </button>

                  {isActive ? (
                    <div className="mt-2 border-t border-border/60 pt-2">
                      {r.by_mode?.length ? (
                        <div className="mb-2 flex flex-wrap gap-1.5">
                          {r.by_mode.map((b, i) => (
                            <span
                              key={i}
                              className="rounded border border-border bg-background px-1.5 py-0.5 text-[11px] text-muted"
                            >
                              {b.mode.toUpperCase()} {b.duration}
                            </span>
                          ))}
                        </div>
                      ) : null}

                      {r.legs?.length ? <RouteTimeline legs={r.legs} /> : null}

                      {r.booking_links?.length ? (
                        <div className="mt-2 flex flex-wrap gap-1.5 border-t border-border/60 pt-2">
                          {r.booking_links.map((l, i) => (
                            <a
                              key={i}
                              href={l.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex min-h-9 items-center rounded border border-border bg-background px-2.5 py-1 text-[11px] font-medium text-foreground hover:bg-foreground hover:text-background sm:text-xs"
                            >
                              Book on {l.label}
                            </a>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
