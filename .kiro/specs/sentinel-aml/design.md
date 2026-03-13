# Sentinel AML System Design Document

## Executive Summary

The Sentinel AML system is a cloud-native, AI-powered anti-money laundering detection platform built on AWS serverless architecture. The system leverages Amazon Neptune for graph-based transaction storage, Neptune ML with Graph Neural Networks (GNN) for pattern detection, and Amazon Bedrock Claude 3 for automated SAR generation. The architecture prioritizes real-time processing, regulatory compliance, and explainable AI decisions.

## System Architecture Overview

### High-Level Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   External      │    │   API Gateway    │    │   Lambda        │
│   Systems       │───▶│   REST API       │───▶│   Functions     │
│                 │    │   Authentication │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
                       ┌─────────────────┐              │
                       │   Step Functions│◀─────────────┘
                       │   Orchestration │
                       └─────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────┐        ┌─────────────┐        ┌─────────────┐
│   Neptune   │        │  Neptune ML │        │   Bedrock   │
│   Graph DB  │        │  GNN Models │        │  Claude 3   │
│             │        │             │        │             │
└─────────────┘        └─────────────┘        └─────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                       ┌─────────────────┐
                       │   CloudWatch    │
                       │   Monitoring    │
                       └─────────────────┘
```

### Technology Stack

**Core Infrastructure:**
- **Compute**: AWS Lambda (Python 3.11)
- **API Layer**: Amazon API Gateway REST API
- **Orchestration**: AWS Step Functions
- **Graph Database**: Amazon Neptune (TinkerPop/Gremlin)
- **Machine Learning**: Neptune ML with DGL/GNN
- **Generative AI**: Amazon Bedrock (Claude 3 Sonnet)
- **Infrastructure as Code**: AWS CDK (Python)

**Supporting Services:**
- **Monitoring**: Amazon CloudWatch, AWS X-Ray
- **Security**: AWS IAM, AWS KMS, AWS VPC
- **Storage**: Amazon S3 (model artifacts, logs)
- **Notifications**: Amazon SNS, Amazon SES

## Detailed Component Design

### 1. Transaction Ingestion Layer

#### 1.1 API Gateway Configuration

**Endpoint Structure:**
```
POST /transactions          # Submit new transactions
GET  /alerts               # Retrieve suspicious activity alerts
GET  /reports/{id}         # Access generated SAR reports
GET  /health               # System health check
```

**Authentication & Security:**
- API Key authentication with rate limiting (100 req/min)
- Request/response validation using JSON Schema
- CORS configuration for web dashboard access
- WAF integration for DDoS protection

#### 1.2 Transaction Processor Lambda

**Function Specifications:**
- **Runtime**: Python 3.11
- **Memory**: 1024 MB
- **Timeout**: 30 seconds
- **Concurrency**: 1000 concurrent executions

**Processing Logic:**
```python
def lambda_handler(event, context):
    # 1. Validate transaction schema (100ms SLA)
    # 2. Enrich with metadata (timestamps, IDs)
    # 3. Store in Neptune Graph (500ms SLA)
    # 4. Trigger Step Functions workflow
    # 5. Return success/error response
```

**Data Model:**
```python
class Transaction(BaseModel):
    transaction_id: str
    from_account: str
    to_account: str
    amount: Decimal
    currency: str = "USD"
    timestamp: datetime
    transaction_type: str
    metadata: Dict[str, Any]
```

### 2. Graph Database Layer

#### 2.1 Neptune Graph Schema

**Node Types:**
```gremlin
// Account Node
g.addV('Account')
  .property('account_id', account_id)
  .property('customer_name', customer_name)
  .property('account_type', account_type)
  .property('risk_score', risk_score)
  .property('creation_date', creation_date)
  .property('last_activity', last_activity)

// Transaction Node  
g.addV('Transaction')
  .property('transaction_id', transaction_id)
  .property('amount', amount)
  .property('timestamp', timestamp)
  .property('transaction_type', transaction_type)
  .property('currency', currency)
```

**Edge Relationships:**
```gremlin
// SENT_TO relationship
g.V().has('Account', 'account_id', from_account)
  .addE('SENT_TO')
  .to(g.V().has('Account', 'account_id', to_account))
  .property('transaction_id', transaction_id)
  .property('amount', amount)
  .property('timestamp', timestamp)
```

#### 2.2 Query Patterns

**Smurfing Detection Query:**
```gremlin
// Find accounts with multiple transactions below $10K in 48 hours
g.V().has('Account', 'account_id', account_id)
  .outE('SENT_TO')
  .has('amount', lt(10000))
  .has('timestamp', between(start_time, end_time))
  .groupCount()
  .by(outV())
  .unfold()
  .where(select(values).is(gte(5)))
