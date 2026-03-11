"""Unit tests for transaction processor Lambda function."""

import json
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from sentinel_aml.lambdas.transaction_processor import (
    TransactionRequest,
    lambda_handler,
    health_check_handler,
    process_transaction,
    ensure_account_exists,
    create_error_response,
    create_success_response,
)
from sentinel_aml.core.exceptions import ValidationError, ProcessingError, NeptuneConnectionError
from sentinel_aml.data.models import TransactionType, AccountType


class TestTransactionRequest:
    """Test TransactionRequest validation and parsing."""
    
    def test_valid_transaction_request(self):
        """Test valid transaction request parsing."""
        data = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "1000.50",
            "transaction_type": "transfer",
            "currency": "USD",
            "description": "Test transfer",
            "channel": "online"
        }
        
        request = TransactionRequest(data)
        
        assert request.from_account_id == "ACC123456789"
        assert request.to_account_id == "ACC987654321"
        assert request.amount == Decimal("1000.50")
        assert request.transaction_type == TransactionType.TRANSFER
        assert request.currency == "USD"
        assert request.description == "Test transfer"
        assert request.channel == "online"
        assert isinstance(request.timestamp, datetime)
    
    def test_missing_required_fields(self):
        """Test validation with missing required fields."""
        data = {
            "from_account_id": "ACC123456789",
            "amount": "1000.50"
            # Missing to_account_id, transaction_type, currency
        }
        
        with pytest.raises(ValidationError) as exc_info:
            TransactionRequest(data)
        
        assert "Missing required fields" in str(exc_info.value)
        assert "to_account_id" in exc_info.value.details["missing_fields"]
        assert "transaction_type" in exc_info.value.details["missing_fields"]
        assert "currency" in exc_info.value.details["missing_fields"]
    
    def test_invalid_transaction_type(self):
        """Test validation with invalid transaction type."""
        data = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "1000.50",
            "transaction_type": "invalid_type",
            "currency": "USD"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            TransactionRequest(data)
        
        assert "Invalid transaction type" in str(exc_info.value)
        assert exc_info.value.error_code == "INVALID_TRANSACTION_TYPE"
    
    def test_invalid_amount(self):
        """Test validation with invalid amounts."""
        # Negative amount
        data = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "-100.00",
            "transaction_type": "transfer",
            "currency": "USD"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            TransactionRequest(data)
        
        assert "must be positive" in str(exc_info.value)
        assert exc_info.value.error_code == "INVALID_AMOUNT"
        
        # Amount too large
        data["amount"] = "1000000000.00"
        
        with pytest.raises(ValidationError) as exc_info:
            TransactionRequest(data)
        
        assert "exceeds maximum limit" in str(exc_info.value)
        assert exc_info.value.error_code == "AMOUNT_EXCEEDS_LIMIT"
    
    def test_same_account_transfer(self):
        """Test validation for same account transfer."""
        data = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC123456789",  # Same as from_account_id
            "amount": "1000.50",
            "transaction_type": "transfer",
            "currency": "USD"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            TransactionRequest(data)
        
        assert "cannot be the same" in str(exc_info.value)
        assert exc_info.value.error_code == "SAME_ACCOUNT_TRANSFER"
    
    def test_unsupported_currency(self):
        """Test validation with unsupported currency."""
        data = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "1000.50",
            "transaction_type": "transfer",
            "currency": "XYZ"  # Unsupported currency
        }
        
        with pytest.raises(ValidationError) as exc_info:
            TransactionRequest(data)
        
        assert "Unsupported currency" in str(exc_info.value)
        assert exc_info.value.error_code == "UNSUPPORTED_CURRENCY"
    
    def test_custom_timestamp(self):
        """Test parsing custom timestamp."""
        timestamp_str = "2024-01-15T10:30:00Z"
        data = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "1000.50",
            "transaction_type": "transfer",
            "currency": "USD",
            "timestamp": timestamp_str
        }
        
        request = TransactionRequest(data)
        
        assert request.timestamp.year == 2024
        assert request.timestamp.month == 1
        assert request.timestamp.day == 15
        assert request.timestamp.hour == 10
        assert request.timestamp.minute == 30
    
    def test_invalid_timestamp_format(self):
        """Test validation with invalid timestamp format."""
        data = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "1000.50",
            "transaction_type": "transfer",
            "currency": "USD",
            "timestamp": "invalid-timestamp"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            TransactionRequest(data)
        
        assert "Invalid timestamp format" in str(exc_info.value)
        assert exc_info.value.error_code == "INVALID_TIMESTAMP"


