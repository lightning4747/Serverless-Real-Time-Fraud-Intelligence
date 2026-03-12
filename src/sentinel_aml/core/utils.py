"""Core utility functions for Sentinel-AML."""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from decimal import Decimal
import decimal
import re

from sentinel_aml.core.exceptions import ValidationError


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for request tracing."""
    return str(uuid.uuid4())


def generate_transaction_id() -> str:
    """Generate a unique transaction ID."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    unique_id = str(uuid.uuid4()).replace("-", "")[:8]
    return f"TXN-{timestamp}-{unique_id}"


def generate_case_id() -> str:
    """Generate a unique case ID for investigations."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    unique_id = str(uuid.uuid4()).replace("-", "")[:8].upper()
    return f"CASE-{timestamp}-{unique_id}"


def hash_pii(data: str, salt: Optional[str] = None) -> str:
    """Hash PII data for privacy protection."""
    if salt is None:
        salt = "sentinel-aml-default-salt"  # In production, use proper salt management
    
    combined = f"{data}{salt}"
    return hashlib.sha256(combined.encode()).hexdigest()


def mask_account_number(account_number: str) -> str:
    """Mask account number for logging and display."""
    if len(account_number) <= 4:
        return "*" * len(account_number)
    
    return "*" * (len(account_number) - 4) + account_number[-4:]


def mask_email(email: str) -> str:
    """Mask email address for logging and display."""
    if "@" not in email:
        # For invalid emails, use max 12 asterisks
        return "*" * min(len(email), 12)
    
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        masked_local = "*" * len(local)
    elif len(local) == 2:
        masked_local = "*" * len(local)
    else:
        # For length > 2: show first and last char, mask the middle with max 5 asterisks
        middle_length = len(local) - 2
        asterisk_count = min(middle_length, 5)
        masked_local = local[0] + "*" * asterisk_count + local[-1]
    
    return f"{masked_local}@{domain}"


def validate_account_id(account_id: str) -> bool:
    """Validate account ID format."""
    # Account ID should be alphanumeric, 8-20 characters
    pattern = r"^[A-Za-z0-9]{8,20}$"
    return bool(re.match(pattern, account_id))


def validate_transaction_amount(amount: Union[float, Decimal, str]) -> Decimal:
    """Validate and normalize transaction amount."""
    try:
        decimal_amount = Decimal(str(amount))
    except (ValueError, TypeError, decimal.InvalidOperation):
        raise ValueError(f"Invalid transaction amount: {amount}")
    
    if decimal_amount < 0:
        raise ValueError("Transaction amount cannot be negative")
    
    if decimal_amount > Decimal("999999999.99"):
        raise ValueError("Transaction amount exceeds maximum limit")
    
    # Round to 2 decimal places for currency using ROUND_HALF_UP
    from decimal import ROUND_HALF_UP
    return decimal_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_currency_code(currency: str) -> str:
    """Validate ISO 4217 currency code."""
    # Common currency codes for AML systems
    valid_currencies = {
        "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", 
        "HKD", "SGD", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF",
        "RUB", "BRL", "MXN", "INR", "KRW", "THB", "MYR", "IDR"
    }
    
    currency_upper = currency.upper()
    if currency_upper not in valid_currencies:
        raise ValueError(f"Invalid currency code: {currency}")
    
    return currency_upper


def is_high_risk_jurisdiction(country_code: str) -> bool:
    """Check if country is in high-risk jurisdiction list."""
    # FATF high-risk jurisdictions (example list - should be updated regularly)
    high_risk_countries = {
        "IR",  # Iran
        "KP",  # North Korea
        "MM",  # Myanmar
        # Add more based on current FATF list
    }
    
    return country_code.upper() in high_risk_countries


def calculate_velocity_score(
    transactions: List[Dict[str, Any]], 
    time_window_hours: int = 24
) -> float:
    """Calculate transaction velocity score for an account."""
    if not transactions:
        return 0.0
    
    # Sort transactions by timestamp
    sorted_txns = sorted(transactions, key=lambda x: x.get("timestamp", 0))
    
    if len(sorted_txns) < 2:
        return 0.0
    
    # Calculate time span and transaction frequency
    time_span = sorted_txns[-1]["timestamp"] - sorted_txns[0]["timestamp"]
    if time_span == 0:
        return 1.0  # Multiple transactions at same time is suspicious
    
    # Normalize to transactions per hour
    hours = time_span / 3600  # Convert seconds to hours
    frequency = len(sorted_txns) / max(hours, 0.1)  # Avoid division by zero
    
    # Score based on frequency (higher frequency = higher score)
    # Normal: 0-2 txns/hour, Suspicious: >10 txns/hour
    if frequency <= 2:
        return 0.1
    elif frequency <= 5:
        return 0.3
    elif frequency <= 10:
        return 0.6
    else:
        return min(1.0, frequency / 20)  # Cap at 1.0


def detect_round_dollar_pattern(amounts: List[Union[float, Decimal]]) -> float:
    """Detect round dollar amount patterns (potential structuring)."""
    if not amounts:
        return 0.0
    
    round_count = 0
    for amount in amounts:
        decimal_amount = Decimal(str(amount))
        # Check if amount is round (no cents)
        if decimal_amount % 1 == 0:
            round_count += 1
    
    round_percentage = round_count / len(amounts)
    
    # High percentage of round amounts is suspicious
    if round_percentage >= 0.8:
        return 0.9
    elif round_percentage >= 0.6:
        return 0.6
    elif round_percentage >= 0.4:
        return 0.3
    else:
        return 0.1


def format_currency(amount: Union[float, Decimal], currency: str = "USD") -> str:
    """Format currency amount for display."""
    decimal_amount = Decimal(str(amount))
    
    if currency == "USD":
        return f"${decimal_amount:,.2f}"
    elif currency == "EUR":
        return f"€{decimal_amount:,.2f}"
    elif currency == "GBP":
        return f"£{decimal_amount:,.2f}"
    else:
        return f"{decimal_amount:,.2f} {currency}"


def sanitize_for_logging(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize sensitive data for logging."""
    sensitive_fields = {
        "account_number", "ssn", "tax_id", "phone", "email", 
        "address", "name", "customer_name", "beneficiary_name"
    }
    
    sanitized = {}
    for key, value in data.items():
        if key.lower() in sensitive_fields:
            if key.lower() == "account_number":
                sanitized[key] = mask_account_number(str(value))
            elif key.lower() == "email":
                sanitized[key] = mask_email(str(value))
            else:
                sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = value
    
    return sanitized


def setup_logging(name: str):
    """Setup logging for a module."""
    import logging
    
    # Configure basic logging if not already configured
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    return logging.getLogger(name)