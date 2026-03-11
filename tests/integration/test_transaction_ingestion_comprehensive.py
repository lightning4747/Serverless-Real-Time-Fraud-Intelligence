"""
Comprehensive integration tests for transaction ingestion Lambda function.

This module implements integration tests for Requirements 1.1, 1.2, 1.3, 1.4
covering end-to-end transaction flow with Neptune and error scenarios.
"""

import asyncio
import json
import pytest
import time
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed

from sentinel_aml.core.exceptions import (
    ValidationError,
    ProcessingError,
    NeptuneConnectionError,
    NeptuneQueryError
)
from sentinel_aml.data.models import Account, Transaction, TransactionEdge, TransactionType, AccountType
from sentinel_aml.lambdas.transaction_processor import lambda_handler, health_check_handler
from sentinel_aml.lambdas.connection_pool import NeptuneConnectionPool, RequestThrottler


@pytest.mark.integration
class TestTransactionIngestionEndToEnd:
    """End-to-end integration tests for transaction ingestion workflow."""
    
    @pytest.fixture
    def mock_neptune_client(self):
        """Create comprehensive mock Neptune client."""
        client = AsyncMock()
        
        # Mock account operations
        client.get_account.return_value = None  # Account doesn't exist initially
        client.create_account.return_value = "account_vertex_id_123"
        
        # Mock transaction operations
        client.create_transaction.return_value = "transaction_vertex_id_456"
        client.create_transaction_edge.return_value = "edge_id_789"
        
        # Mock connection management
        client.connect.return_value = None
        client.disconnect.return_value = None
        
        # Mock health check
        client.get_health_status.return_value = {
            "status": "healthy",
            "vertex_count": 1000,
            "edge_count": 2000,
            "cluster_status": "available"
        }
        
        return client
    
    @pytest.fixture
    def valid_transaction_event(self):
        """Create comprehensive valid transaction event."""
        return {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {
                "Content-Type": "application/json",
                "X-Correlation-ID": "integration-test-001",
                "Authorization": "Bearer test-token"
            },
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                "to_account_id": "ACC987654321",
                "amount": "2500.50",
                "transaction_type": "wire",
                "currency": "USD",
                "description": "Integration test wire transfer",
                "reference_number": "INT-TEST-001",
                "channel": "api",
                "timestamp": "2024-01-15T14:30:00Z",
                "country_code": "US",
                "city": "New York",
                "is_cash": False,
                "is_international": False,
                "from_account": {
                    "customer_name": "John Doe",
                    "account_type": "business",
                    "risk_score": 0.2,
                    "country_code": "US",
                    "customer_id": "US123456789",
                    "is_pep": False,
                    "kyc_status": "approved",
                    "balance": 100000.0,
                    "currency": "USD",
                    "is_active": True
                },
                "to_account": {
                    "customer_name": "Jane Smith",
                    "account_type": "checking",
                    "risk_score": 0.1,
                    "country_code": "US",
                    "customer_id": "US987654321",
                    "is_pep": False,
                    "kyc_status": "approved",
                    "balance": 25000.0,
                    "currency": "USD",
                    "is_active": True
                }
            })
        }
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_complete_transaction_flow_with_neptune_integration(
        self, 
        mock_get_throttler, 
        mock_neptune_class, 
        valid_transaction_event,
        mock_neptune_client
    ):
        """
        Test complete end-to-end transaction flow with Neptune integration.
        
        Validates Requirements 1.1, 1.2, 1.3, 1.4, 1.5:
        - Schema validation within 100ms
        - Transaction storage within 500ms
        - Proper error handling
        - Concurrent request handling
        - Account and edge creation
        """
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_throttler.get_current_rate.return_value = 50.0
        mock_throttler.max_requests_per_second = 1000
        mock_get_throttler.return_value = mock_throttler
        
        # Execute transaction processing
        start_time = time.time()
        response = lambda_handler(valid_transaction_event, None)
        total_time = (time.time() - start_time) * 1000
        
        # Verify successful response
        assert response["statusCode"] == 200
        assert "X-Correlation-ID" in response["headers"]
        assert response["headers"]["X-Correlation-ID"] == "integration-test-001"
        
        # Parse response body
        body = json.loads(response["body"])
        assert "data" in body
        assert body["data"]["status"] == "processed"
        assert "transaction_id" in body["data"]
        assert body["data"]["vertex_id"] == "transaction_vertex_id_456"
        assert body["data"]["edge_id"] == "edge_id_789"
        
        # Verify performance requirements
        assert body["data"]["schema_validation_time_ms"] < 100, "Schema validation exceeded 100ms"
        assert body["data"]["processing_time_ms"] < 500, "Processing exceeded 500ms"
        assert body["data"]["total_processing_time_ms"] < 1000, "Total processing too slow"
        
        # Verify Neptune operations sequence
        # 1. Account existence checks (2 calls)
        assert mock_neptune_client.get_account.call_count == 2
        
        # 2. Account creation (2 calls - both accounts created)
        assert mock_neptune_client.create_account.call_count == 2
        
        # 3. Transaction creation (1 call)
        mock_neptune_client.create_transaction.assert_called_once()
        
        # 4. Transaction edge creation (1 call)
        mock_neptune_client.create_transaction_edge.assert_called_once()
        
        # Verify data integrity in Neptune calls
        transaction_call = mock_neptune_client.create_transaction.call_args[0][0]
        assert transaction_call.amount == Decimal("2500.50")
        assert transaction_call.transaction_type == TransactionType.WIRE
        assert transaction_call.currency == "USD"
        assert transaction_call.description == "Integration test wire transfer"
        
        edge_call = mock_neptune_client.create_transaction_edge.call_args[0][0]
        assert edge_call.from_account_id == "ACC123456789"
        assert edge_call.to_account_id == "ACC987654321"
        assert edge_call.amount == Decimal("2500.50")
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_existing_accounts_optimization(
        self, 
        mock_get_throttler, 
        mock_neptune_class, 
        valid_transaction_event,
        mock_neptune_client
    ):
        """Test optimization when accounts already exist in Neptune."""
        # Setup mocks - accounts already exist
        mock_neptune_class.return_value = mock_neptune_client
        mock_neptune_client.get_account.return_value = {
            "account_id": "existing_account",
            "properties": {"account_type": "checking"}
        }
        
        # Mock throttler
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Process transaction
        response = lambda_handler(valid_transaction_event, None)
        
        # Verify successful processing
        assert response["statusCode"] == 200
        
        # Verify accounts were NOT created (they already existed)
        mock_neptune_client.create_account.assert_not_called()
        
        # But transaction and edge were still created
        mock_neptune_client.create_transaction.assert_called_once()
        mock_neptune_client.create_transaction_edge.assert_called_once()
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_concurrent_transaction_processing(
        self, 
        mock_get_throttler, 
        mock_neptune_class,
        mock_neptune_client
    ):
        """Test concurrent transaction processing under load."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow all requests
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Create multiple transaction events
        events = []
        for i in range(10):
            event = {
                "httpMethod": "POST",
                "path": "/transactions",
                "headers": {
                    "Content-Type": "application/json",
                    "X-Correlation-ID": f"concurrent-test-{i:03d}"
                },
                "body": json.dumps({
                    "from_account_id": f"ACC{i:09d}",
                    "to_account_id": f"ACC{i+1000:09d}",
                    "amount": f"{100 + i}.{i:02d}",
                    "transaction_type": "transfer",
                    "currency": "USD",
                    "reference_number": f"CONCURRENT-{i:03d}",
                    "from_account": {
                        "customer_name": f"Customer {i}",
                        "account_type": "checking"
                    },
                    "to_account": {
                        "customer_name": f"Recipient {i}",
                        "account_type": "savings"
                    }
                })
            }
            events.append(event)
        
        # Process all events concurrently using ThreadPoolExecutor
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(lambda_handler, event, None) for event in events]
            responses = [future.result() for future in as_completed(futures)]
        
        processing_time = (time.time() - start_time) * 1000
        
        # Verify all responses are successful
        successful_responses = [r for r in responses if r["statusCode"] == 200]
        assert len(successful_responses) == 10, "All concurrent transactions should succeed"
        
        # Verify reasonable processing time for concurrent load
        assert processing_time < 5000, f"Concurrent processing took {processing_time}ms, should be under 5s"
        
        # Verify correct number of Neptune operations
        assert mock_neptune_client.create_transaction.call_count == 10
        assert mock_neptune_client.create_account.call_count == 20  # 2 accounts per transaction
        assert mock_neptune_client.create_transaction_edge.call_count == 10

@pytest.mark.integration
class TestErrorScenariosAndRecovery:
    """Integration tests for error scenarios and recovery mechanisms."""
    
    @pytest.fixture
    def mock_neptune_client(self):
        """Create mock Neptune client for error testing."""
        client = AsyncMock()
        client.get_account.return_value = None
        client.create_account.return_value = "account_vertex_id"
        client.create_transaction.return_value = "transaction_vertex_id"
        client.create_transaction_edge.return_value = "edge_id"
        return client
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_neptune_connection_error_handling(
        self, 
        mock_get_throttler, 
        mock_neptune_class,
        mock_neptune_client
    ):
        """Test handling of Neptune connection errors."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Simulate Neptune connection error
        mock_neptune_client.create_transaction.side_effect = NeptuneConnectionError("Connection timeout")
        
        # Create test event
        event = {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                "to_account_id": "ACC987654321",
                "amount": "1000.00",
                "transaction_type": "transfer",
                "currency": "USD",
                "from_account": {"customer_name": "John Doe", "account_type": "checking"},
                "to_account": {"customer_name": "Jane Smith", "account_type": "savings"}
            })
        }
        
        # Process transaction
        response = lambda_handler(event, None)
        
        # Verify error response
        assert response["statusCode"] == 503
        
        body = json.loads(response["body"])
        assert body["error"]["code"] == "DATABASE_ERROR"
        assert "temporarily unavailable" in body["error"]["message"]
        assert "processing_time_ms" in body["error"]["details"]
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_neptune_query_error_handling(
        self, 
        mock_get_throttler, 
        mock_neptune_class,
        mock_neptune_client
    ):
        """Test handling of Neptune query errors."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Simulate Neptune query error
        mock_neptune_client.create_transaction_edge.side_effect = NeptuneQueryError("Invalid query syntax")
        
        # Create test event
        event = {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                "to_account_id": "ACC987654321",
                "amount": "1000.00",
                "transaction_type": "transfer",
                "currency": "USD",
                "from_account": {"customer_name": "John Doe", "account_type": "checking"},
                "to_account": {"customer_name": "Jane Smith", "account_type": "savings"}
            })
        }
        
        # Process transaction
        response = lambda_handler(event, None)
        
        # Verify error response
        assert response["statusCode"] == 503
        
        body = json.loads(response["body"])
        assert body["error"]["code"] == "DATABASE_ERROR"
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_rate_limiting_error_handling(
        self, 
        mock_get_throttler, 
        mock_neptune_class,
        mock_neptune_client
    ):
        """Test rate limiting error handling."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to reject requests
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = False
        mock_throttler.get_current_rate.return_value = 1500.0
        mock_throttler.max_requests_per_second = 1000
        mock_get_throttler.return_value = mock_throttler
        
        # Create test event
        event = {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                "to_account_id": "ACC987654321",
                "amount": "1000.00",
                "transaction_type": "transfer",
                "currency": "USD",
                "from_account": {"customer_name": "John Doe", "account_type": "checking"},
                "to_account": {"customer_name": "Jane Smith", "account_type": "savings"}
            })
        }
        
        # Process transaction
        response = lambda_handler(event, None)
        
        # Verify rate limiting response
        assert response["statusCode"] == 429
        
        body = json.loads(response["body"])
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert body["error"]["details"]["current_rate"] == 1500.0
        assert body["error"]["details"]["max_rate"] == 1000
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_validation_error_handling(
        self, 
        mock_get_throttler, 
        mock_neptune_class,
        mock_neptune_client
    ):
        """Test validation error handling with detailed error messages."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Test cases for various validation errors
        test_cases = [
            {
                "name": "missing_required_fields",
                "data": {
                    "from_account_id": "ACC123456789",
                    # Missing to_account_id, amount, transaction_type, currency
                },
                "expected_code": "MISSING_REQUIRED_FIELDS"
            },
            {
                "name": "invalid_amount",
                "data": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "-100.00",  # Negative amount
                    "transaction_type": "transfer",
                    "currency": "USD"
                },
                "expected_code": "INVALID_AMOUNT"
            },
            {
                "name": "same_account_transfer",
                "data": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC123456789",  # Same as from_account_id
                    "amount": "100.00",
                    "transaction_type": "transfer",
                    "currency": "USD"
                },
                "expected_code": "SAME_ACCOUNT_TRANSFER"
            },
            {
                "name": "unsupported_currency",
                "data": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "100.00",
                    "transaction_type": "transfer",
                    "currency": "XYZ"  # Invalid currency
                },
                "expected_code": "UNSUPPORTED_CURRENCY"
            },
            {
                "name": "invalid_transaction_type",
                "data": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "100.00",
                    "transaction_type": "invalid_type",
                    "currency": "USD"
                },
                "expected_code": "INVALID_TRANSACTION_TYPE"
            }
        ]
        
        for test_case in test_cases:
            event = {
                "httpMethod": "POST",
                "path": "/transactions",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(test_case["data"])
            }
            
            response = lambda_handler(event, None)
            
            # Verify error response
            assert response["statusCode"] == 400, f"Test case '{test_case['name']}' should return 400"
            
            body = json.loads(response["body"])
            assert body["error"]["code"] == test_case["expected_code"], \
                f"Test case '{test_case['name']}' should return error code '{test_case['expected_code']}'"
            
            # Verify error message is descriptive
            assert len(body["error"]["message"]) > 10, "Error message should be descriptive"
            assert "timestamp" in body["error"], "Error should include timestamp"
@pytest.mark.integration
class TestPerformanceAndScalability:
    """Integration tests for performance and scalability requirements."""
    
    @pytest.fixture
    def mock_neptune_client(self):
        """Create mock Neptune client with realistic delays."""
        client = AsyncMock()
        
        # Add realistic delays to simulate network latency
        async def delayed_get_account(*args, **kwargs):
            await asyncio.sleep(0.01)  # 10ms delay
            return None
        
        async def delayed_create_account(*args, **kwargs):
            await asyncio.sleep(0.02)  # 20ms delay
            return "account_vertex_id"
        
        async def delayed_create_transaction(*args, **kwargs):
            await asyncio.sleep(0.03)  # 30ms delay
            return "transaction_vertex_id"
        
        async def delayed_create_edge(*args, **kwargs):
            await asyncio.sleep(0.02)  # 20ms delay
            return "edge_id"
        
        client.get_account.side_effect = delayed_get_account
        client.create_account.side_effect = delayed_create_account
        client.create_transaction.side_effect = delayed_create_transaction
        client.create_transaction_edge.side_effect = delayed_create_edge
        
        return client
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_performance_requirements_under_load(
        self, 
        mock_get_throttler, 
        mock_neptune_class,
        mock_neptune_client
    ):
        """Test performance requirements under realistic load conditions."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow requests
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Create test event
        event = {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                "to_account_id": "ACC987654321",
                "amount": "1500.75",
                "transaction_type": "wire",
                "currency": "USD",
                "description": "Performance test transaction",
                "from_account": {
                    "customer_name": "John Doe",
                    "account_type": "business",
                    "risk_score": 0.2
                },
                "to_account": {
                    "customer_name": "Jane Smith",
                    "account_type": "checking",
                    "risk_score": 0.1
                }
            })
        }
        
        # Process transaction and measure performance
        start_time = time.time()
        response = lambda_handler(event, None)
        total_time = (time.time() - start_time) * 1000
        
        # Verify successful processing
        assert response["statusCode"] == 200
        
        body = json.loads(response["body"])
        
        # Verify performance requirements
        schema_validation_time = body["data"]["schema_validation_time_ms"]
        processing_time = body["data"]["processing_time_ms"]
        
        # Requirement 1.1: Schema validation within 100ms
        assert schema_validation_time < 100, \
            f"Schema validation took {schema_validation_time}ms, should be under 100ms"
        
        # Requirement 1.2: Processing within 500ms (with realistic network delays)
        assert processing_time < 500, \
            f"Processing took {processing_time}ms, should be under 500ms"
        
        # Total end-to-end time should be reasonable
        assert total_time < 1000, \
            f"Total processing took {total_time}ms, should be under 1000ms"
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_high_throughput_processing(
        self, 
        mock_get_throttler, 
        mock_neptune_class,
        mock_neptune_client
    ):
        """Test high-throughput processing capabilities."""
        # Setup mocks
        mock_neptune_class.return_value = mock_neptune_client
        
        # Mock throttler to allow high throughput
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_throttler.get_current_rate.return_value = 500.0
        mock_throttler.max_requests_per_second = 1000
        mock_get_throttler.return_value = mock_throttler
        
        # Create batch of transactions
        batch_size = 50
        events = []
        
        for i in range(batch_size):
            event = {
                "httpMethod": "POST",
                "path": "/transactions",
                "headers": {
                    "Content-Type": "application/json",
                    "X-Correlation-ID": f"throughput-test-{i:03d}"
                },
                "body": json.dumps({
                    "from_account_id": f"ACC{i:09d}",
                    "to_account_id": f"ACC{i+10000:09d}",
                    "amount": f"{100 + i}.{i % 100:02d}",
                    "transaction_type": "transfer",
                    "currency": "USD",
                    "reference_number": f"THROUGHPUT-{i:03d}",
                    "from_account": {
                        "customer_name": f"Sender {i}",
                        "account_type": "checking"
                    },
                    "to_account": {
                        "customer_name": f"Receiver {i}",
                        "account_type": "savings"
                    }
                })
            }
            events.append(event)
        
        # Process batch with timing
        start_time = time.time()
        
        # Use ThreadPoolExecutor for concurrent processing
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(lambda_handler, event, None) for event in events]
            responses = [future.result() for future in as_completed(futures)]
        
        batch_processing_time = (time.time() - start_time) * 1000
        
        # Verify all transactions processed successfully
        successful_responses = [r for r in responses if r["statusCode"] == 200]
        assert len(successful_responses) == batch_size, \
            f"Expected {batch_size} successful responses, got {len(successful_responses)}"
        
        # Calculate throughput
        throughput = (batch_size / batch_processing_time) * 1000  # transactions per second
        
        # Verify throughput meets requirements (should handle significant load)
        assert throughput > 10, f"Throughput {throughput:.2f} TPS is too low"
        
        # Verify individual transaction performance maintained under load
        for response in successful_responses:
            body = json.loads(response["body"])
            assert body["data"]["schema_validation_time_ms"] < 100
            assert body["data"]["processing_time_ms"] < 500
        
        print(f"Batch processing: {batch_size} transactions in {batch_processing_time:.2f}ms")
        print(f"Throughput: {throughput:.2f} transactions per second")


