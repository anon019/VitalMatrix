import { useState, useEffect } from 'react'
import { trends } from '@/services/api'
import type { TrendsOverview, TimeRange, DateRange } from '@/types'
import { getDateRange, formatDuration } from '@/utils/date'
import TimeRangeSelector from '@/components/TimeRangeSelector'
import TrendChart from '@/components/TrendChart'
import BarChart from '@/components/BarChart'
import StatCard from '@/components/StatCard'
import { PageSkeleton } from '@/components/Skeleton'

const COLORS = {
  zone2: '#30D158',
  zone45: '#FF375F',
  duration: '#5E5CE6',
  trimp: '#AF52DE',
}

export default function Training() {
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

  const totalZone2 = data?.training?.reduce((sum, t) => sum + (t.zone2_min || 0), 0) || 0
  const totalZone45 = data?.training?.reduce((sum, t) => sum + (t.hi_min || 0), 0) || 0
  const totalDuration = data?.training?.reduce((sum, t) => sum + (t.total_min || 0), 0) || 0
  const trainingDays = data?.training?.filter(t => t.total_min && t.total_min > 0).length || 0

  const zoneData = data?.training?.map(t => ({
    date: t.date,
    zone2: t.zone2_min || 0,
    zone45: t.hi_min || 0,
  })) || []

  const durationData = data?.training?.map(t => ({
    date: t.date,
    duration: t.total_min || 0,
  })) || []

  const trimpData = data?.training?.map(t => ({
    date: t.date,
    trimp: t.trimp || 0,
  })) || []

  if (loading) {
    return <PageSkeleton />
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-[22px] font-semibold text-[#1d1d1f]">训练数据</h2>
        <TimeRangeSelector value={timeRange} customRange={customRange} onChange={handleRangeChange} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Zone2 总时长"
          value={formatDuration(totalZone2)}
          color={COLORS.zone2}
          subtitle="目标: 200-300分钟/周"
        />
        <StatCard
          title="Zone4-5 总时长"
          value={formatDuration(totalZone45)}
          color={COLORS.zone45}
          subtitle="建议: <30分钟/周"
        />
        <StatCard
          title="总训练时长"
          value={formatDuration(totalDuration)}
          color={COLORS.duration}
        />
        <StatCard
          title="训练天数"
          value={trainingDays}
          unit="天"
          color={COLORS.trimp}
        />
      </div>

      <BarChart
        title="心率区间分布"
        data={zoneData}
        bars={[
          { dataKey: 'zone2', name: 'Zone2', color: COLORS.zone2 },
          { dataKey: 'zone45', name: 'Zone4-5', color: COLORS.zone45 },
        ]}
        stacked
        formatValue={(v) => `${v}分钟`}
        showStats
      />

      <TrendChart
        title="每日训练时长"
        data={durationData}
        lines={[{ dataKey: 'duration', name: '时长', color: COLORS.duration }]}
        formatValue={(v) => `${v}分钟`}
        showStats
      />

      <TrendChart
        title="训练负荷 (TRIMP)"
        data={trimpData}
        lines={[{ dataKey: 'trimp', name: 'TRIMP', color: COLORS.trimp }]}
        showStats
      />
    </div>
  )
}
