interface SkeletonProps {
  className?: string
  style?: React.CSSProperties
}

export function Skeleton({ className = '', style }: SkeletonProps) {
  return <div className={`skeleton ${className}`} style={style} />
}

export function ScoreCardSkeleton() {
  return (
    <div className="bg-white rounded-xl p-5">
      <div className="flex items-start justify-between mb-4">
        <Skeleton className="w-16 h-4" />
        <Skeleton className="w-12 h-8" />
      </div>
      <Skeleton className="h-[6px] w-full mb-3" />
      <div className="flex justify-between">
        <Skeleton className="w-12 h-4" />
        <Skeleton className="w-16 h-3" />
      </div>
    </div>
  )
}

export function StatCardSkeleton() {
  return (
    <div className="bg-white rounded-xl p-5">
      <div className="flex items-center gap-2 mb-3">
        <Skeleton className="w-2 h-2 rounded-full" />
        <Skeleton className="w-16 h-4" />
      </div>
      <Skeleton className="w-20 h-8 mb-1" />
      <Skeleton className="w-12 h-3" />
    </div>
  )
}

export function ChartSkeleton({ height = 240 }: { height?: number }) {
  return (
    <div className="bg-white rounded-xl p-5">
      <Skeleton className="h-5 w-24 mb-4" />
      <Skeleton className="w-full" style={{ height }} />
    </div>
  )
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <Skeleton className="h-7 w-24" />
        <Skeleton className="h-9 w-48" />
      </div>

      {/* Score Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <ScoreCardSkeleton key={i} />
        ))}
      </div>

      {/* Charts */}
      <ChartSkeleton height={240} />

      {/* HRV and HR */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartSkeleton height={200} />
        <ChartSkeleton height={200} />
      </div>

      <ChartSkeleton height={240} />
    </div>
  )
}

export function PageSkeleton() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <Skeleton className="h-7 w-24" />
        <Skeleton className="h-9 w-48" />
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <StatCardSkeleton key={i} />
        ))}
      </div>

      {/* Charts */}
      <ChartSkeleton height={240} />
      <ChartSkeleton height={240} />
    </div>
  )
}
