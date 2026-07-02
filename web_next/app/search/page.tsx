import { Card, CardContent, CardHeader } from "@/components/ui/card";
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
};

async function fetchResults(params: URLSearchParams) {
  const base = process.env.NEXT_PUBLIC_ROUTE_FINDER_API || "http://127.0.0.1:8001";
  const res = await fetch(`${base}/api/search?${params.toString()}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Search failed");
  return (await res.json()) as { routes: Route[] };
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const resolved = await searchParams;
  const params = new URLSearchParams();
  const from = (resolved.from as string) || "Amsterdam";
  const to = (resolved.to as string) || "Naples";
  const date = (resolved.date as string) || "";
  const flex = (resolved.flex as string) || "2";
  params.set("from", from);
  params.set("to", to);
  if (date) params.set("date", date);
  params.set("flex", flex);

  const data = await fetchResults(params);

  return (
    <main className="mx-auto max-w-2xl p-4 sm:p-8">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-base font-semibold">
            {from} → {to}
          </div>
        </div>
        <a href="/" className="text-sm underline underline-offset-4">
          New search
        </a>
      </div>

      <div className="grid gap-3">
        {data.routes.map((r, idx) => (
          <Card key={idx}>
            <CardHeader>
              <div className="text-sm font-semibold">{r.label}</div>
            </CardHeader>
            <CardContent>
              <div className="text-sm">
                <span className="font-semibold">{r.duration}</span> ·{" "}
                {r.total_cost_eur > 0 ? (
                  <span className="font-semibold">
                    {r.cost_is_estimated ? "~" : ""}EUR{" "}
                    {r.total_cost_eur.toFixed(2)}
                  </span>
                ) : (
                  <span className="text-muted">Fare TBC</span>
                )}
              </div>
              {r.via?.length ? (
                <div className="mt-2 text-xs text-muted">
                  Via <span className="text-foreground">{r.via.join(" → ")}</span>
                </div>
              ) : null}
              {r.stopovers?.length ? (
                <div className="mt-2 text-xs text-muted">
                  Suggested stops{" "}
                  <span className="text-foreground">
                    {r.stopovers.map((s) => s.city).join(" · ")}
                  </span>
                </div>
              ) : null}

              <div className="mt-3 flex flex-wrap gap-2">
                {r.by_mode?.map((b, i) => (
                  <div
                    key={i}
                    className="rounded-md border border-border px-2 py-1 text-xs text-muted"
                  >
                    {b.mode.toUpperCase()} {b.duration}
                  </div>
                ))}
              </div>

              {r.booking_links?.length ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {r.booking_links.slice(0, 3).map((l, i) => (
                    <a
                      key={i}
                      href={l.url}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-md border border-border px-3 py-2 text-xs text-foreground hover:opacity-90"
                    >
                      Book on {l.label}
                    </a>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="mt-6">
        <a
          href="/"
          className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
        >
          Back
        </a>
      </div>
    </main>
  );
}

