import Link from "next/link";
import { SearchResults } from "@/components/search-results";
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
    <main className="mx-auto max-w-3xl px-3 py-4 sm:px-6 sm:py-6">
      <header className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-base font-semibold sm:text-lg">
            {from} → {to}
          </h1>
          {date ? (
            <p className="text-xs text-muted">
              {date}
              {flex ? ` · ±${flex} days` : ""}
            </p>
          ) : null}
        </div>
        <Link href="/" className="shrink-0 text-xs text-muted underline-offset-4 hover:underline">
          New search
        </Link>
      </header>

      <SearchResults from={from} to={to} date={date} flex={flex} />

      <div className="mt-4">
        <Link href="/">
          <Button type="button" variant="outline">
            Back
          </Button>
        </Link>
      </div>
    </main>
  );
}
