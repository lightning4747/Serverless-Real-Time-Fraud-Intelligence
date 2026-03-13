import React, { useState, useEffect } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts'
import { useApi } from '../contexts/ApiContext'

interface RiskData {
  level: string
  count: number
  percentage: number
  color: string
}

export const RiskDistributionChart: React.FC = () => {
  const { api } = useApi()
  const [data, setData] = useState<RiskData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadRiskData()
  }, [])

  const loadRiskData = async () => {
    try {
      const response = await api.get('/analytics/risk-distribution')
      const rawData = response.data.data
      
      const processedData = rawData.map((item: any) => ({
        ...item,
        color: getRiskColor(item.level)
      }))
      
      setData(processedData)
    } catch (error) {
      console.error('Failed to load risk distribution:', error)
      // Use mock data for demo
      setData(getMockData())
    } finally {
      setLoading(false)
    }
  }

  const getRiskColor = (level: string) => {
    switch (level.toLowerCase()) {
      case 'critical':
        return '#dc2626'
      case 'high':
        return '#ef4444'
      case 'medium':
        return '#f59e0b'
      case 'low':
        return '#22c55e'
      default:
        return '#6b7280'
    }
  }

  const getMockData = (): RiskData[] => [
    { level: 'Low', count: 856, percentage: 68.7, color: '#22c55e' },
    { level: 'Medium', count: 245, percentage: 19.6, color: '#f59e0b' },
    { level: 'High', count: 123, percentage: 9.9, color: '#ef4444' },
    { level: 'Critical', count: 23, percentage: 1.8, color: '#dc2626' }
  ]

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg">
          <p className="font-medium text-gray-900">{data.level} Risk</p>
          <p className="text-sm text-gray-600">
            {data.count.toLocaleString()} alerts ({data.percentage.toFixed(1)}%)
          </p>
        </div>
      )
    }
    return null
  }

  const renderCustomLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percentage }: any) => {
    if (percentage < 5) return null // Don't show labels for small slices
    
    const RADIAN = Math.PI / 180
    const radius = innerRadius + (outerRadius - innerRadius) * 0.5
    const x = cx + radius * Math.cos(-midAngle * RADIAN)
    const y = cy + radius * Math.sin(-midAngle * RADIAN)

    return (
      <text 
        x={x} 
        y={y} 
        fill="white" 
        textAnchor={x > cx ? 'start' : 'end'} 
        dominantBaseline="central"
        fontSize={12}
        fontWeight="bold"
      >
        {`${percentage.toFixed(0)}%`}
      </text>
    )
  }

  if (loading) {
    return (
      <div className="h-64 flex items-center justify-center">
        <div className="loading-shimmer h-32 w-32 rounded-full"></div>
      </div>
    )
  }

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={renderCustomLabel}
            outerRadius={80}
            fill="#8884d8"
            dataKey="count"
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
        </PieChart>
      </ResponsiveContainer>
      
      {/* Custom Legend */}
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
        {data.map((item) => (
          <div key={item.level} className="flex items-center space-x-2">
            <div 
              className="w-3 h-3 rounded-full flex-shrink-0"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-gray-600 truncate">
              {item.level}: {item.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}