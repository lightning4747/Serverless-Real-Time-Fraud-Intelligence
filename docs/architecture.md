# Sentinel-AML Architecture Guide

## Overview

Sentinel-AML is a serverless, AI-powered Anti-Money Laundering detection platform built on AWS. The system leverages graph neural networks, generative AI, and event-driven architecture to detect suspicious financial activities in real-time.

## Architecture Principles

### 1. Serverless-First
- **AWS Lambda** for all compute workloads
- **Amazon API Gateway** for REST endpoints
- **AWS Step Functions** for orchestration
- **Amazon Neptune** for managed graph database
- **Amazon Bedrock** for generative AI

### 2. Graph-Centric Design
- All transaction data modeled as graph relationships
- Account nodes connected by transaction edges
- Graph neural networks for pattern detection
- Network analysis for money flow tracking

### 3. Event-Driven Processing
- Asynchronous transaction processing
- Event-based workflow orchestration
- Real-time alert generation
- Scalable processing pipeline

### 4. AI-Powered Detection
- Graph Neural Networks (GNN) for fraud scoring
- Generative AI for SAR report creation
- Explainable AI for regulatory compliance
- Continuous learning and adaptation

## System Components

### Core Infrastructure

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   API Gateway   │    │   Lambda Fns    │    │   Step Fns      │
│                 │    │                 │    │                 │
│ • REST API      │───▶│ • Transaction   │───▶│ • Orchestration │
│ • Rate Limiting │    │   Processor     │    │ • Workflow      │
│ • Auth/API Keys │    │ • Fraud Scorer  │    │ • Error Handling│
│ • Validation    │    │ • SAR Generator │    │ • Retry Logic   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Neptune DB    │    │   Bedrock AI    │    │   CloudWatch    │
│                 │    │                 │    │                 │
│ • Graph Storage │    │ • Claude 3      │    │ • Monitoring    │
│ • Gremlin API   │    │ • SAR Reports   │    │ • Logging       │
│ • Neptune ML    │    │ • Explanations  │    │ • Alerting      │
│ • GNN Models    │    │ • Compliance    │    │ • Dashboards    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Data Flow Architecture

```
Transaction Input
       │
       ▼
┌─────────────────┐
│ API Gateway     │
│ • Validation    │
│ • Rate Limiting │
│ • Authentication│
└─────────────────┘
       │
       ▼
┌─────────────────┐
│ Transaction     │
│ Processor       │
│ • Schema Valid  │
│ • Neptune Store │
│ • Trigger Flow  │
└─────────────────┘
       │
       ▼
┌─────────────────┐
│ Step Functions  │
│ Orchestration   │
└─────────────────┘
       │
       ├─────────────────┐
       ▼                 ▼
┌─────────────────┐ ┌─────────────────┐
│ GNN Fraud       │ │ Risk Assessment │
│ Scorer          │ │ • Velocity      │
│ • Pattern Det   │ │ • Amount Patterns│
│ • Risk Score    │ │ • Jurisdiction  │
│ • Feature Imp   │ │ • PEP Status    │
└─────────────────┘ └─────────────────┘
       │                 │
       └─────────┬───────┘
                 ▼
        ┌─────────────────┐
        │ Risk Evaluation │
        │ • Threshold     │
        │ • Decision Tree │
        └─────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌─────────────────┐ ┌─────────────────┐
│ Alert Manager   │ │ SAR Generator   │
│ • Create Alert  │ │ • Bedrock API   │
│ • Notification  │ │ • Report Format │
│ • Investigation │ │ • Compliance    │
└─────────────────┘ └─────────────────┘
```

## Component Details

### 1. API Gateway Layer

**Purpose**: External interface for transaction submission and data retrieval

**Components**:
- REST API endpoints
- Request validation
- Rate limiting (100 req/min)
- API key authentication
- CORS configuration

**Endpoints**:
- `POST /transactions` - Submit new transactions
- `GET /alerts` - Retrieve suspicious activity alerts
- `GET /reports/{id}` - Access generated SAR reports
- `GET /health` - System health check

### 2. Lambda Functions

**Transaction Processor**:
- Validates incoming transaction data
- Stores transactions in Neptune graph
- Triggers Step Functions workflow
- Handles concurrent requests (up to 1000/sec)

**Fraud Scorer**:
- Analyzes transaction patterns using GNN
- Calculates risk scores (0.0-1.0)
- Identifies suspicious patterns (smurfing, structuring)
- Provides feature importance explanations

