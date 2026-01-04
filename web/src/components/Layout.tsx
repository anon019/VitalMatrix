import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

const navItems = [
  { path: '/', label: '总览' },
  { path: '/sleep', label: '睡眠' },
  { path: '/readiness', label: '恢复' },
  { path: '/activity', label: '活动' },
  { path: '/training', label: '训练' },
  { path: '/stress', label: '压力' },
]

export default function Layout() {
  const { logout } = useAuth()

  return (
    <div className="min-h-screen bg-[#f5f5f7]">
      {/* Header - Apple style */}
      <header className="bg-white/80 backdrop-blur-xl sticky top-0 z-10 border-b border-[#d2d2d7]/50">
        <div className="max-w-6xl mx-auto px-6">
          {/* Top bar */}
          <div className="h-12 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-[#30D158]" />
              <span className="text-[15px] font-medium text-[#1d1d1f]">健康数据中心</span>
            </div>
            <button
              onClick={logout}
              className="text-[13px] text-[#86868b] hover:text-[#1d1d1f] transition-colors"
            >
              退出
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex gap-6 -mb-px">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  `py-3 text-[13px] font-medium border-b-2 transition-colors ${
                    isActive
                      ? 'text-[#1d1d1f] border-[#1d1d1f]'
                      : 'text-[#86868b] border-transparent hover:text-[#1d1d1f]'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-6 py-6">
        <Outlet />
      </main>
    </div>
  )
}
