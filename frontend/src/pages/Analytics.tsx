import React, { useState, useEffect } from 'react'
import { 
  TrendingUp, 
  BarChart3, 
  PieChart, 
  Activity, 
  AlertTriangle,
  DollarSign,
  Users,
  Globe,
  Calendar,
  Download,
  RefreshCw
} from 'lucide-react'
import { useApi } from '../contexts/ApiContext'
import { AnalyticsData, LoadingState } from '../types'
import { 
  LineChart, 
  Line, 
  BarChart, 
  Bar, 
  PieChart as RechartsPieChart, 
  Pie, 
  Cell, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  Legend, 
  ResponsiveContainer,
  ComposedChart,
  Area,
  AreaChart
} from 'recharts'
import { format, subDays } from 'date-fns'
import { clsx } from 'clsx'
import { TransactionChart } from '../components/TransactionChart'

export const Analytics: React.FC = () => {
  const { api } = useApi()
  const [analyticsData, setAnalyticsData] = useState<AnalyticsData | null>(null)
  const [loadingState, setLoadingState] = useState<LoadingState>({ isLoading: true })
  const [timeRange, setTimeRange] = useState<'7d' | '30d' | '90d' | '1y'>('30d')

  useEffect(() => {
    loadAnalyticsData(true)
    
    // Auto-refresh for real-time analytics
    const interval = setInterval(() => loadAnalyticsData(false), 3000)
    return () => clearInterval(interval)
  }, [timeRange])

  const loadAnalyticsData = async (initial = false) => {
    try {
      if (initial) setLoadingState({ isLoading: true })
      
      const response = await api.get(`/analytics?period=${timeRange}`)
      setAnalyticsData(response.data.data)
      setLoadingState({ isLoading: false, lastUpdated: new Date().toISOString() })
    } catch (error) {
      console.error('Failed to load analytics data:', error)
      setLoadingState({ isLoading: false, error: 'Failed to load analytics data' })
      
      // Use mock data for demo
      setAnalyticsData(getMockAnalyticsData())
    }
  }

  const getMockAnalyticsData = (): AnalyticsData => {
    const days = timeRange === '7d' ? 7 : timeRange === '30d' ? 30 : timeRange === '90d' ? 90 : 365
    const timeSeries = []
    
    for (let i = days - 1; i >= 0; i--) {
      const date = subDays(new Date(), i)
      timeSeries.push({
        date: format(date, 'MMM dd'),
        alerts: Math.floor(Math.random() * 50) + 10,
        transactions: Math.floor(Math.random() * 5000) + 8000,
        risk_score_avg: Math.random() * 0.3 + 0.1
      })
    }

    return {
      time_series: timeSeries,
      risk_distribution: [
        { level: 'Low', count: 856, percentage: 68.7 },
        { level: 'Medium', count: 245, percentage: 19.6 },
        { level: 'High', count: 123, percentage: 9.9 },
        { level: 'Critical', count: 23, percentage: 1.8 }
      ],
      alert_types: [
        { type: 'Smurfing', count: 342, trend: 12.5 },
        { type: 'Structuring', count: 198, trend: -5.2 },
        { type: 'Layering', count: 156, trend: 8.7 },
        { type: 'Velocity', count: 134, trend: 15.3 },
        { type: 'Integration', count: 89, trend: -2.1 },
        { type: 'Unusual Pattern', count: 328, trend: 22.8 }
      ],
      geographic_distribution: [
        { jurisdiction: 'US-NY', alert_count: 234, risk_level: 0.75 },
        { jurisdiction: 'US-CA', alert_count: 189, risk_level: 0.68 },
        { jurisdiction: 'US-FL', alert_count: 156, risk_level: 0.82 },
        { jurisdiction: 'US-TX', alert_count: 134, risk_level: 0.71 },
        { jurisdiction: 'US-IL', alert_count: 98, risk_level: 0.65 },
        { jurisdiction: 'International', alert_count: 436, risk_level: 0.89 }
      ]
    }
  }

  const exportAnalytics = async () => {
    try {
      const response = await api.get(`/analytics/export?period=${timeRange}`, {
        responseType: 'blob'
      })
      
      const blob = new Blob([response.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `analytics-report-${timeRange}-${format(new Date(), 'yyyy-MM-dd')}.pdf`
      link.click()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to export analytics:', error)
    }
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg">
          <p className="font-medium text-gray-900 mb-2">{label}</p>
          {payload.map((entry: any, index: number) => (
            <p key={index} className="text-sm" style={{ color: entry.color }}>
              {entry.name}: {
                entry.dataKey === 'risk_score_avg' 
                  ? `${(entry.value * 100).toFixed(1)}%`
                  : entry.value.toLocaleString()
              }
            </p>
          ))}
        </div>
      )
    }
    return null
  }

  const COLORS = {
    Low: '#22c55e',
    Medium: '#f59e0b', 
    High: '#ef4444',
    Critical: '#dc2626'
  }

  if (loadingState.isLoading) {
    return (
      <div className="space-y-6">
        <div className="loading-shimmer h-8 w-64 rounded"></div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card p-6">
              <div className="loading-shimmer h-64 w-full rounded"></div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics Dashboard</h1>
          <p className="text-gray-600">Comprehensive insights into AML detection patterns and trends</p>
        </div>
        
        <div className="flex items-center space-x-3">
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value as typeof timeRange)}
            className="input"
          >
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
            <option value="1y">Last year</option>
          </select>
          
          <button
            onClick={() => loadAnalyticsData(true)}
            disabled={loadingState.isLoading}
            className="btn btn-secondary"
          >
            <RefreshCw className={clsx('h-4 w-4 mr-2', loadingState.isLoading && 'animate-spin')} />
            Refresh
          </button>
          
          <button
            onClick={exportAnalytics}
            className="btn btn-primary"
          >
            <Download className="h-4 w-4 mr-2" />
            Export Report
          </button>
        </div>
      </div>

      {analyticsData && (
        <>
          {/* Key Metrics Summary */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="card p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">Total Alerts</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {analyticsData.risk_distribution.reduce((sum, item) => sum + item.count, 0).toLocaleString()}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    {analyticsData.alert_types.reduce((sum, item) => sum + item.trend, 0) > 0 ? '+' : ''}
                    {analyticsData.alert_types.reduce((sum, item) => sum + item.trend, 0).toFixed(1)}% vs previous period
                  </p>
                </div>
                <AlertTriangle className="h-8 w-8 text-danger-500" />
              </div>
            </div>

            <div className="card p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">High Risk Alerts</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {(analyticsData.risk_distribution.find(item => item.level === 'High')?.count || 0) + 
                     (analyticsData.risk_distribution.find(item => item.level === 'Critical')?.count || 0)}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    {((analyticsData.risk_distribution.find(item => item.level === 'High')?.percentage || 0) + 
                      (analyticsData.risk_distribution.find(item => item.level === 'Critical')?.percentage || 0)).toFixed(1)}% of total
                  </p>
                </div>
                <TrendingUp className="h-8 w-8 text-warning-500" />
              </div>
            </div>

            <div className="card p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">Avg Daily Volume</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {Math.round(analyticsData.time_series.reduce((sum, item) => sum + item.transactions, 0) / analyticsData.time_series.length).toLocaleString()}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">Transactions per day</p>
                </div>
                <Activity className="h-8 w-8 text-primary-500" />
              </div>
            </div>

            <div className="card p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">Detection Rate</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {(analyticsData.time_series.reduce((sum, item) => sum + (item.alerts / item.transactions), 0) / analyticsData.time_series.length * 100).toFixed(2)}%
                  </p>
                  <p className="text-xs text-gray-500 mt-1">Alerts per transaction</p>
                </div>
                <BarChart3 className="h-8 w-8 text-success-500" />
              </div>
            </div>
          </div>

          {/* Time Series Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Alerts and Transactions Trend */}
            <div className="lg:col-span-2 card p-6">
              <div className="flex justify-between items-center mb-6">
                <div>
                  <h3 className="text-lg font-bold text-gray-900 tracking-tight">Intelligence & Traffic Trends</h3>
                  <p className="text-xs text-gray-400 font-medium">Monitoring system load and detection patterns</p>
                </div>
              </div>
              
              <div className="h-[400px]">
                <TransactionChart />
              </div>
            </div>

            {/* Risk Distribution */}
            <div className="lg:col-span-1 card p-6">
              <h3 className="text-lg font-bold text-gray-900 mb-6 tracking-tight">Risk Level Distribution</h3>
              
              <div className="h-[400px]">
                <ResponsiveContainer width="100%" height="100%">
                  <RechartsPieChart>
                    <Pie
                      data={analyticsData.risk_distribution}
                      cx="50%"
                      cy="45%"
                      innerRadius={80}
                      outerRadius={110}
                      paddingAngle={5}
                      labelLine={false}
                      label={({ name, percentage }) => `${percentage.toFixed(0)}%`}
                      stroke="none"
                      dataKey="count"
                    >
                      {analyticsData.risk_distribution.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[entry.level as keyof typeof COLORS]} />
                      ))}
                    </Pie>
                    <Tooltip 
                      contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }}
                    />
                    <Legend 
                      verticalAlign="bottom" 
                      align="center"
                      iconType="circle"
                      formatter={(value) => <span className="text-xs font-bold text-gray-600 uppercase tracking-tighter">{value}</span>}
                    />
                  </RechartsPieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Alert Types and Geographic Distribution */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Alert Types */}
            <div className="card p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Alert Types Analysis</h3>
              
              <div className="space-y-4">
                {analyticsData.alert_types.map((type) => (
                  <div key={type.type} className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-sm font-medium text-gray-900">{type.type}</span>
                        <span className="text-sm text-gray-600">{type.count.toLocaleString()}</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-primary-600 h-2 rounded-full"
                          style={{ 
                            width: `${(type.count / Math.max(...analyticsData.alert_types.map(t => t.count))) * 100}%` 
                          }}
                        />
                      </div>
                    </div>
                    <div className={clsx(
                      'ml-4 text-xs font-medium',
                      type.trend > 0 ? 'text-success-600' : 'text-danger-600'
                    )}>
                      {type.trend > 0 ? '+' : ''}{type.trend.toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Geographic Distribution */}
            <div className="card p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Geographic Distribution</h3>
              
              <div className="space-y-4">
                {analyticsData.geographic_distribution.map((geo) => (
                  <div key={geo.jurisdiction} className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-sm font-medium text-gray-900">{geo.jurisdiction}</span>
                        <div className="flex items-center space-x-2">
                          <span className="text-sm text-gray-600">{geo.alert_count.toLocaleString()}</span>
                          <span className={clsx(
                            'text-xs px-2 py-1 rounded-full',
                            geo.risk_level >= 0.8 ? 'bg-danger-100 text-danger-800' :
                            geo.risk_level >= 0.6 ? 'bg-warning-100 text-warning-800' :
                            'bg-success-100 text-success-800'
                          )}>
                            {(geo.risk_level * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className={clsx(
                            'h-2 rounded-full',
                            geo.risk_level >= 0.8 ? 'bg-danger-500' :
                            geo.risk_level >= 0.6 ? 'bg-warning-500' :
                            'bg-success-500'
                          )}
                          style={{ 
                            width: `${(geo.alert_count / Math.max(...analyticsData.geographic_distribution.map(g => g.alert_count))) * 100}%` 
                          }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Model Performance Metrics */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Model Performance Insights</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center">
                <div className="text-3xl font-bold text-primary-600 mb-2">94.7%</div>
                <div className="text-sm text-gray-600">Model Accuracy</div>
                <div className="text-xs text-success-600 mt-1">+2.3% vs last month</div>
              </div>
              
              <div className="text-center">
                <div className="text-3xl font-bold text-warning-600 mb-2">3.2%</div>
                <div className="text-sm text-gray-600">False Positive Rate</div>
                <div className="text-xs text-success-600 mt-1">-0.8% vs last month</div>
              </div>
              
              <div className="text-center">
                <div className="text-3xl font-bold text-success-600 mb-2">145ms</div>
                <div className="text-sm text-gray-600">Avg Processing Time</div>
                <div className="text-xs text-success-600 mt-1">-12ms vs last month</div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}