# Sentinel-AML Deployment Guide

This guide provides comprehensive instructions for deploying the Sentinel-AML system using AWS CDK and the automated deployment scripts.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Configuration](#configuration)
4. [Deployment Process](#deployment-process)
5. [Validation](#validation)
6. [Monitoring](#monitoring)
7. [Troubleshooting](#troubleshooting)
8. [Rollback Procedures](#rollback-procedures)

## Prerequisites

### Required Software

- **Python 3.11+**: For running the deployment scripts and CDK
- **Node.js 18+**: Required for AWS CDK
- **AWS CLI v2**: For AWS authentication and configuration
- **AWS CDK CLI**: For infrastructure deployment
- **Git**: For version control

### AWS Account Requirements

- AWS account with appropriate permissions
- AWS CLI configured with credentials
- Sufficient service limits for:
  - Lambda functions (7+ functions)
  - Neptune cluster
  - API Gateway
  - Step Functions
  - CloudWatch resources

### Permissions Required

The deploying user/role needs the following AWS permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "apigateway:*",
        "neptune:*",
        "stepfunctions:*",
        "iam:*",
        "kms:*",
        "s3:*",
        "logs:*",
        "cloudwatch:*",
        "sns:*",
        "ec2:*",
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

## Environment Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd sentinel-aml-agent-e
```

### 2. Install Python Dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r infrastructure/requirements.txt
```

### 3. Install Node.js Dependencies

```bash
npm install -g aws-cdk@latest
```

### 4. Configure AWS CLI

```bash
aws configure
# Enter your AWS Access Key ID, Secret Access Key, Region, and Output format
```

### 5. Verify Prerequisites

```bash
python scripts/deploy.py --environment development --action validate
```

## Configuration

### Environment-Specific Configuration

Configuration files are located in the `configs/` directory:

- `configs/deployment-development.json`: Development environment settings
- `configs/deployment-production.json`: Production environment settings

### Key Configuration Parameters

```json
{
  "environment": "development",
  "notification_email": "your-email@company.com",
  "enable_deletion_protection": false,
  "backup_retention_days": 7,
  "monitoring_level": "basic",
  "auto_scaling_enabled": false,
  "vpc_cidr": "10.0.0.0/16",
  "neptune_instance_class": "db.t3.medium",
  "lambda_memory_size": 512,
  "lambda_timeout_seconds": 300
}
```

### Environment Variables

Set the following environment variables:

```bash
export ENVIRONMENT=development  # or production
export AWS_REGION=us-east-1
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=$AWS_REGION
```

## Deployment Process

### 1. Bootstrap CDK (First Time Only)

```bash
python scripts/deploy.py --environment development --action bootstrap
```

### 2. Create Deployment Snapshot

```bash
python scripts/deploy.py --environment development --action snapshot
```

### 3. Deploy Infrastructure

#### Full Deployment

```bash
python scripts/deploy.py --environment development --action deploy
```

#### Selective Stack Deployment

```bash
python scripts/deploy.py --environment development --action deploy --stack-filter SentinelAMLSecurity
```

### 4. Validate Deployment

```bash
python scripts/deploy.py --environment development --action validate-deployment
```

### Manual CDK Commands (Alternative)

If you prefer using CDK directly:

```bash
cd infrastructure

# Synthesize CloudFormation templates
cdk synth --all

# Deploy all stacks
cdk deploy --all --require-approval never

# Deploy specific stack
cdk deploy SentinelAMLSecurity-development --require-approval never
```

## Validation

### Automated Validation

The deployment script includes automated validation:

```bash
python scripts/deploy.py --environment development --action validate-deployment
```

### Manual Validation Steps

1. **Check CloudFormation Stacks**
   ```bash
   aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE
   ```

2. **Test API Gateway**
   ```bash
   curl https://your-api-id.execute-api.us-east-1.amazonaws.com/prod/health
   ```

3. **Verify Lambda Functions**
   ```bash
   aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `sentinel-aml`)]'
   ```

4. **Check Step Functions**
   ```bash
   aws stepfunctions list-state-machines --query 'stateMachines[?contains(name, `sentinel-aml`)]'
   ```

### Smoke Tests

Run comprehensive smoke tests:

```bash
python -m pytest tests/smoke/ -v --environment=development
```

## Monitoring

### CloudWatch Dashboard

Access the monitoring dashboard:
1. Go to AWS CloudWatch Console
2. Navigate to Dashboards
3. Open "Sentinel-AML-System-Metrics"

### Key Metrics to Monitor

- **Lambda Function Metrics**
  - Duration
  - Error rate
  - Invocation count
  - Throttles

- **API Gateway Metrics**
  - Request count
  - Latency
  - 4XX/5XX errors

- **Step Functions Metrics**
  - Execution success rate
  - Execution duration
  - Failed executions

- **Neptune Metrics**
  - Database connections
  - Gremlin requests per second
  - CPU utilization

### Alerts

The system automatically creates CloudWatch alarms for:
- High Lambda error rates
- API Gateway 5XX errors
- Step Functions failures
- Neptune connectivity issues

## Troubleshooting

### Common Issues

#### 1. CDK Bootstrap Fails

**Error**: `Need to perform AWS CDK bootstrap`

**Solution**:
```bash
cdk bootstrap aws://ACCOUNT-ID/REGION
```

#### 2. Lambda Deployment Package Too Large

**Error**: `Unzipped size must be smaller than 262144000 bytes`

**Solution**: 
- Optimize dependencies in `requirements.txt`
- Use Lambda layers for common dependencies
- Remove unnecessary files from the package

#### 3. Neptune Connectivity Issues

**Error**: `Cannot connect to Neptune cluster`

**Solution**:
- Verify VPC configuration
- Check security group rules
- Ensure Lambda functions are in the correct subnets

#### 4. Step Functions Execution Failures

**Error**: `States.TaskFailed`

**Solution**:
- Check Lambda function logs in CloudWatch
- Verify IAM permissions
- Review Step Functions execution history

### Debugging Commands

```bash
# View CloudFormation events
aws cloudformation describe-stack-events --stack-name SentinelAMLLambda-development

# Check Lambda logs
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/sentinel-aml

# View Step Functions executions
aws stepfunctions list-executions --state-machine-arn <state-machine-arn>

# Test Lambda function
aws lambda invoke --function-name sentinel-aml-health-checker response.json
```

## Rollback Procedures

### Automated Rollback

```bash
python scripts/deploy.py --environment development --action rollback --snapshot-id <snapshot-id>
```

### Manual Rollback

1. **Identify Previous Version**
   ```bash
   aws s3 ls s3://sentinel-aml-deployments-ACCOUNT-ID/snapshots/
   ```

2. **Destroy Current Stacks**
   ```bash
   cdk destroy --all
   ```

3. **Redeploy from Snapshot**
   - Review snapshot configuration
   - Update deployment configuration if needed
   - Redeploy using standard process

### Emergency Rollback

For critical issues:

1. **Disable API Gateway**
   ```bash
   aws apigateway update-stage --rest-api-id <api-id> --stage-name prod --patch-ops op=replace,path=/throttle/rateLimit,value=0
   ```

2. **Stop Step Functions Executions**
   ```bash
   aws stepfunctions list-executions --state-machine-arn <arn> --status-filter RUNNING
   # Stop each running execution
   aws stepfunctions stop-execution --execution-arn <execution-arn>
   ```

3. **Scale Down Lambda Concurrency**
   ```bash
   aws lambda put-provisioned-concurrency-config --function-name <function-name> --provisioned-concurrency-config ProvisionedConcurrencyConfig=0
   ```

## CI/CD Pipeline

### GitHub Actions

The repository includes a GitHub Actions workflow (`.github/workflows/deploy.yml`) that:

1. Validates code and infrastructure
2. Runs tests
3. Deploys to development on `develop` branch
4. Deploys to production on `main` branch
5. Sends notifications on success/failure

### Required Secrets

Configure these secrets in your GitHub repository:

- `AWS_ACCESS_KEY_ID`: AWS access key for development
- `AWS_SECRET_ACCESS_KEY`: AWS secret key for development
- `PROD_AWS_ACCESS_KEY_ID`: AWS access key for production
- `PROD_AWS_SECRET_ACCESS_KEY`: AWS secret key for production
- `SLACK_WEBHOOK_URL`: Slack webhook for notifications

### Manual Pipeline Trigger

```bash
# Trigger development deployment
git push origin develop

# Trigger production deployment
git push origin main
```

## Security Considerations

### Data Encryption

- All data at rest is encrypted using AWS KMS
- Data in transit uses TLS 1.3
- PII is masked in logs and non-essential operations

### Network Security

- Neptune cluster is deployed in private subnets
- Lambda functions use VPC configuration
- Security groups restrict access to necessary ports only

### Access Control

- IAM roles follow least-privilege principle
- API Gateway uses API key authentication
- CloudTrail logs all API calls for audit

### Compliance

- 7-year data retention for compliance
- Immutable audit logs
- Regular security scans and updates

## Performance Optimization

### Lambda Optimization

- Use appropriate memory allocation
- Enable provisioned concurrency for critical functions
- Implement connection pooling for Neptune

### Neptune Optimization

- Use appropriate instance classes
- Implement query optimization
- Monitor and tune Gremlin queries

### API Gateway Optimization

- Configure appropriate throttling limits
- Use caching where appropriate
- Implement request/response compression

## Cost Management

### Cost Optimization Strategies

- Use Spot instances for non-critical workloads
- Implement S3 lifecycle policies
- Monitor and optimize Lambda memory allocation
- Use Reserved Instances for predictable workloads

### Cost Monitoring

- Set up billing alerts
- Use AWS Cost Explorer
- Tag resources for cost allocation
- Regular cost reviews and optimization

## Support and Maintenance

### Regular Maintenance Tasks

1. **Weekly**
   - Review CloudWatch alarms
   - Check system health metrics
   - Validate backup procedures

2. **Monthly**
   - Update dependencies
   - Review and optimize costs
   - Security patch updates

3. **Quarterly**
   - Disaster recovery testing
   - Performance optimization review
   - Security audit

### Getting Help

- Check CloudWatch logs for error details
- Review AWS service health dashboard
- Consult AWS documentation
- Contact AWS support for service-specific issues

---

For additional support or questions, please contact the development team or refer to the project documentation.