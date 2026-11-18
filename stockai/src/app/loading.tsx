export default function Loading() {
  return (
    <div className="mx-auto max-w-[1400px] space-y-4 p-6" aria-label="Loading">
      <div className="chart-skeleton h-10 w-full rounded-lg" />
      <div className="grid gap-4 md:grid-cols-3">
        <div className="chart-skeleton h-32 rounded-xl" />
        <div className="chart-skeleton h-32 rounded-xl" />
        <div className="chart-skeleton h-32 rounded-xl" />
      </div>
    </div>
  );
}
