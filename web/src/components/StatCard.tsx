interface StatCardProps {
  title: string
  value: string | number | null | undefined
  unit?: string
  color?: string  // Apple color for accent dot
  subtitle?: string
}

export default function StatCard({
  title,
  value,
  unit,
  color = '#1d1d1f',
  subtitle,
}: StatCardProps) {
  return (
    <div className="bg-white rounded-xl p-5">
      {/* Title with color dot */}
      <div className="flex items-center gap-2 mb-3">
        <div
          className="w-2 h-2 rounded-full"
          style={{ backgroundColor: color }}
        />
        <span className="text-[13px] font-medium text-[#86868b]">{title}</span>
      </div>

      {/* Value */}
      <div className="flex items-baseline gap-1">
        <span className="text-[28px] font-semibold text-[#1d1d1f]">
          {value ?? '-'}
        </span>
        {unit && value !== null && value !== undefined && (
          <span className="text-[15px] text-[#86868b]">{unit}</span>
        )}
      </div>

      {/* Subtitle */}
      {subtitle && (
        <div className="mt-1 text-[12px] text-[#86868b]">{subtitle}</div>
      )}
    </div>
  )
}
