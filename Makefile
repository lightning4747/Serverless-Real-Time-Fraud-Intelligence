# Makefile for Sentinel-AML development

.PHONY: help setup install test lint format clean deploy docs

# Default target
help:
	@echo "Sentinel-AML Development Commands"
	@echo "================================="
	@echo "setup     - Set up development environment"
	@echo "install   - Install dependencies"
	@echo "test      - Run all tests"
	@echo "lint      - Run linting checks"
	@echo "format    - Format code"
	@echo "clean     - Clean build artifacts"
	@echo "deploy    - Deploy infrastructure"
	@echo "docs      - Generate documentation"
	@echo "notebook  - Start Jupyter notebook server"

# Environment setup
setup:
	python scripts/setup.py

install:
	pip install -e .
	pip install -e ".[dev]"
	pip install -e ".[cdk]"

# Testing
test:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v -m "not aws"

test-property:
	pytest tests/property/ -v

test-aws:
	pytest tests/ -v -m aws

# Code quality
lint:
	flake8 src/ tests/
	mypy src/
	bandit -r src/ -f json

format:
	black src/ tests/ scripts/
	isort src/ tests/ scripts/

# Security
security:
	bandit -r src/ -f json
	safety check

# Documentation
docs:
	cd docs && make html

# Jupyter notebook
notebook:
	jupyter lab --ip=0.0.0.0 --port=8888 --no-browser

# Infrastructure
cdk-synth:
	cd infrastructure && cdk synth

cdk-diff:
	cd infrastructure && cdk diff

deploy:
	python scripts/deploy.py

deploy-dev:
	cd infrastructure && cdk deploy --all --require-approval never

destroy:
	cd infrastructure && cdk destroy --all --force

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	cd infrastructure && rm -rf cdk.out/

# Development helpers
dev-server:
	uvicorn src.sentinel_aml.api.main:app --reload --host 0.0.0.0 --port 8000

dev-neptune:
	docker run -p 8182:8182 amazonlinux

# Package management
requirements:
	pip-compile pyproject.toml
	pip-compile --extra dev pyproject.toml

upgrade:
	pip-compile --upgrade pyproject.toml
	pip-compile --upgrade --extra dev pyproject.toml

# Git hooks
hooks:
	pre-commit install
	pre-commit run --all-files

# Docker (if needed for local development)
docker-build:
	docker build -t sentinel-aml:latest .

docker-run:
	docker run -p 8000:8000 sentinel-aml:latest

# Monitoring
logs:
	aws logs tail /aws/lambda/sentinel-aml --follow

metrics:
	aws cloudwatch get-dashboard --dashboard-name Sentinel-AML-System-Metrics