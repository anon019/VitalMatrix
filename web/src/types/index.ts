// API 响应类型

// 认证
export interface AuthResponse {
  access_token: string
  token_type: string
}

// Dashboard 数据
export interface DashboardData {
  date: string
  summary: DaySummary
  yesterday_training: TrainingSummary | null
  weekly_training: WeeklyTraining
  ai_suggestion: AISuggestion | null
  health_report: HealthReport | null
}

export interface DaySummary {
  date: string
  sleep_score: number | null
  readiness_score: number | null
  activity_score: number | null
  stress_level: string | null
  training_load: number | null
}

export interface TrainingSummary {
  date: string
  total_duration_min: number
  zone2_min: number
  zone4_5_min: number
  sessions_count: number
  trimp: number | null
}

export interface WeeklyTraining {
  total_min: number
  zone2_min: number
  hi_min: number
  sessions: number
  avg_trimp: number | null
}

export interface AISuggestion {
  id: string
  date: string
  summary: string
  training_advice: string
  risk_assessment: string
  action_items: string[]
  created_at: string
}

export interface HealthReport {
  id: string
  date: string
  report_type: string
  content: string
  created_at: string
}

// 趋势数据 - 匹配实际 API 响应格式
export interface TrendsOverview {
  dates: string[]
  sleep: SleepArrays
  readiness: ReadinessArrays
  activity: ActivityArrays
  training: TrainingDay[]
  stress: StressArrays
}

export interface SleepArrays {
  scores: (number | null)[]
  deep_sleep_min: (number | null)[]
  rem_sleep_min: (number | null)[]
  light_sleep_min: (number | null)[]
  efficiency: (number | null)[]
  hrv: (number | null)[]
  resting_hr: (number | null)[]
}

export interface ReadinessArrays {
  scores: (number | null)[]
}

export interface ActivityArrays {
  scores: (number | null)[]
  steps: (number | null)[]
  active_calories: (number | null)[]
  sedentary_min: (number | null)[]
}

export interface StressArrays {
  high_min: (number | null)[]
  recovery_min: (number | null)[]
}

export interface TrainingDay {
  date: string
  zone2_min: number | null
  hi_min: number | null
  trimp: number | null
  total_min: number | null
}

// 时间范围
export type TimeRange = '7d' | '30d' | '90d' | 'custom'

export interface DateRange {
  startDate: string
  endDate: string
}