@pytest.mark.integration
class TestHealthCheckAndMonitoring:
    """Integration tests for health check and monitoring functionality."""
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_health_check_endpoint(
        self, 
        mock_get_throttler, 
        mock_neptune_class
    ):
        """Test health check endpoint functionality."""
        # Setup mocks
        mock_client = AsyncMock()
        mock_client.get_health_status.return_value = {
            "status": "healthy",
            "vertex_count": 5000,
            "edge_count": 10000,
            "cluster_status": "available"
        }
        mock_neptune_class.return_value = mock_client
        
        # Mock connection pool
        mock_pool = AsyncMock()
        mock_pool.health_check.return_value = {
            "status": "healthy",
            "pool_stats": {
                "active_connections": 2,
                "total_connections": 5,
                "requests_processed": 100,
                "average_response_time_ms": 150.0,
                "error_rate": 0.01
            },
            "neptune_health": {
                "status": "healthy",
                "vertex_count": 5000,
                "edge_count": 10000
            }
        }
        
        # Mock throttler
        mock_throttler = AsyncMock()
        mock_throttler.get_current_rate.return_value = 250.0
        mock_throttler.max_requests_per_second = 1000
        mock_get_throttler.return_value = mock_throttler
        
        # Mock get_connection_pool to return our mock pool
        with patch('sentinel_aml.lambdas.transaction_processor.get_connection_pool', return_value=mock_pool):
            # Create health check event
            event = {
                "httpMethod": "GET",
                "path": "/health",
                "headers": {}
            }
            
            # Execute health check
            response = health_check_handler(event, None)
            
            # Verify health check response
            assert response["statusCode"] == 200
            
            body = json.loads(response["body"])
            assert body["status"] == "healthy"
            assert "service" in body
            assert "version" in body
            assert "timestamp" in body
            assert "environment" in body
            
            # Verify connection pool health included
            assert "connection_pool" in body
            assert body["connection_pool"]["status"] == "healthy"
            
            # Verify throttler status included
            assert "throttler" in body
            assert body["throttler"]["current_rate"] == 250.0
            assert body["throttler"]["max_rate"] == 1000
            assert body["throttler"]["utilization"] == 0.25
    
    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_health_check_degraded_state(
        self, 
        mock_get_throttler, 
        mock_neptune_class
    ):
        """Test health check in degraded state."""
        # Setup mocks with connection issues
        mock_client = AsyncMock()
        mock_client.get_health_status.side_effect = Exception("Connection failed")
        mock_neptune_class.return_value = mock_client
        
        # Mock throttler
        mock_throttler = AsyncMock()
        mock_throttler.get_current_rate.return_value = 100.0
        mock_throttler.max_requests_per_second = 1000
        mock_get_throttler.return_value = mock_throttler
        
        # Create health check event
        event = {
            "httpMethod": "GET",
            "path": "/health",
            "headers": {}
        }
        
        # Execute health check
        response = health_check_handler(event, None)
        
        # Verify degraded health response
        assert response["statusCode"] == 503
        
        body = json.loads(response["body"])
        assert body["status"] == "degraded"
        assert "connection_pool" in body
        assert body["connection_pool"]["status"] == "unhealthy"
        assert "error" in body["connection_pool"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])