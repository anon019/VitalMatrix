import { useState, useEffect } from 'react'
import { trends } from '@/services/api'
import type { TrendsOverview, TimeRange, DateRange } from '@/types'
import { getDateRange } from '@/utils/date'
import TimeRangeSelector from '@/components/TimeRangeSelector'
import BarChart from '@/components/BarChart'
import StatCard from '@/components/StatCard'
import { PageSkeleton } from '@/components/Skeleton'

const COLORS = {
  stress: '#FF375F',
  recovery: '#30D158',
  total: '#5E5CE6',
}

export default function Stress() {
  const [timeRange, setTimeRange] = useState<TimeRange>('7d')
  const [customRange, setCustomRange] = useState<DateRange | undefined>()
  const [data, setData] = useState<TrendsOverview | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const dates = timeRange === 'custom' && customRange
      ? customRange
      : getDateRange(timeRange === 'custom' ? '7d' : timeRange)

    trends.getOverview(dates.startDate, dates.endDate)
      .then(setData)
      .finally(() => setLoading(false))
  }, [timeRange, customRange])

  const handleRangeChange = (range: TimeRange, dates?: DateRange) => {
    setTimeRange(range)
    if (range === 'custom' && dates) {
      setCustomRange(dates)
    }
  }

  const lastIdx = data?.dates?.length ? data.dates.length - 1 : -1
  const latestDate = lastIdx >= 0 ? data?.dates[lastIdx] : null
  const latestStressHigh = lastIdx >= 0 ? data?.stress.high_min[lastIdx] : null
  const latestRecoveryHigh = lastIdx >= 0 ? data?.stress.recovery_min[lastIdx] : null

  const balanceData = data?.dates?.map((date, i) => ({
    date,
    stress: data.stress.high_min[i] || 0,
    recovery: data.stress.recovery_min[i] || 0,
  })) || []

  const totalStress = data?.stress.high_min
    .filter((s): s is number => s !== null)
    .reduce((a, b) => a + b, 0) || 0

  const totalRecovery = data?.stress.recovery_min
    .filter((s): s is number => s !== null)
    .reduce((a, b) => a + b, 0) || 0

  if (loading) {
    return <PageSkeleton />
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-[22px] font-semibold text-[#1d1d1f]">压力数据</h2>
        <TimeRangeSelector value={timeRange} customRange={customRange} onChange={handleRangeChange} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="高压力时长"
          value={latestStressHigh}
          unit="分钟"
          color={COLORS.stress}
          subtitle={latestDate || undefined}
        />
        <StatCard
          title="高恢复时长"
          value={latestRecoveryHigh}
          unit="分钟"
          color={COLORS.recovery}
        />
        <StatCard
          title="累计高压力"
          value={totalStress}
          unit="分钟"
          color={COLORS.stress}
        />
        <StatCard
          title="累计高恢复"
          value={totalRecovery}
          unit="分钟"
          color={COLORS.recovery}
        />
      </div>

      <BarChart
        title="压力与恢复时长"
        data={balanceData}
        bars={[
          { dataKey: 'stress', name: '高压力', color: COLORS.stress },
          { dataKey: 'recovery', name: '高恢复', color: COLORS.recovery },
        ]}
        formatValue={(v) => `${v}分钟`}
        showStats
      />
    </div>
  )
}
