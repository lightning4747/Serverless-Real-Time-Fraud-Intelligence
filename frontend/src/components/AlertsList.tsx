import React from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Clock, User, ArrowRight } from 'lucide-react'
import { Alert } from '../types'
import { formatDistanceToNow } from 'date-fns'
import { clsx } from 'clsx'

interface AlertsListProps {
  alerts: Alert[]
  compact?: boolean
}

export const AlertsList: React.FC<AlertsListProps> = ({ alerts, compact = false }) => {
  const getRiskLevelColor = (level: Alert['risk_level']) => {
    switch (level) {
      case 'critical':
        return 'bg-danger-600 text-white'
      case 'high':
        return 'bg-danger-100 text-danger-800'
      case 'medium':
        return 'bg-warning-100 text-warning-800'
      case 'low':
        return 'bg-success-100 text-success-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const getStatusColor = (status: Alert['status']) => {
    switch (status) {
      case 'new':
        return 'bg-primary-100 text-primary-800'
      case 'investigating':
        return 'bg-warning-100 text-warning-800'
      case 'escalated':
        return 'bg-danger-100 text-danger-800'
      case 'resolved':
        return 'bg-success-100 text-success-800'
      case 'false_positive':
        return 'bg-gray-100 text-gray-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const getAlertTypeLabel = (type: Alert['alert_type']) => {
    switch (type) {
      case 'smurfing':
        return 'Smurfing'
      case 'structuring':
        return 'Structuring'
      case 'layering':
        return 'Layering'
      case 'integration':
        return 'Integration'
      case 'velocity':
        return 'Velocity'
      case 'unusual_pattern':
        return 'Unusual Pattern'
      default:
        return type
    }
  }

  if (alerts.length === 0) {
    return (
      <div className="text-center py-8">
        <AlertTriangle className="h-12 w-12 text-gray-300 mx-auto mb-4" />
        <p className="text-gray-500">No alerts found</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {alerts.map((alert) => (
        <Link
          key={alert.alert_id}
          to={`/alerts/${alert.alert_id}`}
          className="block hover:bg-gray-50 transition-colors rounded-lg p-3 border border-gray-100"
        >
          <div className="flex items-start justify-between">
            <div className="flex-1 min-w-0">
              <div className="flex items-center space-x-2 mb-2">
                <span className={clsx('badge', getRiskLevelColor(alert.risk_level))}>
                  {alert.risk_level.toUpperCase()}
                </span>
                <span className={clsx('badge', getStatusColor(alert.status))}>
                  {alert.status.replace('_', ' ').toUpperCase()}
                </span>
                <span className="text-xs text-gray-500">
                  {getAlertTypeLabel(alert.alert_type)}
                </span>
              </div>
              
              <div className="flex items-center space-x-4 text-sm">
                <div className="flex items-center space-x-1">
                  <span className="font-medium text-gray-900">Risk Score:</span>
                  <span className={clsx(
                    'font-bold',
                    alert.risk_score >= 0.8 ? 'text-danger-600' :
                    alert.risk_score >= 0.6 ? 'text-warning-600' :
                    'text-success-600'
                  )}>
                    {(alert.risk_score * 100).toFixed(0)}%
                  </span>
                </div>
                
                <div className="flex items-center space-x-1 text-gray-500">
                  <Clock className="h-3 w-3" />
                  <span>{(() => {
                    try {
                      const date = new Date(alert.created_at)
                      if (isNaN(date.getTime())) return 'Just now'
                      return formatDistanceToNow(date, { addSuffix: true })
                    } catch (e) {
                      return 'Just now'
                    }
                  })()}</span>
                </div>
                
                {alert.assigned_to && (
                  <div className="flex items-center space-x-1 text-gray-500">
                    <User className="h-3 w-3" />
                    <span className="truncate max-w-24">{alert.assigned_to}</span>
                  </div>
                )}
              </div>
              
              {!compact && (
                <p className="text-sm text-gray-600 mt-2 line-clamp-2">
                  {alert.pattern_description}
                </p>
              )}
              
              <div className="flex items-center justify-between mt-2">
                <span className="text-xs text-gray-500 font-mono">
                  {alert.alert_id}
                </span>
                {alert.regulatory_flags.length > 0 && (
                  <div className="flex space-x-1">
                    {alert.regulatory_flags.slice(0, 2).map((flag) => (
                      <span key={flag} className="badge badge-gray text-xs">
                        {flag}
                      </span>
                    ))}
                    {alert.regulatory_flags.length > 2 && (
                      <span className="text-xs text-gray-500">
                        +{alert.regulatory_flags.length - 2}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
            
            <ArrowRight className="h-4 w-4 text-gray-400 ml-2 flex-shrink-0" />
          </div>
        </Link>
      ))}
    </div>
  )
}