"""
Connection pooling and performance optimization for Lambda functions.

This module provides connection pooling, batch operations, and performance
optimizations for high-throughput transaction processing.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone

from sentinel_aml.core.config import get_settings
from sentinel_aml.core.exceptions import ProcessingError, NeptuneConnectionError
from sentinel_aml.core.logging import get_logger
from sentinel_aml.data.neptune_client import NeptuneClient


logger = get_logger(__name__)


@dataclass
class ConnectionPoolStats:
    """Connection pool statistics."""
    active_connections: int
    total_connections: int
    requests_processed: int
    average_response_time_ms: float
    error_rate: float
    last_reset: datetime


class NeptuneConnectionPool:
    """Connection pool for Neptune database connections."""
    
    def __init__(self, max_connections: int = 10, min_connections: int = 2):
        self.max_connections = max_connections
        self.min_connections = min_connections
        self._connections: List[NeptuneClient] = []
        self._available_connections: asyncio.Queue = asyncio.Queue()
        self._connection_semaphore = asyncio.Semaphore(max_connections)
        self._stats = ConnectionPoolStats(
            active_connections=0,
            total_connections=0,
            requests_processed=0,
            average_response_time_ms=0.0,
            error_rate=0.0,
            last_reset=datetime.now(timezone.utc)
        )
        self._response_times: List[float] = []
        self._error_count = 0
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize the connection pool with minimum connections."""
        logger.info("Initializing Neptune connection pool", 
                   min_connections=self.min_connections,
                   max_connections=self.max_connections)
        
        for _ in range(self.min_connections):
            try:
                client = NeptuneClient()
                await client.connect()
                self._connections.append(client)
                await self._available_connections.put(client)
                self._stats.total_connections += 1
            except Exception as e:
                logger.error("Failed to initialize connection", error=str(e))
                raise NeptuneConnectionError(f"Failed to initialize connection pool: {e}")
        
        logger.info("Connection pool initialized successfully",
                   connections=len(self._connections))
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a connection from the pool."""
        start_time = time.time()
        client = None
        
        try:
            async with self._connection_semaphore:
                try:
                    # Try to get an available connection
                    client = await asyncio.wait_for(
                        self._available_connections.get(), 
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    # Create new connection if under max limit
                    if len(self._connections) < self.max_connections:
                        client = NeptuneClient()
                        await client.connect()
                        self._connections.append(client)
                        async with self._lock:
                            self._stats.total_connections += 1
                    else:
                        raise ProcessingError("Connection pool exhausted")
                
                async with self._lock:
                    self._stats.active_connections += 1
                
                yield client
        
        except Exception as e:
            async with self._lock:
                self._error_count += 1
            logger.error("Connection pool error", error=str(e))
            raise
        
        finally:
            if client:
                # Return connection to pool
                await self._available_connections.put(client)
                async with self._lock:
                    self._stats.active_connections -= 1
                    self._stats.requests_processed += 1
                    
                    # Track response time
                    response_time = (time.time() - start_time) * 1000
                    self._response_times.append(response_time)
                    
                    # Keep only last 1000 response times for average calculation
                    if len(self._response_times) > 1000:
                        self._response_times = self._response_times[-1000:]
                    
                    # Update average response time
                    if self._response_times:
                        self._stats.average_response_time_ms = sum(self._response_times) / len(self._response_times)
                    
                    # Update error rate
                    if self._stats.requests_processed > 0:
                        self._stats.error_rate = self._error_count / self._stats.requests_processed
    
    async def get_stats(self) -> ConnectionPoolStats:
        """Get connection pool statistics."""
        async with self._lock:
            return ConnectionPoolStats(
                active_connections=self._stats.active_connections,
                total_connections=self._stats.total_connections,
                requests_processed=self._stats.requests_processed,
                average_response_time_ms=self._stats.average_response_time_ms,
                error_rate=self._stats.error_rate,
                last_reset=self._stats.last_reset
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on connection pool."""
        try:
            stats = await self.get_stats()
            
            # Test a connection
            async with self.get_connection() as client:
                health = await client.get_health_status()
            
            return {
                "status": "healthy",
                "pool_stats": {
                    "active_connections": stats.active_connections,
                    "total_connections": stats.total_connections,
                    "requests_processed": stats.requests_processed,
                    "average_response_time_ms": stats.average_response_time_ms,
                    "error_rate": stats.error_rate
                },
                "neptune_health": health
            }
        
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def close(self) -> None:
        """Close all connections in the pool."""
        logger.info("Closing connection pool")
        
        for client in self._connections:
            try:
                await client.disconnect()
            except Exception as e:
                logger.error("Error closing connection", error=str(e))
        
        self._connections.clear()
        
        # Clear the queue
        while not self._available_connections.empty():
            try:
                self._available_connections.get_nowait()
            except asyncio.QueueEmpty:
                break


import threading

