import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { trends } from '@/services/api'
import type { TrendsOverview, TimeRange, DateRange } from '@/types'
import { getDateRange } from '@/utils/date'
import TimeRangeSelector from '@/components/TimeRangeSelector'
import ScoreCard from '@/components/ScoreCard'
import TrendChart from '@/components/TrendChart'
import BarChart from '@/components/BarChart'
import { DashboardSkeleton } from '@/components/Skeleton'

// Apple 系统色
const COLORS = {
  sleep: '#5E5CE6',
  readiness: '#30D158',
  activity: '#FF9F0A',
  training: '#FF375F',
  hrv: '#64D2FF',
  stress: '#AF52DE',
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [timeRange, setTimeRange] = useState<TimeRange>('7d')
  const [customRange, setCustomRange] = useState<DateRange | undefined>()
  const [data, setData] = useState<TrendsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = async (startDate: string, endDate: string) => {
    setLoading(true)
    setError(null)
    try {
      const result = await trends.getOverview(startDate, endDate)
      setData(result)
    } catch (err) {
      setError('加载数据失败')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const dates = timeRange === 'custom' && customRange
      ? customRange
      : getDateRange(timeRange === 'custom' ? '7d' : timeRange)
    fetchData(dates.startDate, dates.endDate)
  }, [timeRange, customRange])

  const handleRangeChange = (range: TimeRange, dates?: DateRange) => {
    setTimeRange(range)
    if (range === 'custom' && dates) {
      setCustomRange(dates)
    }
  }

  // Get latest data
  const lastIdx = data?.dates?.length ? data.dates.length - 1 : -1
  const latestSleepScore = lastIdx >= 0 ? data?.sleep.scores[lastIdx] : null
  const latestReadinessScore = lastIdx >= 0 ? data?.readiness.scores[lastIdx] : null
  const latestActivityScore = lastIdx >= 0 ? data?.activity.scores[lastIdx] : null
  const latestStressHigh = lastIdx >= 0 ? data?.stress.high_min[lastIdx] : null

  // Prepare chart data
  const scoreChartData = data?.dates?.map((date, i) => ({
    date,
    sleep: data.sleep.scores[i],
    readiness: data.readiness.scores[i],
    activity: data.activity.scores[i],
  })) || []

  const trainingChartData = data?.training?.map((t) => ({
    date: t.date,
    zone2: t.zone2_min || 0,
    zone45: t.hi_min || 0,
  })) || []

  // HRV and resting heart rate data
  const hrvChartData = data?.dates?.map((date, i) => ({
    date,
    hrv: data.sleep.hrv[i],
  })) || []

  const restingHrChartData = data?.dates?.map((date, i) => ({
    date,
    hr: data.sleep.resting_hr[i],
  })) || []

  // Calculate averages for display
  const hrvValues = data?.sleep.hrv?.filter((v): v is number => v !== null) || []
  const avgHrv = hrvValues.length > 0
    ? Math.round(hrvValues.reduce((a, b) => a + b, 0) / hrvValues.length)
    : null

  const restingHrValues = data?.sleep.resting_hr?.filter((v): v is number => v !== null) || []
  const avgRestingHr = restingHrValues.length > 0
    ? Math.round(restingHrValues.reduce((a, b) => a + b, 0) / restingHrValues.length)
    : null

  if (loading) {
    return <DashboardSkeleton />
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <p className="text-[#86868b]">{error}</p>
        <button
          onClick={() => {
            const dates = getDateRange(timeRange === 'custom' ? '7d' : timeRange)
            fetchData(dates.startDate, dates.endDate)
          }}
          className="px-4 py-2 bg-[#1d1d1f] text-white rounded-lg text-[13px] font-medium hover:bg-[#333] transition-colors"
        >
          重试
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-[22px] font-semibold text-[#1d1d1f]">数据总览</h2>
        <TimeRangeSelector
          value={timeRange}
          customRange={customRange}
          onChange={handleRangeChange}
        />
      </div>

      {/* Score Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <ScoreCard
          title="睡眠"
          score={latestSleepScore}
          color={COLORS.sleep}
          onClick={() => navigate('/sleep')}
        />
        <ScoreCard
          title="恢复"
          score={latestReadinessScore}
          color={COLORS.readiness}
          onClick={() => navigate('/readiness')}
        />
        <ScoreCard
          title="活动"
          score={latestActivityScore}
          color={COLORS.activity}
          onClick={() => navigate('/activity')}
        />
        <ScoreCard
          title="压力"
          score={latestStressHigh}
          color={COLORS.stress}
          subtitle="高压力分钟"
          onClick={() => navigate('/stress')}
          invertScore
          invertThresholds={[15, 30, 60]}
        />
      </div>

      {/* Score Trends */}
      <TrendChart
        title="评分趋势"
        data={scoreChartData}
        lines={[
          { dataKey: 'sleep', name: '睡眠', color: COLORS.sleep },
          { dataKey: 'readiness', name: '恢复', color: COLORS.readiness },
          { dataKey: 'activity', name: '活动', color: COLORS.activity },
        ]}
        yAxisDomain={[0, 100]}
        showStats
      />

      {/* HRV and Resting HR - side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[15px] font-medium text-[#1d1d1f]">HRV 趋势</h3>
            {avgHrv && (
              <span className="text-[13px] text-[#86868b]">
                平均 <span className="font-medium text-[#1d1d1f]">{avgHrv}</span> ms
              </span>
            )}
          </div>
          <TrendChart
            title=""
            data={hrvChartData}
            lines={[{ dataKey: 'hrv', name: 'HRV', color: COLORS.hrv }]}
            height={160}
            compact
            formatValue={(v) => `${v}ms`}
          />
        </div>

        <div className="bg-white rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[15px] font-medium text-[#1d1d1f]">静息心率</h3>
            {avgRestingHr && (
              <span className="text-[13px] text-[#86868b]">
                平均 <span className="font-medium text-[#1d1d1f]">{avgRestingHr}</span> bpm
              </span>
            )}
          </div>
          <TrendChart
            title=""
            data={restingHrChartData}
            lines={[{ dataKey: 'hr', name: '心率', color: COLORS.training }]}
            height={160}
            compact
            formatValue={(v) => `${v}`}
          />
        </div>
      </div>

      {/* Training Chart */}
      <BarChart
        title="训练时长"
        data={trainingChartData}
        bars={[
          { dataKey: 'zone2', name: 'Zone2', color: COLORS.readiness },
          { dataKey: 'zone45', name: 'Zone4-5', color: COLORS.training },
        ]}
        stacked
        formatValue={(v) => `${v}分钟`}
        showStats
      />

      {/* Period Summary */}
      {data && (
        <div className="bg-white rounded-xl p-5">
          <h3 className="text-[15px] font-medium text-[#1d1d1f] mb-4">
            周期汇总
          </h3>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="text-center py-3">
              <div className="text-[28px] font-semibold text-[#1d1d1f]">
                {data.sleep.scores.filter(s => s !== null).length}
              </div>
              <div className="text-[12px] text-[#86868b]">睡眠记录天数</div>
            </div>
            <div className="text-center py-3">
              <div className="text-[28px] font-semibold text-[#1d1d1f]">
                {Math.round(
                  data.sleep.scores
                    .filter((s): s is number => s !== null)
                    .reduce((sum, s) => sum + s, 0) /
                    (data.sleep.scores.filter(s => s !== null).length || 1)
                )}
              </div>
              <div className="text-[12px] text-[#86868b]">平均睡眠评分</div>
            </div>
            <div className="text-center py-3">
              <div className="text-[28px] font-semibold text-[#1d1d1f]">
                {Math.round(data.training.reduce((sum, t) => sum + (t.zone2_min || 0), 0))}
              </div>
              <div className="text-[12px] text-[#86868b]">Zone2 总时长</div>
            </div>
            <div className="text-center py-3">
              <div className="text-[28px] font-semibold text-[#1d1d1f]">
                {data.training.filter(t => t.total_min && t.total_min > 0).length}
              </div>
              <div className="text-[12px] text-[#86868b]">训练天数</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
