# Sentinel-AML: AI-Powered Anti-Money Laundering Detection Platform

Sentinel-AML is an intelligent system for detecting and preventing money laundering activities using AI agents, graph neural networks, and generative AI. The system leverages Amazon Neptune for graph storage, Neptune ML for fraud pattern detection, and Amazon Bedrock for automated Suspicious Activity Report (SAR) generation.

## 🏗️ Architecture Overview

The system follows a serverless, event-driven architecture on AWS:

- **Graph Engine**: Amazon Neptune (TinkerPop/Gremlin) for transaction relationship storage
- **ML Layer**: Neptune ML (built on DGL/GNN) for node classification and fraud scoring  
- **Generative AI**: Amazon Bedrock (Claude 3) for automated SAR generation
- **Agent Orchestration**: AWS Step Functions coordinating the detection pipeline
- **Compute**: AWS Lambda functions for serverless processing
- **API**: Amazon API Gateway for REST endpoints
- **Infrastructure**: AWS CDK for infrastructure as code

## 🚀 Key Features

- **Real-time Transaction Processing**: Ingest and analyze up to 10,000 transactions per minute
- **Graph Neural Network Detection**: Advanced smurfing pattern detection using GNN models
- **Automated SAR Generation**: AI-powered Suspicious Activity Reports compliant with FinCEN requirements
- **Regulatory Compliance**: Built-in BSA, AML, KYC, and CTR compliance features
- **Audit Trail**: Complete immutable audit logs with 7-year retention
- **Enterprise Security**: AES-256 encryption, TLS 1.3, role-based access controls
- **Scalable Architecture**: Auto-scaling serverless components for enterprise workloads

## 📁 Project Structure

```
sentinel-aml/
├── src/
│   └── sentinel_aml/
│       ├── core/              # Core utilities and configuration
│       ├── data/              # Data models and Neptune integration
│       ├── agents/            # AI agent implementations
│       ├── models/            # ML model definitions and training
│       ├── api/               # API Gateway Lambda handlers
│       └── utils/             # Utility functions
├── infrastructure/            # AWS CDK infrastructure code
├── tests/                    # Test files (unit, integration, property)
├── notebooks/               # Jupyter notebooks for exploration
├── scripts/                 # Training and deployment scripts
├── configs/                 # Configuration files
└── docs/                   # Documentation
```

## 🛠️ Development Setup

### Prerequisites

- Python 3.9 or higher
- Node.js 18+ (for AWS CDK)
- AWS CLI configured with appropriate credentials
- Docker (for local Neptune development)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/sentinel-aml/sentinel-aml.git
   cd sentinel-aml
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   # Core dependencies
   pip install -e .
   
   # Development dependencies
   pip install -e ".[dev]"
   
   # CDK dependencies
   pip install -e ".[cdk]"
   
   # ML dependencies (optional)
   pip install -e ".[ml]"
   ```

4. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

5. **Set up AWS CDK**:
   ```bash
   cd infrastructure
   npm install
   cdk bootstrap
   ```

### Environment Configuration

Create a `.env` file in the project root:

```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=your-account-id

# Neptune Configuration
NEPTUNE_ENDPOINT=your-neptune-endpoint
NEPTUNE_PORT=8182

# Bedrock Configuration
BEDROCK_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0

# Application Configuration
LOG_LEVEL=INFO
ENVIRONMENT=development
```

## 🧪 Testing

The project uses comprehensive testing including unit tests, integration tests, and property-based tests:

```bash
# Run all tests
pytest

# Run specific test types
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only  
pytest -m property      # Property-based tests only

# Run with coverage
pytest --cov=src --cov-report=html
```

## 🚀 Deployment

### Local Development

```bash
# Start local Neptune (Docker)
docker run -p 8182:8182 amazonlinux

# Run API locally
uvicorn src.sentinel_aml.api.main:app --reload
```

### AWS Deployment

```bash
# Deploy infrastructure
cd infrastructure
cdk deploy --all

# Deploy Lambda functions
python scripts/deploy.py
```

## 📊 Monitoring and Observability

The system includes comprehensive monitoring:

- **CloudWatch Metrics**: Custom business KPIs and performance metrics
- **CloudWatch Logs**: Structured logging with correlation IDs
- **X-Ray Tracing**: Distributed tracing for complex workflows
- **Custom Dashboards**: Real-time monitoring of detection metrics

## 🔒 Security and Compliance

- **Data Encryption**: AES-256 at rest, TLS 1.3 in transit
- **Access Controls**: IAM roles with least privilege principles
- **Audit Logging**: Immutable audit trails for regulatory compliance
- **PII Protection**: Data masking and redaction for privacy
- **Regulatory Compliance**: BSA, AML, KYC, and FinCEN SAR requirements

## 📚 Documentation

- [API Documentation](docs/api.md)
- [Architecture Guide](docs/architecture.md)
- [Deployment Guide](docs/deployment.md)
- [Security Guide](docs/security.md)
- [Compliance Guide](docs/compliance.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:

- Create an [issue](https://github.com/sentinel-aml/sentinel-aml/issues)
- Check the [documentation](https://sentinel-aml.readthedocs.io)
- Contact the team at team@sentinel-aml.com

## 🏆 Acknowledgments

Built for the NEXUS Hackathon demonstrating modern cloud practices with AWS managed services for AI-powered financial compliance.