import axios from 'axios'
import type { AuthResponse, DashboardData, TrendsOverview } from '@/types'

const api = axios.create({
  baseURL: '/api/v1',
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
export const trends = {
  getOverview: async (startDate: string, endDate: string): Promise<TrendsOverview> => {
    const response = await api.get<TrendsOverview>('/trends/overview', {
      params: { start_date: startDate, end_date: endDate },
    })
    return response.data
  },
}

export default api