# Global connection pools (per-loop)
_connection_pools: Dict[int, NeptuneConnectionPool] = {}
# Global throttler (thread-safe, shared across all loops)
_throttler: Optional['RequestThrottler'] = None


async def get_connection_pool() -> NeptuneConnectionPool:
    """Get or create a loop-specific connection pool."""
    global _connection_pools
    
    loop = asyncio.get_event_loop()
    loop_id = id(loop)
    
    if loop_id not in _connection_pools or loop.is_closed():
        settings = get_settings()
        pool = NeptuneConnectionPool(
            max_connections=settings.neptune_max_connections,
            min_connections=max(2, settings.neptune_max_connections // 2)
        )
        await pool.initialize()
        _connection_pools[loop_id] = pool
    
    return _connection_pools[loop_id]


class BatchProcessor:
    """Batch processor for high-throughput transaction processing."""
    
    def __init__(self, batch_size: int = 100, max_workers: int = 10):
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    async def process_batch(
        self, 
        transactions: List[Dict[str, Any]], 
        processor_func: callable
    ) -> List[Tuple[bool, Any]]:
        """Process a batch of transactions concurrently."""
        if not transactions:
            return []
        
        logger.info("Processing transaction batch", 
                   batch_size=len(transactions),
                   max_workers=self.max_workers)
        
        # Split into smaller batches if needed
        batches = [
            transactions[i:i + self.batch_size] 
            for i in range(0, len(transactions), self.batch_size)
        ]
        
        results = []
        
        for batch in batches:
            batch_results = await self._process_single_batch(batch, processor_func)
            results.extend(batch_results)
        
        return results
    
    async def _process_single_batch(
        self, 
        batch: List[Dict[str, Any]], 
        processor_func: callable
    ) -> List[Tuple[bool, Any]]:
        """Process a single batch of transactions."""
        loop = asyncio.get_event_loop()
        
        # Create tasks for concurrent processing
        tasks = []
        for transaction in batch:
            task = loop.run_in_executor(
                self.executor, 
                self._safe_process_transaction, 
                transaction, 
                processor_func
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append((False, str(result)))
            else:
                processed_results.append(result)
        
        return processed_results
    
    def _safe_process_transaction(
        self, 
        transaction: Dict[str, Any], 
        processor_func: callable
    ) -> Tuple[bool, Any]:
        """Safely process a single transaction."""
        try:
            result = processor_func(transaction)
            return (True, result)
        except Exception as e:
            logger.error("Transaction processing failed", 
                        transaction_id=transaction.get("transaction_id"),
                        error=str(e))
            return (False, str(e))
    
    def close(self) -> None:
        """Close the batch processor."""
        self.executor.shutdown(wait=True)


class RequestThrottler:
    """Request throttling and rate limiting (thread-safe and loop-agnostic)."""
    
    def __init__(self, max_requests_per_second: int = 1000):
        self.max_requests_per_second = max_requests_per_second
        self.request_times: List[float] = []
        self._lock = threading.Lock() # Use threading.Lock for cross-loop safety
    
    async def can_process_request(self) -> bool:
        """Check if request can be processed based on rate limits."""
        current_time = time.time()
        
        with self._lock:
            # Remove requests older than 1 second
            self.request_times = [
                req_time for req_time in self.request_times 
                if current_time - req_time < 1.0
            ]
            
            # Check if under rate limit
            if len(self.request_times) < self.max_requests_per_second:
                self.request_times.append(current_time)
                return True
            
            return False
    
    async def get_current_rate(self) -> float:
        """Get current request rate per second."""
        current_time = time.time()
        
        with self._lock:
            # Count requests in last second
            recent_requests = [
                req_time for req_time in self.request_times 
                if current_time - req_time < 1.0
            ]
            
            return len(recent_requests)


def get_throttler() -> RequestThrottler:
    """Get or create the global request throttler."""
    global _throttler
    
    if _throttler is None:
        settings = get_settings()
        _throttler = RequestThrottler(
            max_requests_per_second=settings.max_concurrent_transactions
        )
    
    return _throttler


class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance."""
    
    def __init__(
        self, 
        failure_threshold: int = 5, 
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._lock = asyncio.Lock()
    
    async def call(self, func: callable, *args, **kwargs):
        """Call function with circuit breaker protection."""
        async with self._lock:
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                else:
                    raise ProcessingError("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        
        except self.expected_exception as e:
            await self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset."""
        return (
            self.last_failure_time is not None and
            time.time() - self.last_failure_time >= self.recovery_timeout
        )
    
    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            self.failure_count = 0
            self.state = "CLOSED"
    
    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
    
    async def get_state(self) -> Dict[str, Any]:
        """Get circuit breaker state."""
        async with self._lock:
            return {
                "state": self.state,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "last_failure_time": self.last_failure_time,
                "recovery_timeout": self.recovery_timeout
            }