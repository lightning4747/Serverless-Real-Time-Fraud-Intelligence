"""Simple pytest configuration without Neptune dependencies."""

import os
import pytest
from unittest.mock import Mock
from decimal import Decimal
from datetime import datetime, timezone

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "DEBUG"


@pytest.fixture
def sample_transaction_data():
    """Sample transaction data for testing."""
    return {
        "from_account_id": "ACC123456789",
        "to_account_id": "ACC987654321",
        "amount": "1500.00",
        "transaction_type": "transfer",
        "currency": "USD",
        "description": "Test transfer",
        "channel": "api"
    }


@pytest.fixture
def mock_lambda_context():
    """Mock Lambda context for testing."""
    context = Mock()
    context.function_name = "test-function"
    context.function_version = "1"
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
    context.memory_limit_in_mb = 128
    context.remaining_time_in_millis = lambda: 30000
    context.aws_request_id = "test-request-id"
    return context


# Pytest markers
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "property: Property-based tests")
    config.addinivalue_line("markers", "aws: Tests requiring AWS credentials")
    config.addinivalue_line("markers", "slow: Slow running tests")