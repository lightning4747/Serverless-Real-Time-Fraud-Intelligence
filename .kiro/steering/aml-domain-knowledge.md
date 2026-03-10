# AML Domain Knowledge

## Anti-Money Laundering Context
- **Regulatory Compliance**: Follow BSA, AML, KYC, and CTR requirements
- **Risk Categories**: Structuring, layering, integration, smurfing
- **Red Flags**: Unusual transaction patterns, high-risk jurisdictions, PEPs
- **Reporting**: SAR (Suspicious Activity Reports) generation and filing

## Financial Data Patterns
- **Transaction Features**: Amount, frequency, timing, counterparties
- **Customer Profiles**: Account age, transaction history, risk scores
- **Network Analysis**: Money flow patterns, entity relationships
- **Temporal Patterns**: Seasonality, anomalous timing, velocity

## Model Considerations
- **False Positive Management**: Balance detection vs operational burden
- **Explainability**: Models must provide clear reasoning for alerts
- **Real-time Processing**: Low latency requirements for transaction monitoring
- **Data Privacy**: Handle PII and financial data with appropriate security

## Agent Responsibilities
- **Alert Triage**: Prioritize and route suspicious activities
- **Investigation Support**: Gather relevant context and evidence
- **Report Generation**: Automate SAR preparation and documentation
- **Continuous Learning**: Adapt to new laundering techniques

## Compliance Requirements
- **Audit Trail**: Maintain complete decision logs
- **Model Governance**: Document model changes and approvals
- **Data Retention**: Follow regulatory data retention policies
- **Testing**: Regular model validation and backtesting