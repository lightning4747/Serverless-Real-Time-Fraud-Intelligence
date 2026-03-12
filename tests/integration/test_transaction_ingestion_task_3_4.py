"""
Integration tests for Task 3.4: Write integration tests for transaction ingestion.
This module implements comprehensive integration tests that validate:
- End-to-end transaction flow with Neptune (Requirement 1.1, 1.2, 1.5)
- Error scenarios and recovery (Requirement 1.3, 1.4)
- Performance requirements validation
- Data integrity and referential constraints
Requirements Coverage:
- 1.1: Transaction validation within 100ms
- 1.2: Store valid transactions in Graph_Engine within 500ms
- 1.3: Return descriptive error messages for invalid data (HTTP 400)
- 1.4: Handle concurrent requests up to 1000 transactions per second
"""
import asyncio
import json
import pytest
import time
import threading
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from concurrent.futures import ThreadPoolExecutor, as_completed
from sentinel_aml.lambdas.transaction_processor import lambda_handler, health_check_handler
from sentinel_aml.core.exceptions import (
    ValidationError,
    ProcessingError,
    NeptuneConnectionError,
    NeptuneQueryError
)
from sentinel_aml.data.models import TransactionType, AccountType


@pytest.mark.integration
class TestTransactionIngestionTask34:
    """
    Integration tests for Task 3.4: Transaction ingestion end-to-end flow.

    Tests complete workflow from API request to Neptune storage,
    including error scenarios and recovery mechanisms.
    """

    @pytest.fixture
    def mock_neptune_client(self):
        """Create mock Neptune client with realistic behavior."""
        client = AsyncMock()

        client.get_account.return_value = None
        client.create_account.return_value = "account_vertex_123"
        client.create_transaction.return_value = "transaction_vertex_456"
        client.create_transaction_edge.return_value = "edge_789"

        client.connect.return_value = None
        client.disconnect.return_value = None

        client.get_health_status.return_value = {
            "status": "healthy",
            "vertex_count": 1000,
            "edge_count": 2000
        }

        return client

    @pytest.fixture
    def valid_transaction_payload(self):
        """Create valid transaction payload for testing."""
        return {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "1500.75",
            "transaction_type": "wire",
            "currency": "USD",
            "description": "Integration test wire transfer",
            "reference_number": "TEST-REF-001",
            "channel": "api",
            "timestamp": "2024-01-15T14:30:00Z",
            "is_cash": False,
            "is_international": False,
            "from_account": {
                "customer_name": "John Doe",
                "account_type": "business",
                "risk_score": 0.2,
                "country_code": "US",
                "customer_id": "CUST001",
                "is_pep": False,
                "kyc_status": "approved",
                "balance": 50000.0,
                "currency": "USD",
                "is_active": True
            },
            "to_account": {
                "customer_name": "Jane Smith",
                "account_type": "checking",
                "risk_score": 0.1,
                "country_code": "US",
                "customer_id": "CUST002",
                "is_pep": False,
                "kyc_status": "approved",
                "balance": 10000.0,
                "currency": "USD",
                "is_active": True
            }
        }

    def create_api_event(self, payload, correlation_id="test-correlation-001"):
        """Create API Gateway event structure."""
        return {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {
                "Content-Type": "application/json",
                "X-Correlation-ID": correlation_id
            },
            "body": json.dumps(payload)
        }

    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_end_to_end_transaction_flow_with_neptune(
        self,
        mock_get_throttler,
        mock_neptune_class,
        mock_neptune_client,
        valid_transaction_payload
    ):
        """
        Test complete end-to-end transaction flow with Neptune integration.

        Validates:
        - Requirement 1.1: Schema validation within 100ms
        - Requirement 1.2: Transaction storage within 500ms
        - Requirement 1.5: Account and edge creation in Neptune
        """
        mock_neptune_class.return_value = mock_neptune_client

        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_throttler.get_current_rate.return_value = 50.0
        mock_throttler.max_requests_per_second = 1000
        mock_get_throttler.return_value = mock_throttler

        event = self.create_api_event(valid_transaction_payload)

        start_time = time.time()
        response = lambda_handler(event, None)
        total_time = (time.time() - start_time) * 1000

        assert response["statusCode"] == 200
        assert "X-Correlation-ID" in response["headers"]
        assert response["headers"]["X-Correlation-ID"] == "test-correlation-001"

        body = json.loads(response["body"])
        assert "data" in body
        assert body["data"]["status"] == "processed"
        assert "transaction_id" in body["data"]
        assert body["data"]["vertex_id"] == "transaction_vertex_456"
        assert body["data"]["edge_id"] == "edge_789"

        schema_validation_time = body["data"]["schema_validation_time_ms"]
        processing_time = body["data"]["processing_time_ms"]

        # Requirement 1.1: Schema validation within 100ms
        assert schema_validation_time < 100, \
            f"Schema validation took {schema_validation_time}ms, exceeds 100ms requirement"

        # Requirement 1.2: Processing within 500ms
        assert processing_time < 500, \
            f"Processing took {processing_time}ms, exceeds 500ms requirement"

        assert mock_neptune_client.get_account.call_count == 2
        assert mock_neptune_client.create_account.call_count == 2
        mock_neptune_client.create_transaction.assert_called_once()
        mock_neptune_client.create_transaction_edge.assert_called_once()

        transaction_call = mock_neptune_client.create_transaction.call_args[0][0]
        assert transaction_call.amount == Decimal("1500.75")
        assert transaction_call.transaction_type == TransactionType.WIRE
        assert transaction_call.currency == "USD"
        assert transaction_call.description == "Integration test wire transfer"

        edge_call = mock_neptune_client.create_transaction_edge.call_args[0][0]
        assert edge_call.from_account_id == "ACC123456789"
        assert edge_call.to_account_id == "ACC987654321"
        assert edge_call.amount == Decimal("1500.75")
        assert edge_call.transaction_type == TransactionType.WIRE

    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_existing_accounts_optimization(
        self,
        mock_get_throttler,
        mock_neptune_class,
        mock_neptune_client,
        valid_transaction_payload
    ):
        """
        Test optimization when accounts already exist in Neptune.

        Validates that existing accounts are not recreated,
        but transaction and edge are still created properly.
        """
        mock_neptune_class.return_value = mock_neptune_client
        mock_neptune_client.get_account.return_value = {
            "account_id": "existing_account",
            "account_type": "checking"
        }

        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler

        event = self.create_api_event(valid_transaction_payload)
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["data"]["status"] == "processed"

        mock_neptune_client.create_account.assert_not_called()
        mock_neptune_client.create_transaction.assert_called_once()
        mock_neptune_client.create_transaction_edge.assert_called_once()

    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_concurrent_request_handling(
        self,
        mock_get_throttler,
        mock_neptune_class
    ):
        """
        Test concurrent request handling capability.

        Validates Requirement 1.4: Handle concurrent requests up to 1000 TPS.
        Tests with smaller batch but validates concurrent processing works.
        """
        # --- FIX 1: Build a fresh mock PER THREAD, not one shared mock ---
        # AsyncMock is not thread-safe; sharing one instance across threads causes
        # "coroutine awaited in wrong event loop" RuntimeErrors that silently drop responses.
        thread_local = threading.local()

        def make_fresh_client():
            client = AsyncMock()
            client.get_account.return_value = None
            client.create_account.return_value = "account_vertex_id"
            client.create_transaction.return_value = "transaction_vertex_id"
            client.create_transaction_edge.return_value = "edge_id"
            client.connect.return_value = None
            client.disconnect.return_value = None
            return client

        def get_thread_local_client():
            if not hasattr(thread_local, 'client'):
                thread_local.client = make_fresh_client()
            return thread_local.client

        mock_neptune_class.side_effect = lambda *a, **kw: get_thread_local_client()

        # --- FIX 2: Mock throttler also per-thread ---
        def make_fresh_throttler():
            mock_throttler = AsyncMock()
            mock_throttler.can_process_request.return_value = True
            mock_throttler.get_current_rate.return_value = 100.0
            mock_throttler.max_requests_per_second = 1000
            return mock_throttler

        throttler_local = threading.local()

        def get_thread_local_throttler():
            if not hasattr(throttler_local, 'throttler'):
                throttler_local.throttler = make_fresh_throttler()
            return throttler_local.throttler

        mock_get_throttler.side_effect = lambda *a, **kw: get_thread_local_throttler()

        # Create batch of concurrent transactions
        batch_size = 20
        events = []

        for i in range(batch_size):
            payload = {
                "from_account_id": f"ACC{i:09d}",
                "to_account_id": f"ACC{i+1000:09d}",
                "amount": f"{100 + i}.{i % 100:02d}",
                "transaction_type": "transfer",
                "currency": "USD",
                "reference_number": f"CONCURRENT-{i:03d}",
                "from_account": {
                    "customer_name": f"Sender {i}",
                    "account_type": "checking"
                },
                "to_account": {
                    "customer_name": f"Receiver {i}",
                    "account_type": "savings"
                }
            }
            event = self.create_api_event(payload, f"concurrent-{i:03d}")
            events.append(event)

        # --- FIX 3: Wrap handler to never raise, collect ALL results before asserting ---
        def run_handler(event):
            try:
                return lambda_handler(event, None)
            except Exception as exc:
                return {
                    "statusCode": 500,
                    "body": json.dumps({"error": {"code": "HANDLER_EXCEPTION", "message": str(exc)}})
                }

        start_time = time.time()

        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(run_handler, event): i for i, event in enumerate(events)}
            for future in as_completed(futures):
                results.append(future.result())

        processing_time = (time.time() - start_time) * 1000

        # Diagnose failures before asserting count
        failed = [r for r in results if r["statusCode"] != 200]
        if failed:
            sample_error = json.loads(failed[0]["body"])
            pytest.fail(
                f"Expected {batch_size} successful responses, got {batch_size - len(failed)} successes.\n"
                f"Sample failure ({failed[0]['statusCode']}): {sample_error}"
            )

        successful_responses = [r for r in results if r["statusCode"] == 200]
        assert len(successful_responses) == batch_size

        throughput = (batch_size / processing_time) * 1000  # TPS
        assert throughput > 5, f"Throughput {throughput:.2f} TPS is too low for concurrent processing"

        # NOTE: Don't assert total Neptune call counts across thread-local mocks —
        # each thread has its own mock instance, so aggregate counts won't add up here.
        # Validate per-response body integrity instead:
        for response in successful_responses:
            body = json.loads(response["body"])
            assert body["data"]["status"] == "processed"
            assert "transaction_id" in body["data"]

        print(f"Concurrent processing: {batch_size} transactions in {processing_time:.2f}ms")
        print(f"Throughput: {throughput:.2f} transactions per second")


