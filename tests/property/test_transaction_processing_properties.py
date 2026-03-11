"""
Property-based tests for transaction processing data integrity.

This module implements Property 2: Data integrity - All valid transactions must be stored correctly.
Validates Requirements 1.1, 1.2, 1.5 using property-based testing with Hypothesis.
"""

import json
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from hypothesis.strategies import composite

from sentinel_aml.core.exceptions import ValidationError, ProcessingError
from sentinel_aml.data.models import Account, Transaction, TransactionEdge, TransactionType, AccountType
from sentinel_aml.lambdas.transaction_processor import (
    lambda_handler,
    TransactionRequest
)


# Hypothesis strategies for generating test data
@composite
def valid_account_id(draw):
    """Generate valid account IDs."""
    prefix = draw(st.sampled_from(["ACC", "ACCT", "A"]))
    number = draw(st.integers(min_value=100000000, max_value=999999999999))
    return f"{prefix}{number}"


@composite
def valid_amount(draw):
    """Generate valid transaction amounts."""
    # Generate amounts between 0.01 and 999999999.99
    dollars = draw(st.integers(min_value=0, max_value=999999999))
    cents = draw(st.integers(min_value=1 if dollars == 0 else 0, max_value=99))
    return Decimal(f"{dollars}.{cents:02d}")


@composite
def valid_currency(draw):
    """Generate valid currency codes."""
    return draw(st.sampled_from(["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF"]))


@composite
def valid_transaction_type(draw):
    """Generate valid transaction types."""
    return draw(st.sampled_from([t.value for t in TransactionType]))


@composite
def valid_account_type(draw):
    """Generate valid account types."""
    return draw(st.sampled_from([t.value for t in AccountType]))


@composite
def valid_timestamp(draw):
    """Generate valid timestamps."""
    # Generate timestamps within reasonable range (last 10 years to 1 year future)
    # Note: min_value and max_value must be timezone-naive for Hypothesis
    min_timestamp = datetime(2014, 1, 1)
    max_timestamp = datetime(2026, 12, 31)
    
    timestamp = draw(st.datetimes(
        min_value=min_timestamp,
        max_value=max_timestamp,
        timezones=st.just(timezone.utc)
    ))
    return timestamp


@composite
def valid_customer_name(draw):
    """Generate valid customer names."""
    first_names = ["John", "Jane", "Michael", "Sarah", "David", "Lisa", "Robert", "Emily"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
    
    first = draw(st.sampled_from(first_names))
    last = draw(st.sampled_from(last_names))
    return f"{first} {last}"


@composite
def valid_account_info(draw):
    """Generate valid account information."""
    return {
        "customer_name": draw(valid_customer_name()),
        "account_type": draw(valid_account_type()),
        "risk_score": draw(st.floats(min_value=0.0, max_value=1.0)),
        "country_code": draw(st.sampled_from(["US", "CA", "GB", "DE", "FR", "JP", "AU"])),
        "customer_id": draw(st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))),
        "is_pep": draw(st.booleans()),
        "kyc_status": draw(st.sampled_from(["pending", "approved", "rejected", "expired"])),
        "balance": float(draw(st.floats(min_value=0.0, max_value=1000000.0))),
        "currency": draw(valid_currency()),
        "is_active": draw(st.booleans())
    }


