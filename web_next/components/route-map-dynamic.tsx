"use client";

import dynamic from "next/dynamic";

const RouteMapInner = dynamic(
  () => import("@/components/route-map").then((m) => m.RouteMap),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full min-h-[220px] items-center justify-center rounded-lg border border-border bg-card text-sm text-muted">
        Loading map…
      </div>
    ),
  },
);

export { RouteMapInner as RouteMap };
