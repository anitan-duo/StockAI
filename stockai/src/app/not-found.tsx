import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-[640px] flex-col items-center p-12 text-center">
      <p className="font-mono text-sm text-muted-foreground">404</p>
      <h1 className="mt-2 text-3xl font-bold">Page not found</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        The route doesn&apos;t exist. If you followed a ticker link, check the exchange — symbols are
        exchange-specific (e.g. AAPL on NASDAQ).
      </p>
      <div className="mt-6 flex gap-2">
        <Link href="/dashboard"><Button>Back to dashboard</Button></Link>
        <Link href="/markets"><Button variant="outline">Browse markets</Button></Link>
      </div>
    </div>
  );
}
