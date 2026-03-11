"""Integration tests for transaction ingestion Lambda function."""

import json
import pytest
import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch

from sentinel_aml.lambdas.transaction_processor import lambda_handler, process_transaction
from sentinel_aml.lambdas.connection_pool import NeptuneConnectionPool, get_connection_pool
from sentinel_aml.data.models import Account, Transaction, TransactionEdge, TransactionType, AccountType
from sentinel_aml.core.exceptions import NeptuneConnectionError, ProcessingError


@pytest.mark.integration
class TestTransactionIngestionIntegration:
    """Integration tests for complete transaction ingestion workflow."""
    
    @pytest.fixture
    def valid_transaction_event(self):
        """Create valid transaction event for testing."""
        return {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {
                "Content-Type": "application/json",
                "X-Correlation-ID": "test-correlation-123"
            },
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                "to_account_id": "ACC987654321",
                "amount": "1500.75",
                "transaction_type": "transfer",
                "currency": "USD",
                "description": "Integration test transfer",
                "channel": "api",
                "reference_number": "REF-INT-001",
                "from_account": {
                    "customer_name": "John Doe",
                    "account_type": "checking",
                    "risk_score": 0.1,
                    "country_code": "US"
                },
                "to_account": {
                    "customer_name": "Jane Smith",
                    "account_type": "savings",
                    "risk_score": 0.2,
                    "country_code": "US"
                }
            })
        }
    
    @pytest.fixture
    def mock_neptune_client(self):
        """Create mock Neptune client for integration tests."""
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
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    async def test_end_to_end_transaction_processing(self, mock_get_throttler, mock_neptune_class, 
                                                   valid_transaction_event, mock_neptune_client):
        """Test complete end-to-end transaction processing."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Process the transaction
        response = lambda_handler(valid_transaction_event, None)
        
        # Verify response
        assert response["statusCode"] == 200
        assert "X-Correlation-ID" in response["headers"]
        
        body = json.loads(response["body"])
        assert "data" in body
        assert body["data"]["status"] == "processed"
        assert "transaction_id" in body["data"]
        assert "processing_time_ms" in body["data"]
        assert "schema_validation_time_ms" in body["data"]
        assert "total_processing_time_ms" in body["data"]
        
        # Verify Neptune operations were called
        assert mock_neptune_client.create_account.call_count == 2  # Both accounts
        mock_neptune_client.create_transaction.assert_called_once()
        mock_neptune_client.create_transaction_edge.assert_called_once()
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    async def test_account_creation_with_existing_accounts(self, mock_get_throttler, mock_neptune_class,
                                                         valid_transaction_event, mock_neptune_client):
        """Test transaction processing when accounts already exist."""
        # Setup mocks - accounts already exist
        mock_neptune_class.return_value = mock_neptune_client
        mock_neptune_client.get_account.return_value = {"account_id": "existing"}
        
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Process the transaction
        response = lambda_handler(valid_transaction_event, None)
        
        # Verify response
        assert response["statusCode"] == 200
        
        # Verify accounts were not created (they already existed)
        mock_neptune_client.create_account.assert_not_called()
        
        # But transaction and edge were still created
        mock_neptune_client.create_transaction.assert_called_once()
        mock_neptune_client.create_transaction_edge.assert_called_once()
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    async def test_performance_requirements_validation(self, mock_get_throttler, mock_neptune_class,
                                                     valid_transaction_event, mock_neptune_client):
        """Test that performance requirements are met."""
        # Setup mocks with realistic delays
        mock_neptune_class.return_value = mock_neptune_client
        
        # Add small delays to simulate real operations
        async def delayed_operation(*args, **kwargs):
            await asyncio.sleep(0.01)  # 10ms delay
            return "result"
        
        mock_neptune_client.get_account.side_effect = delayed_operation
        mock_neptune_client.create_account.side_effect = delayed_operation
        mock_neptune_client.create_transaction.side_effect = delayed_operation
        mock_neptune_client.create_transaction_edge.side_effect = delayed_operation
        
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Process the transaction
        response = lambda_handler(valid_transaction_event, None)
        
        # Verify response
        assert response["statusCode"] == 200
        
        body = json.loads(response["body"])
        
        # Verify performance requirements
        # Schema validation should be under 100ms
        assert body["data"]["schema_validation_time_ms"] < 100
        
        # Total processing should be reasonable (allowing for mock delays)
        assert body["data"]["total_processing_time_ms"] < 1000
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    async def test_concurrent_request_handling(self, mock_get_throttler, mock_neptune_class,
                                             valid_transaction_event, mock_neptune_client):
        """Test handling of concurrent requests."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow requests
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Create multiple events with different transaction IDs
        events = []
        for i in range(5):
            event = valid_transaction_event.copy()
            body = json.loads(event["body"])
            body["from_account_id"] = f"ACC{i:09d}"
            body["to_account_id"] = f"ACC{i+1000:09d}"
            body["reference_number"] = f"REF-CONCURRENT-{i:03d}"
            event["body"] = json.dumps(body)
            events.append(event)
        
        # Process all events concurrently
        tasks = [lambda_handler(event, None) for event in events]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all responses are successful
        for response in responses:
            assert not isinstance(response, Exception)
            assert response["statusCode"] == 200
        
        # Verify all Neptune operations were called
        assert mock_neptune_client.create_transaction.call_count == 5
        assert mock_neptune_client.create_transaction_edge.call_count == 5
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    async def test_rate_limiting_integration(self, mock_get_throttler, mock_neptune_class,
                                           valid_transaction_event, mock_neptune_client):
        """Test rate limiting integration."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to reject requests after first few
        mock_throttler = AsyncMock()
        call_count = 0
        
        async def can_process_side_effect():
            nonlocal call_count
            call_count += 1
            return call_count <= 2  # Allow first 2 requests, reject rest
        
        mock_throttler.can_process_request.side_effect = can_process_side_effect
        mock_throttler.get_current_rate.return_value = 1500
        mock_throttler.max_requests_per_second = 1000
        mock_get_throttler.return_value = mock_throttler
        
        # Send multiple requests
        responses = []
        for i in range(5):
            response = lambda_handler(valid_transaction_event, None)
            responses.append(response)
        
        # Verify first 2 requests succeeded
        assert responses[0]["statusCode"] == 200
        assert responses[1]["statusCode"] == 200
        
        # Verify remaining requests were rate limited
        for response in responses[2:]:
            assert response["statusCode"] == 429
            body = json.loads(response["body"])
            assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    async def test_error_handling_and_recovery(self, mock_get_throttler, mock_neptune_class,
                                             valid_transaction_event, mock_neptune_client):
        """Test error handling and recovery mechanisms."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Test Neptune connection error
        mock_neptune_client.create_transaction.side_effect = NeptuneConnectionError("Connection failed")
        
        response = lambda_handler(valid_transaction_event, None)
        
        assert response["statusCode"] == 503
        body = json.loads(response["body"])
        assert body["error"]["code"] == "DATABASE_ERROR"
        assert "temporarily unavailable" in body["error"]["message"]
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    async def test_data_validation_edge_cases(self, mock_get_throttler, mock_neptune_class,
                                            mock_neptune_client):
        """Test data validation with various edge cases."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Test cases with various validation scenarios
        test_cases = [
            {
                "name": "minimum_amount",
                "body": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "0.01",  # Minimum valid amount
                    "transaction_type": "transfer",
                    "currency": "USD"
                },
                "expected_status": 200
            },
            {
                "name": "maximum_amount",
                "body": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "999999999.99",  # Maximum valid amount
                    "transaction_type": "transfer",
                    "currency": "USD"
                },
                "expected_status": 200
            },
            {
                "name": "zero_amount",
                "body": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "0.00",  # Invalid zero amount
                    "transaction_type": "transfer",
                    "currency": "USD"
                },
                "expected_status": 400
            },
            {
                "name": "negative_amount",
                "body": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "-100.00",  # Invalid negative amount
                    "transaction_type": "transfer",
                    "currency": "USD"
                },
                "expected_status": 400
            },
            {
                "name": "excessive_amount",
                "body": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "1000000000.00",  # Exceeds maximum
                    "transaction_type": "transfer",
                    "currency": "USD"
                },
                "expected_status": 400
            }
        ]
        
        for test_case in test_cases:
            event = {
                "httpMethod": "POST",
                "path": "/transactions",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(test_case["body"])
            }
            
            response = lambda_handler(event, None)
            
            assert response["statusCode"] == test_case["expected_status"], \
                f"Test case '{test_case['name']}' failed: expected {test_case['expected_status']}, got {response['statusCode']}"
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    async def test_international_transaction_handling(self, mock_get_throttler, mock_neptune_class,
                                                    mock_neptune_client):
        """Test handling of international transactions."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # International transaction event
        event = {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                "to_account_id": "ACC987654321",
                "amount": "5000.00",
                "transaction_type": "wire",
                "currency": "EUR",
                "description": "International wire transfer",
                "is_international": True,
                "country_code": "DE",
                "city": "Berlin",
                "from_account": {
                    "customer_name": "Hans Mueller",
                    "account_type": "business",
                    "country_code": "DE"
                },
                "to_account": {
                    "customer_name": "John Smith",
                    "account_type": "checking",
                    "country_code": "US"
                }
            })
        }
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 200
        
        # Verify transaction was processed with international flags
        mock_neptune_client.create_transaction.assert_called_once()
        transaction_call = mock_neptune_client.create_transaction.call_args[0][0]
        assert transaction_call.is_international is True
        assert transaction_call.currency == "EUR"
        assert transaction_call.country_code == "DE"
        assert transaction_call.city == "Berlin"


