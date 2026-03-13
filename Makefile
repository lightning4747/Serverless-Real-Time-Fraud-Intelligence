# Sentinel-AML Deployment Makefile
# Provides simplified commands for common deployment tasks

.PHONY: help install validate bootstrap deploy deploy-dev deploy-prod test smoke-test clean

# Default environment
ENVIRONMENT ?= development
REGION ?= us-east-1

# Colors for output
RED = \033[0;31m
GREEN = \033[0;32m
YELLOW = \033[1;33m
BLUE = \033[0;34m
NC = \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Sentinel-AML Deployment Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

install: ## Install all dependencies
	@echo "$(YELLOW)Installing Python dependencies...$(NC)"
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	pip install -r infrastructure/requirements.txt
	@echo "$(YELLOW)Installing Node.js dependencies...$(NC)"
	npm install -g aws-cdk@latest
	@echo "$(GREEN)Dependencies installed successfully!$(NC)"

validate: ## Validate prerequisites and code
	@echo "$(YELLOW)Validating prerequisites...$(NC)"
	python scripts/deploy.py --environment $(ENVIRONMENT) --action validate
	@echo "$(YELLOW)Running code validation...$(NC)"
	python -m flake8 src/ tests/ --max-line-length=100 || true
	python -m black --check src/ tests/ || true
	@echo "$(GREEN)Validation completed!$(NC)"

bootstrap: ## Bootstrap CDK in the target account/region
	@echo "$(YELLOW)Bootstrapping CDK for $(ENVIRONMENT) in $(REGION)...$(NC)"
	python scripts/deploy.py --environment $(ENVIRONMENT) --region $(REGION) --action bootstrap
	@echo "$(GREEN)CDK bootstrap completed!$(NC)"

deploy: ## Deploy infrastructure to specified environment
	@echo "$(YELLOW)Deploying to $(ENVIRONMENT) environment...$(NC)"
	python scripts/deploy.py --environment $(ENVIRONMENT) --region $(REGION) --action snapshot
	python scripts/deploy.py --environment $(ENVIRONMENT) --region $(REGION) --action deploy
	python scripts/deploy.py --environment $(ENVIRONMENT) --region $(REGION) --action validate-deployment
	@echo "$(GREEN)Deployment completed successfully!$(NC)"

deploy-dev: ## Deploy to development environment
	@$(MAKE) deploy ENVIRONMENT=development

deploy-prod: ## Deploy to production environment
	@$(MAKE) deploy ENVIRONMENT=production

deploy-stack: ## Deploy specific stack (usage: make deploy-stack STACK=SentinelAMLSecurity)
	@echo "$(YELLOW)Deploying stack $(STACK) to $(ENVIRONMENT)...$(NC)"
	python scripts/deploy.py --environment $(ENVIRONMENT) --region $(REGION) --action deploy --stack-filter $(STACK)
	@echo "$(GREEN)Stack $(STACK) deployed successfully!$(NC)"

test: ## Run all tests
	@echo "$(YELLOW)Running unit tests...$(NC)"
	python -m pytest tests/unit/ -v --cov=src --cov-report=term-missing
	@echo "$(YELLOW)Running property tests...$(NC)"
	python -m pytest tests/property/ -v --maxfail=5
	@echo "$(YELLOW)Running integration tests...$(NC)"
	python -m pytest tests/integration/ -v --maxfail=3
	@echo "$(GREEN)All tests completed!$(NC)"

smoke-test: ## Run smoke tests against deployed environment
	@echo "$(YELLOW)Running smoke tests against $(ENVIRONMENT)...$(NC)"
	ENVIRONMENT=$(ENVIRONMENT) python -m pytest tests/smoke/ -v
	@echo "$(GREEN)Smoke tests completed!$(NC)"

deployment-test: ## Run deployment-specific tests
	@echo "$(YELLOW)Running deployment tests...$(NC)"
	python -m pytest tests/deployment/ -v
	@echo "$(GREEN)Deployment tests completed!$(NC)"

synth: ## Synthesize CloudFormation templates
	@echo "$(YELLOW)Synthesizing CDK templates...$(NC)"
	cd infrastructure && cdk synth --all
	@echo "$(GREEN)Templates synthesized successfully!$(NC)"

diff: ## Show differences between deployed and local infrastructure
	@echo "$(YELLOW)Showing infrastructure differences...$(NC)"
	cd infrastructure && cdk diff --all
	@echo "$(GREEN)Diff completed!$(NC)"

destroy: ## Destroy infrastructure (use with caution!)
	@echo "$(RED)WARNING: This will destroy all infrastructure in $(ENVIRONMENT)!$(NC)"
	@echo "$(RED)Press Ctrl+C to cancel, or wait 10 seconds to continue...$(NC)"
	@sleep 10
	cd infrastructure && cdk destroy --all --force
	@echo "$(GREEN)Infrastructure destroyed!$(NC)"

snapshot: ## Create deployment snapshot
	@echo "$(YELLOW)Creating deployment snapshot for $(ENVIRONMENT)...$(NC)"
	python scripts/deploy.py --environment $(ENVIRONMENT) --action snapshot
	@echo "$(GREEN)Snapshot created successfully!$(NC)"

rollback: ## Rollback to previous snapshot (usage: make rollback SNAPSHOT_ID=snapshot-id)
	@echo "$(YELLOW)Rolling back to snapshot $(SNAPSHOT_ID)...$(NC)"
	python scripts/deploy.py --environment $(ENVIRONMENT) --action rollback --snapshot-id $(SNAPSHOT_ID)
	@echo "$(GREEN)Rollback completed!$(NC)"

cleanup: ## Cleanup old snapshots and resources
	@echo "$(YELLOW)Cleaning up old resources...$(NC)"
	python scripts/deploy.py --environment $(ENVIRONMENT) --action cleanup
	@echo "$(GREEN)Cleanup completed!$(NC)"

logs: ## View recent Lambda logs (usage: make logs FUNCTION=transaction-processor)
	@echo "$(YELLOW)Fetching logs for sentinel-aml-$(FUNCTION)...$(NC)"
	aws logs tail /aws/lambda/sentinel-aml-$(FUNCTION) --follow

status: ## Check deployment status
	@echo "$(YELLOW)Checking deployment status for $(ENVIRONMENT)...$(NC)"
	@echo "$(BLUE)CloudFormation Stacks:$(NC)"
	aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query 'StackSummaries[?contains(StackName, `SentinelAML`) && contains(StackName, `$(ENVIRONMENT)`)].{Name:StackName,Status:StackStatus}' --output table
	@echo "$(BLUE)Lambda Functions:$(NC)"
	aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `sentinel-aml`)].{Name:FunctionName,Runtime:Runtime,State:State}' --output table
	@echo "$(GREEN)Status check completed!$(NC)"

health: ## Check system health
	@echo "$(YELLOW)Checking system health...$(NC)"
	python -c "
import boto3
import json
try:
    # Get API Gateway URL from CloudFormation
    cf = boto3.client('cloudformation')
    stacks = cf.describe_stacks(StackName='SentinelAMLAPI-$(ENVIRONMENT)')
    api_url = None
    for output in stacks['Stacks'][0].get('Outputs', []):
        if output['OutputKey'] == 'APIGatewayURL':
            api_url = output['OutputValue']
            break
    
    if api_url:
        import requests
        response = requests.get(f'{api_url}/health', timeout=10)
        print(f'API Health: {response.status_code} - {response.text}')
    else:
        print('API Gateway URL not found')
except Exception as e:
    print(f'Health check failed: {e}')
"
	@echo "$(GREEN)Health check completed!$(NC)"

format: ## Format code using black and isort
	@echo "$(YELLOW)Formatting Python code...$(NC)"
	python -m black src/ tests/ scripts/
	python -m isort src/ tests/ scripts/
	@echo "$(GREEN)Code formatting completed!$(NC)"

lint: ## Lint code using flake8
	@echo "$(YELLOW)Linting Python code...$(NC)"
	python -m flake8 src/ tests/ scripts/ --max-line-length=100
	@echo "$(GREEN)Linting completed!$(NC)"

security-scan: ## Run security scan on code
	@echo "$(YELLOW)Running security scan...$(NC)"
	python -m bandit -r src/ -f json -o security-report.json || true
	@echo "$(GREEN)Security scan completed! Check security-report.json$(NC)"

docs: ## Generate documentation
	@echo "$(YELLOW)Generating documentation...$(NC)"
	python -m sphinx-build -b html docs/ docs/_build/html/ || echo "Sphinx not installed, skipping docs generation"
	@echo "$(GREEN)Documentation generated!$(NC)"

env-dev: ## Set environment to development
	$(eval ENVIRONMENT := development)
	@echo "$(GREEN)Environment set to development$(NC)"

env-prod: ## Set environment to production
	$(eval ENVIRONMENT := production)
	@echo "$(GREEN)Environment set to production$(NC)"

quick-deploy: ## Quick deployment (skip tests and validation)
	@echo "$(YELLOW)Quick deployment to $(ENVIRONMENT) (skipping tests)...$(NC)"
	python scripts/deploy.py --environment $(ENVIRONMENT) --region $(REGION) --action deploy
	@echo "$(GREEN)Quick deployment completed!$(NC)"

full-deploy: ## Full deployment with all checks
	@echo "$(YELLOW)Full deployment pipeline for $(ENVIRONMENT)...$(NC)"
	@$(MAKE) validate
	@$(MAKE) test
	@$(MAKE) deploy
	@$(MAKE) smoke-test
	@echo "$(GREEN)Full deployment pipeline completed successfully!$(NC)"

ci-deploy: ## CI/CD deployment (for automated pipelines)
	@echo "$(YELLOW)CI/CD deployment for $(ENVIRONMENT)...$(NC)"
	python scripts/deploy.py --environment $(ENVIRONMENT) --region $(REGION) --action validate
	python scripts/deploy.py --environment $(ENVIRONMENT) --region $(REGION) --action snapshot
	python scripts/deploy.py --environment $(ENVIRONMENT) --region $(REGION) --action deploy
	python scripts/deploy.py --environment $(ENVIRONMENT) --region $(REGION) --action validate-deployment
	ENVIRONMENT=$(ENVIRONMENT) python -m pytest tests/smoke/ -v --tb=short
	@echo "$(GREEN)CI/CD deployment completed!$(NC)"

clean: ## Clean up temporary files and caches
	@echo "$(YELLOW)Cleaning up temporary files...$(NC)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + || true
	find . -type f -name ".coverage" -delete || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + || true
	find . -type d -name "cdk.out" -exec rm -rf {} + || true
	@echo "$(GREEN)Cleanup completed!$(NC)"

# Development shortcuts
dev: env-dev ## Switch to development environment
prod: env-prod ## Switch to production environment

# Common workflows
setup: install bootstrap ## Complete setup (install + bootstrap)
	@echo "$(GREEN)Setup completed! You can now run 'make deploy' to deploy the infrastructure.$(NC)"

update: ## Update dependencies and redeploy
	@$(MAKE) install
	@$(MAKE) deploy
	@echo "$(GREEN)Update completed!$(NC)"

# Help is the default target
.DEFAULT_GOAL := help