import { useTrendsPage } from '@/hooks/useTrendsPage'
import TimeRangeSelector from '@/components/TimeRangeSelector'
import TrendChart from '@/components/TrendChart'
import StatCard from '@/components/StatCard'
import { PageSkeleton } from '@/components/Skeleton'

const COLORS = {
  readiness: '#30D158',
  hrv: '#64D2FF',
  days: '#5E5CE6',
}

export default function Readiness() {
  const { timeRange, customRange, data, loading, error, handleRangeChange } = useTrendsPage('加载恢复数据失败，请稍后重试')

  const lastIdx = data?.dates?.length ? data.dates.length - 1 : -1
  const latestDate = lastIdx >= 0 ? data?.dates[lastIdx] : null
  const latestScore = lastIdx >= 0 ? data?.readiness.scores[lastIdx] : null
  const latestHrv = lastIdx >= 0 ? data?.sleep.hrv[lastIdx] : null

  const chartData = data?.dates?.map((date, i) => ({
    date,
    score: data.readiness.scores[i],
  })) || []

  const hrvData = data?.dates?.map((date, i) => ({
    date,
    hrv: data.sleep.hrv[i],
  })) || []

  const validScores = data?.readiness?.scores?.filter((s): s is number => s !== null) || []
  const avgScore = validScores.length > 0
    ? Math.round(validScores.reduce((a, b) => a + b, 0) / validScores.length)
    : null

  if (loading) {
    return <PageSkeleton />
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[200px]">
        <p className="text-red-500">{error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-[22px] font-semibold text-[#1d1d1f]">恢复数据</h2>
        <TimeRangeSelector value={timeRange} customRange={customRange} onChange={handleRangeChange} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="恢复评分"
          value={latestScore}
          color={COLORS.readiness}
          subtitle={latestDate || undefined}
        />
        <StatCard
          title="平均评分"
          value={avgScore}
          color={COLORS.readiness}
        />
        <StatCard
          title="HRV"
          value={latestHrv}
          unit="ms"
          color={COLORS.hrv}
        />
        <StatCard
          title="记录天数"
          value={data?.readiness.scores.filter(s => s !== null).length}
          unit="天"
          color={COLORS.days}
        />
      </div>

      <TrendChart
        title="恢复评分趋势"
        data={chartData}
        lines={[{ dataKey: 'score', name: '恢复评分', color: COLORS.readiness }]}
        yAxisDomain={[0, 100]}
        showStats
      />

      <TrendChart
        title="HRV 趋势"
        data={hrvData}
        lines={[{ dataKey: 'hrv', name: 'HRV', color: COLORS.hrv }]}
        formatValue={(v) => `${v}ms`}
        showStats
      />
    </div>
  )
}
