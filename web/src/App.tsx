import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from '@/hooks/useAuth'
import Layout from '@/components/Layout'

const Login = lazy(() => import('@/pages/Login'))
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Nutrition = lazy(() => import('@/pages/Nutrition'))
const AI = lazy(() => import('@/pages/AI'))
const Sleep = lazy(() => import('@/pages/Sleep'))
const Readiness = lazy(() => import('@/pages/Readiness'))
const Activity = lazy(() => import('@/pages/Activity'))
const Stress = lazy(() => import('@/pages/Stress'))
const Training = lazy(() => import('@/pages/Training'))

function PageFallback() {
  return <div className="min-h-64 flex items-center justify-center text-[#86868b]">加载中...</div>
}

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-500">加载中...</div>
      </div>
    )
  }

  return isAuthenticated ? <>{children}</> : <Navigate to="/login" />
}

function AppRoutes() {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-500">加载中...</div>
      </div>
    )
  }

  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" /> : <Login />}
      />
      <Route
        path="/"
        element={
          <PrivateRoute>
            <Layout />
          </PrivateRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="nutrition" element={<Nutrition />} />
        <Route path="ai" element={<AI />} />
        <Route path="sleep" element={<Sleep />} />
        <Route path="readiness" element={<Readiness />} />
        <Route path="activity" element={<Activity />} />
        <Route path="stress" element={<Stress />} />
        <Route path="training" element={<Training />} />
      </Route>
      <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Suspense>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
