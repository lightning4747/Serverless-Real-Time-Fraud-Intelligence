"""Custom exceptions for Sentinel-AML system."""

from typing import Any, Dict, Optional


class SentinelAMLError(Exception):
    """Base exception for all Sentinel-AML errors."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class ValidationError(SentinelAMLError):
    """Raised when data validation fails."""
    pass


class ProcessingError(SentinelAMLError):
    """Raised when transaction processing fails."""
    pass


class NeptuneConnectionError(SentinelAMLError):
    """Raised when Neptune database connection fails."""
    pass


class NeptuneQueryError(SentinelAMLError):
    """Raised when Neptune query execution fails."""
    pass


class MLModelError(SentinelAMLError):
    """Raised when ML model operations fail."""
    pass


class BedrockError(SentinelAMLError):
    """Raised when Bedrock API operations fail."""
    pass


class SARGenerationError(SentinelAMLError):
    """Raised when SAR generation fails."""
    pass


class AuthenticationError(SentinelAMLError):
    """Raised when authentication fails."""
    pass


class AuthorizationError(SentinelAMLError):
    """Raised when authorization fails."""
    pass


class RateLimitError(SentinelAMLError):
    """Raised when rate limits are exceeded."""
    pass


class ConfigurationError(SentinelAMLError):
    """Raised when configuration is invalid."""
    pass


class ComplianceError(SentinelAMLError):
    """Raised when compliance requirements are not met."""
    pass