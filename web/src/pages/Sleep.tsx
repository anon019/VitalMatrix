import { useState, useEffect } from 'react'
import { trends } from '@/services/api'
import type { TrendsOverview, TimeRange, DateRange } from '@/types'
import { getDateRange } from '@/utils/date'
import TimeRangeSelector from '@/components/TimeRangeSelector'
import TrendChart from '@/components/TrendChart'
import BarChart from '@/components/BarChart'
import StatCard from '@/components/StatCard'
import { PageSkeleton } from '@/components/Skeleton'

const COLORS = {
  sleep: '#5E5CE6',
  deep: '#5E5CE6',
  rem: '#AF52DE',
  light: '#64D2FF',
  hrv: '#30D158',
}

export default function Sleep() {
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
  const latestScore = lastIdx >= 0 ? data?.sleep.scores[lastIdx] : null
  const latestEfficiency = lastIdx >= 0 ? data?.sleep.efficiency[lastIdx] : null
  const latestHrv = lastIdx >= 0 ? data?.sleep.hrv[lastIdx] : null
  const latestDeep = lastIdx >= 0 ? data?.sleep.deep_sleep_min[lastIdx] : null

  const scoreData = data?.dates?.map((date, i) => ({
    date,
    score: data.sleep.scores[i],
  })) || []

  const stagesData = data?.dates?.map((date, i) => ({
    date,
    deep: data.sleep.deep_sleep_min[i] || 0,
    rem: data.sleep.rem_sleep_min[i] || 0,
    light: data.sleep.light_sleep_min[i] || 0,
  })) || []

  const hrvData = data?.dates?.map((date, i) => ({
    date,
    hrv: data.sleep.hrv[i],
  })) || []

  if (loading) {
    return <PageSkeleton />
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-[22px] font-semibold text-[#1d1d1f]">睡眠数据</h2>
        <TimeRangeSelector value={timeRange} customRange={customRange} onChange={handleRangeChange} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="睡眠评分"
          value={latestScore}
          color={COLORS.sleep}
          subtitle={latestDate || undefined}
        />
        <StatCard
          title="睡眠效率"
          value={latestEfficiency}
          unit="%"
          color={COLORS.deep}
        />
        <StatCard
          title="HRV"
          value={latestHrv}
          unit="ms"
          color={COLORS.hrv}
        />
        <StatCard
          title="深睡时长"
          value={latestDeep}
          unit="分钟"
          color={COLORS.rem}
        />
      </div>

      <TrendChart
        title="睡眠评分趋势"
        data={scoreData}
        lines={[{ dataKey: 'score', name: '评分', color: COLORS.sleep }]}
        yAxisDomain={[0, 100]}
        showStats
      />

      <BarChart
        title="睡眠阶段分布"
        data={stagesData}
        bars={[
          { dataKey: 'deep', name: '深睡', color: COLORS.deep },
          { dataKey: 'rem', name: 'REM', color: COLORS.rem },
          { dataKey: 'light', name: '浅睡', color: COLORS.light },
        ]}
        stacked
        formatValue={(v) => `${v}分钟`}
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