class TestLambdaHandler:
    """Test Lambda handler function."""
    
    def test_cors_preflight_request(self):
        """Test CORS preflight OPTIONS request."""
        event = {
            "httpMethod": "OPTIONS",
            "headers": {}
        }
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 200
        assert "Access-Control-Allow-Origin" in response["headers"]
        assert "Access-Control-Allow-Methods" in response["headers"]
        assert response["body"] == ""
    
    def test_invalid_http_method(self):
        """Test invalid HTTP method."""
        event = {
            "httpMethod": "GET",
            "headers": {}
        }
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 405
        body = json.loads(response["body"])
        assert body["error"]["code"] == "METHOD_NOT_ALLOWED"
    
    def test_missing_request_body(self):
        """Test missing request body."""
        event = {
            "httpMethod": "POST",
            "headers": {},
            "body": None
        }
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Request body is required" in body["error"]["message"]
    
    def test_invalid_json_body(self):
        """Test invalid JSON in request body."""
        event = {
            "httpMethod": "POST",
            "headers": {},
            "body": "invalid json"
        }
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "INVALID_JSON"
    
    def test_schema_validation_failure(self):
        """Test schema validation failure."""
        event = {
            "httpMethod": "POST",
            "headers": {},
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                # Missing required fields
            })
        }
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "MISSING_REQUIRED_FIELDS"
    
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    @patch('sentinel_aml.lambdas.transaction_processor.process_transaction')
    def test_rate_limiting(self, mock_process, mock_get_throttler):
        """Test rate limiting functionality."""
        # Mock throttler to reject request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = False
        mock_throttler.get_current_rate.return_value = 1500
        mock_throttler.max_requests_per_second = 1000
        mock_get_throttler.return_value = mock_throttler
        
        event = {
            "httpMethod": "POST",
            "headers": {},
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                "to_account_id": "ACC987654321",
                "amount": "1000.50",
                "transaction_type": "transfer",
                "currency": "USD"
            })
        }
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 429
        body = json.loads(response["body"])
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert "1500" in body["error"]["message"]
    
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    @patch('sentinel_aml.lambdas.transaction_processor.process_transaction')
    def test_successful_transaction_processing(self, mock_process, mock_get_throttler):
        """Test successful transaction processing."""
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Mock successful processing
        mock_process.return_value = {
            "transaction_id": "TXN-20240115-12345678",
            "status": "processed",
            "vertex_id": "vertex123",
            "edge_id": "edge456",
            "processing_time_ms": 250.0,
            "timestamp": "2024-01-15T10:30:00Z"
        }
        
        event = {
            "httpMethod": "POST",
            "headers": {},
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                "to_account_id": "ACC987654321",
                "amount": "1000.50",
                "transaction_type": "transfer",
                "currency": "USD"
            })
        }
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["data"]["transaction_id"] == "TXN-20240115-12345678"
        assert body["data"]["status"] == "processed"
        assert "schema_validation_time_ms" in body["data"]
        assert "total_processing_time_ms" in body["data"]
    
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    @patch('sentinel_aml.lambdas.transaction_processor.process_transaction')
    def test_neptune_connection_error(self, mock_process, mock_get_throttler):
        """Test Neptune connection error handling."""
        # Mock throttler to allow request
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler
        
        # Mock Neptune connection error
        mock_process.side_effect = NeptuneConnectionError("Connection failed")
        
        event = {
            "httpMethod": "POST",
            "headers": {},
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                "to_account_id": "ACC987654321",
                "amount": "1000.50",
                "transaction_type": "transfer",
                "currency": "USD"
            })
        }
        
        response = lambda_handler(event, None)
        
        assert response["statusCode"] == 503
        body = json.loads(response["body"])
        assert body["error"]["code"] == "DATABASE_ERROR"
        assert "temporarily unavailable" in body["error"]["message"]
    
    def test_correlation_id_handling(self):
        """Test correlation ID handling."""
        correlation_id = "test-correlation-123"
        event = {
            "httpMethod": "POST",
            "headers": {
                "X-Correlation-ID": correlation_id
            },
            "body": json.dumps({
                "from_account_id": "ACC123456789",
                # Missing required fields to trigger error
            })
        }
        
        response = lambda_handler(event, None)
        
        assert response["headers"]["X-Correlation-ID"] == correlation_id
        body = json.loads(response["body"])
        assert body["error"]["correlation_id"] == correlation_id


