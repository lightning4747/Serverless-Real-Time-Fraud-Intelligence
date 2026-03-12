"""Comprehensive audit logging system for regulatory compliance."""

import json
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field

from sentinel_aml.core.config import get_settings
from sentinel_aml.core.logging import get_logger
from sentinel_aml.security.pii_protection import get_pii_service

logger = get_logger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events for AML compliance."""
    
    # Transaction Processing
    TRANSACTION_RECEIVED = "transaction_received"
    TRANSACTION_VALIDATED = "transaction_validated"
    TRANSACTION_STORED = "transaction_stored"
    TRANSACTION_REJECTED = "transaction_rejected"
    
    # Risk Assessment
    RISK_ANALYSIS_STARTED = "risk_analysis_started"
    RISK_SCORE_CALCULATED = "risk_score_calculated"
    SUSPICIOUS_ACTIVITY_FLAGGED = "suspicious_activity_flagged"
    
    # SAR Generation
    SAR_GENERATION_STARTED = "sar_generation_started"
    SAR_GENERATED = "sar_generated"
    SAR_REVIEWED = "sar_reviewed"
    SAR_FILED = "sar_filed"
    
    # Data Access
    PII_ACCESSED = "pii_accessed"
    DATA_ENCRYPTED = "data_encrypted"
    DATA_DECRYPTED = "data_decrypted"
    DATA_MASKED = "data_masked"
    
    # System Events
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    CONFIGURATION_CHANGED = "configuration_changed"
    MODEL_DEPLOYED = "model_deployed"
    
    # Compliance Events
    AUDIT_REPORT_GENERATED = "audit_report_generated"
    REGULATORY_INQUIRY = "regulatory_inquiry"
    DATA_RETENTION_APPLIED = "data_retention_applied"


class AuditEvent(BaseModel):
    """Audit event model for compliance logging."""
    
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: AuditEventType
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Event details
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: str
    outcome: str  # SUCCESS, FAILURE, PARTIAL
    
    # Context and metadata
    details: Dict[str, Any] = Field(default_factory=dict)
    risk_score: Optional[float] = None
    compliance_flags: List[str] = Field(default_factory=list)
    
    # Traceability
    correlation_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    
    # Data classification
    contains_pii: bool = False
    data_classification: str = "internal"  # public, internal, confidential, restricted
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AuditLogger:
    """Comprehensive audit logging service for AML compliance."""
    
    def __init__(self):
        """Initialize audit logger."""
        self.settings = get_settings()
        self.pii_service = get_pii_service()
        
        # Initialize audit storage (will be implemented in audit_storage.py)
        from sentinel_aml.compliance.audit_storage import get_audit_storage
        self.storage = get_audit_storage()
    
    def log_event(self, 
                  event_type: AuditEventType,
                  action: str,
                  outcome: str = "SUCCESS",
                  user_id: Optional[str] = None,
                  resource_type: Optional[str] = None,
                  resource_id: Optional[str] = None,
                  details: Optional[Dict[str, Any]] = None,
                  **kwargs) -> str:
        """Log an audit event and return event ID."""
        
        # Create audit event
        event = AuditEvent(
            event_type=event_type,
            action=action,
            outcome=outcome,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            **kwargs
        )
        
        # Check for PII in details
        if details:
            event.contains_pii = self._contains_pii(details)
            
            # Sanitize details for logging if PII is present
            if event.contains_pii:
                sanitized_details = self.pii_service.sanitize_for_logging(details)
                event.details = sanitized_details
        
        # Store audit event
        try:
            self.storage.store_audit_record(event)
            logger.info(f"Audit event logged: {event.event_id} - {event_type.value}")
            return event.event_id
            
        except Exception as e:
            logger.error(f"Failed to store audit event: {e}")
            # In case of storage failure, at least log to application logs
            logger.critical(f"AUDIT_FAILURE: {event.model_dump_json()}")
            raise
    
    def log_transaction_event(self,
                            transaction_id: str,
                            event_type: AuditEventType,
                            action: str,
                            outcome: str = "SUCCESS",
                            amount: Optional[float] = None,
                            currency: Optional[str] = None,
                            risk_score: Optional[float] = None,
                            **kwargs) -> str:
        """Log transaction-related audit event."""
        
        details = {
            "transaction_id": transaction_id,
            "amount": amount,
            "currency": currency,
        }
        details.update(kwargs.get('details', {}))
        
        return self.log_event(
            event_type=event_type,
            action=action,
            outcome=outcome,
            resource_type="transaction",
            resource_id=transaction_id,
            risk_score=risk_score,
            details=details,
            **{k: v for k, v in kwargs.items() if k != 'details'}
        )
    
    def log_sar_event(self,
                     sar_id: str,
                     event_type: AuditEventType,
                     action: str,
                     outcome: str = "SUCCESS",
                     confidence_score: Optional[float] = None,
                     **kwargs) -> str:
        """Log SAR-related audit event."""
        
        details = {
            "sar_id": sar_id,
            "confidence_score": confidence_score,
        }
        details.update(kwargs.get('details', {}))
        
        return self.log_event(
            event_type=event_type,
            action=action,
            outcome=outcome,
            resource_type="sar",
            resource_id=sar_id,
            details=details,
            data_classification="confidential",
            **{k: v for k, v in kwargs.items() if k != 'details'}
        )
    
    def log_pii_access(self,
                      user_id: str,
                      resource_id: str,
                      pii_fields: List[str],
                      action: str = "access",
                      **kwargs) -> str:
        """Log PII access for compliance tracking."""
        
        details = {
            "pii_fields_accessed": pii_fields,
            "access_reason": kwargs.get('reason', 'investigation'),
        }
        
        return self.log_event(
            event_type=AuditEventType.PII_ACCESSED,
            action=action,
            user_id=user_id,
            resource_type="pii_data",
            resource_id=resource_id,
            details=details,
            contains_pii=True,
            data_classification="restricted",
            compliance_flags=["PII_ACCESS", "PRIVACY_SENSITIVE"],
            **kwargs
        )
    
    def log_model_decision(self,
                          model_name: str,
                          model_version: str,
                          input_data_hash: str,
                          prediction: Any,
                          confidence: float,
                          **kwargs) -> str:
        """Log ML model decisions for explainability."""
        
        details = {
            "model_name": model_name,
            "model_version": model_version,
            "input_data_hash": input_data_hash,
            "prediction": prediction,
            "confidence": confidence,
            "feature_importance": kwargs.get('feature_importance', {}),
        }
        
        return self.log_event(
            event_type=AuditEventType.RISK_SCORE_CALCULATED,
            action="model_prediction",
            resource_type="ml_model",
            resource_id=f"{model_name}:{model_version}",
            details=details,
            risk_score=confidence if isinstance(prediction, (int, float)) else None,
            **kwargs
        )
    
    def _contains_pii(self, data: Dict[str, Any]) -> bool:
        """Check if data contains PII fields."""
        for key in data.keys():
            if self.pii_service.is_pii_field(key):
                return True
        return False
    
    def get_audit_trail(self,
                       resource_type: Optional[str] = None,
                       resource_id: Optional[str] = None,
                       user_id: Optional[str] = None,
                       start_time: Optional[datetime] = None,
                       end_time: Optional[datetime] = None,
                       limit: int = 100) -> List[AuditEvent]:
        """Retrieve audit trail for compliance reporting."""
        
        return self.storage.query_audit_records(
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )


@lru_cache()
def get_audit_logger() -> AuditLogger:
    """Get cached audit logger instance."""
    return AuditLogger()


def log_audit_event(event_type: AuditEventType, 
                   action: str, 
                   **kwargs) -> str:
    """Convenience function to log audit event."""
    logger_instance = get_audit_logger()
    return logger_instance.log_event(event_type, action, **kwargs)