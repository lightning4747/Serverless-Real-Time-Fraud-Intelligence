import React, { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { 
  Search, 
  Filter, 
  Download, 
  RefreshCw, 
  FileText,
  Clock,
  CheckCircle,
  AlertCircle,
  XCircle,
  Eye,
  Calendar,
  User
} from 'lucide-react'
import { useApi } from '../contexts/ApiContext'
import { SuspiciousActivityReport, ReportFilters, PaginatedResponse, LoadingState } from '../types'
import { Pagination } from '../components/Pagination'
import { formatDistanceToNow, format } from 'date-fns'
import { clsx } from 'clsx'

export const Reports: React.FC = () => {
  const { api } = useApi()
  const [searchParams, setSearchParams] = useSearchParams()
  const [reports, setReports] = useState<SuspiciousActivityReport[]>([])
  const [pagination, setPagination] = useState({ page: 1, limit: 20, total: 0, total_pages: 0 })
  const [loadingState, setLoadingState] = useState<LoadingState>({ isLoading: true })
  const [searchTerm, setSearchTerm] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  
  const [filters, setFilters] = useState<ReportFilters>({
    status: searchParams.get('status')?.split(',') as SuspiciousActivityReport['status'][] || [],
    date_from: searchParams.get('date_from') || '',
    date_to: searchParams.get('date_to') || '',
    case_id: searchParams.get('case_id') || '',
    reviewer: searchParams.get('reviewer') || ''
  })

  useEffect(() => {
    loadReports()
  }, [searchParams])

  const loadReports = async () => {
    try {
      setLoadingState({ isLoading: true })
      
      const params = new URLSearchParams(searchParams)
      const response = await api.get(`/reports?${params.toString()}`)
      
      const data: PaginatedResponse<SuspiciousActivityReport> = response.data
      setReports(data.data)
      setPagination(data.pagination)
      setLoadingState({ isLoading: false, lastUpdated: new Date().toISOString() })
    } catch (error) {
      console.error('Failed to load reports:', error)
      setLoadingState({ isLoading: false, error: 'Failed to load reports' })
      
      // Use mock data for demo
      setReports(getMockReports())
      setPagination({ page: 1, limit: 20, total: 25, total_pages: 2 })
    }
  }

  const getMockReports = (): SuspiciousActivityReport[] => [
    {
      sar_id: 'SAR-2024-001',
      case_id: 'CASE-2024-001',
      alert_id: 'ALT-2024-001',
      status: 'pending_review',
      created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
      narrative: 'Suspicious structured transaction pattern detected involving multiple accounts with transactions consistently below CTR reporting thresholds.',
      suspicious_activity_type: ['Structuring', 'Smurfing'],
      involved_parties: [
        {
          account_id: 'ACC-001',
          role: 'subject',
          customer_name: 'John D***',
          relationship: 'Primary account holder'
        }
      ],
      total_amount: 127500,
      currency: 'USD',
      transaction_count: 15,
      date_range: {
        start: new Date(Date.now() - 1000 * 60 * 60 * 48).toISOString(),
        end: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString()
      },
      regulatory_requirements: ['BSA', 'CTR'],
      filing_deadline: new Date(Date.now() + 1000 * 60 * 60 * 24 * 30).toISOString(),
      confidence_score: 0.89
    },
    {
      sar_id: 'SAR-2024-002',
      case_id: 'CASE-2024-002',
      alert_id: 'ALT-2024-002',
      status: 'submitted',
      created_at: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
      submitted_at: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
      narrative: 'High velocity transaction pattern with circular money flows detected through graph neural network analysis.',
      suspicious_activity_type: ['Layering', 'Velocity'],
      involved_parties: [
        {
          account_id: 'ACC-002',
          role: 'subject',
          customer_name: 'Jane S***',
          relationship: 'Primary account holder'
        }
      ],
      total_amount: 89000,
      currency: 'USD',
      transaction_count: 25,
      date_range: {
        start: new Date(Date.now() - 1000 * 60 * 60 * 72).toISOString(),
        end: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString()
      },
      regulatory_requirements: ['AML'],
      filing_deadline: new Date(Date.now() + 1000 * 60 * 60 * 24 * 29).toISOString(),
      confidence_score: 0.76,
      reviewer: 'compliance.officer@company.com'
    }
  ]

  const getStatusIcon = (status: SuspiciousActivityReport['status']) => {
    switch (status) {
      case 'draft':
        return <FileText className="h-4 w-4 text-gray-500" />
      case 'pending_review':
        return <Clock className="h-4 w-4 text-warning-500" />
      case 'submitted':
        return <CheckCircle className="h-4 w-4 text-primary-500" />
      case 'filed':
        return <CheckCircle className="h-4 w-4 text-success-500" />
      case 'rejected':
        return <XCircle className="h-4 w-4 text-danger-500" />
      default:
        return <FileText className="h-4 w-4 text-gray-500" />
    }
  }

  const getStatusColor = (status: SuspiciousActivityReport['status']) => {
    switch (status) {
      case 'draft':
        return 'bg-gray-100 text-gray-800'
      case 'pending_review':
        return 'bg-warning-100 text-warning-800'
      case 'submitted':
        return 'bg-primary-100 text-primary-800'
      case 'filed':
        return 'bg-success-100 text-success-800'
      case 'rejected':
        return 'bg-danger-100 text-danger-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const getDaysUntilDeadline = (deadline: string) => {
    const days = Math.ceil((new Date(deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
    return days
  }

  if (loadingState.isLoading) {
    return (
      <div className="space-y-6">
        <div className="loading-shimmer h-8 w-64 rounded"></div>
        <div className="card p-6">
          <div className="loading-shimmer h-64 w-full rounded"></div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">SAR Reports</h1>
          <p className="text-gray-600">Suspicious Activity Reports management and filing</p>
        </div>
        
        <div className="flex items-center space-x-3">
          <button
            onClick={loadReports}
            disabled={loadingState.isLoading}
            className="btn btn-secondary"
          >
            <RefreshCw className={clsx('h-4 w-4 mr-2', loadingState.isLoading && 'animate-spin')} />
            Refresh
          </button>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="card p-4">
        <div className="flex flex-col lg:flex-row lg:items-center space-y-4 lg:space-y-0 lg:space-x-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search reports by SAR ID, case ID, or content..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="input pl-10 w-full"
            />
          </div>
          
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="btn btn-secondary"
          >
            <Filter className="h-4 w-4 mr-2" />
            Filters
          </button>
        </div>

        {showFilters && (
          <div className="mt-4 pt-4 border-t border-gray-200 animate-slide-down">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {/* Status Filter */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-gray-400 uppercase tracking-wider">Report Status</label>
                <select
                  multiple
                  value={filters.status || []}
                  onChange={(e) => setFilters(prev => ({ 
                    ...prev, 
                    status: Array.from(e.target.selectedOptions, option => option.value) as SuspiciousActivityReport['status'][]
                  }))}
                  className="input h-auto min-h-[140px] shadow-inner"
                >
                  <option value="draft">Draft</option>
                  <option value="pending_review">Pending Review</option>
                  <option value="submitted">Submitted</option>
                  <option value="filed">Filed</option>
                  <option value="rejected">Rejected</option>
                </select>
                <p className="text-[10px] text-gray-400 font-medium">Use Ctrl/Cmd to select multiple</p>
              </div>

              {/* Date Filter */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-gray-400 uppercase tracking-wider">Date Range</label>
                <div className="flex flex-col space-y-2">
                  <div className="flex items-center space-x-2">
                    <span className="text-xs text-gray-400 w-8">From</span>
                    <input
                      type="date"
                      value={filters.date_from}
                      onChange={(e) => setFilters(prev => ({ ...prev, date_from: e.target.value }))}
                      className="input flex-1"
                    />
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs text-gray-400 w-8">To</span>
                    <input
                      type="date"
                      value={filters.date_to}
                      onChange={(e) => setFilters(prev => ({ ...prev, date_to: e.target.value }))}
                      className="input flex-1"
                    />
                  </div>
                </div>
              </div>

              {/* Advanced Filter */}
              <div className="space-y-4 flex flex-col justify-between">
                <div className="space-y-2">
                  <label className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center">
                    Case Association
                  </label>
                  <input
                    type="text"
                    value={filters.case_id}
                    onChange={(e) => setFilters(prev => ({ ...prev, case_id: e.target.value }))}
                    className="input w-full"
                    placeholder="Enter case ID (e.g. CASE-2024)"
                  />
                </div>
                
                <button 
                  onClick={() => setFilters({ status: [], date_from: '', date_to: '', case_id: '' })}
                  className="btn btn-secondary w-full"
                >
                  Reset All Reports
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Reports List */}
      <div className="card">
        <div className="p-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">
            Reports ({pagination.total.toLocaleString()})
          </h3>
        </div>

        <div className="divide-y divide-gray-200">
          {reports.map((report) => {
            const daysUntilDeadline = getDaysUntilDeadline(report.filing_deadline)
            
            return (
              <Link
                key={report.sar_id}
                to={`/reports/${report.sar_id}`}
                className="block hover:bg-gray-50 transition-colors p-6"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-3 mb-2">
                      {getStatusIcon(report.status)}
                      <span className="font-medium text-gray-900">{report.sar_id}</span>
                      <span className={clsx('badge text-xs', getStatusColor(report.status))}>
                        {report.status.replace('_', ' ').toUpperCase()}
                      </span>
                      
                      {daysUntilDeadline <= 7 && daysUntilDeadline > 0 && (
                        <span className="badge badge-warning text-xs">
                          {daysUntilDeadline} days left
                        </span>
                      )}
                      
                      {daysUntilDeadline <= 0 && (
                        <span className="badge badge-danger text-xs">
                          Overdue
                        </span>
                      )}
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-sm mb-3">
                      <div className="flex items-center space-x-1">
                        <FileText className="h-3 w-3 text-gray-400" />
                        <span className="text-gray-600">Case:</span>
                        <span className="font-mono">{report.case_id}</span>
                      </div>
                      
                      <div className="flex items-center space-x-1">
                        <Calendar className="h-3 w-3 text-gray-400" />
                        <span className="text-gray-600">Created:</span>
                        <span>{formatDistanceToNow(new Date(report.created_at), { addSuffix: true })}</span>
                      </div>
                      
                      <div className="flex items-center space-x-1">
                        <span className="text-gray-600">Amount:</span>
                        <span className="font-medium">${report.total_amount.toLocaleString()} {report.currency}</span>
                      </div>
                      
                      <div className="flex items-center space-x-1">
                        <span className="text-gray-600">Transactions:</span>
                        <span>{report.transaction_count}</span>
                      </div>
                    </div>
                    
                    <p className="text-sm text-gray-700 line-clamp-2 mb-3">
                      {report.narrative}
                    </p>
                    
                    <div className="flex items-center justify-between">
                      <div className="flex space-x-2">
                        {report.suspicious_activity_type.map((type) => (
                          <span key={type} className="badge badge-gray text-xs">
                            {type}
                          </span>
                        ))}
                      </div>
                      
                      <div className="flex items-center space-x-4 text-xs text-gray-500">
                        {report.reviewer && (
                          <div className="flex items-center space-x-1">
                            <User className="h-3 w-3" />
                            <span>{report.reviewer}</span>
                          </div>
                        )}
                        
                        <div className="flex items-center space-x-1">
                          <span>Confidence:</span>
                          <span className="font-medium">{(report.confidence_score * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <Eye className="h-4 w-4 text-gray-400 ml-4 flex-shrink-0" />
                </div>
              </Link>
            )
          })}
        </div>

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