export interface AuthResponse {
  access_token: string
  token_type: string
  user_id: string
  is_new_user: boolean
}

export interface RecommendationSection {
  title: string
  emoji: string
  items: string[]
}

export interface HealthEducation {
  title: string
  emoji: string
  sections: Array<{
    subtitle: string
    highlight: boolean
    items: Array<{ label: string; content: string }>
  }>
}

export interface AIRecommendation {
  id: string
  date: string
  provider: string
  model: string | null
  summary: string
  yesterday_review: RecommendationSection
  today_recommendation: RecommendationSection
  health_education: HealthEducation
  created_at: string
  requested_date?: string
  source_date?: string
  is_stale: boolean
  generation_metadata?: {
    prompt_version?: string
    data_completeness?: Record<string, boolean | number>
  } | null
}

export interface NutritionDailySummary {
  id: string
  user_id: string
  date: string
  total_calories: number | null
  total_protein: number | null
  total_carbs: number | null
  total_fat: number | null
  total_fiber: number | null
  meals_count: number
  breakfast_calories: number | null
  lunch_calories: number | null
  dinner_calories: number | null
  snack_calories: number | null
  flags: Record<string, boolean> | null
  created_at: string
  updated_at: string
}

export interface FoodItem {
  id: string
  meal_id: string
  food_name: string
  category: string | null
  estimated_weight: number | null
  calories: number | null
  protein: number | null
  carbs: number | null
  fat: number | null
  fiber: number | null
  sodium: number | null
  sugar: number | null
  notes: string | null
  created_at: string
}

export interface MealRecord {
  id: string
  user_id: string
  meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  meal_time: string
  notes: string | null
  photo_path: string | null
  thumbnail_path: string | null
  total_calories: number | null
  total_protein: number | null
  total_carbs: number | null
  total_fat: number | null
  total_fiber: number | null
  ai_model: string | null
  current_ai_model: string
  analysis_is_legacy: boolean
  analysis_status: 'pending' | 'processing' | 'completed' | 'failed'
  recommendation_status: 'pending' | 'processing' | 'completed' | 'failed'
  recommendation_attempts: number
  analysis_error: string | null
  analysis_started_at: string | null
  analysis_completed_at: string | null
  recommendation_updated_at: string | null
  ai_analysis: NutritionAnalysis | null
  food_items: FoodItem[]
  created_at: string
  updated_at: string
}

export interface RecommendedDish {
  name?: string
  portion?: string
  calories?: number
  protein?: number
  ingredients?: string[]
  cooking_steps?: string[]
  health_benefit?: string
  nutrition?: { calories?: number; protein?: number; carbs?: number; fat?: number }
}

export interface RecommendedMealPlan {
  meal_name?: string
  timing?: string
  total_calories?: number
  flavor_profile?: string
  experience_note?: string
  why_this_menu?: string
  dishes?: RecommendedDish[]
}

export interface NutritionAnalysis {
  _ai_model?: string
  _schema_version?: string
  _search_grounded?: boolean
  nutrition_summary?: {
    calorie_range_low?: number
    calorie_range_high?: number
    estimate_note?: string
  }
  analysis_quality?: {
    overall_confidence?: 'high' | 'medium' | 'low'
    needs_user_confirmation?: boolean
    questions?: string[]
  }
  nutrition_analysis?: {
    overall_score?: number
    overall_rating?: string
    overall_comment?: string
  }
  health_insights?: {
    strengths?: string[]
    weaknesses?: string[]
    risk_level?: string
    uncertainty_notes?: string[]
  }
  recommendations?: {
    status?: 'pending' | 'processing' | 'completed' | 'failed'
    summary?: string
    action_items?: Array<{ priority?: string; action?: string; rationale?: string }>
    next_meal_recipes?: RecommendedMealPlan[]
    next_meals?: RecommendedMealPlan[]
    sleep_support?: string
  }
}

export interface MealAnalysisStatus {
  meal_id: string
  analysis_status: MealRecord['analysis_status']
  recommendation_status: MealRecord['recommendation_status']
  recommendation_attempts: number
  analysis_error: string | null
  analysis_completed_at: string | null
  recommendation_updated_at: string | null
}

export type MealRecommendationTrigger = Pick<
  MealAnalysisStatus,
  'meal_id' | 'analysis_status' | 'recommendation_status'
>

export interface MealListResponse {
  meals: MealRecord[]
  total: number
  page: number
  page_size: number
}

export interface MealPosterResponse {
  poster_url: string
  generated: boolean
  model: string
  verified_metrics: Record<string, number | string | null>
  content_digest: string
  layout_version: string
}

export interface WeeklyNutritionTrend {
  start_date: string
  end_date: string
  daily_data: NutritionDailySummary[]
  weekly_avg_calories: number
  weekly_avg_protein: number
  weekly_avg_carbs: number
  weekly_avg_fat: number
  recorded_days: number
  expected_days: number
}

export interface OuraSummary {
  sleep_score?: number | null
  readiness_score?: number | null
  activity_score?: number | null
  stress_high_min?: number | null
  total_sleep_hours?: number | null
  average_hrv?: number | null
  sleep_date?: string | null
  readiness_date?: string | null
  activity_date?: string | null
  stress_date?: string | null
}

export interface DashboardData {
  date: string
  recommendation: AIRecommendation | null
  training: Record<string, unknown> | null
  weekly_training: Record<string, unknown> | null
  oura_today: OuraSummary | null
  oura_yesterday: OuraSummary | null
  nutrition_today: NutritionDailySummary | null
  nutrition_yesterday: NutritionDailySummary | null
}

export interface TrendsOverview {
  dates: string[]
  sleep: SleepArrays
  readiness: ReadinessArrays
  activity: ActivityArrays
  training: TrainingDay[]
  stress: StressArrays
  nutrition: NutritionArrays
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

export interface ReadinessArrays { scores: (number | null)[] }
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
export interface NutritionArrays {
  calories: (number | null)[]
  protein_g: (number | null)[]
  carbs_g: (number | null)[]
  fat_g: (number | null)[]
  meals_count: number[]
}
export interface TrainingDay {
  date: string
  zone2_min: number | null
  hi_min: number | null
  trimp: number | null
  total_min: number | null
}

export type TimeRange = '7d' | '30d' | '90d' | 'custom'
export interface DateRange { startDate: string; endDate: string }