class TestProcessTransaction:
    """Test transaction processing function."""
    
    @pytest.fixture
    def mock_transaction_request(self):
        """Create mock transaction request."""
        data = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "1000.50",
            "transaction_type": "transfer",
            "currency": "USD",
            "description": "Test transfer"
        }
        return TransactionRequest(data)
    
    @patch('sentinel_aml.lambdas.transaction_processor.get_connection_pool')
    @patch('sentinel_aml.lambdas.transaction_processor.ensure_account_exists')
    async def test_successful_transaction_processing(self, mock_ensure_account, mock_get_pool, mock_transaction_request):
        """Test successful transaction processing."""
        # Mock connection pool and client
        mock_client = AsyncMock()
        mock_client.create_transaction.return_value = "vertex123"
        mock_client.create_transaction_edge.return_value = "edge456"
        
        mock_pool = AsyncMock()
        mock_pool.get_connection.return_value.__aenter__.return_value = mock_client
        mock_get_pool.return_value = mock_pool
        
        # Mock account existence check
        mock_ensure_account.return_value = None
        
        result = await process_transaction(mock_transaction_request)
        
        assert result["transaction_id"] == mock_transaction_request.transaction_id
        assert result["status"] == "processed"
        assert result["vertex_id"] == "vertex123"
        assert result["edge_id"] == "edge456"
        assert "processing_time_ms" in result
        
        # Verify account existence was checked for both accounts
        assert mock_ensure_account.call_count == 2
        
        # Verify transaction and edge creation
        mock_client.create_transaction.assert_called_once()
        mock_client.create_transaction_edge.assert_called_once()
    
    @patch('sentinel_aml.lambdas.transaction_processor.get_connection_pool')
    async def test_connection_pool_error(self, mock_get_pool, mock_transaction_request):
        """Test connection pool error handling."""
        mock_get_pool.side_effect = NeptuneConnectionError("Pool initialization failed")
        
        with pytest.raises(NeptuneConnectionError):
            await process_transaction(mock_transaction_request)


class TestEnsureAccountExists:
    """Test account existence checking and creation."""
    
    @patch('sentinel_aml.lambdas.transaction_processor.hash_pii')
    async def test_create_new_account(self, mock_hash_pii):
        """Test creating new account when it doesn't exist."""
        mock_hash_pii.return_value = "hashed_customer_name"
        
        # Mock connection pool and client
        mock_client = AsyncMock()
        mock_client.get_account.return_value = None  # Account doesn't exist
        mock_client.create_account.return_value = "account_vertex_id"
        
        mock_pool = AsyncMock()
        mock_pool.get_connection.return_value.__aenter__.return_value = mock_client
        
        account_info = {
            "customer_name": "John Doe",
            "account_type": "checking",
            "risk_score": 0.2
        }
        
        await ensure_account_exists(mock_pool, "ACC123456789", account_info)
        
        # Verify account creation was called
        mock_client.create_account.assert_called_once()
        
        # Verify account data
        created_account = mock_client.create_account.call_args[0][0]
        assert created_account.account_id == "ACC123456789"
        assert created_account.customer_name == "hashed_customer_name"
        assert created_account.account_type == AccountType.CHECKING
        assert created_account.risk_score == 0.2
    
    async def test_account_already_exists(self):
        """Test when account already exists."""
        # Mock connection pool and client
        mock_client = AsyncMock()
        mock_client.get_account.return_value = {"account_id": "ACC123456789"}  # Account exists
        
        mock_pool = AsyncMock()
        mock_pool.get_connection.return_value.__aenter__.return_value = mock_client
        
        await ensure_account_exists(mock_pool, "ACC123456789", {})
        
        # Verify account creation was NOT called
        mock_client.create_account.assert_not_called()


