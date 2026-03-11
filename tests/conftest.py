"""Pytest configuration and fixtures for Sentinel-AML tests."""

import os
import pytest
from unittest.mock import Mock, patch
from decimal import Decimal
from datetime import datetime, timezone

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "DEBUG"

from sentinel_aml.core.config import get_settings
from sentinel_aml.data.models import Account, Transaction, TransactionEdge
from sentinel_aml.data.neptune_client import NeptuneClient


@pytest.fixture(scope="session")
def test_settings():
    """Test settings fixture."""
    return get_settings()


@pytest.fixture
def mock_neptune_client():
    """Mock Neptune client for testing."""
    with patch('sentinel_aml.data.neptune_client.NeptuneClient') as mock_client:
        client_instance = Mock(spec=NeptuneClient)
        mock_client.return_value = client_instance
        yield client_instance


@pytest.fixture
def sample_account():
    """Sample account for testing."""
    return Account(
        account_id="ACC123456789",
        customer_name="John Doe",
        account_type="checking",
        risk_score=0.2,
        customer_id="CUST001",
        country_code="US",
        is_pep=False,
        kyc_status="verified",
        balance=Decimal("10000.00"),
        currency="USD",
        is_active=True
    )


@pytest.fixture
def sample_transaction():
    """Sample transaction for testing."""
    return Transaction(
        transaction_id="TXN123456789",
        amount=Decimal("1500.00"),
        timestamp=datetime.now(timezone.utc),
        transaction_type="transfer",
        currency="USD",
        description="Wire transfer",
        is_cash=False,
        is_international=False
    )


@pytest.fixture
def sample_transaction_edge(sample_transaction):
    """Sample transaction edge for testing."""
    return TransactionEdge(
        from_account_id="ACC123456789",
        to_account_id="ACC987654321",
        transaction_id=sample_transaction.transaction_id,
        amount=sample_transaction.amount,
        timestamp=sample_transaction.timestamp,
        transaction_type=sample_transaction.transaction_type
    )


@pytest.fixture
def sample_risk_score():
    """Sample risk score for testing."""
    from sentinel_aml.data.models import RiskScore
    return RiskScore(
        entity_id="ACC123456789",
        entity_type="account",
        risk_score=0.75,
        model_name="gnn_fraud_detector",
        model_version="v1.2.3",
        feature_scores={"velocity": 0.8, "amount_pattern": 0.7},
        explanation="High risk due to unusual transaction patterns",
        confidence=0.85,
        risk_factors=["high_velocity", "unusual_amounts"],
        pattern_matches=["smurfing_pattern"]
    )


@pytest.fixture
def sample_alert():
    """Sample alert for testing."""
    from sentinel_aml.data.models import Alert, RiskLevel, AlertStatus
    return Alert(
        case_id="CASE-20241201-ABC123",
        title="Suspicious Transaction Pattern",
        description="Multiple transactions below reporting threshold detected",
        risk_level=RiskLevel.HIGH,
        status=AlertStatus.OPEN,
        account_ids=["ACC123456789", "ACC987654321"],
        transaction_ids=["TXN001", "TXN002", "TXN003"],
        risk_score=0.85,
        suspicious_patterns=["smurfing", "structuring"],
        investigator_id="INV001"
    )


@pytest.fixture
def sample_sar():
    """Sample Suspicious Activity Report for testing."""
    from sentinel_aml.data.models import SuspiciousActivityReport
    from decimal import Decimal
    from datetime import datetime, timezone
    
    return SuspiciousActivityReport(
        case_id="CASE-20241201-ABC123",
        report_number="SAR-2024-001",
        subject_accounts=["ACC123456789", "ACC987654321"],
        subject_names=["hash_customer_1", "hash_customer_2"],
        activity_description="Structured cash deposits to avoid CTR reporting requirements",
        suspicious_patterns=["smurfing", "structuring", "cash_intensive"],
        transaction_summary="Multiple cash deposits under $10,000 over 30-day period",
        total_amount=Decimal("95000.00"),
        currency="USD",
        date_range_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        date_range_end=datetime(2024, 1, 31, tzinfo=timezone.utc),
        regulation_violated=["BSA", "AML"],
        reporting_reason="Potential money laundering through structured transactions",
        generated_by_ai=True,
        ai_model_version="claude-3-sonnet-v1",
        ai_confidence=0.92
    )
    """Sample suspicious transaction pattern for testing."""
    base_time = datetime.now(timezone.utc)
    transactions = []
    
    # Create pattern of small transactions (potential smurfing)
    for i in range(10):
        transactions.append(Transaction(
            transaction_id=f"TXN{i:06d}",
            amount=Decimal("9500.00"),  # Just under $10k reporting threshold
            timestamp=base_time,
            transaction_type="deposit",
            currency="USD",
            is_cash=True,
            is_international=False
        ))
    
    return transactions


@pytest.fixture
def mock_bedrock_client():
    """Mock Bedrock client for testing."""
    with patch('boto3.client') as mock_boto3:
        mock_client = Mock()
        mock_boto3.return_value = mock_client
        
        # Mock successful response
        mock_client.invoke_model.return_value = {
            'body': Mock(read=lambda: b'{"completion": "Mock SAR report generated"}')
        }
        
        yield mock_client


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


@pytest.fixture(autouse=True)
def reset_lru_cache():
    """Reset LRU cache for settings between tests."""
    get_settings.cache_clear()


# Pytest markers
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "property: Property-based tests")
    config.addinivalue_line("markers", "aws: Tests requiring AWS credentials")
    config.addinivalue_line("markers", "slow: Slow running tests")


# Skip AWS tests if credentials not available
def pytest_collection_modifyitems(config, items):
    """Modify test collection to skip AWS tests if credentials not available."""
    try:
        import boto3
        boto3.Session().get_credentials()
        aws_available = True
    except Exception:
        aws_available = False
    
    if not aws_available:
        skip_aws = pytest.mark.skip(reason="AWS credentials not available")
        for item in items:
            if "aws" in item.keywords:
                item.add_marker(skip_aws)