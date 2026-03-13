// Core AML domain types based on requirements

export interface Account {
  account_id: string
  customer_name: string
  account_type: 'checking' | 'savings' | 'business' | 'investment'
  risk_score: number
  creation_date: string
  status: 'active' | 'suspended' | 'closed'
  kyc_status: 'verified' | 'pending' | 'failed'
  pep_status: boolean // Politically Exposed Person
  jurisdiction: string
  last_activity: string
}

export interface Transaction {
  transaction_id: string
  from_account_id: string
  to_account_id: string
  amount: number
  currency: string
  transaction_type: 'deposit' | 'withdrawal' | 'transfer' | 'payment' | 'wire' | 'ach' | 'check' | 'card'
  timestamp: string
  description?: string
  status: 'completed' | 'pending' | 'failed' | 'cancelled'
  risk_indicators?: string[]
}

export interface Alert {
  alert_id: string
  case_id: string
  risk_score: number
  risk_level: 'low' | 'medium' | 'high' | 'critical'
  alert_type: 'smurfing' | 'structuring' | 'layering' | 'integration' | 'velocity' | 'unusual_pattern'
  status: 'new' | 'investigating' | 'escalated' | 'resolved' | 'false_positive'
  priority: 'low' | 'medium' | 'high' | 'urgent'
  created_at: string
  updated_at: string
  assigned_to?: string
  
  // Related entities
  accounts: Account[]
  transactions: Transaction[]
  
  // AI Analysis
  gnn_explanation: string
  confidence_score: number
  pattern_description: string
  regulatory_flags: string[]
  
  // Investigation details
  investigation_notes?: string
  evidence_links?: string[]
  compliance_officer?: string
  resolution_reason?: string
}

export interface SuspiciousActivityReport {
  sar_id: string
  case_id: string
  alert_id: string
  status: 'draft' | 'pending_review' | 'submitted' | 'filed' | 'rejected'
  created_at: string
  submitted_at?: string
  filed_at?: string
  
  // Report content
  narrative: string
  suspicious_activity_type: string[]
  involved_parties: {
    account_id: string
    role: 'subject' | 'beneficiary' | 'originator'
    customer_name: string // Redacted for privacy
    relationship: string
  }[]
  
  // Financial details
  total_amount: number
  currency: string
  transaction_count: number
  date_range: {
    start: string
    end: string
  }
  
  // Compliance
  regulatory_requirements: string[]
  filing_deadline: string
  confidence_score: number
  review_notes?: string
  reviewer?: string
}

export interface GraphNode {
  id: string
  type: 'account' | 'transaction'
  label: string
  risk_score?: number
  properties: Record<string, any>
  x?: number
  y?: number
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  type: 'sent_to' | 'received_from'
  amount?: number
  timestamp?: string
  properties: Record<string, any>
}

export interface TransactionGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  center_account?: string
  analysis_summary: {
    total_amount: number
    transaction_count: number
    unique_accounts: number
    risk_patterns: string[]
    time_span: string
  }
}

export interface DashboardMetrics {
  alerts: {
    total: number
    new: number
    investigating: number
    high_risk: number
    trend: number // percentage change
  }
  transactions: {
    total_today: number
    flagged_today: number
    volume_usd: number
    trend: number
  }
  reports: {
    pending: number
    filed_this_month: number
    avg_resolution_time: number // hours
    trend: number
  }
  system: {
    model_accuracy: number
    false_positive_rate: number
    processing_latency: number // ms
    uptime: number // percentage
  }
}

export interface AnalyticsData {
  time_series: {
    date: string
    alerts: number
    transactions: number
    risk_score_avg: number
  }[]
  risk_distribution: {
    level: string
    count: number
    percentage: number
  }[]
  alert_types: {
    type: string
    count: number
    trend: number
  }[]
  geographic_distribution: {
    jurisdiction: string
    alert_count: number
    risk_level: number
  }[]
}

// API Response types
export interface ApiResponse<T> {
  data: T
  message?: string
  timestamp: string
  request_id: string
}

export interface PaginatedResponse<T> {
  data: T[]
  pagination: {
    page: number
    limit: number
    total: number
    total_pages: number
  }
  filters?: Record<string, any>
}

// Filter and search types
export interface AlertFilters {
  status?: Alert['status'][]
  risk_level?: Alert['risk_level'][]
  alert_type?: Alert['alert_type'][]
  date_from?: string
  date_to?: string
  assigned_to?: string
  account_id?: string
}

export interface ReportFilters {
  status?: SuspiciousActivityReport['status'][]
  date_from?: string
  date_to?: string
  case_id?: string
  reviewer?: string
}

// UI State types
export interface LoadingState {
  isLoading: boolean
  error?: string
  lastUpdated?: string
}

export interface TableSort {
  field: string
  direction: 'asc' | 'desc'
}

export interface TablePagination {
  page: number
  limit: number
}

// Configuration types
export interface SystemConfig {
  risk_thresholds: {
    low: number
    medium: number
    high: number
    critical: number
  }
  alert_settings: {
    auto_escalation_hours: number
    notification_channels: string[]
    priority_rules: Record<string, any>
  }
  compliance_settings: {
    sar_filing_deadline_days: number
    retention_period_years: number
    required_approvals: number
  }
}