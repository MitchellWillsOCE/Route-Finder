"use client";

import { useEffect, useState } from "react";
import { RouteTimeline, type RouteLeg } from "@/components/route-timeline";
import { Button } from "@/components/ui/button";

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

function apiBase(): string {
  return process.env.NEXT_PUBLIC_ROUTE_FINDER_API || "http://127.0.0.1:8001";
}

export function SearchResults({ from, to, date, flex }: Props) {
  const [routes, setRoutes] = useState<Route[] | null>(null);
  const [status, setStatus] = useState("Searching routes...");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    async function run() {
      setRoutes(null);
      setError(null);
      setStatus("Searching routes...");

      try {
        const base = apiBase();
        const startRes = await fetch(`${base}/api/search/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            from,
            to,
            date: date || undefined,
            flex: Number(flex) || 2,
          }),
        });
        if (!startRes.ok) throw new Error("Could not start search");
        const { job_id } = (await startRes.json()) as { job_id: string };

        await new Promise<void>((resolve, reject) => {
          timer = setInterval(async () => {
            if (cancelled) return;
            try {
              const jobRes = await fetch(`${base}/api/job/${job_id}`);
              if (!jobRes.ok) throw new Error("Search failed");
              const job = (await jobRes.json()) as {
                status: string;
                message: string;
                error?: string;
                result?: { routes: Route[] };
              };
              if (job.status === "pending") {
                setStatus(job.message || "Searching...");
                return;
              }
              clearInterval(timer);
              if (job.status === "error") {
                reject(new Error(job.error || "Search failed"));
                return;
              }
              setRoutes(job.result?.routes || []);
              resolve();
            } catch (err) {
              clearInterval(timer);
              reject(err);
            }
          }, 1200);
        });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Search failed");
        }
      }
    }

    run();
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [from, to, date, flex]);

  if (error) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-sm">
        <p className="text-foreground">{error}</p>
        <a href="/" className="mt-3 inline-block">
          <Button type="button">New search</Button>
        </a>
      </div>
    );
  }

  if (!routes) {
    return (
      <div className="rounded-lg border border-border bg-card p-6 text-center text-sm text-muted">
        <div className="mx-auto mb-3 h-5 w-5 animate-pulse rounded-full bg-muted/40" />
        {status}
      </div>
    );
  }

  if (!routes.length) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted">
        No routes found.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {routes.map((r, idx) => (
        <article
          key={idx}
          className="rounded-lg border border-border bg-card px-3 py-2.5 sm:px-4"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h2 className="text-sm font-semibold">{r.label}</h2>
            <div className="text-sm tabular-nums">
              <span className="font-semibold">{r.duration}</span>
              <span className="mx-1.5 text-muted">·</span>
              {r.total_cost_eur > 0 ? (
                <span className="font-semibold">
                  {r.cost_is_estimated ? "~" : ""}EUR {r.total_cost_eur.toFixed(2)}
                </span>
              ) : (
                <span className="text-muted">Fare TBC</span>
              )}
            </div>
          </div>

          {r.via?.length ? (
            <p className="mt-1 text-xs text-muted">
              Via <span className="text-foreground">{r.via.join(" → ")}</span>
            </p>
          ) : null}

          {r.by_mode?.length ? (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {r.by_mode.map((b, i) => (
                <span
                  key={i}
                  className="rounded border border-border bg-background px-1.5 py-0.5 text-[11px] text-muted"
                >
                  {b.mode.toUpperCase()} {b.duration}
                  {b.has_cost ? ` · EUR ${b.cost_eur.toFixed(0)}` : ""}
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
                  className="inline-flex items-center rounded border border-border bg-background px-2.5 py-1 text-[11px] font-medium text-foreground hover:bg-foreground hover:text-background"
                >
                  Book on {l.label}
                </a>
              ))}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}
