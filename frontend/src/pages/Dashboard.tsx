import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { 
  AlertTriangle, 
  TrendingUp, 
  FileText, 
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  Shield,
  DollarSign,
  Users
} from 'lucide-react'
import { useApi } from '../contexts/ApiContext'
import { DashboardMetrics, Alert, LoadingState } from '../types'
import { MetricCard } from '../components/MetricCard'
import { AlertsList } from '../components/AlertsList'
import { TransactionChart } from '../components/TransactionChart'
import { RiskDistributionChart } from '../components/RiskDistributionChart'
import { RealTimePredictions } from '../components/RealTimePredictions'

export const Dashboard: React.FC = () => {
  const { api } = useApi()
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null)
  const [recentAlerts, setRecentAlerts] = useState<Alert[]>([])
  const [loadingState, setLoadingState] = useState<LoadingState>({ isLoading: true })

  useEffect(() => {
    loadDashboardData(true)
    
    // Set up auto-refresh every 3 seconds for real-time feel
    const interval = setInterval(() => loadDashboardData(false), 3000)
    return () => clearInterval(interval)
  }, [])

  const loadDashboardData = async (initial = false) => {
    try {
      if (initial) setLoadingState({ isLoading: true })
      
      const [metricsResponse, alertsResponse] = await Promise.all([
        api.get('/dashboard/metrics'),
        api.get('/alerts?limit=5&sort=created_at&order=desc')
      ])
      
      setMetrics(metricsResponse.data.data)
      setRecentAlerts(alertsResponse.data.data)
      setLoadingState({ 
        isLoading: false, 
        lastUpdated: new Date().toISOString() 
      })
    } catch (error) {
      console.error('Failed to load dashboard data:', error)
      setLoadingState({ 
        isLoading: false, 
        error: 'Failed to load dashboard data' 
      })
      
      // Use mock data for demo purposes
      setMetrics(getMockMetrics())
      setRecentAlerts(getMockAlerts())
    }
  }

  const getMockMetrics = (): DashboardMetrics => ({
    alerts: {
      total: 1247,
      new: 23,
      investigating: 45,
      high_risk: 12,
      trend: 8.5
    },
    transactions: {
      total_today: 15420,
      flagged_today: 89,
      volume_usd: 2450000,
      trend: -2.3
    },
    reports: {
      pending: 8,
      filed_this_month: 34,
      avg_resolution_time: 4.2,
      trend: -12.5
    },
    system: {
      model_accuracy: 94.7,
      false_positive_rate: 3.2,
      processing_latency: 145,
      uptime: 99.8
    }
  })

  const getMockAlerts = (): Alert[] => [
    {
      alert_id: 'ALT-2024-001',
      case_id: 'CASE-2024-001',
      risk_score: 0.89,
      risk_level: 'high',
      alert_type: 'smurfing',
      status: 'new',
      priority: 'high',
      created_at: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
      updated_at: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
      accounts: [],
      transactions: [],
      gnn_explanation: 'Multiple small transactions below reporting threshold detected',
      confidence_score: 0.89,
      pattern_description: 'Structured deposits across multiple accounts',
      regulatory_flags: ['BSA', 'CTR']
    },
    {
      alert_id: 'ALT-2024-002',
      case_id: 'CASE-2024-002',
      risk_score: 0.76,
      risk_level: 'medium',
      alert_type: 'velocity',
      status: 'investigating',
      priority: 'medium',
      created_at: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
      updated_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
      assigned_to: 'analyst@company.com',
      accounts: [],
      transactions: [],
      gnn_explanation: 'Unusual transaction velocity detected',
      confidence_score: 0.76,
      pattern_description: 'High frequency transfers in short time window',
      regulatory_flags: ['AML']
    }
  ]

  if (loadingState.isLoading && !metrics) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card p-6">
              <div className="loading-shimmer h-4 w-24 mb-2 rounded"></div>
              <div className="loading-shimmer h-8 w-16 mb-2 rounded"></div>
              <div className="loading-shimmer h-3 w-20 rounded"></div>
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
          <h1 className="text-2xl font-bold text-gray-900">AML Dashboard</h1>
          <p className="text-gray-600">Real-time monitoring of suspicious activities</p>
        </div>
        <div className="flex items-center space-x-2 text-sm text-gray-500">
          <Clock className="h-4 w-4" />
          <span>
            Last updated: {loadingState.lastUpdated 
              ? new Date(loadingState.lastUpdated).toLocaleTimeString()
              : 'Never'
            }
          </span>
        </div>
      </div>

      {/* Key Metrics */}
      {metrics && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <MetricCard
            title="Active Alerts"
            value={metrics.alerts.total.toLocaleString()}
            change={metrics.alerts.trend}
            icon={AlertTriangle}
            color="danger"
            subtitle={`${metrics.alerts.new} new, ${metrics.alerts.high_risk} high risk`}
          />
          
          <MetricCard
            title="Daily Transactions"
            value={metrics.transactions.total_today.toLocaleString()}
            change={metrics.transactions.trend}
            icon={Activity}
            color="primary"
            subtitle={`${metrics.transactions.flagged_today} flagged (${(metrics.transactions.flagged_today / metrics.transactions.total_today * 100).toFixed(1)}%)`}
          />
          
          <MetricCard
            title="Transaction Volume"
            value={`$${(metrics.transactions.volume_usd / 1000000).toFixed(1)}M`}
            change={metrics.transactions.trend}
            icon={DollarSign}
            color="success"
            subtitle="USD processed today"
          />
          
          <MetricCard
            title="Model Accuracy"
            value={`${metrics.system.model_accuracy}%`}
            change={0}
            icon={Shield}
            color="primary"
            subtitle={`${metrics.system.false_positive_rate}% false positive rate`}
          />
        </div>
      )}

      {/* Charts and Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Transaction Trends */}
        <div className="lg:col-span-2 card p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold text-gray-900">Transaction Trends</h3>
            <Link 
              to="/analytics" 
              className="text-sm text-primary-600 hover:text-primary-700 flex items-center"
            >
              View Analytics <ArrowUpRight className="h-4 w-4 ml-1" />
            </Link>
          </div>
          <div className="h-[320px]">
            <TransactionChart />
          </div>
        </div>
        <div className="card p-6">
          <RealTimePredictions />
        </div>
      </div>

      {/* Risk Distribution and Recent Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 card p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Risk Distribution</h3>
          <RiskDistributionChart />
        </div>
        <div className="lg:col-span-2 card p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold text-gray-900">Recent Alerts</h3>
            <Link 
              to="/alerts" 
              className="text-sm text-primary-600 hover:text-primary-700 flex items-center"
            >
              View All <ArrowUpRight className="h-4 w-4 ml-1" />
            </Link>
          </div>
          <AlertsList alerts={recentAlerts} compact />
        </div>
      </div>

      {/* System Status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* System Status */}
        <div className="card p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">System Status</h3>
          {metrics && (
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">System Uptime</span>
                <div className="flex items-center space-x-2">
                  <div className="h-2 w-2 bg-success-500 rounded-full"></div>
                  <span className="text-sm font-medium">{metrics.system.uptime}%</span>
                </div>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Processing Latency</span>
                <span className="text-sm font-medium">{metrics.system.processing_latency}ms</span>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Pending Reports</span>
                <div className="flex items-center space-x-2">
                  {metrics.reports.pending > 0 && (
                    <div className="h-2 w-2 bg-warning-500 rounded-full"></div>
                  )}
                  <span className="text-sm font-medium">{metrics.reports.pending}</span>
                </div>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Avg Resolution Time</span>
                <span className="text-sm font-medium">{metrics.reports.avg_resolution_time}h</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="card p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            to="/alerts?status=new"
            className="flex items-center p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <AlertTriangle className="h-8 w-8 text-danger-500 mr-3" />
            <div>
              <div className="font-medium text-gray-900">Review New Alerts</div>
              <div className="text-sm text-gray-500">{metrics?.alerts.new || 0} pending review</div>
            </div>
          </Link>
          
          <Link
            to="/reports?status=pending"
            className="flex items-center p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <FileText className="h-8 w-8 text-warning-500 mr-3" />
            <div>
              <div className="font-medium text-gray-900">Pending Reports</div>
              <div className="text-sm text-gray-500">{metrics?.reports.pending || 0} awaiting submission</div>
            </div>
          </Link>
          
          <Link
            to="/analytics"
            className="flex items-center p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <TrendingUp className="h-8 w-8 text-primary-500 mr-3" />
            <div>
              <div className="font-medium text-gray-900">View Analytics</div>
              <div className="text-sm text-gray-500">Detailed insights & trends</div>
            </div>
          </Link>
        </div>
      </div>
    </div>
  )
}