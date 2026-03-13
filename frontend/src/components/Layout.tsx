import React, { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { 
  Shield, 
  BarChart3, 
  AlertTriangle, 
  FileText, 
  Settings, 
  Menu, 
  X,
  Bell,
  User,
  Activity,
  Wifi,
  WifiOff,
  ChevronDown
} from 'lucide-react'
import { useApi } from '../contexts/ApiContext'
import { clsx } from 'clsx'

interface LayoutProps {
  children: React.ReactNode
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const location = useLocation()
  const { isConnected, lastError, retryConnection } = useApi()

  const navigation = [
    { name: 'Dashboard', href: '/dashboard', icon: BarChart3 },
    { name: 'Alerts', href: '/alerts', icon: AlertTriangle },
    { name: 'Reports', href: '/reports', icon: FileText },
    { name: 'Analytics', href: '/analytics', icon: Activity },
    { name: 'Settings', href: '/settings', icon: Settings },
  ]

  const isCurrentPath = (path: string) => {
    return location.pathname === path || location.pathname.startsWith(path + '/')
  }

  return (
    <div className="min-h-screen bg-gray-50 flex overflow-hidden">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 z-40 bg-slate-900/60 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={`
        fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 shadow-2xl transform transition-transform duration-300 ease-in-out lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        <div className="flex items-center justify-between h-16 px-6 border-b border-slate-800">
          <div className="flex items-center space-x-3">
            <div className="p-1.5 bg-primary-600 rounded-lg shadow-lg shadow-primary-900/20">
              <Shield className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight text-sm">Sentinel AML</h1>
              <p className="text-[10px] text-slate-400 uppercase tracking-widest font-semibold">Intelligence</p>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="mt-8 px-4 space-y-1">
          {navigation.map((item) => {
            const Icon = item.icon
            const current = isCurrentPath(item.href)
            
            return (
              <Link
                key={item.name}
                to={item.href}
                onClick={() => setSidebarOpen(false)}
                className={`
                  group flex items-center px-4 py-3 text-sm font-medium rounded-xl transition-all duration-200
                  ${current 
                    ? 'bg-primary-600 text-white shadow-lg shadow-primary-900/40' 
                    : 'text-slate-400 hover:bg-slate-800/50 hover:text-white'
                  }
                `}
              >
                <Icon className={`
                  mr-3 h-5 w-5 flex-shrink-0 transition-colors
                  ${current ? 'text-white' : 'text-slate-500 group-hover:text-slate-300'}
                `} />
                {item.name}
              </Link>
            )
          })}
        </nav>

        {/* Connection status */}
        <div className="absolute bottom-6 left-4 right-4">
          <div className={`
            flex items-center space-x-3 px-4 py-3 rounded-xl text-xs font-semibold border
            ${isConnected 
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
              : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
            }
          `}>
            {isConnected ? (
              <>
                <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></div>
                <span className="flex-1">SYSTEM ONLINE</span>
                <Wifi className="h-3.5 w-3.5" />
              </>
            ) : (
              <>
                <div className="h-2 w-2 rounded-full bg-rose-500 animate-pulse"></div>
                <span className="flex-1">OFFLINE</span>
                <button
                  onClick={retryConnection}
                  className="hover:underline flex items-center"
                >
                  RETRY
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Main content wrapper */}
      <div className="flex-1 flex flex-col min-w-0 lg:pl-64 h-screen overflow-hidden">
        {/* Top Header */}
        <header className="sticky top-0 z-40 bg-white/80 backdrop-blur-xl border-b border-gray-100 px-6 sm:px-8 flex-shrink-0">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden p-2 -ml-2 rounded-xl text-gray-500 hover:text-gray-900 hover:bg-gray-100 transition-all"
              >
                <Menu className="h-6 w-6" />
              </button>
              
              <div className="ml-4 lg:ml-0">
                <h2 className="text-xl font-bold text-gray-900 tracking-tight capitalize">
                  {location.pathname.split('/')[1] || 'Dashboard'}
                </h2>
              </div>
            </div>

            <div className="flex items-center space-x-3 sm:space-x-4">
              {/* Monitoring Status Badge */}
              <div className="hidden md:flex items-center px-3 py-1 bg-primary-50 text-primary-700 rounded-full text-xs font-bold space-x-2">
                <Activity className="h-3 w-3" />
                <span>LIVE TELEMETRY</span>
              </div>

              {/* Notifications */}
              <button className="relative p-2 text-gray-400 hover:text-gray-900 hover:bg-gray-50 rounded-xl transition-all">
                <Bell className="h-5 w-5" />
                <span className="absolute top-2 right-2 h-2 w-2 bg-rose-500 border-2 border-white rounded-full"></span>
              </button>

              <div className="h-8 w-px bg-gray-200 mx-1 sm:mx-2"></div>

              {/* User menu dropdown */}
              <div className="relative">
                <button 
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center space-x-3 p-1 rounded-xl hover:bg-gray-50 transition-all outline-none"
                >
                  <div className="hidden sm:block text-right">
                    <div className="text-sm font-bold text-gray-900 leading-none">Officer Sarah</div>
                    <div className="text-[10px] text-gray-500 font-medium mt-1">L3 Compliance Analyst</div>
                  </div>
                  <div className="relative group">
                    <div className="h-9 w-9 bg-gradient-to-tr from-primary-600 to-indigo-600 rounded-xl shadow-md flex items-center justify-center p-0.5 transform transition-transform group-hover:scale-105">
                      <div className="h-full w-full bg-white rounded-[10px] flex items-center justify-center">
                        <User className="h-5 w-5 text-primary-600" />
                      </div>
                    </div>
                  </div>
                  <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform duration-200 ${userMenuOpen ? 'rotate-180' : ''}`} />
                </button>

                {/* Dropdown Menu */}
                {userMenuOpen && (
                  <>
                    <div 
                      className="fixed inset-0 z-[60]" 
                      onClick={() => setUserMenuOpen(false)}
                    />
                    <div className="absolute right-0 mt-3 w-64 bg-white rounded-2xl shadow-2xl border border-gray-100 py-2 z-[70] animate-slide-down origin-top-right">
                      <div className="px-4 py-3 border-b border-gray-50">
                        <p className="text-xs font-bold text-gray-400 uppercase tracking-widest">Signed in as</p>
                        <p className="text-sm font-bold text-gray-900 mt-1">sarah.compliance@sentinel.ai</p>
                      </div>
                      <div className="p-1">
                        <button className="w-full flex items-center space-x-3 px-3 py-2.5 text-sm text-gray-600 hover:text-primary-600 hover:bg-primary-50 rounded-xl transition-all group">
                          <Settings className="h-4 w-4 group-hover:rotate-45 transition-transform" />
                          <span>Profile Settings</span>
                        </button>
                        <button className="w-full flex items-center space-x-3 px-3 py-2.5 text-sm text-gray-600 hover:text-primary-600 hover:bg-primary-50 rounded-xl transition-all">
                          <Shield className="h-4 w-4" />
                          <span>Security Dashboard</span>
                        </button>
                      </div>
                      <div className="border-t border-gray-50 mt-1 p-1">
                        <button className="w-full flex items-center space-x-3 px-3 py-2.5 text-sm font-bold text-rose-600 hover:bg-rose-50 rounded-xl transition-all">
                          <span>Sign Out</span>
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-gray-50/50">
          <div className="p-6 sm:p-8 max-w-7xl mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}