```

### 3. Machine Learning Layer

#### 3.1 Neptune ML Integration

**GNN Model Architecture:**
```python
class AMLGraphNet(nn.Module):
    def __init__(self, input_dim, hidden_dim, output_dim):
        super().__init__()
        self.conv1 = GraphConv(input_dim, hidden_dim)
        self.conv2 = GraphConv(hidden_dim, hidden_dim)
        self.classifier = nn.Linear(hidden_dim, output_dim)
        self.dropout = nn.Dropout(0.2)
    
    def forward(self, g, features):
        h = F.relu(self.conv1(g, features))
        h = self.dropout(h)
        h = F.relu(self.conv2(g, h))
        return torch.sigmoid(self.classifier(h))
```

**Feature Engineering:**
- Transaction velocity (transactions per hour)
- Amount patterns (below threshold clustering)
- Network centrality measures
- Temporal patterns (time-of-day, day-of-week)
- Geographic dispersion metrics

#### 3.2 Fraud Scoring Lambda

**Function Specifications:**
- **Runtime**: Python 3.11
- **Memory**: 3008 MB (ML workload)
- **Timeout**: 5 minutes
- **Layers**: NumPy, SciPy, DGL, PyTorch

**Scoring Algorithm:**
```python
def calculate_risk_score(transaction_cluster):
    # 1. Extract subgraph around suspicious accounts
    # 2. Generate node/edge features
    # 3. Apply GNN model inference
    # 4. Calculate risk score (0.0-1.0)
    # 5. Generate explanation features
    return {
        'risk_score': float,
        'confidence': float,
        'contributing_factors': List[str],
        'similar_patterns': List[Dict]
    }
```

### 4. Generative AI Layer

#### 4.1 SAR Generation with Bedrock

**Claude 3 Integration:**
```python
def generate_sar_report(suspicious_activity):
    prompt = f"""
    Generate a Suspicious Activity Report (SAR) based on the following analysis:
    
    Customer: {activity.customer_name}
    Account: {activity.account_id}
    Risk Score: {activity.risk_score}
    Pattern: {activity.pattern_type}
    Transactions: {activity.transaction_summary}
    
    Format according to FinCEN requirements with:
    1. Executive Summary
    2. Suspicious Activity Description
    3. Supporting Documentation
    4. Regulatory Justification
    """
    
    response = bedrock_client.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000,
            "temperature": 0.1
        })
    )
    return response
```

#### 4.2 Report Structure

**SAR Document Schema:**
```python
class SARReport(BaseModel):
    report_id: str
    filing_date: datetime
    customer_info: CustomerInfo
    suspicious_activity: SuspiciousActivity
    supporting_evidence: List[Evidence]
    regulatory_basis: str
    confidence_score: float
    generated_by: str = "Sentinel-AML-AI"
```

### 5. Orchestration Layer

#### 5.1 Step Functions State Machine

**Workflow Definition:**
```json
{
  "Comment": "AML Processing Workflow",
  "StartAt": "TransactionIngestion",
  "States": {
    "TransactionIngestion": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:region:account:function:TransactionProcessor",
      "Next": "WaitForAnalysis",
      "Retry": [{"ErrorEquals": ["States.ALL"], "MaxAttempts": 3}]
    },
    "WaitForAnalysis": {
      "Type": "Wait",
      "Seconds": 300,
      "Next": "GNNAnalysis"
    },
    "GNNAnalysis": {
      "Type": "Task", 
      "Resource": "arn:aws:lambda:region:account:function:FraudScorer",
      "Next": "CheckRiskScore"
    },
    "CheckRiskScore": {
      "Type": "Choice",
      "Choices": [{
        "Variable": "$.risk_score",
        "NumericGreaterThan": 0.7,
        "Next": "GenerateSAR"
      }],
      "Default": "EndProcessing"
    },
    "GenerateSAR": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:region:account:function:SARGenerator",
      "End": true
    },
    "EndProcessing": {
      "Type": "Succeed"
    }
  }
}
```

### 6. User Interface Layer

#### 6.1 Web Dashboard Architecture

**Frontend Stack:**
- **Framework**: React 18 with TypeScript
- **UI Library**: Material-UI (MUI) v5
- **State Management**: React Context + useReducer
- **Visualization**: Recharts, D3.js
- **Routing**: React Router v6

**Component Architecture:**
```
src/
├── components/
│   ├── common/           # Reusable UI components
│   ├── charts/           # Data visualization components
│   ├── forms/            # Form components
│   └── layout/           # Layout components
├── pages/
│   ├── Dashboard/        # Main monitoring dashboard
│   ├── Alerts/           # Alert management
│   ├── Investigations/   # Case management
│   ├── Reports/          # SAR report management
│   └── Analytics/        # Performance analytics
├── services/
│   ├── api.ts           # API client
│   ├── auth.ts          # Authentication
│   └── websocket.ts     # Real-time updates
└── types/
    └── index.ts         # TypeScript definitions
