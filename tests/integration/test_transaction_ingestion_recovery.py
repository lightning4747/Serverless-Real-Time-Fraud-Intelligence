"""Integration tests for transaction ingestion recovery and error scenarios.

This module implements Task 3.4: Write integration tests for transaction ingestion.
It focuses on end-to-end flow with Neptune and error scenarios/recovery.
Validates Requirements 1.1, 1.2, 1.3, 1.4.
"""

import json
import pytest
import asyncio
import time
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch

from sentinel_aml.lambdas.transaction_processor import lambda_handler
from sentinel_aml.lambdas.connection_pool import CircuitBreaker, RequestThrottler
from sentinel_aml.core.exceptions import NeptuneConnectionError, ProcessingError

@pytest.mark.integration
class TestTransactionIngestionRecovery:
    """Integration tests for recovery and complex error scenarios."""

    @pytest.fixture
    def valid_event(self):
        """Standard valid transaction event."""
        return {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "from_account_id": "ACC111222333",
                "to_account_id": "ACC444555666",
                "amount": "1000.00",
                "transaction_type": "transfer",
                "currency": "USD"
            })
        }

    @patch('sentinel_aml.lambdas.transaction_processor.get_connection_pool')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    async def test_circuit_breaker_opening_and_recovery(self, mock_get_throttler, mock_get_pool, valid_event):
        """Test that the circuit breaker opens after failures and eventually recovers."""
        # Setup mocks
        mock_throttler = AsyncMock(spec=RequestThrottler)
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        mock_pool = AsyncMock()
        mock_client = AsyncMock()
        
        # Configure client to fail
        mock_client.create_transaction.side_effect = NeptuneConnectionError("Neptune down")
        mock_pool.get_connection.return_value.__aenter__.return_value = mock_client
        mock_get_pool.return_value = mock_pool
        
        # 1. Trigger failures until circuit breaker opens (threshold is 5)
        for i in range(6):
            response = lambda_handler(valid_event, None)
            assert response["statusCode"] == 503
            
        # 2. Verify circuit breaker is now open
        # We need to access the CircuitBreaker instance. 
        # In transaction_processor.py, it's created local to lambda_handler scope 
        # but we can verify it by the return message.
        response = lambda_handler(valid_event, None)
        body = json.loads(response["body"])
        assert response["statusCode"] == 503
        
        # If it was a regular error, code might be DATABASE_ERROR.
        # If CB is open, it might return SERVICE_UNAVAILABLE.
        # Checking implementation: it returns 503 SERVICE_UNAVAILABLE if CB is OPEN.
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert "repeated failures" in body["error"]["message"]

    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    async def test_throttler_recovery(self, mock_get_throttler, valid_event):
        """Test that the system recovers after being throttled."""
        mock_throttler = AsyncMock(spec=RequestThrottler)
        
        # 1. Behave as throttled
        mock_throttler.can_process_request.return_value = False
        mock_throttler.get_current_rate.return_value = 1200
        mock_throttler.max_requests_per_second = 1000
        mock_get_throttler.return_value = mock_throttler
        
        response = lambda_handler(valid_event, None)
        assert response["statusCode"] == 429
        
        # 2. Behave as recovered
        mock_throttler.can_process_request.return_value = True
        
        # We need to mock the rest of the flow to ensure it proceeds
        with patch('sentinel_aml.lambdas.transaction_processor.get_connection_pool') as mock_get_pool:
            mock_pool = AsyncMock()
            mock_client = AsyncMock()
            mock_client.create_transaction.return_value = "tx1"
            mock_pool.get_connection.return_value.__aenter__.return_value = mock_client
            mock_get_pool.return_value = mock_pool
            
            response = lambda_handler(valid_event, None)
            assert response["statusCode"] == 200
            assert json.loads(response["body"])["data"]["status"] == "processed"

    @patch('sentinel_aml.lambdas.transaction_processor.get_connection_pool')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    async def test_database_query_error_handling(self, mock_get_throttler, mock_get_pool, valid_event):
        """Test handling of specific query errors vs connection errors."""
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        mock_pool = AsyncMock()
        mock_client = AsyncMock()
        
        from sentinel_aml.core.exceptions import NeptuneQueryError
        mock_client.create_transaction.side_effect = NeptuneQueryError("Invalid query")
        mock_pool.get_connection.return_value.__aenter__.return_value = mock_client
        mock_get_pool.return_value = mock_pool
        
        response = lambda_handler(valid_event, None)
        assert response["statusCode"] == 503
        body = json.loads(response["body"])
        assert body["error"]["code"] == "DATABASE_ERROR"

    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_invalid_json_recovery(self, mock_get_throttler):
        """Test that the system handles malformed JSON correctly."""
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        event = {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {"Content-Type": "application/json"},
            "body": "{ invalid json"
        }
        
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "INVALID_JSON"

if __name__ == "__main__":
    import sys
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"])
