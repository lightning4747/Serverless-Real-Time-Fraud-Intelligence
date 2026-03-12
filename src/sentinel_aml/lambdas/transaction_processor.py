"""
Transaction ingestion Lambda function for Sentinel-AML system.

This Lambda function handles POST /transactions endpoint requests,
validates transaction data, and stores it in Neptune graph database.
"""

import asyncio
import json
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone

from sentinel_aml.core.config import get_settings
from sentinel_aml.core.exceptions import (
    ValidationError,
    ProcessingError,
    NeptuneConnectionError,
    NeptuneQueryError,
)
from sentinel_aml.core.logging import get_logger, set_correlation_id
from sentinel_aml.core.utils import (
    generate_correlation_id,
    generate_transaction_id,
    sanitize_for_logging,
    hash_pii,
)
from sentinel_aml.data.models import Account, Transaction, TransactionEdge, TransactionType, AccountType
from sentinel_aml.lambdas.connection_pool import (
    get_connection_pool,
    get_throttler,
    CircuitBreaker,
    BatchProcessor,
)


# Global connection pool and throttler
logger = get_logger(__name__)


class TransactionRequest:
    """Transaction request model for API validation."""
    
    def __init__(self, data: Dict[str, Any]):
        self.raw_data = data
        self._validate_required_fields()
        self._parse_and_validate()
    
    def _validate_required_fields(self) -> None:
        """Validate required fields are present."""
        required_fields = [
            "from_account_id", "to_account_id", "amount", 
            "transaction_type", "currency"
        ]
        
        missing_fields = [field for field in required_fields if field not in self.raw_data]
        if missing_fields:
            raise ValidationError(
                f"Missing required fields: {', '.join(missing_fields)}",
                error_code="MISSING_REQUIRED_FIELDS",
                details={"missing_fields": missing_fields}
            )
    
    def _parse_and_validate(self) -> None:
        """Parse and validate transaction data."""
        try:
            # Parse basic transaction data
            self.from_account_id = str(self.raw_data["from_account_id"]).strip()
            self.to_account_id = str(self.raw_data["to_account_id"]).strip()
            self.amount = Decimal(str(self.raw_data["amount"]))
            self.currency = str(self.raw_data["currency"]).upper()
            
            # Validate transaction type
            transaction_type_str = str(self.raw_data["transaction_type"]).lower()
            try:
                self.transaction_type = TransactionType(transaction_type_str)
            except ValueError:
                raise ValidationError(
                    f"Invalid transaction type: {transaction_type_str}",
                    error_code="INVALID_TRANSACTION_TYPE"
                )
            
            # Optional fields with defaults
            self.transaction_id = self.raw_data.get("transaction_id") or generate_transaction_id()
            self.description = self.raw_data.get("description")
            self.reference_number = self.raw_data.get("reference_number")
            self.channel = self.raw_data.get("channel", "api")
            self.country_code = self.raw_data.get("country_code")
            self.city = self.raw_data.get("city")
            self.is_cash = bool(self.raw_data.get("is_cash", False))
            self.is_international = bool(self.raw_data.get("is_international", False))
            
            # Parse timestamp
            timestamp_str = self.raw_data.get("timestamp")
            if timestamp_str:
                try:
                    self.timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except ValueError:
                    raise ValidationError(
                        f"Invalid timestamp format: {timestamp_str}",
                        error_code="INVALID_TIMESTAMP"
                    )
            else:
                self.timestamp = datetime.now(timezone.utc)
            
            # Account information (optional, for account creation if needed)
            self.from_account_info = self.raw_data.get("from_account", {})
            self.to_account_info = self.raw_data.get("to_account", {})
            
            # Validate business rules
            self._validate_business_rules()
            
        except (ValueError, TypeError, KeyError) as e:
            raise ValidationError(
                f"Invalid transaction data: {str(e)}",
                error_code="INVALID_DATA_FORMAT"
            )
    
    def _validate_business_rules(self) -> None:
        """Validate business rules for transactions."""
        # Amount validation
        if self.amount <= 0:
            raise ValidationError(
                "Transaction amount must be positive",
                error_code="INVALID_AMOUNT"
            )
        
        if self.amount > Decimal("999999999.99"):
            raise ValidationError(
                "Transaction amount exceeds maximum limit",
                error_code="AMOUNT_EXCEEDS_LIMIT"
            )
        
        # Account validation
        if self.from_account_id == self.to_account_id:
            raise ValidationError(
                "Source and destination accounts cannot be the same",
                error_code="SAME_ACCOUNT_TRANSFER"
            )
        
        # Currency validation
        valid_currencies = {"USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF"}
        if self.currency not in valid_currencies:
            raise ValidationError(
                f"Unsupported currency: {self.currency}",
                error_code="UNSUPPORTED_CURRENCY"
            )


