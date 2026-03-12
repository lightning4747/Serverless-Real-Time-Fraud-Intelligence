"""PII protection and data masking service for compliance."""

import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Union

from sentinel_aml.core.config import get_settings
from sentinel_aml.core.logging import get_logger

logger = get_logger(__name__)


class PIIProtectionService:
    """Service for PII protection, masking, and redaction."""
    
    def __init__(self):
        """Initialize PII protection service."""
        self.settings = get_settings()
        
        # Define PII field patterns
        self.pii_fields = {
            'customer_name', 'beneficiary_name', 'account_holder_name',
            'account_number', 'routing_number', 'swift_code', 'iban',
            'ssn', 'tax_id', 'national_id', 'passport_number',
            'phone', 'mobile', 'telephone', 'phone_number',
            'email', 'email_address',
            'address', 'street_address', 'home_address', 'billing_address',
            'date_of_birth', 'birth_date', 'dob',
            'credit_card', 'card_number', 'cc_number'
        }
        
        # Define sensitive patterns for content scanning
        self.sensitive_patterns = {
            'ssn': re.compile(r'\b\d{3}-?\d{2}-?\d{4}\b'),
            'phone': re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),
            'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            'credit_card': re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
            'account_number': re.compile(r'\b\d{8,20}\b'),
        }
    
    def is_pii_field(self, field_name: str) -> bool:
        """Check if a field name indicates PII data."""
        return field_name.lower() in self.pii_fields
    
    def mask_account_number(self, account_number: str) -> str:
        """Mask account number showing only last 4 digits."""
        if not account_number or len(account_number) <= 4:
            return "*" * len(account_number) if account_number else ""
        
        return "*" * (len(account_number) - 4) + account_number[-4:]
    
    def mask_ssn(self, ssn: str) -> str:
        """Mask SSN showing only last 4 digits."""
        # Remove any formatting
        clean_ssn = re.sub(r'[^\d]', '', ssn)
        
        if len(clean_ssn) != 9:
            return "*" * len(ssn)  # Invalid SSN, mask completely
        
        return f"***-**-{clean_ssn[-4:]}"
    
    def mask_phone(self, phone: str) -> str:
        """Mask phone number showing only last 4 digits."""
        # Extract digits only
        digits = re.sub(r'[^\d]', '', phone)
        
        if len(digits) < 4:
            return "*" * len(phone)
        
        # Keep original formatting but replace digits
        masked = phone
        for i, char in enumerate(phone):
            if char.isdigit() and i < len(phone) - 4:
                masked = masked[:i] + '*' + masked[i+1:]
        
        return masked
    
    def mask_email(self, email: str) -> str:
        """Mask email address preserving domain."""
        if "@" not in email:
            return "*" * min(len(email), 12)
        
        local, domain = email.split("@", 1)
        
        if len(local) <= 1:
            masked_local = "*" * len(local)
        elif len(local) == 2:
            masked_local = "*" * len(local)
        else:
            # Show first and last char, mask middle with max 5 asterisks
            middle_length = len(local) - 2
            asterisk_count = min(middle_length, 5)
            masked_local = local[0] + "*" * asterisk_count + local[-1]
        
        return f"{masked_local}@{domain}"
    
    def mask_name(self, name: str) -> str:
        """Mask personal name showing only first letter of each word."""
        if not name:
            return ""
        
        words = name.split()
        masked_words = []
        
        for word in words:
            if len(word) == 1:
                masked_words.append("*")
            else:
                masked_words.append(word[0] + "*" * (len(word) - 1))
        
        return " ".join(masked_words)
    
    def mask_address(self, address: str) -> str:
        """Mask address showing only city/state information."""
        if not address:
            return ""
        
        # Simple masking - replace numbers and first part
        # Keep potential city/state at the end
        words = address.split()
        if len(words) <= 2:
            return "[REDACTED ADDRESS]"
        
        # Mask first part, keep last 2 words (likely city, state)
        masked_parts = ["***" for _ in words[:-2]]
        masked_parts.extend(words[-2:])
        
        return " ".join(masked_parts)
    
    def mask_credit_card(self, card_number: str) -> str:
        """Mask credit card number showing only last 4 digits."""
        # Remove any formatting
        digits = re.sub(r'[^\d]', '', card_number)
        
        if len(digits) < 4:
            return "*" * len(card_number)
        
        return "*" * (len(digits) - 4) + digits[-4:]
    
    def mask_field_value(self, field_name: str, value: Any) -> str:
        """Mask a field value based on field name and content."""
        if value is None:
            return ""
        
        str_value = str(value)
        field_lower = field_name.lower()
        
        # Apply specific masking based on field name
        if 'account' in field_lower and 'number' in field_lower:
            return self.mask_account_number(str_value)
        elif 'ssn' in field_lower or 'social' in field_lower:
            return self.mask_ssn(str_value)
        elif 'phone' in field_lower or 'mobile' in field_lower:
            return self.mask_phone(str_value)
        elif 'email' in field_lower:
            return self.mask_email(str_value)
        elif 'name' in field_lower:
            return self.mask_name(str_value)
        elif 'address' in field_lower:
            return self.mask_address(str_value)
        elif 'card' in field_lower or 'credit' in field_lower:
            return self.mask_credit_card(str_value)
        else:
            # Generic masking for unknown PII
            if len(str_value) <= 4:
                return "*" * len(str_value)
            else:
                return str_value[:2] + "*" * (len(str_value) - 4) + str_value[-2:]
    
    def mask_pii_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mask PII fields in a data dictionary."""
        if not self.settings.pii_masking_enabled:
            return data
        
        masked_data = {}
        
        for field_name, value in data.items():
            if self.is_pii_field(field_name) and value is not None:
                masked_data[field_name] = self.mask_field_value(field_name, value)
                logger.debug(f"Masked PII field: {field_name}")
            else:
                masked_data[field_name] = value
        
        return masked_data
    
    def redact_sensitive_fields(
        self, 
        data: Dict[str, Any], 
        redaction_level: str = 'partial'
    ) -> Dict[str, Any]:
        """Redact sensitive fields with different levels of redaction.
        
        Args:
            data: Data dictionary to redact
            redaction_level: 'partial' (mask), 'full' (remove), or 'hash' (hash values)
        """
        redacted_data = {}
        
        for field_name, value in data.items():
            if self.is_pii_field(field_name) and value is not None:
                if redaction_level == 'full':
                    redacted_data[field_name] = "[REDACTED]"
                elif redaction_level == 'hash':
                    # Use a simple hash for demonstration
                    import hashlib
                    hash_value = hashlib.sha256(str(value).encode()).hexdigest()[:16]
                    redacted_data[field_name] = f"[HASH:{hash_value}]"
                else:  # partial
                    redacted_data[field_name] = self.mask_field_value(field_name, value)
                
                logger.debug(f"Redacted field {field_name} with level {redaction_level}")
            else:
                redacted_data[field_name] = value
        
        return redacted_data
    
    def scan_for_pii_patterns(self, text: str) -> Dict[str, List[str]]:
        """Scan text for PII patterns and return findings."""
        findings = {}
        
        for pattern_name, pattern in self.sensitive_patterns.items():
            matches = pattern.findall(text)
            if matches:
                findings[pattern_name] = matches
        
        return findings
    
    def sanitize_for_logging(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize data for safe logging by masking PII."""
        return self.mask_pii_data(data)
    
    def create_pii_audit_record(
        self, 
        operation: str, 
        field_names: List[str], 
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create audit record for PII access."""
        from datetime import datetime, timezone
        
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'operation': operation,
            'pii_fields_accessed': field_names,
            'user_id': user_id,
            'service': 'sentinel-aml-pii-protection'
        }


@lru_cache()
def get_pii_service() -> PIIProtectionService:
    """Get cached PII protection service instance."""
    return PIIProtectionService()


def mask_pii_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function to mask PII data."""
    service = get_pii_service()
    return service.mask_pii_data(data)


def redact_sensitive_fields(
    data: Dict[str, Any], 
    redaction_level: str = 'partial'
) -> Dict[str, Any]:
    """Convenience function to redact sensitive fields."""
    service = get_pii_service()
    return service.redact_sensitive_fields(data, redaction_level)