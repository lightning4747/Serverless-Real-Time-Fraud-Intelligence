import React, { createContext, useContext, useState, useEffect } from 'react'
import axios, { AxiosInstance, AxiosError } from 'axios'
import toast from 'react-hot-toast'

interface ApiConfig {
  baseURL: string
  apiKey: string
  timeout: number
}

interface ApiContextType {
  api: AxiosInstance
  isConnected: boolean
  lastError: string | null
  retryConnection: () => void
}

const ApiContext = createContext<ApiContextType | undefined>(undefined)

export const useApi = () => {
  const context = useContext(ApiContext)
  if (context === undefined) {
    throw new Error('useApi must be used within an ApiProvider')
  }
  return context
}

interface ApiProviderProps {
  children: React.ReactNode
}

export const ApiProvider: React.FC<ApiProviderProps> = ({ children }) => {
  const [isConnected, setIsConnected] = useState(false)
  const [lastError, setLastError] = useState<string | null>(null)

  // API configuration from environment variables
  const config: ApiConfig = {
    baseURL: import.meta.env.VITE_API_URL || '/api',
    apiKey: import.meta.env.VITE_API_KEY || 'demo-key',
    timeout: 30000
  }

  // Create axios instance with configuration
  const api = axios.create({
    baseURL: config.baseURL,
    timeout: config.timeout,
    headers: {
      'Content-Type': 'application/json',
      'X-Api-Key': config.apiKey,
      'Accept': 'application/json'
    }
  })

  // Request interceptor for logging and authentication
  api.interceptors.request.use(
    (config) => {
      console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`)
      return config
    },
    (error) => {
      console.error('API Request Error:', error)
      return Promise.reject(error)
    }
  )

  // Response interceptor for error handling
  api.interceptors.response.use(
    (response) => {
      setIsConnected(true)
      setLastError(null)
      return response
    },
    (error: AxiosError) => {
      setIsConnected(false)
      
      let errorMessage = 'Unknown error occurred'
      
      if (error.response) {
        // Server responded with error status
        const status = error.response.status
        const data = error.response.data as any
        
        switch (status) {
          case 401:
            errorMessage = 'Authentication failed - Invalid API key'
            break
          case 403:
            errorMessage = 'Access forbidden - Insufficient permissions'
            break
          case 404:
            errorMessage = 'Resource not found'
            break
          case 429:
            errorMessage = 'Rate limit exceeded - Please try again later'
            break
          case 500:
            errorMessage = 'Internal server error'
            break
          default:
            errorMessage = data?.message || `Server error (${status})`
        }
      } else if (error.request) {
        // Network error
        errorMessage = 'Network error - Unable to connect to API'
      } else {
        // Request setup error
        errorMessage = error.message
      }
      
      setLastError(errorMessage)
      
      // Show toast for critical errors
      if (error.response?.status === 401) {
        toast.error('Authentication failed. Please check your API key.')
      } else if (error.response?.status === 500) {
        toast.error('Server error. Please try again later.')
      }
      
      console.error('API Response Error:', errorMessage, error)
      return Promise.reject(error)
    }
  )

  // Health check function
  const checkConnection = async () => {
    try {
      await api.get('/health')
      setIsConnected(true)
      setLastError(null)
    } catch (error) {
      setIsConnected(false)
      // Error already handled by interceptor
    }
  }

  // Retry connection function
  const retryConnection = () => {
    checkConnection()
  }

  // Initial connection check
  useEffect(() => {
    checkConnection()
    
    // Set up periodic health checks
    const interval = setInterval(checkConnection, 60000) // Check every minute
    
    return () => clearInterval(interval)
  }, [])

  const value: ApiContextType = {
    api,
    isConnected,
    lastError,
    retryConnection
  }

  return (
    <ApiContext.Provider value={value}>
      {children}
    </ApiContext.Provider>
  )
}