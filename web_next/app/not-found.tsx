export default function NotFound() {
  return (
    <main className="mx-auto max-w-xl p-6">
      <div className="text-base font-semibold">Not found</div>
      <div className="mt-2 text-sm text-muted">This page does not exist.</div>
      <div className="mt-4">
        <a className="underline underline-offset-4" href="/">
          Go home
        </a>
      </div>
    </main>
  );
}