@pytest.mark.integration
class TestErrorScenariosAndRecovery:
    """
    Integration tests for error scenarios and recovery mechanisms.

    Validates Requirement 1.3: Return descriptive error messages for invalid data.
    Tests various error conditions and recovery patterns.
    """

    @pytest.fixture
    def mock_neptune_client(self):
        """Create mock Neptune client for error testing."""
        client = AsyncMock()
        client.get_account.return_value = None
        client.create_account.return_value = "account_vertex_id"
        client.create_transaction.return_value = "transaction_vertex_id"
        client.create_transaction_edge.return_value = "edge_id"
        return client

    def create_api_event(self, payload):
        """Create API Gateway event structure."""
        return {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload)
        }

    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_validation_error_scenarios(
        self,
        mock_get_throttler,
        mock_neptune_class,
        mock_neptune_client
    ):
        """
        Test validation error scenarios with descriptive error messages.

        Validates Requirement 1.3: Return descriptive error messages for invalid data (HTTP 400).
        """
        mock_neptune_class.return_value = mock_neptune_client

        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler

        validation_test_cases = [
            {
                "name": "missing_required_fields",
                "payload": {
                    "from_account_id": "ACC123456789",
                },
                "expected_code": "MISSING_REQUIRED_FIELDS",
                "expected_status": 400
            },
            {
                "name": "invalid_negative_amount",
                "payload": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "-100.00",
                    "transaction_type": "transfer",
                    "currency": "USD"
                },
                "expected_code": "INVALID_AMOUNT",
                "expected_status": 400
            },
            {
                "name": "zero_amount",
                "payload": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "0.00",
                    "transaction_type": "transfer",
                    "currency": "USD"
                },
                "expected_code": "INVALID_AMOUNT",
                "expected_status": 400
            },
            {
                "name": "same_account_transfer",
                "payload": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC123456789",
                    "amount": "100.00",
                    "transaction_type": "transfer",
                    "currency": "USD"
                },
                "expected_code": "SAME_ACCOUNT_TRANSFER",
                "expected_status": 400
            },
            {
                "name": "unsupported_currency",
                "payload": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "100.00",
                    "transaction_type": "transfer",
                    "currency": "XYZ"
                },
                "expected_code": "UNSUPPORTED_CURRENCY",
                "expected_status": 400
            },
            {
                "name": "invalid_transaction_type",
                "payload": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "100.00",
                    "transaction_type": "invalid_type",
                    "currency": "USD"
                },
                "expected_code": "INVALID_TRANSACTION_TYPE",
                "expected_status": 400
            },
            {
                "name": "excessive_amount",
                "payload": {
                    "from_account_id": "ACC123456789",
                    "to_account_id": "ACC987654321",
                    "amount": "1000000000.00",
                    "transaction_type": "transfer",
                    "currency": "USD"
                },
                "expected_code": "AMOUNT_EXCEEDS_LIMIT",
                "expected_status": 400
            }
        ]

        for test_case in validation_test_cases:
            event = self.create_api_event(test_case["payload"])
            response = lambda_handler(event, None)

            assert response["statusCode"] == test_case["expected_status"], \
                f"Test case '{test_case['name']}' expected status {test_case['expected_status']}, got {response['statusCode']}"

            body = json.loads(response["body"])
            assert "error" in body, f"Test case '{test_case['name']}' should have error in response"
            assert body["error"]["code"] == test_case["expected_code"], \
                f"Test case '{test_case['name']}' expected error code '{test_case['expected_code']}', got '{body['error']['code']}'"

            assert len(body["error"]["message"]) > 10, \
                f"Test case '{test_case['name']}' should have descriptive error message"
            assert "timestamp" in body["error"], \
                f"Test case '{test_case['name']}' should include timestamp"

            print(f"✓ Validation test '{test_case['name']}': {body['error']['message']}")

    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_neptune_connection_error_recovery(
        self,
        mock_get_throttler,
        mock_neptune_class,
        mock_neptune_client
    ):
        """
        Test Neptune connection error handling and recovery.

        Validates proper error handling when Neptune is unavailable.
        """
        mock_neptune_class.return_value = mock_neptune_client

        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler

        mock_neptune_client.create_transaction.side_effect = NeptuneConnectionError("Connection timeout")

        payload = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "1000.00",
            "transaction_type": "transfer",
            "currency": "USD",
            "from_account": {"customer_name": "John Doe", "account_type": "checking"},
            "to_account": {"customer_name": "Jane Smith", "account_type": "savings"}
        }

        event = self.create_api_event(payload)
        response = lambda_handler(event, None)

        assert response["statusCode"] == 503

        body = json.loads(response["body"])
        assert body["error"]["code"] == "DATABASE_ERROR"
        assert "temporarily unavailable" in body["error"]["message"]
        assert "processing_time_ms" in body["error"]["details"]

        print(f"✓ Neptune connection error handled: {body['error']['message']}")

    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_neptune_query_error_recovery(
        self,
        mock_get_throttler,
        mock_neptune_class,
        mock_neptune_client
    ):
        """
        Test Neptune query error handling and recovery.

        Validates proper error handling for query-specific errors.
        """
        mock_neptune_class.return_value = mock_neptune_client

        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler

        mock_neptune_client.create_transaction_edge.side_effect = NeptuneQueryError("Invalid query syntax")

        payload = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "1000.00",
            "transaction_type": "transfer",
            "currency": "USD",
            "from_account": {"customer_name": "John Doe", "account_type": "checking"},
            "to_account": {"customer_name": "Jane Smith", "account_type": "savings"}
        }

        event = self.create_api_event(payload)
        response = lambda_handler(event, None)

        assert response["statusCode"] == 503

        body = json.loads(response["body"])
        assert body["error"]["code"] == "DATABASE_ERROR"

        print(f"✓ Neptune query error handled: {body['error']['message']}")

    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_rate_limiting_error_handling(
        self,
        mock_get_throttler,
        mock_neptune_class,
        mock_neptune_client
    ):
        """
        Test rate limiting error handling.

        Validates Requirement 1.4: Handle concurrent requests up to 1000 TPS.
        Tests behavior when rate limit is exceeded.
        """
        mock_neptune_class.return_value = mock_neptune_client

        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = False
        mock_throttler.get_current_rate.return_value = 1200.0
        mock_throttler.max_requests_per_second = 1000
        mock_get_throttler.return_value = mock_throttler

        payload = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "1000.00",
            "transaction_type": "transfer",
            "currency": "USD",
            "from_account": {"customer_name": "John Doe", "account_type": "checking"},
            "to_account": {"customer_name": "Jane Smith", "account_type": "savings"}
        }

        event = self.create_api_event(payload)
        response = lambda_handler(event, None)

        assert response["statusCode"] == 429

        body = json.loads(response["body"])
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert body["error"]["details"]["current_rate"] == 1200.0
        assert body["error"]["details"]["max_rate"] == 1000

        print(f"✓ Rate limiting handled: {body['error']['message']}")

    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_malformed_json_error_handling(self, mock_get_throttler):
        """
        Test handling of malformed JSON in request body.

        Validates proper error handling for invalid JSON.
        """
        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler

        event = {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {"Content-Type": "application/json"},
            "body": "{ invalid json syntax"
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 400

        body = json.loads(response["body"])
        assert body["error"]["code"] == "INVALID_JSON"
        assert "Invalid JSON" in body["error"]["message"]

        print(f"✓ Malformed JSON handled: {body['error']['message']}")


@pytest.mark.integration
class TestDataIntegrityAndConstraints:
    """
    Integration tests for data integrity and referential constraints.

    Validates that the system maintains data consistency in Neptune.
    """

    @patch('sentinel_aml.lambdas.connection_pool.NeptuneClient')
    @patch('sentinel_aml.lambdas.transaction_processor.get_throttler')
    def test_referential_integrity_validation(
        self,
        mock_get_throttler,
        mock_neptune_class
    ):
        """
        Test referential integrity validation in Neptune operations.

        Validates that accounts and transactions are properly linked.
        """
        mock_client = AsyncMock()
        mock_neptune_class.return_value = mock_client

        mock_client.get_account.return_value = None
        mock_client.create_account.return_value = "account_vertex_id"
        mock_client.create_transaction.return_value = "transaction_vertex_id"
        mock_client.create_transaction_edge.return_value = "edge_id"

        mock_throttler = AsyncMock()
        mock_throttler.can_process_request.return_value = True
        mock_get_throttler.return_value = mock_throttler

        payload = {
            "from_account_id": "ACC123456789",
            "to_account_id": "ACC987654321",
            "amount": "2500.00",
            "transaction_type": "wire",
            "currency": "USD",
            "description": "Referential integrity test",
            "from_account": {
                "customer_name": "John Doe",
                "account_type": "business",
                "customer_id": "CUST001"
            },
            "to_account": {
                "customer_name": "Jane Smith",
                "account_type": "checking",
                "customer_id": "CUST002"
            }
        }

        event = {
            "httpMethod": "POST",
            "path": "/transactions",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload)
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 200

        assert mock_client.get_account.call_count == 2
        assert mock_client.create_account.call_count == 2

        account_calls = mock_client.create_account.call_args_list
        from_account = account_calls[0][0][0]
        to_account = account_calls[1][0][0]

        assert from_account.account_id == "ACC123456789"
        assert from_account.account_type == AccountType.BUSINESS
        assert to_account.account_id == "ACC987654321"
        assert to_account.account_type == AccountType.CHECKING

        mock_client.create_transaction.assert_called_once()
        transaction_call = mock_client.create_transaction.call_args[0][0]
        assert transaction_call.amount == Decimal("2500.00")
        assert transaction_call.transaction_type == TransactionType.WIRE

        mock_client.create_transaction_edge.assert_called_once()
        edge_call = mock_client.create_transaction_edge.call_args[0][0]
        assert edge_call.from_account_id == "ACC123456789"
        assert edge_call.to_account_id == "ACC987654321"
        assert edge_call.transaction_id == transaction_call.transaction_id

        print("✓ Referential integrity maintained across Neptune operations")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])