```

#### 6.2 Real-time Updates

**WebSocket Integration:**
```typescript
class DashboardWebSocket {
  private ws: WebSocket;
  
  connect() {
    this.ws = new WebSocket('wss://api.sentinel-aml.com/ws');
    this.ws.onmessage = (event) => {
      const update = JSON.parse(event.data);
      this.handleUpdate(update);
    };
  }
  
  private handleUpdate(update: AlertUpdate) {
    // Update dashboard state with new alerts
    // Trigger notifications for high-priority alerts
    // Refresh relevant charts and metrics
  }
}
```

### 7. Security Architecture

#### 7.1 Data Protection

**Encryption Strategy:**
- **At Rest**: AES-256 encryption for Neptune, S3, Lambda environment variables
- **In Transit**: TLS 1.3 for all API communications
- **Key Management**: AWS KMS with customer-managed keys
- **PII Handling**: Field-level encryption for sensitive data

**Access Control:**
```python
# IAM Role for Lambda Functions
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "neptune-db:ReadDataViaQuery",
                "neptune-db:WriteDataViaQuery"
            ],
            "Resource": "arn:aws:neptune-db:*:*:cluster/sentinel-aml/*"
        },
        {
            "Effect": "Allow", 
            "Action": [
                "bedrock:InvokeModel"
            ],
            "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-sonnet-*"
        }
    ]
}
```

#### 7.2 Compliance Controls

**Audit Logging:**
- All API calls logged to CloudTrail
- Application-level audit logs in CloudWatch
- Immutable log storage in S3 with 7-year retention
- Automated compliance reporting

**Data Retention:**
```python
class DataRetentionPolicy:
    TRANSACTION_DATA = timedelta(days=2555)  # 7 years
    AUDIT_LOGS = timedelta(days=2555)        # 7 years  
    MODEL_ARTIFACTS = timedelta(days=1095)   # 3 years
    TEMP_DATA = timedelta(days=30)           # 30 days
```

### 8. Performance Architecture

#### 8.1 Scalability Design

**Auto-scaling Configuration:**
```yaml
Lambda Functions:
  - Reserved Concurrency: 1000
  - Provisioned Concurrency: 100 (for critical functions)
  - Memory: 1024-3008 MB based on workload

Neptune Cluster:
  - Instance Type: db.r5.xlarge (primary)
  - Read Replicas: 2 (for read scaling)
  - Auto-scaling: Enabled (2-8 instances)

API Gateway:
  - Throttling: 10,000 requests/second
  - Burst: 5,000 requests
  - Caching: Enabled for GET endpoints
```

#### 8.2 Performance Monitoring

**Key Metrics:**
- Transaction ingestion latency (target: <500ms)
- GNN inference time (target: <30s for 50K nodes)
- SAR generation time (target: <60s)
- End-to-end processing time (target: <10min for 95% of cases)
- System availability (target: 99.9%)

**Alerting Thresholds:**
```python
PERFORMANCE_ALERTS = {
    'ingestion_latency_p95': 1000,  # ms
    'gnn_inference_time': 45,       # seconds
    'sar_generation_time': 90,      # seconds
    'error_rate': 0.01,             # 1%
    'availability': 0.999           # 99.9%
}
```

### 9. Deployment Architecture

#### 9.1 Infrastructure as Code

**CDK Stack Structure:**
```python
class SentinelAMLStack(Stack):
    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # VPC and Networking
        self.vpc = self.create_vpc()
        
        # Neptune Cluster
        self.neptune = self.create_neptune_cluster()
        
        # Lambda Functions
        self.lambdas = self.create_lambda_functions()
        
        # Step Functions
        self.state_machine = self.create_state_machine()
        
        # API Gateway
        self.api = self.create_api_gateway()
        
        # Monitoring
        self.monitoring = self.create_monitoring()
```

#### 9.2 CI/CD Pipeline

**Deployment Stages:**
1. **Development**: Feature branches, unit tests
2. **Staging**: Integration tests, performance tests
3. **Production**: Blue/green deployment, canary releases

**Pipeline Configuration:**
```yaml
stages:
  - name: test
    script:
      - pytest tests/unit/
      - pytest tests/integration/
      - python -m mypy src/
  
  - name: deploy-staging
    script:
      - cdk deploy SentinelAMLStack-staging
      - python tests/e2e/run_tests.py
  
  - name: deploy-production
    script:
      - cdk deploy SentinelAMLStack-prod --require-approval never
    when: manual
