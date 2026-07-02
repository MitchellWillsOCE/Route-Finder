"use client";

import { CalendarDays } from "lucide-react";

import { Button } from "@/components/ui/button";
import { LocationAutocomplete } from "@/components/location-autocomplete";
import { cn } from "@/lib/utils";

function defaultDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 14);
  return d.toISOString().slice(0, 10);
}

type Props = {
  initialFrom?: string;
  initialTo?: string;
  initialDate?: string;
  initialFlex?: string;
  compact?: boolean;
};

export function SearchForm({
  initialFrom = "Amsterdam",
  initialTo = "Naples",
  initialDate,
  initialFlex = "2",
  compact = false,
}: Props) {
  const dateValue = initialDate || defaultDate();

  return (
    <form action="/search" method="get" className="grid gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <LocationAutocomplete name="from" label="From" defaultValue={initialFrom} required />
        <LocationAutocomplete name="to" label="To" defaultValue={initialTo} required />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="travel-date" className="mb-1 block text-xs text-muted">
            Date
          </label>
          <div className="relative">
            <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              id="travel-date"
              name="date"
              type="date"
              defaultValue={dateValue}
              required
              className={cn(
                "h-12 w-full rounded-md border border-border bg-card py-2 pl-9 pr-3 text-base text-foreground sm:text-sm",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/30",
                "[color-scheme:dark]",
              )}
            />
          </div>
        </div>

        <div>
          <label htmlFor="travel-flex" className="mb-1 block text-xs text-muted">
            Flexibility
          </label>
          <select
            id="travel-flex"
            name="flex"
            defaultValue={initialFlex}
            className={cn(
              "h-12 w-full appearance-none rounded-md border border-border bg-card px-3 text-base text-foreground sm:text-sm",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/30",
            )}
          >
            <option value="0">Exact date</option>
            <option value="1">±1 day</option>
            <option value="2">±2 days</option>
            <option value="3">±3 days</option>
            <option value="7">±7 days</option>
          </select>
        </div>
      </div>

      <Button type="submit" className={cn("h-12 w-full text-base sm:h-11 sm:text-sm", compact && "sm:w-auto")}>
        Find routes
      </Button>
    </form>
  );
}
