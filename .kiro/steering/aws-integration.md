# AWS Integration Guidelines

## AWS Services for AML System
- **SageMaker**: Model training, hosting, and batch transform jobs
- **Lambda**: Real-time inference and event processing
- **S3**: Data lake for transaction data and model artifacts
- **DynamoDB**: Customer profiles and risk scores
- **Kinesis**: Real-time transaction streaming
- **EventBridge**: Event-driven architecture for alerts
- **Step Functions**: Orchestrate complex ML workflows

## Security & Compliance
- **IAM**: Least privilege access for all services
- **KMS**: Encrypt sensitive financial data at rest and in transit
- **VPC**: Network isolation for sensitive workloads
- **CloudTrail**: Audit all API calls for compliance
- **Config**: Monitor configuration compliance

## Cost Optimization
- **Spot Instances**: Use for non-critical training jobs
- **Reserved Instances**: For predictable inference workloads
- **S3 Lifecycle**: Archive old transaction data to cheaper storage
- **Lambda Provisioned Concurrency**: Only for critical real-time functions

## Monitoring & Observability
- **CloudWatch**: Metrics, logs, and alarms for all services
- **X-Ray**: Distributed tracing for complex workflows
- **SageMaker Model Monitor**: Track model drift and data quality
- **Custom Metrics**: Business KPIs like false positive rates

## Deployment Patterns
- **Blue/Green**: Safe model deployments with rollback capability
- **Canary**: Gradual rollout of new models
- **Multi-AZ**: High availability for critical components
- **Auto Scaling**: Handle variable transaction volumes