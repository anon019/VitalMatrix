import { useEffect, useState } from 'react'
import { trends } from '@/services/api'
import type { DateRange, TimeRange, TrendsOverview } from '@/types'
import { getDateRange } from '@/utils/date'

export function useTrendsPage(errorMessage: string) {
  const [timeRange, setTimeRange] = useState<TimeRange>('7d')
  const [customRange, setCustomRange] = useState<DateRange | undefined>()
  const [data, setData] = useState<TrendsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const dates = timeRange === 'custom' && customRange
      ? customRange
      : getDateRange(timeRange === 'custom' ? '7d' : timeRange)
    void trends.getOverview(dates.startDate, dates.endDate)
      .then((result) => { if (active) setData(result) })
      .catch(() => { if (active) setError(errorMessage) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [customRange, errorMessage, timeRange])

  const handleRangeChange = (range: TimeRange, dates?: DateRange) => {
    setLoading(true)
    setError(null)
    setTimeRange(range)
    if (range === 'custom' && dates) setCustomRange(dates)
  }

  return { timeRange, customRange, data, loading, error, handleRangeChange }
}
