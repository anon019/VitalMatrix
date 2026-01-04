import { useState, useEffect } from 'react'
import { trends } from '@/services/api'
import type { TrendsOverview, TimeRange, DateRange } from '@/types'
import { getDateRange } from '@/utils/date'
import TimeRangeSelector from '@/components/TimeRangeSelector'
import TrendChart from '@/components/TrendChart'
import StatCard from '@/components/StatCard'
import { PageSkeleton } from '@/components/Skeleton'

const COLORS = {
  activity: '#FF9F0A',
  steps: '#30D158',
  calories: '#FF375F',
  sedentary: '#86868b',
}

export default function Activity() {
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
  const latestScore = lastIdx >= 0 ? data?.activity.scores[lastIdx] : null
  const latestSteps = lastIdx >= 0 ? data?.activity.steps[lastIdx] : null
  const latestCalories = lastIdx >= 0 ? data?.activity.active_calories[lastIdx] : null
  const latestSedentary = lastIdx >= 0 ? data?.activity.sedentary_min[lastIdx] : null

  const scoreData = data?.dates?.map((date, i) => ({
    date,
    score: data.activity.scores[i],
  })) || []

  const stepsData = data?.dates?.map((date, i) => ({
    date,
    steps: data.activity.steps[i],
  })) || []

  const caloriesData = data?.dates?.map((date, i) => ({
    date,
    calories: data.activity.active_calories[i],
  })) || []

  // 久坐时间数据（秒转小时）
  const sedentaryData = data?.dates?.map((date, i) => ({
    date,
    sedentary: data.activity.sedentary_min[i] ? Math.round(data.activity.sedentary_min[i]! / 360) / 10 : null,
  })) || []

  if (loading) {
    return <PageSkeleton />
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-[22px] font-semibold text-[#1d1d1f]">活动数据</h2>
        <TimeRangeSelector value={timeRange} customRange={customRange} onChange={handleRangeChange} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="活动评分"
          value={latestScore}
          color={COLORS.activity}
          subtitle={latestDate || undefined}
        />
        <StatCard
          title="步数"
          value={latestSteps?.toLocaleString()}
          color={COLORS.steps}
        />
        <StatCard
          title="活动消耗"
          value={latestCalories}
          unit="kcal"
          color={COLORS.calories}
        />
        <StatCard
          title="久坐时间"
          value={latestSedentary ? (latestSedentary / 3600).toFixed(1) : null}
          unit="小时"
          color={COLORS.sedentary}
        />
      </div>

      <TrendChart
        title="活动评分趋势"
        data={scoreData}
        lines={[{ dataKey: 'score', name: '活动评分', color: COLORS.activity }]}
        yAxisDomain={[0, 100]}
        showStats
      />

      <TrendChart
        title="每日步数"
        data={stepsData}
        lines={[{ dataKey: 'steps', name: '步数', color: COLORS.steps }]}
        showStats
      />

      <TrendChart
        title="活动消耗"
        data={caloriesData}
        lines={[{ dataKey: 'calories', name: '消耗', color: COLORS.calories }]}
        formatValue={(v) => `${v}kcal`}
        showStats
      />

      <TrendChart
        title="久坐时间"
        data={sedentaryData}
        lines={[{ dataKey: 'sedentary', name: '久坐', color: COLORS.sedentary }]}
        formatValue={(v) => `${v}小时`}
        showStats
      />
    </div>
  )
}