**SAR Generator**:
- Uses Amazon Bedrock (Claude 3) for report generation
- Creates FinCEN-compliant SAR reports
- Applies PII redaction and data privacy
- Provides confidence scores for findings

**Alert Manager**:
- Creates and manages suspicious activity alerts
- Routes alerts based on risk level
- Tracks investigation status
- Sends notifications to compliance teams

### 3. Neptune Graph Database

**Schema Design**:
```
Account Nodes:
- account_id (unique identifier)
- customer_name_hash (privacy-protected)
- account_type (checking, savings, business, etc.)
- risk_score (0.0-1.0)
- country_code (jurisdiction)
- is_pep (politically exposed person flag)
- kyc_status (verification status)

Transaction Nodes:
- transaction_id (unique identifier)
- amount (transaction value)
- timestamp (transaction time)
- transaction_type (wire, ach, deposit, etc.)
- currency (USD, EUR, etc.)
- is_cash (cash transaction flag)
- is_international (cross-border flag)

SENT_TO Edges:
- Connect accounts through transactions
- Include transaction metadata
- Enable graph traversal for pattern detection
```

**Query Patterns**:
- Transaction cluster analysis
- Money flow path detection
- Account relationship mapping
- Temporal pattern identification

### 4. Step Functions Orchestration

**Workflow States**:
1. **Fraud Analysis** - Invoke GNN scoring
2. **Risk Evaluation** - Decision logic based on thresholds
3. **Parallel Processing** - SAR generation + Alert creation
4. **Error Handling** - Retry logic and failure management

**Decision Logic**:
- Risk Score > 0.7: Generate SAR + Create Alert
- Risk Score 0.4-0.7: Create Alert only
- Risk Score < 0.4: Log and continue

### 5. Monitoring and Observability

**CloudWatch Integration**:
- Custom business metrics
- Performance monitoring
- Error tracking and alerting
- Log aggregation and analysis

**Key Metrics**:
- Transaction processing rate
- Fraud detection accuracy
- False positive rate
- System latency and availability

## Security Architecture

### 1. Data Protection

**Encryption**:
- AES-256 encryption at rest (KMS)
- TLS 1.3 encryption in transit
- Field-level encryption for PII

**Access Control**:
- IAM roles with least privilege
- API key authentication
- VPC network isolation
- Security group restrictions

### 2. Compliance Features

**Audit Trail**:
- Immutable transaction logs
- Complete decision history
- 7-year data retention
- Regulatory reporting capabilities

**Privacy Protection**:
- PII hashing and masking
- Data anonymization
- Consent management
- Right to erasure support

## Scalability and Performance

### 1. Auto-Scaling

**Lambda Concurrency**:
- Automatic scaling based on demand
- Reserved concurrency for critical functions
- Cold start optimization

**Neptune Scaling**:
- Read replicas for query performance
- Automatic storage scaling
- Multi-AZ deployment for availability

### 2. Performance Optimization

**Caching Strategy**:
- API Gateway response caching
- Lambda function warming
- Neptune query optimization

**Batch Processing**:
- Transaction batching for efficiency
- Bulk graph operations
- Optimized data pipelines

## Deployment Architecture

### 1. Infrastructure as Code

**AWS CDK Stacks**:
- Security stack (KMS, IAM)
- Neptune stack (database, networking)
- Lambda stack (functions, layers)
- API Gateway stack (endpoints, validation)
- Step Functions stack (workflows)
- Monitoring stack (CloudWatch, alarms)

### 2. CI/CD Pipeline

**Deployment Stages**:
1. Code validation and testing
2. Infrastructure provisioning
3. Lambda function deployment
4. Integration testing
5. Production deployment

## Disaster Recovery

### 1. Backup Strategy

**Neptune Backups**:
- Automated daily backups
- Point-in-time recovery
- Cross-region replication

**Lambda Functions**:
- Version management
- Blue/green deployments
- Rollback capabilities

### 2. High Availability

**Multi-AZ Deployment**:
- Neptune cluster across AZs
- Lambda function distribution
- API Gateway regional endpoints

## Cost Optimization

### 1. Resource Optimization

**Lambda Sizing**:
- Right-sized memory allocation
- Efficient execution time
- Reserved concurrency management

**Neptune Optimization**:
- Instance type selection
- Storage optimization
- Query performance tuning

### 2. Cost Monitoring

**Budget Controls**:
- Cost allocation tags
- Budget alerts and limits
- Resource usage monitoring

This architecture provides a robust, scalable, and compliant foundation for AI-powered anti-money laundering detection while maintaining security, performance, and cost-effectiveness.