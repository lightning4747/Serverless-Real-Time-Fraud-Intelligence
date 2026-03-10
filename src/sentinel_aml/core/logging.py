"""Structured logging configuration for Sentinel-AML."""

import logging
import sys
from typing import Any, Dict, Optional

import structlog
from pythonjsonlogger import jsonlogger

from sentinel_aml.core.config import get_settings


def configure_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            # Add log level and timestamp
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Add context processors
            add_correlation_id,
            add_service_context,
            # JSON formatting for production, pretty printing for development
            structlog.processors.JSONRenderer() if settings.environment == "production"
            else structlog.dev.ConsoleRenderer(colors=True)
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def add_correlation_id(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add correlation ID to log entries."""
    # Try to get correlation ID from context (would be set by middleware)
    correlation_id = getattr(logger, '_correlation_id', None)
    if correlation_id:
        event_dict['correlation_id'] = correlation_id
    return event_dict


def add_service_context(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add service context to log entries."""
    settings = get_settings()
    event_dict.update({
        'service': settings.app_name,
        'version': settings.app_version,
        'environment': settings.environment,
    })
    return event_dict


def get_logger(name: Optional[str] = None, **context: Any) -> structlog.BoundLogger:
    """Get a structured logger with optional context."""
    if not structlog.is_configured():
        configure_logging()
    
    logger = structlog.get_logger(name or __name__)
    
    # Bind additional context if provided
    if context:
        logger = logger.bind(**context)
    
    return logger


def set_correlation_id(logger: structlog.BoundLogger, correlation_id: str) -> structlog.BoundLogger:
    """Set correlation ID for request tracing."""
    return logger.bind(correlation_id=correlation_id)


class AMLLoggerMixin:
    """Mixin class to add structured logging to AML components."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = get_logger(
            name=self.__class__.__module__ + "." + self.__class__.__name__
        )
    
    def log_transaction_event(
        self,
        event_type: str,
        transaction_id: str,
        account_id: Optional[str] = None,
        amount: Optional[float] = None,
        **extra_context: Any
    ) -> None:
        """Log transaction-related events with standard context."""
        context = {
            'event_type': event_type,
            'transaction_id': transaction_id,
        }
        
        if account_id:
            context['account_id'] = account_id
        if amount is not None:
            context['amount'] = amount
        
        context.update(extra_context)
        
        self.logger.info("Transaction event", **context)
    
    def log_ml_event(
        self,
        model_name: str,
        event_type: str,
        risk_score: Optional[float] = None,
        features: Optional[Dict[str, Any]] = None,
        **extra_context: Any
    ) -> None:
        """Log ML model events with standard context."""
        context = {
            'model_name': model_name,
            'event_type': event_type,
        }
        
        if risk_score is not None:
            context['risk_score'] = risk_score
        if features:
            context['features'] = features
        
        context.update(extra_context)
        
        self.logger.info("ML model event", **context)
    
    def log_compliance_event(
        self,
        event_type: str,
        case_id: Optional[str] = None,
        regulation: Optional[str] = None,
        **extra_context: Any
    ) -> None:
        """Log compliance-related events with standard context."""
        context = {
            'event_type': event_type,
        }
        
        if case_id:
            context['case_id'] = case_id
        if regulation:
            context['regulation'] = regulation
        
        context.update(extra_context)
        
        self.logger.info("Compliance event", **context)


# Initialize logging on module import
configure_logging()