```

### 10. Monitoring and Observability

#### 10.1 Logging Strategy

**Log Levels and Content:**
```python
# Application Logging
logger.info("Transaction processed", extra={
    "transaction_id": tx_id,
    "amount": amount,
    "processing_time_ms": duration,
    "risk_score": score
})

logger.warning("High risk transaction detected", extra={
    "transaction_id": tx_id,
    "risk_score": score,
    "pattern_type": pattern,
    "customer_id": customer_id
})
```

#### 10.2 Dashboards and Alerts

**CloudWatch Dashboards:**
- System health and performance metrics
- Business KPIs (alerts generated, SARs filed)
- Cost optimization metrics
- Security and compliance metrics

**Alert Configuration:**
```python
CLOUDWATCH_ALARMS = {
    'HighErrorRate': {
        'metric': 'ErrorRate',
        'threshold': 0.01,
        'comparison': 'GreaterThanThreshold'
    },
    'HighLatency': {
        'metric': 'Duration',
        'threshold': 30000,  # 30 seconds
        'comparison': 'GreaterThanThreshold'
    }
}
```

## Data Flow Diagrams

### Transaction Processing Flow

```
External System → API Gateway → Transaction Processor Lambda
                                        ↓
                                Neptune Graph Database
                                        ↓
                                Step Functions Orchestrator
                                        ↓
                    ┌───────────────────┴───────────────────┐
                    ↓                                       ↓
            GNN Fraud Scorer                        Wait State (5 min)
                    ↓                                       ↓
            Risk Score > 0.7? ──────No──────→ End Processing
                    ↓ Yes
            SAR Generator (Bedrock)
                    ↓
            Store SAR Report
                    ↓
            Notify Dashboard
```

### Alert Investigation Flow

```
Dashboard Alert → Investigation Started → Customer Profile Review
                                                ↓
                                        Transaction Analysis
                                                ↓
                                        Enhanced Due Diligence
                                                ↓
                                        Decision & Documentation
                                                ↓
                                        Case Closed/SAR Filed
```

## API Specifications

### REST API Endpoints

#### POST /transactions
```json
{
  "transaction_id": "string",
  "from_account": "string", 
  "to_account": "string",
  "amount": "number",
  "currency": "string",
  "timestamp": "ISO8601",
  "transaction_type": "string",
  "metadata": {}
}
```

#### GET /alerts
```json
{
  "alerts": [
    {
      "alert_id": "string",
      "transaction_ids": ["string"],
      "risk_score": "number",
      "pattern_type": "string",
      "created_at": "ISO8601",
      "status": "string"
    }
  ],
  "pagination": {
    "page": "number",
    "limit": "number", 
    "total": "number"
  }
}
```

#### GET /reports/{id}
```json
{
  "report_id": "string",
  "filing_date": "ISO8601",
  "customer_info": {},
  "suspicious_activity": {},
  "confidence_score": "number",
  "status": "string"
}
```

## Correctness Properties

### Property 1: Data Integrity
**Specification**: All valid transactions submitted to the system must be stored in Neptune with complete referential integrity.

**Test Strategy**: Property-based testing with generated transaction data to verify storage completeness and relationship consistency.

### Property 2: Risk Score Bounds  
**Specification**: All GNN-generated risk scores must be within the range [0.0, 1.0].

**Test Strategy**: Statistical testing of model outputs across diverse transaction patterns.

### Property 3: Alert Generation
**Specification**: All transactions with risk scores ≥ 0.7 must generate alerts within 10 minutes.

**Test Strategy**: End-to-end testing with synthetic high-risk transaction patterns.

### Property 4: SAR Completeness
**Specification**: All generated SARs must include required FinCEN fields and pass validation.

**Test Strategy**: Schema validation and regulatory compliance testing.

### Property 5: Audit Trail Completeness
**Specification**: All system decisions must be logged with sufficient detail for regulatory audit.

**Test Strategy**: Audit log analysis and completeness verification.

## Conclusion

The Sentinel AML system design provides a comprehensive, scalable, and compliant solution for anti-money laundering detection. The serverless architecture ensures cost-effectiveness and scalability, while the AI-powered detection capabilities provide superior accuracy compared to traditional rule-based systems. The design prioritizes regulatory compliance, data security, and operational efficiency to meet the demanding requirements of financial institutions.