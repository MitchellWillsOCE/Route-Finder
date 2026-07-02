"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { MapPin } from "lucide-react";

import { fetchPlaces, type PlaceSuggestion } from "@/lib/api";
import { cn } from "@/lib/utils";

type Props = {
  name: string;
  label: string;
  defaultValue?: string;
  placeholder?: string;
  required?: boolean;
};

export function LocationAutocomplete({
  name,
  label,
  defaultValue = "",
  placeholder = "City or station",
  required,
}: Props) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [value, setValue] = useState(defaultValue);
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  useEffect(() => {
    if (!open) {
      setSuggestions([]);
      return;
    }

    let cancelled = false;
    const timer = setTimeout(async () => {
      setLoading(true);
      const places = await fetchPlaces(value.trim());
      if (!cancelled) {
        setSuggestions(places);
        setActiveIndex(places.length ? 0 : -1);
        setLoading(false);
      }
    }, value.trim() ? 180 : 0);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [value, open]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const pick = useCallback((place: PlaceSuggestion) => {
    setValue(place.name);
    setOpen(false);
    setSuggestions([]);
  }, []);

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || !suggestions.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      pick(suggestions[activeIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <label htmlFor={listId} className="mb-1 block text-xs text-muted">
        {label}
      </label>
      <div className="relative">
        <MapPin className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
        <input
          id={listId}
          name={name}
          type="text"
          value={value}
          required={required}
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          placeholder={placeholder}
          onChange={(e) => {
            setValue(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          className={cn(
            "h-12 w-full rounded-md border border-border bg-card py-2 pl-9 pr-3 text-base text-foreground sm:text-sm",
            "placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/30",
          )}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${listId}-list`}
          aria-autocomplete="list"
        />
      </div>

      {open && (suggestions.length > 0 || loading) ? (
        <ul
          id={`${listId}-list`}
          role="listbox"
          className="absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded-md border border-border bg-card py-1 shadow-lg"
        >
          {loading && !suggestions.length ? (
            <li className="px-3 py-2.5 text-sm text-muted">Searching…</li>
          ) : null}
          {suggestions.map((place, index) => (
            <li key={place.name} role="option" aria-selected={index === activeIndex}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(place)}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-3 text-left text-sm sm:py-2.5",
                  index === activeIndex ? "bg-foreground/10" : "hover:bg-foreground/5",
                )}
              >
                <MapPin className="h-3.5 w-3.5 shrink-0 text-muted" />
                <span>{place.name}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
