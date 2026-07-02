import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { SearchForm } from "@/components/search-form";

export default function Home() {
  return (
    <main className="mx-auto min-h-screen max-w-xl px-3 py-4 pb-8 sm:px-6 sm:py-8">
      <div className="mb-4">
        <div className="text-xl font-semibold sm:text-2xl">Route Finder</div>
        <div className="text-sm text-muted">Bus · Train · Flight</div>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <div className="text-sm font-semibold">Search</div>
        </CardHeader>
        <CardContent>
          <SearchForm />
        </CardContent>
      </Card>
    </main>
  );
}