async def ensure_account_exists(
    connection_pool, 
    account_id: str, 
    account_info: Dict[str, Any]
) -> None:
    """Ensure account exists in Neptune, create if necessary."""
    try:
        # Use connection pool for better performance
        async with connection_pool.get_connection() as client:
            # Check if account exists
            existing_account = await client.get_account(account_id)
            
            if existing_account is None:
                # Create account with provided info or defaults
                account_type_str = account_info.get("account_type", "checking")
                try:
                    account_type = AccountType(account_type_str.lower())
                except ValueError:
                    account_type = AccountType.CHECKING
                
                account = Account(
                    account_id=account_id,
                    customer_name=hash_pii(account_info.get("customer_name", f"Customer_{account_id}")),
                    account_type=account_type,
                    risk_score=float(account_info.get("risk_score", 0.0)),
                    customer_id=account_info.get("customer_id"),
                    country_code=account_info.get("country_code"),
                    is_pep=bool(account_info.get("is_pep", False)),
                    kyc_status=account_info.get("kyc_status", "pending"),
                    balance=Decimal(str(account_info.get("balance", 0))) if account_info.get("balance") else None,
                    currency=account_info.get("currency", "USD"),
                    is_active=bool(account_info.get("is_active", True))
                )
                
                await client.create_account(account)
                logger.info(
                    "Created new account",
                    account_id=account_id,
                    account_type=account_type.value
                )
    
    except Exception as e:
        logger.error("Failed to ensure account exists", account_id=account_id, error=str(e))
        raise ProcessingError(f"Failed to ensure account exists: {e}")


async def process_transaction(request: TransactionRequest) -> Dict[str, Any]:
    """Process a single transaction request with connection pooling."""
    start_time = time.time()
    
    try:
        # Get connection pool
        connection_pool = await get_connection_pool()
        
        # Use connection pool for better performance and concurrency
        async with connection_pool.get_connection() as client:
            # Ensure both accounts exist
            await ensure_account_exists(connection_pool, request.from_account_id, request.from_account_info)
            await ensure_account_exists(connection_pool, request.to_account_id, request.to_account_info)
            
            # Create transaction
            transaction = Transaction(
                transaction_id=request.transaction_id,
                amount=request.amount,
                timestamp=request.timestamp,
                transaction_type=request.transaction_type,
                currency=request.currency,
                description=request.description,
                reference_number=request.reference_number,
                channel=request.channel,
                country_code=request.country_code,
                city=request.city,
                is_cash=request.is_cash,
                is_international=request.is_international
            )
            
            transaction_vertex_id = await client.create_transaction(transaction)
            
            # Create transaction edge (SENT_TO relationship)
            edge = TransactionEdge(
                from_account_id=request.from_account_id,
                to_account_id=request.to_account_id,
                transaction_id=request.transaction_id,
                amount=request.amount,
                timestamp=request.timestamp,
                transaction_type=request.transaction_type
            )
            
            edge_id = await client.create_transaction_edge(edge)
            
            processing_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            logger.info(
                "Transaction processed successfully",
                transaction_id=request.transaction_id,
                from_account=request.from_account_id,
                to_account=request.to_account_id,
                amount=float(request.amount),
                processing_time_ms=processing_time
            )
            
            return {
                "transaction_id": request.transaction_id,
                "status": "processed",
                "vertex_id": transaction_vertex_id,
                "edge_id": edge_id,
                "processing_time_ms": processing_time,
                "timestamp": request.timestamp.isoformat()
            }
    
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        logger.error(
            "Transaction processing failed",
            transaction_id=request.transaction_id,
            error=str(e),
            processing_time_ms=processing_time
        )
        raise