class TestHealthCheckHandler:
    """Test health check handler."""
    
    @patch('sentinel_aml.lambdas.transaction_processor.get_settings')
    def test_basic_health_check(self, mock_get_settings):
        """Test basic health check without Neptune."""
        mock_settings = Mock()
        mock_settings.app_name = "Sentinel-AML"
        mock_settings.app_version = "0.1.0"
        mock_settings.environment = "test"
        mock_settings.neptune_endpoint = None
        mock_get_settings.return_value = mock_settings
        
        response = health_check_handler({}, None)
        
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "healthy"
        assert body["service"] == "Sentinel-AML"
        assert body["version"] == "0.1.0"
        assert body["environment"] == "test"
    
    @patch('sentinel_aml.lambdas.transaction_processor.get_settings')
    @patch('sentinel_aml.lambdas.transaction_processor.get_connection_pool')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_health_check_with_neptune(self, mock_get_throttler, mock_get_pool, mock_get_settings):
        """Test health check with Neptune connection."""
        mock_settings = Mock()
        mock_settings.app_name = "Sentinel-AML"
        mock_settings.app_version = "0.1.0"
        mock_settings.environment = "test"
        mock_settings.neptune_endpoint = "test-endpoint"
        mock_get_settings.return_value = mock_settings
        
        # Mock connection pool health check
        mock_pool = AsyncMock()
        mock_pool.health_check.return_value = {
            "status": "healthy",
            "pool_stats": {"active_connections": 2, "total_connections": 5}
        }
        mock_get_pool.return_value = mock_pool
        
        # Mock throttler
        mock_throttler = AsyncMock()
        mock_throttler.get_current_rate.return_value = 50
        mock_throttler.max_requests_per_second = 1000
        mock_get_throttler.return_value = mock_throttler
        
        response = health_check_handler({}, None)
        
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "healthy"
        assert "connection_pool" in body
        assert "throttler" in body
        assert body["throttler"]["current_rate"] == 50
        assert body["throttler"]["max_rate"] == 1000


class TestResponseHelpers:
    """Test response helper functions."""
    
    def test_create_error_response(self):
        """Test error response creation."""
        response = create_error_response(
            400,
            "TEST_ERROR",
            "Test error message",
            details={"field": "value"},
            correlation_id="test-123"
        )
        
        assert response["statusCode"] == 400
        assert response["headers"]["Content-Type"] == "application/json"
        assert response["headers"]["X-Correlation-ID"] == "test-123"
        
        body = json.loads(response["body"])
        assert body["error"]["code"] == "TEST_ERROR"
        assert body["error"]["message"] == "Test error message"
        assert body["error"]["details"]["field"] == "value"
        assert body["error"]["correlation_id"] == "test-123"
    
    def test_create_success_response(self):
        """Test success response creation."""
        data = {"transaction_id": "TXN-123", "status": "processed"}
        response = create_success_response(data, correlation_id="test-123")
        
        assert response["statusCode"] == 200
        assert response["headers"]["Content-Type"] == "application/json"
        assert response["headers"]["X-Correlation-ID"] == "test-123"
        
        body = json.loads(response["body"])
        assert body["data"]["transaction_id"] == "TXN-123"
        assert body["data"]["status"] == "processed"
        assert "timestamp" in body