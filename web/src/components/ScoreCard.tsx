interface ScoreCardProps {
  title: string
  score: number | null | undefined
  color: string  // Apple color like #5E5CE6
  subtitle?: string
  onClick?: () => void
  /** 是否反向评分（数值越低越好，如压力分钟数） */
  invertScore?: boolean
  /** 反向评分的阈值配置 [优秀上限, 良好上限, 一般上限] */
  invertThresholds?: [number, number, number]
}

function getScoreLabel(score: number | null | undefined): string {
  if (score === null || score === undefined) return '无数据'
  if (score >= 85) return '优秀'
  if (score >= 70) return '良好'
  if (score >= 60) return '一般'
  return '较差'
}

/** 反向评分：数值越低越好（如压力分钟数） */
function getInvertedScoreLabel(
  score: number | null | undefined,
  thresholds: [number, number, number] = [15, 30, 60]
): string {
  if (score === null || score === undefined) return '无数据'
  const [excellent, good, fair] = thresholds
  if (score <= excellent) return '优秀'
  if (score <= good) return '良好'
  if (score <= fair) return '一般'
  return '较差'
}

export default function ScoreCard({
  title,
  score,
  color,
  subtitle,
  onClick,
  invertScore = false,
  invertThresholds,
}: ScoreCardProps) {
  const label = invertScore
    ? getInvertedScoreLabel(score, invertThresholds)
    : getScoreLabel(score)

  // 对于反向评分，进度条逻辑也需要反转（越少进度条越满）
  let percent: number
  if (invertScore && score !== null && score !== undefined) {
    // 反向：0分钟=100%, 60+分钟=0%
    const maxThreshold = invertThresholds?.[2] ?? 60
    percent = Math.max(0, Math.min(100, 100 - (score / maxThreshold) * 100))
  } else {
    percent = score !== null && score !== undefined ? Math.min(score, 100) : 0
  }

  return (
    <div
      onClick={onClick}
      className={`bg-white rounded-xl p-5 ${onClick ? 'cursor-pointer hover:bg-[#fafafa] transition-colors' : ''}`}
    >
      {/* Header: Title left, Score right */}
      <div className="flex items-start justify-between mb-4">
        <span className="text-[13px] font-medium text-[#86868b]">{title}</span>
        <span className="text-[32px] font-semibold text-[#1d1d1f] leading-none">
          {score ?? '-'}
        </span>
      </div>

      {/* Progress bar */}
      <div className="mb-3">
        <div className="h-[6px] bg-[#e5e5e5] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{ width: `${percent}%`, backgroundColor: color }}
          />
        </div>
      </div>

      {/* Footer: Label and subtitle */}
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium" style={{ color }}>
          {label}
        </span>
        {subtitle && (
          <span className="text-[11px] text-[#86868b]">{subtitle}</span>
        )}
      </div>
    </div>
  )
}
