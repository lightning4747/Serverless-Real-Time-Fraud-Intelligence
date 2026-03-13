import React, { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { 
  ArrowLeft, 
  FileText, 
  Download, 
  Send, 
  Edit, 
  Check, 
  X,
  Clock,
  User,
  AlertTriangle,
  Shield,
  Calendar,
  DollarSign
} from 'lucide-react'
import { useApi } from '../contexts/ApiContext'
import { SuspiciousActivityReport, LoadingState } from '../types'
import { format } from 'date-fns'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'

export const ReportDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { api } = useApi()
  
  const [report, setReport] = useState<SuspiciousActivityReport | null>(null)
  const [loadingState, setLoadingState] = useState<LoadingState>({ isLoading: true })
  const [isUpdating, setIsUpdating] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editedNarrative, setEditedNarrative] = useState('')

  useEffect(() => {
    if (id) {
      loadReportDetail(id)
    }
  }, [id])

  const loadReportDetail = async (reportId: string) => {
    try {
      setLoadingState({ isLoading: true })
      
      const response = await api.get(`/reports/${reportId}`)
      setReport(response.data.data)
      setEditedNarrative(response.data.data.narrative)
      setLoadingState({ isLoading: false })
    } catch (error) {
      console.error('Failed to load report detail:', error)
      setLoadingState({ isLoading: false, error: 'Failed to load report details' })
      
      // Use mock data for demo
      const mockReport = getMockReport()
      setReport(mockReport)
      setEditedNarrative(mockReport.narrative)
    }
  }

  const getMockReport = (): SuspiciousActivityReport => ({
    sar_id: 'SAR-2024-001',
    case_id: 'CASE-2024-001',
    alert_id: 'ALT-2024-001',
    status: 'pending_review',
    created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    narrative: `Based on the analysis conducted by our AI-powered Anti-Money Laundering system, we have identified suspicious transaction patterns that warrant reporting under the Bank Secrecy Act (BSA) and Currency Transaction Report (CTR) requirements.

SUSPICIOUS ACTIVITY DESCRIPTION:
The subject account holder engaged in a pattern of structured transactions designed to evade federal reporting requirements. Over a 48-hour period, the Graph Neural Network (GNN) analysis detected 15 separate transactions, each below the $10,000 CTR threshold, totaling $127,500.

PATTERN ANALYSIS:
Our machine learning model identified the following red flags:
- Deliberate structuring: All transactions were between $8,000-$9,900
- Timing patterns: Transactions occurred in rapid succession across multiple days
- Network analysis: Connected accounts showed coordinated activity
- Velocity indicators: Unusual frequency compared to historical patterns

AI CONFIDENCE ASSESSMENT:
The GNN model assigned a confidence score of 89% to this suspicious activity pattern, indicating high certainty of intentional structuring behavior.

REGULATORY COMPLIANCE:
This activity appears to violate:
- Bank Secrecy Act (BSA) anti-structuring provisions
- Currency Transaction Report (CTR) evasion statutes
- Anti-Money Laundering (AML) regulations

RECOMMENDATION:
Based on the AI analysis and supporting evidence, we recommend filing this Suspicious Activity Report with FinCEN within the required timeframe.`,
    suspicious_activity_type: ['Structuring', 'Smurfing'],
    involved_parties: [
      {
        account_id: 'ACC-001',
        role: 'subject',
        customer_name: 'John D***',
        relationship: 'Primary account holder'
      },
      {
        account_id: 'ACC-002',
        role: 'beneficiary',
        customer_name: 'Jane S***',
        relationship: 'Frequent recipient'
      }
    ],
    total_amount: 127500,
    currency: 'USD',
    transaction_count: 15,
    date_range: {
      start: new Date(Date.now() - 1000 * 60 * 60 * 48).toISOString(),
      end: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString()
    },
    regulatory_requirements: ['BSA', 'CTR', 'AML'],
    filing_deadline: new Date(Date.now() + 1000 * 60 * 60 * 24 * 30).toISOString(),
    confidence_score: 0.89,
    review_notes: 'Initial AI-generated report requires compliance officer review before submission.'
  })

  const updateReportStatus = async (newStatus: SuspiciousActivityReport['status']) => {
    if (!report) return
    
    try {
      setIsUpdating(true)
      await api.patch(`/reports/${report.sar_id}`, { status: newStatus })
      
      const updateData: Partial<SuspiciousActivityReport> = { status: newStatus }
      if (newStatus === 'submitted') {
        updateData.submitted_at = new Date().toISOString()
      } else if (newStatus === 'filed') {
        updateData.filed_at = new Date().toISOString()
      }
      
      setReport(prev => prev ? { ...prev, ...updateData } : null)
      toast.success(`Report status updated to ${newStatus.replace('_', ' ')}`)
    } catch (error) {
      console.error('Failed to update report status:', error)
      toast.error('Failed to update report status')
    } finally {
      setIsUpdating(false)
    }
  }

  const saveNarrative = async () => {
    if (!report) return
    
    try {
      setIsUpdating(true)
      await api.patch(`/reports/${report.sar_id}`, { narrative: editedNarrative })
      
      setReport(prev => prev ? { ...prev, narrative: editedNarrative } : null)
      setEditMode(false)
      toast.success('Report narrative updated')
    } catch (error) {
      console.error('Failed to update narrative:', error)
      toast.error('Failed to update report narrative')
    } finally {
      setIsUpdating(false)
    }
  }

  const downloadReport = async () => {
    if (!report) return
    
    try {
      const response = await api.get(`/reports/${report.sar_id}/download`, {
        responseType: 'blob'
      })
      
      const blob = new Blob([response.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `SAR-${report.sar_id}.pdf`
      link.click()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to download report:', error)
      toast.error('Failed to download report')
    }
  }

  const submitReport = async () => {
    if (!report) return
    
    if (window.confirm('Are you sure you want to submit this SAR? This action cannot be undone.')) {
      await updateReportStatus('submitted')
    }
  }

  if (loadingState.isLoading) {
    return (
      <div className="space-y-6">
        <div className="loading-shimmer h-8 w-64 rounded"></div>
        <div className="card p-6">
          <div className="loading-shimmer h-96 w-full rounded"></div>
        </div>
      </div>
    )
  }

  if (loadingState.error || !report) {
    return (
      <div className="text-center py-12">
        <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">Report Not Found</h3>
        <p className="text-gray-500 mb-4">{loadingState.error || 'The requested report could not be found.'}</p>
        <Link to="/reports" className="btn btn-primary">
          Back to Reports
        </Link>
      </div>
    )
  }

  const getStatusColor = (status: SuspiciousActivityReport['status']) => {
    switch (status) {
      case 'draft': return 'bg-gray-100 text-gray-800'
      case 'pending_review': return 'bg-warning-100 text-warning-800'
      case 'submitted': return 'bg-primary-100 text-primary-800'
      case 'filed': return 'bg-success-100 text-success-800'
      case 'rejected': return 'bg-danger-100 text-danger-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  const getDaysUntilDeadline = () => {
    return Math.ceil((new Date(report.filing_deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
  }

  const daysUntilDeadline = getDaysUntilDeadline()

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link to="/reports" className="btn btn-secondary">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Reports
          </Link>
          
          <div>
            <h1 className="text-2xl font-bold text-gray-900">SAR {report.sar_id}</h1>
            <p className="text-gray-600">Case ID: {report.case_id}</p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={downloadReport}
            className="btn btn-secondary"
          >
            <Download className="h-4 w-4 mr-2" />
            Download PDF
          </button>
          
          {report.status === 'pending_review' && (
            <button
              onClick={submitReport}
              disabled={isUpdating}
              className="btn btn-primary"
            >
              <Send className="h-4 w-4 mr-2" />
              Submit SAR
            </button>
          )}
        </div>
      </div>

      {/* Status and Metadata */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-4">
            <span className={clsx('badge text-sm', getStatusColor(report.status))}>
              {report.status.replace('_', ' ').toUpperCase()}
            </span>
            
            {daysUntilDeadline <= 7 && daysUntilDeadline > 0 && (
              <span className="badge badge-warning text-sm">
                {daysUntilDeadline} days until deadline
              </span>
            )}
            
            {daysUntilDeadline <= 0 && (
              <span className="badge badge-danger text-sm">
                Overdue
              </span>
            )}
          </div>
          
          <div className="flex items-center space-x-2">
            <select
              value={report.status}
              onChange={(e) => updateReportStatus(e.target.value as SuspiciousActivityReport['status'])}
              disabled={isUpdating || report.status === 'filed'}
              className="input text-sm"
            >
              <option value="draft">Draft</option>
              <option value="pending_review">Pending Review</option>
              <option value="submitted">Submitted</option>
              <option value="filed">Filed</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-sm">
          <div className="flex items-center space-x-2">
            <Calendar className="h-4 w-4 text-gray-400" />
            <span className="text-gray-600">Created:</span>
            <span>{format(new Date(report.created_at), 'MMM dd, yyyy')}</span>
          </div>
          
          <div className="flex items-center space-x-2">
            <DollarSign className="h-4 w-4 text-gray-400" />
            <span className="text-gray-600">Amount:</span>
            <span className="font-medium">${report.total_amount.toLocaleString()} {report.currency}</span>
          </div>
          
          <div className="flex items-center space-x-2">
            <Shield className="h-4 w-4 text-gray-400" />
            <span className="text-gray-600">Confidence:</span>
            <span className="font-bold text-primary-600">{(report.confidence_score * 100).toFixed(1)}%</span>
          </div>
          
          <div className="flex items-center space-x-2">
            <Clock className="h-4 w-4 text-gray-400" />
            <span className="text-gray-600">Deadline:</span>
            <span>{format(new Date(report.filing_deadline), 'MMM dd, yyyy')}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* SAR Narrative */}
          <div className="card p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold text-gray-900">SAR Narrative</h3>
              
              {!editMode ? (
                <button
                  onClick={() => setEditMode(true)}
                  disabled={report.status === 'filed'}
                  className="btn btn-secondary btn-sm"
                >
                  <Edit className="h-4 w-4 mr-2" />
                  Edit
                </button>
              ) : (
                <div className="flex space-x-2">
                  <button
                    onClick={saveNarrative}
                    disabled={isUpdating}
                    className="btn btn-primary btn-sm"
                  >
                    <Check className="h-4 w-4 mr-2" />
                    Save
                  </button>
                  <button
                    onClick={() => {
                      setEditMode(false)
                      setEditedNarrative(report.narrative)
                    }}
                    className="btn btn-secondary btn-sm"
                  >
                    <X className="h-4 w-4 mr-2" />
                    Cancel
                  </button>
                </div>
              )}
            </div>
            
            {editMode ? (
              <textarea
                value={editedNarrative}
                onChange={(e) => setEditedNarrative(e.target.value)}
                className="input w-full h-96 resize-none font-mono text-sm"
                placeholder="Enter SAR narrative..."
              />
            ) : (
              <div className="prose max-w-none">
                <pre className="whitespace-pre-wrap text-sm text-gray-700 font-sans leading-relaxed">
                  {report.narrative}
                </pre>
              </div>
            )}
          </div>

          {/* Activity Timeline */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Activity Timeline</h3>
            
            <div className="space-y-4">
              <div className="flex items-start space-x-3">
                <div className="flex-shrink-0 w-2 h-2 bg-primary-500 rounded-full mt-2"></div>
                <div>
                  <div className="text-sm font-medium text-gray-900">Report Created</div>
                  <div className="text-xs text-gray-500">{format(new Date(report.created_at), 'MMM dd, yyyy HH:mm')}</div>
                </div>
              </div>
              
              {report.submitted_at && (
                <div className="flex items-start space-x-3">
                  <div className="flex-shrink-0 w-2 h-2 bg-success-500 rounded-full mt-2"></div>
                  <div>
                    <div className="text-sm font-medium text-gray-900">Report Submitted</div>
                    <div className="text-xs text-gray-500">{format(new Date(report.submitted_at), 'MMM dd, yyyy HH:mm')}</div>
                  </div>
                </div>
              )}
              
              {report.filed_at && (
                <div className="flex items-start space-x-3">
                  <div className="flex-shrink-0 w-2 h-2 bg-success-600 rounded-full mt-2"></div>
                  <div>
                    <div className="text-sm font-medium text-gray-900">Report Filed with FinCEN</div>
                    <div className="text-xs text-gray-500">{format(new Date(report.filed_at), 'MMM dd, yyyy HH:mm')}</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Report Summary */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Report Summary</h3>
            
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-gray-600">Transaction Count:</span>
                <span className="ml-2 font-medium">{report.transaction_count}</span>
              </div>
              
              <div>
                <span className="text-gray-600">Date Range:</span>
                <div className="ml-2 text-xs">
                  <div>{format(new Date(report.date_range.start), 'MMM dd, yyyy')}</div>
                  <div>to {format(new Date(report.date_range.end), 'MMM dd, yyyy')}</div>
                </div>
              </div>
              
              <div>
                <span className="text-gray-600">Activity Types:</span>
                <div className="ml-2 mt-1 flex flex-wrap gap-1">
                  {report.suspicious_activity_type.map((type) => (
                    <span key={type} className="badge badge-gray text-xs">
                      {type}
                    </span>
                  ))}
                </div>
              </div>
              
              <div>
                <span className="text-gray-600">Regulatory Requirements:</span>
                <div className="ml-2 mt-1 flex flex-wrap gap-1">
                  {report.regulatory_requirements.map((req) => (
                    <span key={req} className="badge badge-warning text-xs">
                      {req}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Involved Parties */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Involved Parties</h3>
            
            <div className="space-y-3">
              {report.involved_parties.map((party, index) => (
                <div key={index} className="border border-gray-200 rounded-lg p-3">
                  <div className="flex justify-between items-start mb-2">
                    <div className="font-medium text-gray-900">{party.customer_name}</div>
                    <span className={clsx(
                      'text-xs px-2 py-1 rounded-full',
                      party.role === 'subject' ? 'bg-danger-100 text-danger-800' :
                      party.role === 'beneficiary' ? 'bg-warning-100 text-warning-800' :
                      'bg-gray-100 text-gray-800'
                    )}>
                      {party.role}
                    </span>
                  </div>
                  
                  <div className="text-xs text-gray-600">
                    <div>Account: {party.account_id}</div>
                    <div>Relationship: {party.relationship}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Related Alert */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Related Alert</h3>
            
            <Link
              to={`/alerts/${report.alert_id}`}
              className="block border border-gray-200 rounded-lg p-3 hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-center space-x-2 mb-2">
                <AlertTriangle className="h-4 w-4 text-danger-500" />
                <span className="font-medium text-gray-900">{report.alert_id}</span>
              </div>
              <div className="text-xs text-gray-600">
                View original alert that generated this SAR
              </div>
            </Link>
          </div>

          {/* Review Notes */}
          {report.review_notes && (
            <div className="card p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Review Notes</h3>
              <p className="text-sm text-gray-700">{report.review_notes}</p>
              
              {report.reviewer && (
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <div className="flex items-center space-x-2 text-xs text-gray-500">
                    <User className="h-3 w-3" />
                    <span>Reviewed by: {report.reviewer}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}