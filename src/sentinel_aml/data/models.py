"""Pydantic data models for Sentinel-AML system."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, ConfigDict

from sentinel_aml.core.utils import (
    validate_account_id,
    validate_currency_code,
    validate_transaction_amount,
)


class AccountType(str, Enum):
    """Account type enumeration."""
    CHECKING = "checking"
    SAVINGS = "savings"
    BUSINESS = "business"
    INVESTMENT = "investment"
    CREDIT = "credit"
    LOAN = "loan"


class TransactionType(str, Enum):
    """Transaction type enumeration."""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    PAYMENT = "payment"
    WIRE = "wire"
    ACH = "ach"
    CHECK = "check"
    CARD = "card"


class RiskLevel(str, Enum):
    """Risk level enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status enumeration."""
    OPEN = "open"
    INVESTIGATING = "investigating"
    CLOSED = "closed"
    ESCALATED = "escalated"
    FALSE_POSITIVE = "false_positive"


class Account(BaseModel):
    """Account node model for Neptune graph."""
    
    account_id: str = Field(..., description="Unique account identifier")
    customer_name: str = Field(..., description="Customer name (will be hashed for privacy)")
    account_type: AccountType = Field(..., description="Type of account")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Current risk score")
    creation_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_date: Optional[datetime] = Field(default=None, description="Last transaction date")
    
    # Customer profile information
    customer_id: Optional[str] = Field(default=None, description="Customer identifier")
    country_code: Optional[str] = Field(default=None, description="Country code (ISO 3166-1)")
    is_pep: bool = Field(default=False, description="Politically Exposed Person flag")
    kyc_status: str = Field(default="pending", description="KYC verification status")
    
    # Account metadata
    balance: Optional[Decimal] = Field(default=None, description="Current account balance")
    currency: str = Field(default="USD", description="Account currency")
    is_active: bool = Field(default=True, description="Account active status")
    
    @field_validator("account_id")
    @classmethod
    def validate_account_id_format(cls, v):
        """Validate account ID format."""
        if not validate_account_id(v):
            raise ValueError("Invalid account ID format")
        return v
    
    @field_validator("currency")
    @classmethod
    def validate_currency_format(cls, v):
        """Validate currency code."""
        return validate_currency_code(v)
    
    @field_validator("country_code")
    @classmethod
    def validate_country_code_format(cls, v):
        """Validate country code format."""
        if v and len(v) != 2:
            raise ValueError("Country code must be 2 characters (ISO 3166-1)")
        return v.upper() if v else v
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v),
        }
    )


class Transaction(BaseModel):
    """Transaction node model for Neptune graph."""
    
    transaction_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique transaction ID")
    amount: Decimal = Field(..., description="Transaction amount")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    transaction_type: TransactionType = Field(..., description="Type of transaction")
    currency: str = Field(default="USD", description="Transaction currency")
    
    # Transaction details
    description: Optional[str] = Field(default=None, description="Transaction description")
    reference_number: Optional[str] = Field(default=None, description="External reference number")
    channel: Optional[str] = Field(default=None, description="Transaction channel (online, atm, branch)")
    
    # Geographic information
    country_code: Optional[str] = Field(default=None, description="Transaction country")
    city: Optional[str] = Field(default=None, description="Transaction city")
    
    # Risk indicators
    is_cash: bool = Field(default=False, description="Cash transaction flag")
    is_international: bool = Field(default=False, description="International transaction flag")
    risk_flags: List[str] = Field(default_factory=list, description="Risk flags identified")
    
    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        """Validate transaction amount."""
        return validate_transaction_amount(v)
    
    @field_validator("currency")
    @classmethod
    def validate_currency_format(cls, v):
        """Validate currency code."""
        return validate_currency_code(v)
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v),
        }
    )


class TransactionEdge(BaseModel):
    """Transaction edge model representing SENT_TO relationships."""
    
    from_account_id: str = Field(..., description="Source account ID")
    to_account_id: str = Field(..., description="Destination account ID")
    transaction_id: str = Field(..., description="Transaction ID")
    
    # Edge properties
    amount: Decimal = Field(..., description="Transaction amount")
    timestamp: datetime = Field(..., description="Transaction timestamp")
    transaction_type: TransactionType = Field(..., description="Transaction type")
    
    # Relationship metadata
    edge_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique edge ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v),
        }
    )


class RiskScore(BaseModel):
    """Risk score model for ML predictions."""
    
    entity_id: str = Field(..., description="Entity ID (account or transaction)")
    entity_type: str = Field(..., description="Entity type (account or transaction)")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Risk score between 0 and 1")
    
    # Model information
    model_name: str = Field(..., description="ML model name")
    model_version: str = Field(..., description="ML model version")
    prediction_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Feature importance and explanation
    feature_scores: Dict[str, float] = Field(default_factory=dict, description="Feature importance scores")
    explanation: Optional[str] = Field(default=None, description="Human-readable explanation")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Prediction confidence")
    
    # Risk factors
    risk_factors: List[str] = Field(default_factory=list, description="Identified risk factors")
    pattern_matches: List[str] = Field(default_factory=list, description="Matched suspicious patterns")
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
        }
    )


class Alert(BaseModel):
    """Alert model for suspicious activity notifications."""
    
    alert_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique alert ID")
    case_id: Optional[str] = Field(default=None, description="Associated case ID")
    
    # Alert details
    title: str = Field(..., description="Alert title")
    description: str = Field(..., description="Alert description")
    risk_level: RiskLevel = Field(..., description="Risk level")
    status: AlertStatus = Field(default=AlertStatus.OPEN, description="Alert status")
    
    # Associated entities
    account_ids: List[str] = Field(default_factory=list, description="Involved account IDs")
    transaction_ids: List[str] = Field(default_factory=list, description="Involved transaction IDs")
    
    # Risk information
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Overall risk score")
    suspicious_patterns: List[str] = Field(default_factory=list, description="Detected patterns")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    investigated_at: Optional[datetime] = Field(default=None, description="Investigation start time")
    closed_at: Optional[datetime] = Field(default=None, description="Alert closure time")
    
    # Investigation details
    investigator_id: Optional[str] = Field(default=None, description="Assigned investigator")
    investigation_notes: Optional[str] = Field(default=None, description="Investigation notes")
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
        }
    )


class SuspiciousActivityReport(BaseModel):
    """Suspicious Activity Report (SAR) model."""
    
    sar_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique SAR ID")
    case_id: str = Field(..., description="Associated case ID")
    
    # Report metadata
    report_number: Optional[str] = Field(default=None, description="Official SAR report number")
    filing_date: Optional[datetime] = Field(default=None, description="SAR filing date")
    status: str = Field(default="draft", description="SAR status")
    
    # Involved parties
    subject_accounts: List[str] = Field(..., description="Subject account IDs")
    subject_names: List[str] = Field(..., description="Subject names (hashed)")
    
    # Suspicious activity details
    activity_description: str = Field(..., description="Description of suspicious activity")
    suspicious_patterns: List[str] = Field(..., description="Identified suspicious patterns")
    transaction_summary: str = Field(..., description="Summary of transactions")
    
    # Financial information
    total_amount: Decimal = Field(..., description="Total amount involved")
    currency: str = Field(default="USD", description="Currency")
    date_range_start: datetime = Field(..., description="Activity start date")
    date_range_end: datetime = Field(..., description="Activity end date")
    
    # Regulatory information
    regulation_violated: List[str] = Field(default_factory=list, description="Regulations violated")
    reporting_reason: str = Field(..., description="Reason for reporting")
    
    # AI generation metadata
    generated_by_ai: bool = Field(default=True, description="Generated by AI flag")
    ai_model_version: Optional[str] = Field(default=None, description="AI model version")
    ai_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="AI confidence score")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @field_validator("total_amount")
    @classmethod
    def validate_total_amount(cls, v):
        """Validate total amount."""
        return validate_transaction_amount(v)
    
    @field_validator("currency")
    @classmethod
    def validate_currency_format(cls, v):
        """Validate currency code."""
        return validate_currency_code(v)
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v),
        }
    )