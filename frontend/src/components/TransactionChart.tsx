import React, { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Area, AreaChart, ComposedChart, Bar } from 'recharts'
import { useApi } from '../contexts/ApiContext'
import { clsx } from 'clsx'
import { Info, Zap, Calendar } from 'lucide-react'

interface ChartData {
  date?: string
  time?: string
  transactions: number
  alerts: number
  risk_score: number
  risk_score_avg?: number // Alias from analytics endpoint
}

export const TransactionChart: React.FC = () => {
  const { api } = useApi()
  const [data, setData] = useState<ChartData[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'30d' | 'live'>('live')
  const [visibleMetrics, setVisibleMetrics] = useState({
    transactions: true,
    alerts: true,
    risk: true
  })

  useEffect(() => {
    loadChartData()
    
    let interval: any
    if (activeTab === 'live') {
      interval = setInterval(loadChartData, 3000)
    }
    
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [activeTab])

  const loadChartData = async () => {
    try {
      const endpoint = activeTab === 'live' ? '/analytics/live-traffic' : '/analytics/time-series?period=30d'
      const response = await api.get(endpoint)
      // Normalize data if coming from different endpoints
      const normalizedData = response.data.data.map((item: any) => ({
        ...item,
        risk_score: item.risk_score || item.risk_score_avg || 0
      }))
      setData(normalizedData)
    } catch (error) {
      console.error('Failed to load chart data:', error)
    } finally {
      setLoading(false)
    }
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white/95 backdrop-blur-md p-4 border border-gray-100 rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.1)] ring-1 ring-black/5">
          <p className="font-bold text-gray-900 mb-3 flex items-center text-xs uppercase tracking-widest">
            {activeTab === 'live' ? <Zap className="h-3 w-3 mr-2 text-primary-500" /> : <Calendar className="h-3 w-3 mr-2 text-primary-500" />}
            {label}
          </p>
          <div className="space-y-2">
            {payload.map((entry: any, index: number) => (
              <div key={index} className="flex items-center justify-between space-x-6">
                <div className="flex items-center">
                  <div className="w-2 h-2 rounded-full mr-2" style={{ backgroundColor: entry.color }}></div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{entry.name}</span>
                </div>
                <span className="text-sm font-black tabular-nums" style={{ color: entry.color }}>
                  {entry.name.includes('Risk') 
                    ? `${(entry.value * 100).toFixed(1)}%`
                    : entry.value.toLocaleString()
                  }
                </span>
              </div>
            ))}
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div className="flex flex-col h-full">
      {/* Enhanced Header with Tabbed Navigation and Legend Toggles */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-8 gap-4">
        <div className="flex p-1.5 bg-gray-100/80 backdrop-blur rounded-2xl self-start">
          <button
            onClick={() => setActiveTab('30d')}
            className={clsx(
              'px-5 py-2 text-xs font-bold rounded-xl transition-all duration-300',
              activeTab === '30d' 
                ? 'bg-white text-gray-900 shadow-[0_4px_12px_rgba(0,0,0,0.05)] scale-100' 
                : 'text-gray-500 hover:text-gray-900 scale-95 opacity-70'
            )}
          >
            30 Days Historical
          </button>
          <button
            onClick={() => setActiveTab('live')}
            className={clsx(
              'px-5 py-2 text-xs font-bold rounded-xl transition-all duration-300 flex items-center',
              activeTab === 'live' 
                ? 'bg-white text-primary-600 shadow-[0_4px_12px_rgba(0,0,0,0.05)] scale-100' 
                : 'text-gray-500 hover:text-gray-900 scale-95 opacity-70'
            )}
          >
            {activeTab === 'live' && (
              <span className="relative flex h-2 w-2 mr-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-primary-500"></span>
              </span>
            )}
            Live Traffic
          </button>
        </div>

        <div className="flex items-center space-x-3">
          <button 
            onClick={() => setVisibleMetrics(v => ({...v, transactions: !v.transactions}))}
            className={clsx(
              "flex items-center px-3 py-1.5 rounded-full border text-[10px] font-bold uppercase tracking-wider transition-all",
              visibleMetrics.transactions ? "bg-blue-50 text-blue-700 border-blue-200" : "bg-gray-50 text-gray-400 border-gray-200 line-through opacity-50"
            )}
          >
            Transactions
          </button>
          <button 
            onClick={() => setVisibleMetrics(v => ({...v, alerts: !v.alerts}))}
            className={clsx(
              "flex items-center px-3 py-1.5 rounded-full border text-[10px] font-bold uppercase tracking-wider transition-all",
              visibleMetrics.alerts ? "bg-red-50 text-red-700 border-red-200" : "bg-gray-50 text-gray-400 border-gray-200 line-through opacity-50"
            )}
          >
            Alerts
          </button>
          <button 
            onClick={() => setVisibleMetrics(v => ({...v, risk: !v.risk}))}
            className={clsx(
              "flex items-center px-3 py-1.5 rounded-full border text-[10px] font-bold uppercase tracking-wider transition-all",
              visibleMetrics.risk ? "bg-amber-50 text-amber-700 border-amber-200" : "bg-gray-50 text-gray-400 border-gray-200 line-through opacity-50"
            )}
          >
            Risk Avg
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-[220px]">
        {loading && data.length === 0 ? (
          <div className="h-full w-full flex items-center justify-center">
             <div className="loading-shimmer h-full w-full rounded-3xl" />
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorTransactions" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorAlerts" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.15}/>
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="6 6" vertical={false} stroke="#f1f5f9" />
              <XAxis 
                dataKey={activeTab === 'live' ? 'time' : 'date'} 
                stroke="#94a3b8"
                fontSize={10}
                fontWeight={700}
                axisLine={false}
                tickLine={false}
                tickMargin={15}
              />
              <YAxis 
                yAxisId="left"
                stroke="#94a3b8"
                fontSize={10}
                fontWeight={700}
                axisLine={false}
                tickLine={false}
                tickMargin={15}
              />
              <YAxis 
                yAxisId="right"
                orientation="right"
                stroke="#94a3b8"
                fontSize={10}
                fontWeight={700}
                axisLine={false}
                tickLine={false}
                tickFormatter={(value) => `${(value * 100).toFixed(0)}%`}
                hide={!visibleMetrics.risk}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ stroke: '#e2e8f0', strokeWidth: 1, strokeDasharray: '4 4' }} />
              
              {visibleMetrics.transactions && (
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="transactions"
                  stroke="#3b82f6"
                  strokeWidth={3}
                  fillOpacity={1}
                  fill="url(#colorTransactions)"
                  name="Transactions"
                  animationDuration={activeTab === 'live' ? 0 : 800}
                />
              )}
              
              {(activeTab === 'live' && visibleMetrics.alerts) ? (
                <Line
                  yAxisId="left"
                  type="stepAfter"
                  dataKey="alerts"
                  stroke="#ef4444"
                  strokeWidth={3}
                  dot={false}
                  name="Alerts"
                  animationDuration={0}
                />
              ) : (
                visibleMetrics.alerts && (
                   <Area
                    yAxisId="left"
                    type="monotone"
                    dataKey="alerts"
                    stroke="#ef4444"
                    strokeWidth={3}
                    fillOpacity={1}
                    fill="url(#colorAlerts)"
                    name="Alerts"
                    animationDuration={800}
                  />
                )
              )}

              {visibleMetrics.risk && (
                <Line 
                  yAxisId="right"
                  type="monotone"
                  dataKey="risk_score"
                  stroke="#f59e0b"
                  strokeWidth={3}
                  dot={activeTab !== 'live'}
                  name="Avg Risk Score"
                  animationDuration={activeTab === 'live' ? 0 : 1200}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}