import { useState } from 'react'
import dayjs from 'dayjs'
import type { TimeRange, DateRange } from '@/types'
import { getDateRange } from '@/utils/date'

interface TimeRangeSelectorProps {
  value: TimeRange
  customRange?: DateRange
  onChange: (range: TimeRange, dates?: DateRange) => void
}

const presets: { value: TimeRange; label: string }[] = [
  { value: '7d', label: '7 天' },
  { value: '30d', label: '30 天' },
  { value: '90d', label: '90 天' },
  { value: 'custom', label: '自定义' },
]

export default function TimeRangeSelector({
  value,
  customRange,
  onChange,
}: TimeRangeSelectorProps) {
  const [showCustom, setShowCustom] = useState(value === 'custom')
  const [startDate, setStartDate] = useState(
    customRange?.startDate || dayjs().subtract(6, 'day').format('YYYY-MM-DD')
  )
  const [endDate, setEndDate] = useState(
    customRange?.endDate || dayjs().format('YYYY-MM-DD')
  )

  const handlePresetChange = (preset: TimeRange) => {
    if (preset === 'custom') {
      setShowCustom(true)
      onChange('custom', { startDate, endDate })
    } else {
      setShowCustom(false)
      const dates = getDateRange(preset)
      onChange(preset, dates)
    }
  }

  const handleCustomApply = () => {
    onChange('custom', { startDate, endDate })
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Preset Buttons */}
      <div className="flex bg-[#e5e5e5] rounded-lg p-0.5">
        {presets.map((preset) => (
          <button
            key={preset.value}
            onClick={() => handlePresetChange(preset.value)}
            className={`px-3 py-1.5 text-[13px] font-medium rounded-md transition-all ${
              value === preset.value
                ? 'bg-white text-[#1d1d1f] shadow-sm'
                : 'text-[#86868b] hover:text-[#1d1d1f]'
            }`}
          >
            {preset.label}
          </button>
        ))}
      </div>

      {/* Custom Date Inputs */}
      {showCustom && (
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            max={endDate}
            className="px-2 py-1.5 text-[13px] border border-[#d2d2d7] rounded-lg bg-white focus:outline-none focus:border-[#1d1d1f]"
          />
          <span className="text-[13px] text-[#86868b]">至</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            min={startDate}
            max={dayjs().format('YYYY-MM-DD')}
            className="px-2 py-1.5 text-[13px] border border-[#d2d2d7] rounded-lg bg-white focus:outline-none focus:border-[#1d1d1f]"
          />
          <button
            onClick={handleCustomApply}
            className="px-3 py-1.5 text-[13px] font-medium text-white bg-[#1d1d1f] rounded-lg hover:bg-[#333] transition-colors"
          >
            应用
          </button>
        </div>
      )}
    </div>
  )
}
