import { Skeleton } from '@/components/ui/skeleton'

export function StatTileSkeletons({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        // biome-ignore lint: static skeleton list
        <Skeleton key={i} className="h-24 rounded-lg" />
      ))}
    </div>
  )
}

export function ListSkeleton({ count = 5, className }: { count?: number; className?: string }) {
  return (
    <div className={className ?? 'flex flex-col gap-2'}>
      {Array.from({ length: count }).map((_, i) => (
        // biome-ignore lint: static skeleton list
        <Skeleton key={i} className="h-12 w-full rounded-md" />
      ))}
    </div>
  )
}

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2">
      <Skeleton className="h-9 w-64 rounded-md" />
      <div className="rounded-lg border">
        {Array.from({ length: rows }).map((_, i) => (
          // biome-ignore lint: static skeleton list
          <div key={i} className="flex items-center gap-4 border-b p-3 last:border-b-0">
            <Skeleton className="size-8 shrink-0 rounded-full" />
            <Skeleton className="h-4 w-full max-w-64" />
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-16" />
          </div>
        ))}
      </div>
    </div>
  )
}
