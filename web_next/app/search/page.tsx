import Link from "next/link";
import { SearchResults } from "@/components/search-results";
import { SearchForm } from "@/components/search-form";
import { Button } from "@/components/ui/button";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const resolved = await searchParams;
  const from = (resolved.from as string) || "Amsterdam";
  const to = (resolved.to as string) || "Naples";
  const date = (resolved.date as string) || "";
  const flex = (resolved.flex as string) || "2";

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col px-3 py-3 sm:px-5 sm:py-5">
      <header className="mb-3 flex shrink-0 items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold sm:text-lg">
            {from} → {to}
          </h1>
          {date ? (
            <p className="text-xs text-muted">
              {date}
              {flex ? ` · ±${flex} days` : ""}
            </p>
          ) : null}
        </div>
        <Link
          href="/"
          className="shrink-0 text-xs text-muted underline-offset-4 hover:underline"
        >
          New search
        </Link>
      </header>

      <div className="mb-3 hidden rounded-lg border border-border bg-card p-3 lg:block">
        <SearchForm
          initialFrom={from}
          initialTo={to}
          initialDate={date}
          initialFlex={flex}
          compact
        />
      </div>

      <SearchResults from={from} to={to} date={date} flex={flex} />

      <div className="mt-4 shrink-0 pb-2">
        <Link href="/">
          <Button type="button" variant="outline" className="min-h-11">
            Back
          </Button>
        </Link>
      </div>
    </main>
  );
}
