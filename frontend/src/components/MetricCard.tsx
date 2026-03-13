import React from 'react'
import { LucideIcon, TrendingUp, TrendingDown } from 'lucide-react'
import { clsx } from 'clsx'

interface MetricCardProps {
  title: string
  value: string | number
  change?: number
  icon: LucideIcon
  color: 'primary' | 'success' | 'warning' | 'danger'
  subtitle?: string
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  change,
  icon: Icon,
  color,
  subtitle
}) => {
  const colorClasses = {
    primary: 'text-primary-600 bg-primary-100',
    success: 'text-success-600 bg-success-100',
    warning: 'text-warning-600 bg-warning-100',
    danger: 'text-danger-600 bg-danger-100'
  }

  const trendColor = change && change > 0 ? 'text-success-600' : 'text-danger-600'
  const TrendIcon = change && change > 0 ? TrendingUp : TrendingDown

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
          
          {change !== undefined && (
            <div className={clsx('flex items-center mt-2 text-sm', trendColor)}>
              <TrendIcon className="h-4 w-4 mr-1" />
              <span>{Math.abs(change).toFixed(1)}%</span>
              <span className="text-gray-500 ml-1">vs last period</span>
            </div>
          )}
          
          {subtitle && (
            <p className="text-xs text-gray-500 mt-1">{subtitle}</p>
          )}
        </div>
        
        <div className={clsx('p-3 rounded-lg', colorClasses[color])}>
          <Icon className="h-6 w-6" />
        </div>
      </div>
    </div>
  )
}