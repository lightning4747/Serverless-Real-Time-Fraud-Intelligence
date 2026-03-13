import React, { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { 
  Search, 
  Filter, 
  Download, 
  RefreshCw, 
  Plus,
  ChevronDown,
  X,
  AlertTriangle,
  Clock,
  User,
  Eye
} from 'lucide-react'
import { useApi } from '../contexts/ApiContext'
import { Alert, AlertFilters, PaginatedResponse, LoadingState, TableSort } from '../types'
import { AlertsList } from '../components/AlertsList'
import { Pagination } from '../components/Pagination'
import { formatDistanceToNow } from 'date-fns'
import { clsx } from 'clsx'

export const Alerts: React.FC = () => {
  const { api } = useApi()
  const [searchParams, setSearchParams] = useSearchParams()
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [pagination, setPagination] = useState({ page: 1, limit: 20, total: 0, total_pages: 0 })
  const [loadingState, setLoadingState] = useState<LoadingState>({ isLoading: true })
  const [searchTerm, setSearchTerm] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [sort, setSort] = useState<TableSort>({ field: 'created_at', direction: 'desc' })
  
  const [filters, setFilters] = useState<AlertFilters>({
    status: searchParams.get('status')?.split(',') as Alert['status'][] || [],
    risk_level: searchParams.get('risk_level')?.split(',') as Alert['risk_level'][] || [],
    alert_type: searchParams.get('alert_type')?.split(',') as Alert['alert_type'][] || [],
    date_from: searchParams.get('date_from') || '',
    date_to: searchParams.get('date_to') || '',
    assigned_to: searchParams.get('assigned_to') || '',
    account_id: searchParams.get('account_id') || ''
  })

  useEffect(() => {
    loadAlerts()
  }, [searchParams, sort])

  useEffect(() => {
    // Update URL params when filters change
    const params = new URLSearchParams()
    
    if (filters.status?.length) params.set('status', filters.status.join(','))
    if (filters.risk_level?.length) params.set('risk_level', filters.risk_level.join(','))
    if (filters.alert_type?.length) params.set('alert_type', filters.alert_type.join(','))
    if (filters.date_from) params.set('date_from', filters.date_from)
    if (filters.date_to) params.set('date_to', filters.date_to)
    if (filters.assigned_to) params.set('assigned_to', filters.assigned_to)
    if (filters.account_id) params.set('account_id', filters.account_id)
    if (searchTerm) params.set('search', searchTerm)
    
    params.set('page', pagination.page.toString())
    params.set('limit', pagination.limit.toString())
    params.set('sort', sort.field)
    params.set('order', sort.direction)
    
    setSearchParams(params)
  }, [filters, searchTerm, pagination.page, pagination.limit, sort])

  const loadAlerts = async () => {
    try {
      setLoadingState({ isLoading: true })
      
      const params = new URLSearchParams(searchParams)
      const response = await api.get(`/alerts?${params.toString()}`)
      
      const data: PaginatedResponse<Alert> = response.data
      setAlerts(data.data)
      setPagination(data.pagination)
      setLoadingState({ isLoading: false, lastUpdated: new Date().toISOString() })
    } catch (error) {
      console.error('Failed to load alerts:', error)
      setLoadingState({ isLoading: false, error: 'Failed to load alerts' })
      
      // Use mock data for demo
      setAlerts(getMockAlerts())
      setPagination({ page: 1, limit: 20, total: 50, total_pages: 3 })
    }
  }

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
      gnn_explanation: 'Multiple small transactions below reporting threshold detected across connected accounts',
      confidence_score: 0.89,
      pattern_description: 'Structured deposits pattern: 15 transactions under $9,000 within 48 hours',
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
      gnn_explanation: 'Unusual transaction velocity detected in account cluster',
      confidence_score: 0.76,
      pattern_description: 'High frequency transfers: 25 transactions in 2-hour window',
      regulatory_flags: ['AML']
    },
    {
      alert_id: 'ALT-2024-003',
      case_id: 'CASE-2024-003',
      risk_score: 0.92,
      risk_level: 'critical',
      alert_type: 'layering',
      status: 'escalated',
      priority: 'urgent',
      created_at: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
      updated_at: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
      assigned_to: 'senior.analyst@company.com',
      accounts: [],
      transactions: [],
      gnn_explanation: 'Complex layering scheme identified through graph analysis',
      confidence_score: 0.92,
      pattern_description: 'Multi-hop transaction chain with circular patterns detected',
      regulatory_flags: ['BSA', 'AML', 'OFAC']
    }
  ]

  const handleFilterChange = (key: keyof AlertFilters, value: any) => {
    setFilters(prev => ({ ...prev, [key]: value }))
    setPagination(prev => ({ ...prev, page: 1 })) // Reset to first page
  }

  const clearFilters = () => {
    setFilters({
      status: [],
      risk_level: [],
      alert_type: [],
      date_from: '',
      date_to: '',
      assigned_to: '',
      account_id: ''
    })
    setSearchTerm('')
  }

  const exportAlerts = async () => {
    try {
      const params = new URLSearchParams(searchParams)
      params.set('export', 'csv')
      
      const response = await api.get(`/alerts/export?${params.toString()}`, {
        responseType: 'blob'
      })
      
      const blob = new Blob([response.data], { type: 'text/csv' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `alerts-${new Date().toISOString().split('T')[0]}.csv`
      link.click()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to export alerts:', error)
    }
  }

  const activeFiltersCount = Object.values(filters).filter(value => 
    Array.isArray(value) ? value.length > 0 : Boolean(value)
  ).length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Alerts Management</h1>
          <p className="text-gray-600">Monitor and investigate suspicious activities</p>
        </div>
        
        <div className="flex items-center space-x-3">
          <button
            onClick={loadAlerts}
            disabled={loadingState.isLoading}
            className="btn btn-secondary"
          >
            <RefreshCw className={clsx('h-4 w-4 mr-2', loadingState.isLoading && 'animate-spin')} />
            Refresh
          </button>
          
          <button
            onClick={exportAlerts}
            className="btn btn-secondary"
          >
            <Download className="h-4 w-4 mr-2" />
            Export
          </button>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="card p-4">
        <div className="flex flex-col lg:flex-row lg:items-center space-y-4 lg:space-y-0 lg:space-x-4">
          {/* Search */}
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search alerts by ID, account, or description..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="input pl-10 w-full"
            />
          </div>
          
          {/* Filter Toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={clsx(
              'btn btn-secondary relative',
              activeFiltersCount > 0 && 'bg-primary-50 text-primary-700 border-primary-200'
            )}
          >
            <Filter className="h-4 w-4 mr-2" />
            Filters
            {activeFiltersCount > 0 && (
              <span className="absolute -top-2 -right-2 h-5 w-5 bg-primary-600 text-white text-xs rounded-full flex items-center justify-center">
                {activeFiltersCount}
              </span>
            )}
            <ChevronDown className={clsx('h-4 w-4 ml-2 transition-transform', showFilters && 'rotate-180')} />
          </button>
        </div>

        {/* Filter Panel */}
        {showFilters && (
          <div className="mt-4 pt-4 border-t border-gray-200 animate-slide-down">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {/* Status Filter */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-gray-400 uppercase tracking-wider">Status</label>
                <select
                  multiple
                  value={filters.status || []}
                  onChange={(e) => handleFilterChange('status', Array.from(e.target.selectedOptions, option => option.value))}
                  className="input h-auto min-h-[140px] shadow-inner"
                >
                  <option value="new">New</option>
                  <option value="investigating">Investigating</option>
                  <option value="escalated">Escalated</option>
                  <option value="resolved">Resolved</option>
                  <option value="false_positive">False Positive</option>
                </select>
                <p className="text-[10px] text-gray-400">Hold Cmd/Ctrl to select multiple</p>
              </div>

              {/* Risk Level Filter */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-gray-400 uppercase tracking-wider">Risk Level</label>
                <select
                  multiple
                  value={filters.risk_level || []}
                  onChange={(e) => handleFilterChange('risk_level', Array.from(e.target.selectedOptions, option => option.value))}
                  className="input h-auto min-h-[140px] shadow-inner"
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
                <p className="text-[10px] text-gray-400">Filter by severity</p>
              </div>

              {/* Alert Type Filter */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-gray-400 uppercase tracking-wider">Alert Type</label>
                <select
                  multiple
                  value={filters.alert_type || []}
                  onChange={(e) => handleFilterChange('alert_type', Array.from(e.target.selectedOptions, option => option.value))}
                  className="input h-auto min-h-[140px] shadow-inner"
                >
                  <option value="smurfing">Smurfing</option>
                  <option value="structuring">Structuring</option>
                  <option value="layering">Layering</option>
                  <option value="integration">Integration</option>
                  <option value="velocity">Velocity</option>
                  <option value="unusual_pattern">Unusual Pattern</option>
                </select>
              </div>

              {/* Date & Actions */}
              <div className="flex flex-col space-y-4">
                <div className="space-y-2">
                  <label className="text-xs font-bold text-gray-400 uppercase tracking-wider">Date Range</label>
                  <div className="space-y-2">
                    <input
                      type="date"
                      value={filters.date_from}
                      onChange={(e) => handleFilterChange('date_from', e.target.value)}
                      className="input w-full"
                      placeholder="From"
                    />
                    <input
                      type="date"
                      value={filters.date_to}
                      onChange={(e) => handleFilterChange('date_to', e.target.value)}
                      className="input w-full"
                      placeholder="To"
                    />
                  </div>
                </div>
                
                <button 
                  onClick={clearFilters}
                  className="btn btn-secondary w-full mt-auto"
                >
                  Clear All Filters
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Results */}
      <div className="card">
        <div className="p-4 border-b border-gray-200">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold text-gray-900">
              Alerts ({pagination.total.toLocaleString()})
            </h3>
            
            {loadingState.lastUpdated && (
              <div className="flex items-center text-sm text-gray-500">
                <Clock className="h-4 w-4 mr-1" />
                Last updated: {new Date(loadingState.lastUpdated).toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>

        <div className="p-4">
          {loadingState.isLoading ? (
            <div className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="border border-gray-100 rounded-lg p-4">
                  <div className="loading-shimmer h-4 w-32 mb-2 rounded"></div>
                  <div className="loading-shimmer h-6 w-48 mb-2 rounded"></div>
                  <div className="loading-shimmer h-4 w-full rounded"></div>
                </div>
              ))}
            </div>
          ) : loadingState.error ? (
            <div className="text-center py-8">
              <AlertTriangle className="h-12 w-12 text-danger-300 mx-auto mb-4" />
              <p className="text-gray-500 mb-4">{loadingState.error}</p>
              <button onClick={loadAlerts} className="btn btn-primary">
                Try Again
              </button>
            </div>
          ) : (
            <AlertsList alerts={alerts} />
          )}
        </div>

        {/* Pagination */}
        {pagination.total_pages > 1 && (
          <div className="border-t border-gray-200 p-4">
            <Pagination
              currentPage={pagination.page}
              totalPages={pagination.total_pages}
              onPageChange={(page) => setPagination(prev => ({ ...prev, page }))}
            />
          </div>
        )}
      </div>
    </div>
  )
}