import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
      <div className="text-xs font-medium uppercase tracking-[0.04em] text-text-tertiary">
        404
      </div>
      <h1 className="text-2xl font-semibold tracking-display">No such page</h1>
      <p className="max-w-md text-sm text-text-secondary">
        We could not find that route. The control plane only ships a handful of pages — try the
        dashboard, or press ⌘K to search.
      </p>
      <Button asChild>
        <Link href="/">Back to dashboard</Link>
      </Button>
    </div>
  );
}