@composite
def valid_transaction_data(draw):
    """Generate valid transaction data for property testing."""
    from_account_id = draw(valid_account_id())
    to_account_id = draw(valid_account_id())
    
    # Ensure different accounts
    assume(from_account_id != to_account_id)
    
    transaction_data = {
        "from_account_id": from_account_id,
        "to_account_id": to_account_id,
        "amount": str(draw(valid_amount())),
        "transaction_type": draw(valid_transaction_type()),
        "currency": draw(valid_currency()),
        "description": draw(st.text(min_size=0, max_size=200)),
        "reference_number": draw(st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Pd")))),
        "channel": draw(st.sampled_from(["api", "web", "mobile", "atm", "branch"])),
        "timestamp": draw(valid_timestamp()).isoformat(),
        "country_code": draw(st.sampled_from(["US", "CA", "GB", "DE", "FR", "JP", "AU"])),
        "city": draw(st.text(min_size=2, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Zs")))),
        "is_cash": draw(st.booleans()),
        "is_international": draw(st.booleans()),
        "from_account": draw(valid_account_info()),
        "to_account": draw(valid_account_info())
    }
    
    return transaction_data


class TestTransactionProcessingProperties:
    """Property-based tests for transaction processing data integrity."""
    
    @pytest.fixture
    def mock_neptune_client(self):
        """Create mock Neptune client for property testing."""
        client = AsyncMock()
        
        # Mock account operations
        client.get_account.return_value = None  # Account doesn't exist initially
        client.create_account.return_value = "account_vertex_id"
        
        # Mock transaction operations  
        client.create_transaction.return_value = "transaction_vertex_id"
        client.create_transaction_edge.return_value = "edge_id"
        
        # Mock health check
        client.get_health_status.return_value = {
            "status": "healthy",
            "vertex_count": 1000,
            "edge_count": 2000
        }
        
        return client
    
    @given(transaction_data=valid_transaction_data())
    @settings(max_examples=10, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_data_integrity_all_valid_transactions_stored_correctly(
        self, 
        transaction_data
    ):
        """
        Property 2: Data integrity - All valid transactions must be stored correctly.
        
        For ANY valid transaction data:
        - WHEN processed through the transaction ingestion pipeline
        - THEN the transaction MUST be stored correctly in Neptune
        
        Validates Requirements 1.1, 1.2, 1.5
        """
        with patch('sentinel_aml.lambdas.transaction_processor.get_connection_pool') as mock_get_pool, \
             patch('sentinel_aml.lambdas.transaction_processor.get_throttler') as mock_get_throttler:
            
            # Create mock Neptune client
            mock_neptune_client = AsyncMock()
            mock_neptune_client.get_account.return_value = None  # Account doesn't exist initially
            mock_neptune_client.create_account.return_value = "account_vertex_id"
            mock_neptune_client.create_transaction.return_value = "transaction_vertex_id"
            mock_neptune_client.create_transaction_edge.return_value = "edge_id"
            mock_neptune_client.get_health_status.return_value = {
                "status": "healthy",
                "vertex_count": 1000,
                "edge_count": 2000
            }
            
            # Setup connection pool mock - get_connection_pool() is async
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_neptune_client)
            mock_cm.__aexit__ = AsyncMock(return_value=None)
            
            mock_pool = AsyncMock()
            mock_pool.get_connection = MagicMock(return_value=mock_cm)
            
            # get_connection_pool is async, so mock it as a coroutine
            async def mock_get_pool_func():
                return mock_pool
            
            mock_get_pool.side_effect = mock_get_pool_func
            
            # Mock throttler to allow request
            mock_throttler = AsyncMock()
            mock_throttler.can_process_request.return_value = True
            mock_get_throttler.return_value = mock_throttler
            
            # Create Lambda event
            event = {
                "httpMethod": "POST",
                "path": "/transactions",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(transaction_data)
            }
            
            # Process the transaction
            response = lambda_handler(event, None)
            
            # Property assertion: All valid transactions must result in successful processing
            assert response["statusCode"] == 200, f"Valid transaction should succeed, got {response['statusCode']}"
            
            body = json.loads(response["body"])
            assert "data" in body
            assert body["data"]["status"] == "processed"
            
            # Verify Neptune operations were called correctly
            # Note: If accounts already exist, create_account won't be called
            # But transaction and edge should always be created
            mock_neptune_client.create_transaction.assert_called_once()
            mock_neptune_client.create_transaction_edge.assert_called_once()
            
            # Verify account lookups were performed
            assert mock_neptune_client.get_account.call_count >= 2  # At least 2 account lookups
            
            # Verify performance requirements
            assert body["data"]["schema_validation_time_ms"] < 100, "Schema validation should be under 100ms"
            assert body["data"]["processing_time_ms"] < 500, "Processing should be under 500ms"
    
    @given(transaction_data=valid_transaction_data())
    @settings(max_examples=10, deadline=3000)
    def test_property_transaction_request_validation_preserves_data_integrity(self, transaction_data):
        """
        Property: Transaction request validation preserves all data without corruption.
        
        For ANY valid transaction data:
        - WHEN parsed through TransactionRequest validation
        - THEN all data MUST be preserved accurately with correct types
        """
        # Create TransactionRequest from generated data
        request = TransactionRequest(transaction_data)
        
        # Verify all data is preserved with correct types
        assert request.from_account_id == transaction_data["from_account_id"]
        assert request.to_account_id == transaction_data["to_account_id"]
        assert request.amount == Decimal(transaction_data["amount"])
        assert request.transaction_type.value == transaction_data["transaction_type"]
        assert request.currency == transaction_data["currency"]
        
        # Verify timestamp parsing
        expected_timestamp = datetime.fromisoformat(transaction_data["timestamp"].replace('Z', '+00:00'))
        assert request.timestamp == expected_timestamp
        
        # Verify account info preservation
        assert request.from_account_info == transaction_data["from_account"]
        assert request.to_account_info == transaction_data["to_account"]


class TestTransactionProcessingExamples:
    """Example-based tests for specific edge cases and scenarios."""
    
    @pytest.fixture
    def mock_neptune_client(self):
        """Create mock Neptune client."""
        client = AsyncMock()
        client.get_account.return_value = None
        client.create_account.return_value = "account_vertex_id"
        client.create_transaction.return_value = "transaction_vertex_id"
        client.create_transaction_edge.return_value = "edge_id"
        return client
    
    @patch('sentinel_aml.lambdas.transaction_processor.get_connection_pool')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_minimum_amount_transaction_integrity(
        self, 
        mock_get_throttler, 
        mock_get_pool,
        mock_neptune_client
    ):
        """Test data integrity for minimum amount transactions."""
        # Setup connection pool mock - get_connection_pool() is async
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_neptune_client
        mock_cm.__aexit__.return_value = None
        
        mock_pool = AsyncMock()
        mock_pool.get_connection = MagicMock(return_value=mock_cm)
        
        # get_connection_pool is async, so mock it as a coroutine
        async def mock_get_pool_func():
            return mock_pool
        
        mock_get_pool.side_effect = mock_get_pool_func
        
        # Setup throttler mock
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Minimum amount transaction
        transaction_data = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "0.01",  # Minimum amount
            "transaction_type": "transfer",
            "currency": "USD",
            "from_account": {"customer_name": "John Doe", "account_type": "checking"},
            "to_account": {"customer_name": "Jane Smith", "account_type": "savings"}
        }
        
        event = {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(transaction_data)
        }
        
        response = lambda_handler(event, None)
        
        # Verify successful processing
        assert response["statusCode"] == 200
        
        # Verify exact amount preservation
        transaction_call = mock_neptune_client.create_transaction.call_args[0][0]
        assert transaction_call.amount == Decimal("0.01")
        
        edge_call = mock_neptune_client.create_transaction_edge.call_args[0][0]
        assert edge_call.amount == Decimal("0.01")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])