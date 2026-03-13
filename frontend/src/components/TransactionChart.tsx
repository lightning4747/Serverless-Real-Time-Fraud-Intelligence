import React, { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useApi } from '../contexts/ApiContext'

interface ChartData {
  date: string
  transactions: number
  alerts: number
  risk_score: number
}

export const TransactionChart: React.FC = () => {
  const { api } = useApi()
  const [data, setData] = useState<ChartData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadChartData()
  }, [])

  const loadChartData = async () => {
    try {
      const response = await api.get('/analytics/time-series?period=7d')
      setData(response.data.data)
    } catch (error) {
      console.error('Failed to load chart data:', error)
      // Use mock data for demo
      setData(getMockData())
    } finally {
      setLoading(false)
    }
  }

  const getMockData = (): ChartData[] => {
    const days = 7
    const data: ChartData[] = []
    
    for (let i = days - 1; i >= 0; i--) {
      const date = new Date()
      date.setDate(date.getDate() - i)
      
      data.push({
        date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        transactions: Math.floor(Math.random() * 5000) + 10000,
        alerts: Math.floor(Math.random() * 50) + 20,
        risk_score: Math.random() * 0.3 + 0.1 // 0.1 to 0.4
      })
    }
    
    return data
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg">
          <p className="font-medium text-gray-900 mb-2">{label}</p>
          {payload.map((entry: any, index: number) => (
            <p key={index} className="text-sm" style={{ color: entry.color }}>
              {entry.name}: {
                entry.dataKey === 'risk_score' 
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

  if (loading) {
    return (
      <div className="h-64 flex items-center justify-center">
        <div className="loading-shimmer h-full w-full rounded"></div>
      </div>
    )
  }

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis 
            dataKey="date" 
            stroke="#6b7280"
            fontSize={12}
          />
          <YAxis 
            yAxisId="left"
            stroke="#6b7280"
            fontSize={12}
          />
          <YAxis 
            yAxisId="right"
            orientation="right"
            stroke="#6b7280"
            fontSize={12}
            tickFormatter={(value) => `${(value * 100).toFixed(0)}%`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="transactions"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={{ fill: '#3b82f6', strokeWidth: 2, r: 4 }}
            name="Transactions"
          />
          
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="alerts"
            stroke="#ef4444"
            strokeWidth={2}
            dot={{ fill: '#ef4444', strokeWidth: 2, r: 4 }}
            name="Alerts"
          />
          
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="risk_score"
            stroke="#f59e0b"
            strokeWidth={2}
            dot={{ fill: '#f59e0b', strokeWidth: 2, r: 4 }}
            name="Avg Risk Score"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}