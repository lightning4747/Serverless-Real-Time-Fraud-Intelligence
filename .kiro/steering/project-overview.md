# AI/ML System Project Overview

This steering file provides context about the AI/ML project structure, conventions, and guidelines.

## Project Description
AI Agentic AML (Anti-Money Laundering) System - An intelligent system for detecting and preventing money laundering activities using AI agents and machine learning models.

## Technology Stack (Hackathon Optimized)
- **Graph Engine**: Amazon Neptune (TinkerPop/Gremlin) for Smurfing pattern storage.
- **ML Layer**: Neptune ML (built on DGL/GNN) for node classification and fraud scoring.
- **Generative AI**: Amazon Bedrock (Claude 3) for automated SAR (Suspicious Activity Report) generation.
- **Agent Orchestration**: AWS Step Functions or LangChain (running on AWS Lambda).
- **Compute**: AWS Lambda (Serverless) & Amazon API Gateway.
- **Spec-Driven Dev**: Kiro (Spec Mode) for all infrastructure scaffolding.

## Coding Standards
- Follow PEP 8 for Python code
- Use type hints for all function signatures
- Document all model parameters, hyperparameters, and data schemas
- Include docstrings for all classes and functions
- Use meaningful variable names that reflect financial/ML domain concepts
- Separate data preprocessing, model training, and inference code

## Build & Development
- Use virtual environments (venv, conda, or poetry)
- Include requirements.txt or environment.yml
- Provide clear setup instructions for data dependencies
- Use Jupyter notebooks for experimentation, Python modules for production
- Include data validation and schema checks
- Implement proper logging for model performance and agent actions

## Architecture Guidelines (NEXUS Hackathon Focus)
- **Graph-First**: All transaction data must be modeled as a Graph (Nodes: Users, Edges: Transactions).
- **Explainability**: Every GNN flag must trigger a Bedrock prompt to explain the "math" in "human" terms.
- **Serverless**: Minimize EC2 usage; prioritize Lambda and Managed Services to demonstrate "Modern Cloud Practices."

## Testing Strategy
- Unit tests for data preprocessing and utility functions
- Integration tests for model pipelines
- Property-based testing for data validation
- Model performance tests with baseline metrics
- Agent behavior testing with mock scenarios
- Data drift detection and monitoring