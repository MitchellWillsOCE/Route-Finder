import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="mx-auto max-w-xl p-4 sm:p-8">
      <div className="mb-4">
        <div className="text-xl font-semibold">Route Finder</div>
        <div className="text-sm text-muted">Bus · Train · Flight</div>
      </div>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold">Search</div>
        </CardHeader>
        <CardContent>
          <form
            action="/search"
            method="get"
            className="grid gap-3"
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <div className="mb-1 text-xs text-muted">From</div>
                <Input name="from" defaultValue="Amsterdam" />
              </div>
              <div>
                <div className="mb-1 text-xs text-muted">To</div>
                <Input name="to" defaultValue="Naples" />
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <div className="mb-1 text-xs text-muted">Date</div>
                <Input name="date" placeholder="2026-07-15" />
              </div>
              <div>
                <div className="mb-1 text-xs text-muted">Flex</div>
                <Input name="flex" defaultValue="2" inputMode="numeric" />
              </div>
            </div>

            <Button type="submit">Find routes</Button>
          </form>
        </CardContent>
      </Card>

      <div className="mt-4 text-xs text-muted">
        This UI is intentionally minimal. Results show only duration, cost, and key hubs.
      </div>
    </main>
  );
}

