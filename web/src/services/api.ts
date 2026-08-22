import axios from 'axios'
import type {
  AIRecommendation,
  AuthResponse,
  DashboardData,
  MealListResponse,
  MealAnalysisStatus,
  MealRecommendationTrigger,
  MealPosterResponse,
  MealRecord,
  NutritionDailySummary,
  TrendsOverview,
  WeeklyNutritionTrend,
} from '@/types'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器 - 添加 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器 - 处理认证错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// 认证
export const auth = {
  login: async (password: string): Promise<AuthResponse> => {
    const response = await api.post<AuthResponse>('/auth/simple-login', { password })
    return response.data
  },
}

// Dashboard
export const dashboard = {
  getToday: async (): Promise<DashboardData> => {
    const response = await api.get<DashboardData>('/dashboard/today')
    return response.data
  },
}

// 趋势数据
const trendsCache = new Map<string, { data: TrendsOverview; expiresAt: number }>()
const trendsInFlight = new Map<string, Promise<TrendsOverview>>()
export const trends = {
  getOverview: async (startDate: string, endDate: string): Promise<TrendsOverview> => {
    const key = `${startDate}:${endDate}`
    const cached = trendsCache.get(key)
    if (cached && cached.expiresAt > Date.now()) return cached.data
    const pending = trendsInFlight.get(key)
    if (pending) return pending

    const request = api.get<TrendsOverview>('/trends/overview', {
      params: { start_date: startDate, end_date: endDate },
    }).then((response) => {
      trendsCache.set(key, { data: response.data, expiresAt: Date.now() + 60_000 })
      return response.data
    }).finally(() => {
      trendsInFlight.delete(key)
    })
    trendsInFlight.set(key, request)
    return request
  },
}

export const nutrition = {
  getMeals: async (page = 1, pageSize = 20): Promise<MealListResponse> => {
    const response = await api.get<MealListResponse>('/nutrition/meals', {
      params: { page, page_size: pageSize },
    })
    return response.data
  },
  getDaily: async (date: string): Promise<NutritionDailySummary | null> => {
    const response = await api.get<NutritionDailySummary | null>(`/nutrition/daily/${date}`)
    return response.data
  },
  getWeekly: async (): Promise<WeeklyNutritionTrend> => {
    const response = await api.get<WeeklyNutritionTrend>('/nutrition/weekly')
    return response.data
  },
  getMeal: async (mealId: string): Promise<MealRecord> => {
    const response = await api.get<MealRecord>(`/nutrition/meals/${mealId}`)
    return response.data
  },
  getAnalysisStatus: async (mealId: string): Promise<MealAnalysisStatus> => {
    const response = await api.get<MealAnalysisStatus>(`/nutrition/meals/${mealId}/analysis-status`)
    return response.data
  },
  generateRecommendations: async (mealId: string): Promise<MealRecommendationTrigger> => {
    const response = await api.post<MealRecommendationTrigger>(`/nutrition/meals/${mealId}/recommendations`)
    return response.data
  },
  upload: async (form: FormData): Promise<MealRecord> => {
    const response = await api.post<MealRecord>('/nutrition/upload', form, {
      timeout: 150_000,
      headers: { 'Content-Type': undefined },
    })
    return response.data
  },
  generatePoster: async (mealId: string): Promise<MealPosterResponse> => {
    const response = await api.post<MealPosterResponse>(`/nutrition/meals/${mealId}/poster`, null, {
      timeout: 120_000,
    })
    return response.data
  },
  reanalyze: async (mealId: string): Promise<MealRecord> => {
    const response = await api.post<MealRecord>(`/nutrition/meals/${mealId}/reanalyze`, null, {
      timeout: 150_000,
    })
    return response.data
  },
}

export const ai = {
  getToday: async (): Promise<AIRecommendation | null> => {
    const response = await api.get<AIRecommendation | null>('/ai/recommendation/today')
    return response.data
  },
  regenerate: async (date: string): Promise<AIRecommendation> => {
    const response = await api.post<AIRecommendation>('/ai/regenerate', { date }, { timeout: 150_000 })
    return response.data
  },
  chat: async (messages: Array<{ role: 'user' | 'assistant'; content: string }>) => {
    const response = await api.post<{ message: string; usage?: Record<string, number> }>(
      '/ai/chat',
      { messages },
      { timeout: 150_000 },
    )
    return response.data
  },
}

export default api
