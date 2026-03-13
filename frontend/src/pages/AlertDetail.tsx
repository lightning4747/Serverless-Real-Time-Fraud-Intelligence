import React, { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { 
  ArrowLeft, 
  AlertTriangle, 
  Clock, 
  User, 
  FileText, 
  Eye, 
  Edit, 
  Check, 
  X,
  Flag,
  Shield,
  Activity,
  DollarSign,
  Calendar,
  MapPin,
  Network
} from 'lucide-react'
import { useApi } from '../contexts/ApiContext'
import { Alert, TransactionGraph, LoadingState } from '../types'
import { TransactionGraphVisualization } from '../components/TransactionGraphVisualization'
import { formatDistanceToNow, format } from 'date-fns'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'

export const AlertDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { api } = useApi()
  
  const [alert, setAlert] = useState<Alert | null>(null)
  const [graph, setGraph] = useState<TransactionGraph | null>(null)
  const [loadingState, setLoadingState] = useState<LoadingState>({ isLoading: true })
  const [isUpdating, setIsUpdating] = useState(false)
  const [showAssignModal, setShowAssignModal] = useState(false)
  const [investigationNotes, setInvestigationNotes] = useState('')

  useEffect(() => {
    if (id) {
      loadAlertDetail(id)
    }
  }, [id])

  const loadAlertDetail = async (alertId: string) => {
    try {
      setLoadingState({ isLoading: true })
      
      const [alertResponse, graphResponse] = await Promise.all([
        api.get(`/alerts/${alertId}`),
        api.get(`/alerts/${alertId}/graph`)
      ])
      
      setAlert(alertResponse.data.data)
      setGraph(graphResponse.data.data)
      setInvestigationNotes(alertResponse.data.data.investigation_notes || '')
      setLoadingState({ isLoading: false })
    } catch (error) {
      console.error('Failed to load alert detail:', error)
      setLoadingState({ isLoading: false, error: 'Failed to load alert details' })
      
      // Use mock data for demo
      setAlert(getMockAlert())
      setGraph(getMockGraph())
    }
  }

  const getMockAlert = (): Alert => ({
    alert_id: 'ALT-2024-001',
    case_id: 'CASE-2024-001',
    risk_score: 0.89,
    risk_level: 'high',
    alert_type: 'smurfing',
    status: 'new',
    priority: 'high',
    created_at: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
    updated_at: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
    accounts: [
      {
        account_id: 'ACC-001',
        customer_name: 'John D***',
        account_type: 'checking',
        risk_score: 0.75,
        creation_date: '2023-01-15',
        status: 'active',
        kyc_status: 'verified',
        pep_status: false,
        jurisdiction: 'US-NY',
        last_activity: new Date().toISOString()
      },
      {
        account_id: 'ACC-002',
        customer_name: 'Jane S***',
        account_type: 'savings',
        risk_score: 0.82,
        creation_date: '2023-03-22',
        status: 'active',
        kyc_status: 'verified',
        pep_status: false,
        jurisdiction: 'US-CA',
        last_activity: new Date().toISOString()
      }
    ],
    transactions: [
      {
        transaction_id: 'TXN-001',
        from_account_id: 'ACC-001',
        to_account_id: 'ACC-002',
        amount: 8500,
        currency: 'USD',
        transaction_type: 'transfer',
        timestamp: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
        description: 'Wire transfer',
        status: 'completed'
      }
    ],
    gnn_explanation: 'The Graph Neural Network detected a structured transaction pattern consistent with smurfing behavior. Multiple transactions below the $10,000 reporting threshold were identified across connected accounts within a 48-hour window. The pattern shows deliberate structuring to avoid Currency Transaction Report (CTR) requirements.',
    confidence_score: 0.89,
    pattern_description: 'Structured deposits pattern: 15 transactions under $9,000 within 48 hours across 3 connected accounts',
    regulatory_flags: ['BSA', 'CTR', 'AML'],
    investigation_notes: 'Initial review shows suspicious timing and amounts. Requires deeper investigation into account relationships.'
  })

  const getMockGraph = (): TransactionGraph => ({
    nodes: [
      { id: 'ACC-001', type: 'account', label: 'John D***', risk_score: 0.75, properties: {} },
      { id: 'ACC-002', type: 'account', label: 'Jane S***', risk_score: 0.82, properties: {} },
      { id: 'TXN-001', type: 'transaction', label: '$8,500', properties: {} }
    ],
    edges: [
      { id: 'edge-1', source: 'ACC-001', target: 'TXN-001', type: 'sent_to', amount: 8500, properties: {} },
      { id: 'edge-2', source: 'TXN-001', target: 'ACC-002', type: 'received_from', amount: 8500, properties: {} }
    ],
    analysis_summary: {
      total_amount: 127500,
      transaction_count: 15,
      unique_accounts: 3,
      risk_patterns: ['Below threshold structuring', 'Rapid sequential transfers', 'Connected account network'],
      time_span: '48 hours'
    }
  })

  const updateAlertStatus = async (newStatus: Alert['status']) => {
    if (!alert) return
    
    try {
      setIsUpdating(true)
      await api.patch(`/alerts/${alert.alert_id}`, { status: newStatus })
      
      setAlert(prev => prev ? { ...prev, status: newStatus, updated_at: new Date().toISOString() } : null)
      toast.success(`Alert status updated to ${newStatus.replace('_', ' ')}`)
    } catch (error) {
      console.error('Failed to update alert status:', error)
      toast.error('Failed to update alert status')
    } finally {
      setIsUpdating(false)
    }
  }

  const assignAlert = async (assignee: string) => {
    if (!alert) return
    
    try {
      setIsUpdating(true)
      await api.patch(`/alerts/${alert.alert_id}`, { assigned_to: assignee })
      
      setAlert(prev => prev ? { ...prev, assigned_to: assignee, updated_at: new Date().toISOString() } : null)
      toast.success('Alert assigned successfully')
      setShowAssignModal(false)
    } catch (error) {
      console.error('Failed to assign alert:', error)
      toast.error('Failed to assign alert')
    } finally {
      setIsUpdating(false)
    }
  }

  const saveInvestigationNotes = async () => {
    if (!alert) return
    
    try {
      setIsUpdating(true)
      await api.patch(`/alerts/${alert.alert_id}`, { investigation_notes: investigationNotes })
      
      setAlert(prev => prev ? { ...prev, investigation_notes: investigationNotes, updated_at: new Date().toISOString() } : null)
      toast.success('Investigation notes saved')
    } catch (error) {
      console.error('Failed to save notes:', error)
      toast.error('Failed to save investigation notes')
    } finally {
      setIsUpdating(false)
    }
  }

  const generateSAR = async () => {
    if (!alert) return
    
    try {
      setIsUpdating(true)
      const response = await api.post(`/alerts/${alert.alert_id}/generate-sar`)
      
      toast.success('SAR generation initiated')
      navigate(`/reports/${response.data.data.sar_id}`)
    } catch (error) {
      console.error('Failed to generate SAR:', error)
      toast.error('Failed to generate SAR')
    } finally {
      setIsUpdating(false)
    }
  }

  if (loadingState.isLoading) {
    return (
      <div className="space-y-6">
        <div className="loading-shimmer h-8 w-64 rounded"></div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="card p-6">
              <div className="loading-shimmer h-64 w-full rounded"></div>
            </div>
          </div>
          <div className="space-y-6">
            <div className="card p-6">
              <div className="loading-shimmer h-32 w-full rounded"></div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (loadingState.error || !alert) {
    return (
      <div className="text-center py-12">
        <AlertTriangle className="h-12 w-12 text-danger-300 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">Alert Not Found</h3>
        <p className="text-gray-500 mb-4">{loadingState.error || 'The requested alert could not be found.'}</p>
        <Link to="/alerts" className="btn btn-primary">
          Back to Alerts
        </Link>
      </div>
    )
  }

  const getRiskLevelColor = (level: Alert['risk_level']) => {
    switch (level) {
      case 'critical': return 'bg-danger-600 text-white'
      case 'high': return 'bg-danger-100 text-danger-800'
      case 'medium': return 'bg-warning-100 text-warning-800'
      case 'low': return 'bg-success-100 text-success-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  const getStatusColor = (status: Alert['status']) => {
    switch (status) {
      case 'new': return 'bg-primary-100 text-primary-800'
      case 'investigating': return 'bg-warning-100 text-warning-800'
      case 'escalated': return 'bg-danger-100 text-danger-800'
      case 'resolved': return 'bg-success-100 text-success-800'
      case 'false_positive': return 'bg-gray-100 text-gray-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link to="/alerts" className="btn btn-secondary">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Alerts
          </Link>
          
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Alert {alert.alert_id}</h1>
            <p className="text-gray-600">Case ID: {alert.case_id}</p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={generateSAR}
            disabled={isUpdating}
            className="btn btn-primary"
          >
            <FileText className="h-4 w-4 mr-2" />
            Generate SAR
          </button>
        </div>
      </div>

      {/* Alert Status and Actions */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-4">
            <span className={clsx('badge text-sm', getRiskLevelColor(alert.risk_level))}>
              {alert.risk_level.toUpperCase()} RISK
            </span>
            <span className={clsx('badge text-sm', getStatusColor(alert.status))}>
              {alert.status.replace('_', ' ').toUpperCase()}
            </span>
            <span className="text-sm text-gray-500">
              {alert.alert_type.replace('_', ' ').toUpperCase()}
            </span>
          </div>
          
          <div className="flex items-center space-x-2">
            <select
              value={alert.status}
              onChange={(e) => updateAlertStatus(e.target.value as Alert['status'])}
              disabled={isUpdating}
              className="input text-sm"
            >
              <option value="new">New</option>
              <option value="investigating">Investigating</option>
              <option value="escalated">Escalated</option>
              <option value="resolved">Resolved</option>
              <option value="false_positive">False Positive</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-sm">
          <div className="flex items-center space-x-2">
            <Shield className="h-4 w-4 text-gray-400" />
            <span className="text-gray-600">Risk Score:</span>
            <span className="font-bold text-danger-600">{(alert.risk_score * 100).toFixed(0)}%</span>
          </div>
          
          <div className="flex items-center space-x-2">
            <Clock className="h-4 w-4 text-gray-400" />
            <span className="text-gray-600">Created:</span>
            <span>{(() => {
              try {
                const date = new Date(alert.created_at)
                if (isNaN(date.getTime())) return 'Recently'
                return formatDistanceToNow(date, { addSuffix: true })
              } catch (e) {
                return 'Recently'
              }
            })()}</span>
          </div>
          
          <div className="flex items-center space-x-2">
            <User className="h-4 w-4 text-gray-400" />
            <span className="text-gray-600">Assigned:</span>
            <span>{alert.assigned_to || 'Unassigned'}</span>
          </div>
          
          <div className="flex items-center space-x-2">
            <Flag className="h-4 w-4 text-gray-400" />
            <span className="text-gray-600">Priority:</span>
            <span className="capitalize">{alert.priority}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* AI Analysis */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
              <Activity className="h-5 w-5 mr-2" />
              AI Analysis & Explanation
            </h3>
            
            <div className="space-y-4">
              <div>
                <h4 className="font-medium text-gray-900 mb-2">Pattern Description</h4>
                <p className="text-gray-700">{alert.pattern_description}</p>
              </div>
              
              <div>
                <h4 className="font-medium text-gray-900 mb-2">GNN Explanation</h4>
                <p className="text-gray-700">{alert.gnn_explanation}</p>
              </div>
              
              <div className="flex items-center justify-between pt-4 border-t border-gray-200">
                <div className="flex items-center space-x-4">
                  <span className="text-sm text-gray-600">Confidence Score:</span>
                  <span className="font-bold text-primary-600">{(alert.confidence_score * 100).toFixed(1)}%</span>
                </div>
                
                <div className="flex space-x-2">
                  {alert.regulatory_flags.map((flag) => (
                    <span key={flag} className="badge badge-gray text-xs">
                      {flag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Transaction Graph */}
          {graph && (
            <div className="card p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <Network className="h-5 w-5 mr-2" />
                Transaction Network
              </h3>
              
              <div className="mb-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div className="text-center">
                  <div className="text-2xl font-bold text-primary-600">{graph.analysis_summary.transaction_count}</div>
                  <div className="text-gray-600">Transactions</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-primary-600">{graph.analysis_summary.unique_accounts}</div>
                  <div className="text-gray-600">Accounts</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-primary-600">${(graph.analysis_summary.total_amount / 1000).toFixed(0)}K</div>
                  <div className="text-gray-600">Total Amount</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-primary-600">{graph.analysis_summary.time_span}</div>
                  <div className="text-gray-600">Time Span</div>
                </div>
              </div>
              
              <TransactionGraphVisualization graph={graph} />
              
              <div className="mt-4">
                <h4 className="font-medium text-gray-900 mb-2">Risk Patterns Detected</h4>
                <div className="flex flex-wrap gap-2">
                  {graph.analysis_summary.risk_patterns.map((pattern, index) => (
                    <span key={index} className="badge badge-warning text-xs">
                      {pattern}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Investigation Notes */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
              <Edit className="h-5 w-5 mr-2" />
              Investigation Notes
            </h3>
            
            <div className="space-y-4">
              <textarea
                value={investigationNotes}
                onChange={(e) => setInvestigationNotes(e.target.value)}
                placeholder="Add investigation notes, findings, and next steps..."
                className="input w-full h-32 resize-none"
              />
              
              <div className="flex justify-end">
                <button
                  onClick={saveInvestigationNotes}
                  disabled={isUpdating}
                  className="btn btn-primary"
                >
                  <Check className="h-4 w-4 mr-2" />
                  Save Notes
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Involved Accounts */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Involved Accounts</h3>
            
            <div className="space-y-3">
              {alert.accounts.map((account) => (
                <div key={account.account_id} className="border border-gray-200 rounded-lg p-3">
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <div className="font-medium text-gray-900">{account.customer_name}</div>
                      <div className="text-sm text-gray-500">{account.account_id}</div>
                    </div>
                    <span className={clsx(
                      'text-xs px-2 py-1 rounded-full',
                      account.risk_score >= 0.8 ? 'bg-danger-100 text-danger-800' :
                      account.risk_score >= 0.6 ? 'bg-warning-100 text-warning-800' :
                      'bg-success-100 text-success-800'
                    )}>
                      {(account.risk_score * 100).toFixed(0)}%
                    </span>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
                    <div>Type: {account.account_type}</div>
                    <div>Status: {account.status}</div>
                    <div>KYC: {account.kyc_status}</div>
                    <div>Jurisdiction: {account.jurisdiction}</div>
                  </div>
                  
                  {account.pep_status && (
                    <div className="mt-2">
                      <span className="badge badge-warning text-xs">PEP</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Recent Transactions */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Key Transactions</h3>
            
            <div className="space-y-3">
              {alert.transactions.slice(0, 5).map((transaction) => (
                <div key={transaction.transaction_id} className="border border-gray-200 rounded-lg p-3">
                  <div className="flex justify-between items-start mb-2">
                    <div className="text-sm">
                      <div className="font-medium text-gray-900">
                        ${transaction.amount.toLocaleString()} {transaction.currency}
                      </div>
                      <div className="text-gray-500">{transaction.transaction_type}</div>
                    </div>
                    <span className={clsx(
                      'text-xs px-2 py-1 rounded-full',
                      transaction.status === 'completed' ? 'bg-success-100 text-success-800' :
                      transaction.status === 'pending' ? 'bg-warning-100 text-warning-800' :
                      'bg-gray-100 text-gray-800'
                    )}>
                      {transaction.status}
                    </span>
                  </div>
                  
                  <div className="text-xs text-gray-600">
                    <div>From: {transaction.from_account_id}</div>
                    <div>To: {transaction.to_account_id}</div>
                    <div>{(() => {
                      try {
                        const date = new Date(transaction.timestamp)
                        if (isNaN(date.getTime())) return 'Time unavailable'
                        return format(date, 'MMM dd, yyyy HH:mm')
                      } catch (e) {
                        return 'Time unavailable'
                      }
                    })()}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Quick Actions */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h3>
            
            <div className="space-y-3">
              <button
                onClick={() => setShowAssignModal(true)}
                className="w-full btn btn-secondary text-left"
              >
                <User className="h-4 w-4 mr-2" />
                {alert.assigned_to ? 'Reassign Alert' : 'Assign Alert'}
              </button>
              
              <button
                onClick={() => updateAlertStatus('escalated')}
                disabled={isUpdating || alert.status === 'escalated'}
                className="w-full btn btn-danger text-left"
              >
                <Flag className="h-4 w-4 mr-2" />
                Escalate Alert
              </button>
              
              <Link
                to={`/reports?case_id=${alert.case_id}`}
                className="w-full btn btn-secondary text-left inline-flex items-center"
              >
                <FileText className="h-4 w-4 mr-2" />
                View Related Reports
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}