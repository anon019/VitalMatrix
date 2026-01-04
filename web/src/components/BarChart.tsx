import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
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

interface BarConfig {
  dataKey: string
  name: string
  color: string
}

interface BarChartProps {
  data: DataPoint[]
  bars: BarConfig[]
  title: string
  height?: number
  formatValue?: (value: number) => string
  stacked?: boolean
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
            className="w-2 h-2 rounded-sm"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-[12px] text-[#86868b]">{entry.name}</span>
          <span className="text-[12px] font-medium text-[#1d1d1f] ml-auto">
            {formatValue && typeof entry.value === 'number' ? formatValue(entry.value) : entry.value}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function BarChart({
  data,
  bars,
  title,
  height = 240,
  formatValue,
  stacked = false,
  showStats = false,
}: BarChartProps) {
  const formatDate = (dateStr: string) => dayjs(dateStr).format('M/D')

  // 计算每个 bar 的统计数据
  const barStats = showStats
    ? bars.map((bar) => {
        const values = data
          .map((d) => d[bar.dataKey])
          .filter((v): v is number => typeof v === 'number' && v !== null)
        return {
          dataKey: bar.dataKey,
          name: bar.name,
          color: bar.color,
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
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[15px] font-medium text-[#1d1d1f]">{title}</h3>
        {showStats && barStats.length > 0 && (
          <div className="flex items-center gap-4 text-[13px] text-[#86868b]">
            {barStats.map((stat) => (
              <span key={stat.dataKey}>
                {bars.length > 1 && <span>{stat.name} </span>}
                平均 <span className="font-medium text-[#1d1d1f]">{formatValue ? formatValue(stat.avg) : stat.avg}</span>
                {' / '}中位数 <span className="font-medium text-[#1d1d1f]">{formatValue ? formatValue(stat.med) : stat.med}</span>
              </span>
            ))}
          </div>
        )}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsBarChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={formatDate}
            tick={{ fontSize: 11, fill: '#86868b' }}
            axisLine={{ stroke: '#e5e5e5' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#86868b' }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip content={<CustomTooltip formatValue={formatValue} />} />
          {bars.map((bar) => (
            <Bar
              key={bar.dataKey}
              dataKey={bar.dataKey}
              name={bar.name}
              fill={bar.color}
              stackId={stacked ? 'stack' : undefined}
              radius={[3, 3, 0, 0]}
              maxBarSize={40}
            />
          ))}
        </RechartsBarChart>
      </ResponsiveContainer>
      {/* Legend */}
      {bars.length > 1 && (
        <div className="flex items-center justify-center gap-6 mt-4">
          {bars.map((bar) => (
            <div key={bar.dataKey} className="flex items-center gap-1.5">
              <div
                className="w-2.5 h-2.5 rounded-sm"
                style={{ backgroundColor: bar.color }}
              />
              <span className="text-[12px] text-[#86868b]">{bar.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