@pytest.mark.integration
class TestConnectionPoolIntegration:
    """Integration tests for connection pool functionality."""
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    async def test_connection_pool_initialization(self, mock_neptune_class):
        """Test connection pool initialization."""
        mock_client = AsyncMock()
        mock_neptune_class.return_value = mock_client
        
        pool = NeptuneConnectionPool(max_connections=5, min_connections=2)
        await pool.initialize()
        
        # Verify minimum connections were created
        assert len(pool._connections) == 2
        assert pool._stats.total_connections == 2
        
        # Verify connections were established
        assert mock_client.connect.call_count == 2
        
        await pool.close()
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    async def test_connection_pool_usage(self, mock_neptune_class):
        """Test connection pool usage patterns."""
        mock_client = AsyncMock()
        mock_neptune_class.return_value = mock_client
        
        pool = NeptuneConnectionPool(max_connections=3, min_connections=1)
        await pool.initialize()
        
        # Test getting and using connections
        async with pool.get_connection() as conn1:
            assert conn1 is not None
            assert pool._stats.active_connections == 1
        
        # Connection should be returned to pool
        assert pool._stats.active_connections == 0
        assert pool._stats.requests_processed == 1
        
        # Test concurrent connection usage
        async def use_connection():
            async with pool.get_connection() as conn:
                await asyncio.sleep(0.01)  # Simulate work
                return conn
        
        # Use multiple connections concurrently
        tasks = [use_connection() for _ in range(3)]
        connections = await asyncio.gather(*tasks)
        
        # All tasks should complete successfully
        assert len(connections) == 3
        assert pool._stats.requests_processed == 4  # 1 + 3
        
        await pool.close()
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    async def test_connection_pool_health_check(self, mock_neptune_class):
        """Test connection pool health check."""
        mock_client = AsyncMock()
        mock_client.get_health_status.return_value = {
            "status": "healthy",
            "vertex_count": 1000,
            "edge_count": 2000
        }
        mock_neptune_class.return_value = mock_client
        
        pool = NeptuneConnectionPool(max_connections=2, min_connections=1)
        await pool.initialize()
        
        health = await pool.health_check()
        
        assert health["status"] == "healthy"
        assert "pool_stats" in health
        assert "neptune_health" in health
        assert health["neptune_health"]["status"] == "healthy"
        
        await pool.close()