def create_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    correlation_id: Optional[str] = None
) -> Dict[str, Any]:
    """Create standardized error response."""
    response = {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Correlation-ID"
        },
        "body": json.dumps({
            "error": {
                "code": error_code,
                "message": message,
                "details": details or {},
                "correlation_id": correlation_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        })
    }
    
    if correlation_id:
        response["headers"]["X-Correlation-ID"] = correlation_id
    
    return response


def create_success_response(
    data: Dict[str, Any],
    correlation_id: Optional[str] = None
) -> Dict[str, Any]:
    """Create standardized success response."""
    response = {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Correlation-ID"
        },
        "body": json.dumps({
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    }
    
    if correlation_id:
        response["headers"]["X-Correlation-ID"] = correlation_id
    
    return response


async def _lambda_handler_internal(
    event: Dict[str, Any], 
    correlation_id: str,
    start_time: float
) -> Dict[str, Any]:
    """Internal async handler for transaction ingestion."""
    # Check rate limiting (requirement 1.4: handle up to 1000 transactions per second)
    throttler = get_throttler()
    
    can_process = await throttler.can_process_request()
    if not can_process:
        current_rate = await throttler.get_current_rate()
        logger.warning(
            "Request throttled due to rate limit",
            current_rate=current_rate,
            max_rate=throttler.max_requests_per_second
        )
        
        return create_error_response(
            429,
            "RATE_LIMIT_EXCEEDED",
            f"Rate limit exceeded. Current rate: {current_rate}/sec, Max: {throttler.max_requests_per_second}/sec",
            details={"current_rate": current_rate, "max_rate": throttler.max_requests_per_second},
            correlation_id=correlation_id
        )
    
    # Parse request body
    try:
        if not event.get("body"):
            return create_error_response(
                400,
                "MISSING_REQUEST_BODY",
                "Request body is required",
                correlation_id=correlation_id
            )
        
        body = json.loads(event["body"])
        if not isinstance(body, dict):
            return create_error_response(
                400,
                "INVALID_REQUEST_BODY",
                "Request body must be a JSON object",
                correlation_id=correlation_id
            )
    
    except json.JSONDecodeError as e:
        return create_error_response(
            400,
            "INVALID_JSON",
            f"Invalid JSON in request body: {str(e)}",
            correlation_id=correlation_id
        )
    
    # Validate schema within 100ms requirement
    schema_validation_start = time.time()
    
    try:
        transaction_request = TransactionRequest(body)
    except ValidationError as e:
        schema_validation_time = (time.time() - schema_validation_start) * 1000
        logger.warning(
            "Schema validation failed",
            validation_time_ms=schema_validation_time,
            error=e.message,
            error_code=e.error_code
        )
        
        return create_error_response(
            400,
            e.error_code,
            e.message,
            details=e.details,
            correlation_id=correlation_id
        )
    
    schema_validation_time = (time.time() - schema_validation_start) * 1000
    
    # Check if schema validation exceeded 100ms requirement
    if schema_validation_time > 100:
        logger.warning(
            "Schema validation exceeded 100ms requirement",
            validation_time_ms=schema_validation_time
        )
    
    # Process transaction within 500ms requirement with circuit breaker
    processing_start = time.time()
    
    # Initialize circuit breaker for Neptune operations
    circuit_breaker = CircuitBreaker(
        failure_threshold=5,
        recovery_timeout=60,
        expected_exception=(NeptuneConnectionError, NeptuneQueryError, ProcessingError)
    )
    
    try:
        # Run async transaction processing with circuit breaker protection
        result = await circuit_breaker.call(process_transaction, transaction_request)
    
    except (NeptuneConnectionError, NeptuneQueryError) as e:
        processing_time = (time.time() - processing_start) * 1000
        logger.error(
            "Neptune database error",
            processing_time_ms=processing_time,
            error=str(e)
        )
        
        return create_error_response(
            503,
            "DATABASE_ERROR",
            "Database temporarily unavailable. Please try again later.",
            details={"processing_time_ms": processing_time},
            correlation_id=correlation_id
        )
    
    except ProcessingError as e:
        processing_time = (time.time() - processing_start) * 1000
        logger.error(
            "Transaction processing error",
            processing_time_ms=processing_time,
            error=str(e)
        )
        
        # Check if circuit breaker is open
        cb_state = await circuit_breaker.get_state()
        if cb_state["state"] == "OPEN":
            return create_error_response(
                503,
                "SERVICE_UNAVAILABLE",
                "Service temporarily unavailable due to repeated failures. Please try again later.",
                details={"circuit_breaker_state": cb_state, "processing_time_ms": processing_time},
                correlation_id=correlation_id
            )
        
        return create_error_response(
            500,
            "PROCESSING_ERROR",
            "Failed to process transaction. Please try again later.",
            details={"processing_time_ms": processing_time},
            correlation_id=correlation_id
        )
    
    processing_time = (time.time() - processing_start) * 1000
    total_time = (time.time() - start_time) * 1000
    
    # Check if processing exceeded 500ms requirement
    if processing_time > 500:
        logger.warning(
            "Transaction processing exceeded 500ms requirement",
            processing_time_ms=processing_time
        )
    
    # Add timing information to result
    result.update({
        "schema_validation_time_ms": schema_validation_time,
        "total_processing_time_ms": total_time
    })
    
    logger.info(
        "Transaction ingestion completed successfully",
        transaction_id=result["transaction_id"],
        total_time_ms=total_time,
        schema_validation_ms=schema_validation_time,
        processing_time_ms=processing_time
    )
    
    return create_success_response(result, correlation_id)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for transaction ingestion.
    """
    start_time = time.time()
    
    # Generate correlation ID for request tracing
    correlation_id = (
        event.get("headers", {}).get("X-Correlation-ID") or
        event.get("headers", {}).get("x-correlation-id") or
        generate_correlation_id()
    )
    
    # Set up logging context
    global logger
    logger = set_correlation_id(logger, correlation_id)
    
    try:
        # Log request start
        logger.info(
            "Transaction ingestion request started",
            http_method=event.get("httpMethod"),
            path=event.get("path"),
            correlation_id=correlation_id
        )
        
        # Handle CORS preflight requests
        if event.get("httpMethod") == "OPTIONS":
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Correlation-ID"
                },
                "body": ""
            }
        
        # Validate HTTP method
        if event.get("httpMethod") != "POST":
            return create_error_response(
                405,
                "METHOD_NOT_ALLOWED",
                "Only POST method is allowed for transaction ingestion",
                correlation_id=correlation_id
            )

        # Execute using a fresh managed event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                _lambda_handler_internal(event, correlation_id, start_time)
            )
        finally:
            loop.close()
            
    except Exception as e:
        total_time = (time.time() - start_time) * 1000
        logger.error(
            "Unexpected error in transaction ingestion",
            error=str(e),
            total_time_ms=total_time,
            correlation_id=correlation_id
        )
        
        return create_error_response(
            500,
            "INTERNAL_ERROR",
            "An unexpected error occurred. Please try again later.",
            details={"total_time_ms": total_time},
            correlation_id=correlation_id
        )


# Health check handler for monitoring
def health_check_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Health check endpoint for Lambda function monitoring."""
    try:
        settings = get_settings()
        
        # Basic health check
        health_status = {
            "status": "healthy",
            "service": settings.app_name,
            "version": settings.app_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": settings.environment
        }
        
        # Test connection pool and Neptune connection if available
        if settings.neptune_endpoint:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Get connection pool health
                    connection_pool = loop.run_until_complete(get_connection_pool())
                    pool_health = loop.run_until_complete(connection_pool.health_check())
                    health_status["connection_pool"] = pool_health
                    
                    # Get throttler status
                    throttler = get_throttler()
                    current_rate = loop.run_until_complete(throttler.get_current_rate())
                    health_status["throttler"] = {
                        "current_rate": current_rate,
                        "max_rate": throttler.max_requests_per_second,
                        "utilization": current_rate / throttler.max_requests_per_second
                    }
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                health_status["connection_pool"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
                health_status["status"] = "degraded"
        
        status_code = 200 if health_status["status"] == "healthy" else 503
        
        return {
            "statusCode": status_code,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(health_status)
        }
    
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        }