import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
} from 'recharts'
import dayjs from 'dayjs'

/** 计算中位数 */
function median(values: number[]): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

/** 计算平均值 */
function average(values: number[]): number {
  if (values.length === 0) return 0
  return values.reduce((a, b) => a + b, 0) / values.length
}

interface DataPoint {
  date: string
  [key: string]: string | number | null
}

interface LineConfig {
  dataKey: string
  name: string
  color: string
}

interface TrendChartProps {
  data: DataPoint[]
  lines: LineConfig[]
  title: string
  height?: number
  yAxisDomain?: [number, number]
  formatValue?: (value: number) => string
  compact?: boolean  // For smaller charts
  /** 显示平均值和中位数参考线 */
  showStats?: boolean
}

interface TooltipPayloadItem {
  color: string
  name: string
  value: number | null
}

interface CustomTooltipProps {
  active?: boolean
  payload?: TooltipPayloadItem[]
  label?: string
  formatValue?: (value: number) => string
}

const CustomTooltip = ({ active, payload, label, formatValue }: CustomTooltipProps) => {
  if (!active || !payload?.length) return null

  return (
    <div className="bg-white rounded-lg shadow-lg border border-[#e5e5e5] px-3 py-2">
      <p className="text-[11px] text-[#86868b] mb-1.5">
        {dayjs(label).format('M月D日')}
      </p>
      {payload.map((entry, index) => (
        <div key={index} className="flex items-center gap-2 py-0.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-[12px] text-[#86868b]">{entry.name}</span>
          <span className="text-[12px] font-medium text-[#1d1d1f] ml-auto">
            {formatValue && typeof entry.value === 'number'
              ? formatValue(entry.value)
              : entry.value ?? '-'}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function TrendChart({
  data,
  lines,
  title,
  height = 240,
  yAxisDomain,
  formatValue,
  compact = false,
  showStats = false,
}: TrendChartProps) {
  const formatDate = (dateStr: string) => dayjs(dateStr).format('M/D')

  // 计算每条线的统计数据
  const lineStats = showStats
    ? lines.map((line) => {
        const values = data
          .map((d) => d[line.dataKey])
          .filter((v): v is number => typeof v === 'number' && v !== null)
        return {
          dataKey: line.dataKey,
          color: line.color,
          avg: Math.round(average(values) * 10) / 10,
          med: Math.round(median(values) * 10) / 10,
        }
      })
    : []

  if (!data || data.length === 0) {
    return (
      <div className="bg-white rounded-xl p-5">
        <h3 className="text-[15px] font-medium text-[#1d1d1f] mb-4">{title}</h3>
        <div className="flex items-center justify-center text-[#86868b]" style={{ height }}>
          暂无数据
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl p-5">
      {!compact && (
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[15px] font-medium text-[#1d1d1f]">{title}</h3>
          {showStats && lineStats.length > 0 && (
            <div className="flex items-center gap-4 text-[13px] text-[#86868b]">
              {lineStats.map((stat, idx) => (
                <span key={stat.dataKey}>
                  {lines.length > 1 && <span>{lines[idx].name} </span>}
                  平均 <span className="font-medium text-[#1d1d1f]">{formatValue ? formatValue(stat.avg) : stat.avg}</span>
                  {' / '}中位数 <span className="font-medium text-[#1d1d1f]">{formatValue ? formatValue(stat.med) : stat.med}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 5, right: 10, left: compact ? -20 : 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={formatDate}
            tick={{ fontSize: 11, fill: '#86868b' }}
            axisLine={{ stroke: '#e5e5e5' }}
            tickLine={false}
          />
          <YAxis
            domain={yAxisDomain}
            tick={{ fontSize: 11, fill: '#86868b' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={formatValue}
            width={compact ? 30 : 40}
          />
          <Tooltip content={<CustomTooltip formatValue={formatValue} />} />
          {lines.map((line) => (
            <Line
              key={line.dataKey}
              type="monotone"
              dataKey={line.dataKey}
              name={line.name}
              stroke={line.color}
              strokeWidth={2}
              dot={{ fill: line.color, strokeWidth: 0, r: 2 }}
              activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }}
              connectNulls
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      {/* Legend */}
      {!compact && lines.length > 1 && (
        <div className="flex items-center justify-center gap-6 mt-4">
          {lines.map((line) => (
            <div key={line.dataKey} className="flex items-center gap-1.5">
              <div
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: line.color }}
              />
              <span className="text-[12px] text-[#86868b]">{line.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
