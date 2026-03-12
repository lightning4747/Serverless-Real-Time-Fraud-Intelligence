"""Unit tests for PII protection and masking functionality."""

import pytest

from sentinel_aml.security.pii_protection import PIIProtectionService, mask_pii_data, redact_sensitive_fields


class TestPIIProtectionService:
    """Test PII protection service functionality."""
    
    @pytest.fixture
    def pii_service(self):
        """Create PII protection service for testing."""
        return PIIProtectionService()
    
    def test_is_pii_field_detection(self, pii_service):
        """Test PII field detection."""
        # Should detect PII fields
        assert pii_service.is_pii_field("customer_name")
        assert pii_service.is_pii_field("account_number")
        assert pii_service.is_pii_field("email")
        assert pii_service.is_pii_field("ssn")
        
        # Should not detect non-PII fields
        assert not pii_service.is_pii_field("transaction_id")
        assert not pii_service.is_pii_field("amount")
        assert not pii_service.is_pii_field("currency")
    
    def test_mask_account_number(self, pii_service):
        """Test account number masking."""
        # Normal account number
        assert pii_service.mask_account_number("1234567890") == "******7890"
        
        # Short account number
        assert pii_service.mask_account_number("1234") == "****"
        
        # Very short
        assert pii_service.mask_account_number("12") == "**"
        
        # Empty
        assert pii_service.mask_account_number("") == ""
    
    def test_mask_ssn(self, pii_service):
        """Test SSN masking."""
        # Formatted SSN
        assert pii_service.mask_ssn("123-45-6789") == "***-**-6789"
        
        # Unformatted SSN
        assert pii_service.mask_ssn("123456789") == "***-**-6789"
        
        # Invalid SSN
        assert pii_service.mask_ssn("12345") == "*****"
    
    def test_mask_phone(self, pii_service):
        """Test phone number masking."""
        # Formatted phone
        result = pii_service.mask_phone("(555) 123-4567")
        assert result.endswith("4567")
        assert "*" in result
        
        # Unformatted phone
        result = pii_service.mask_phone("5551234567")
        assert result.endswith("4567")
        
        # Short phone
        assert pii_service.mask_phone("123") == "***"
    
    def test_mask_email(self, pii_service):
        """Test email masking."""
        # Normal email
        assert pii_service.mask_email("john.doe@example.com") == "j*****e@example.com"
        
        # Short local part
        assert pii_service.mask_email("ab@example.com") == "**@example.com"
        
        # Single char local part
        assert pii_service.mask_email("a@example.com") == "*@example.com"
        
        # Invalid email
        assert pii_service.mask_email("notanemail") == "************"
    
    def test_mask_name(self, pii_service):
        """Test name masking."""
        # Full name
        assert pii_service.mask_name("John Doe") == "J*** D**"
        
        # Single name
        assert pii_service.mask_name("John") == "J***"
        
        # Single character
        assert pii_service.mask_name("J") == "*"
        
        # Empty
        assert pii_service.mask_name("") == ""
    
    def test_mask_address(self, pii_service):
        """Test address masking."""
        # Full address
        result = pii_service.mask_address("123 Main St, New York, NY")
        assert "New York" in result
        assert "NY" in result
        assert "***" in result
        
        # Short address
        assert pii_service.mask_address("Main St") == "[REDACTED ADDRESS]"
    
    def test_mask_credit_card(self, pii_service):
        """Test credit card masking."""
        # Formatted card
        assert pii_service.mask_credit_card("1234-5678-9012-3456") == "************3456"
        
        # Unformatted card
        assert pii_service.mask_credit_card("1234567890123456") == "************3456"
        
        # Short number
        assert pii_service.mask_credit_card("123") == "***"
    
    def test_mask_field_value(self, pii_service):
        """Test field-specific masking."""
        # Account number field
        assert pii_service.mask_field_value("account_number", "1234567890") == "******7890"
        
        # Email field
        assert pii_service.mask_field_value("email", "test@example.com") == "t**t@example.com"
        
        # Name field
        assert pii_service.mask_field_value("customer_name", "John Doe") == "J*** D**"
        
        # Unknown PII field (generic masking)
        result = pii_service.mask_field_value("unknown_pii", "sensitive_data")
        assert result.startswith("se")
        assert result.endswith("ta")
        assert "*" in result
    
    def test_mask_pii_data(self, pii_service):
        """Test masking PII data in dictionary."""
        data = {
            "transaction_id": "TXN-123",
            "customer_name": "John Doe",
            "account_number": "1234567890",
            "amount": 1000.50,
            "email": "john@example.com"
        }
        
        masked = pii_service.mask_pii_data(data)
        
        # Non-PII should remain unchanged
        assert masked["transaction_id"] == "TXN-123"
        assert masked["amount"] == 1000.50
        
        # PII should be masked
        assert masked["customer_name"] == "J*** D**"
        assert masked["account_number"] == "******7890"
        assert masked["email"] == "j**n@example.com"  # Shows first and last char of local part
    
    def test_redact_sensitive_fields_partial(self, pii_service):
        """Test partial redaction (masking)."""
        data = {
            "customer_name": "John Doe",
            "account_number": "1234567890",
            "amount": 1000.50
        }
        
        redacted = pii_service.redact_sensitive_fields(data, redaction_level='partial')
        
        assert redacted["amount"] == 1000.50  # Non-PII unchanged
        assert redacted["customer_name"] == "J*** D**"  # PII masked
        assert redacted["account_number"] == "******7890"
    
    def test_redact_sensitive_fields_full(self, pii_service):
        """Test full redaction (removal)."""
        data = {
            "customer_name": "John Doe",
            "account_number": "1234567890",
            "amount": 1000.50
        }
        
        redacted = pii_service.redact_sensitive_fields(data, redaction_level='full')
        
        assert redacted["amount"] == 1000.50  # Non-PII unchanged
        assert redacted["customer_name"] == "[REDACTED]"  # PII removed
        assert redacted["account_number"] == "[REDACTED]"
    
    def test_redact_sensitive_fields_hash(self, pii_service):
        """Test hash redaction."""
        data = {
            "customer_name": "John Doe",
            "account_number": "1234567890",
            "amount": 1000.50
        }
        
        redacted = pii_service.redact_sensitive_fields(data, redaction_level='hash')
        
        assert redacted["amount"] == 1000.50  # Non-PII unchanged
        assert redacted["customer_name"].startswith("[HASH:")  # PII hashed
        assert redacted["account_number"].startswith("[HASH:")
    
    def test_scan_for_pii_patterns(self, pii_service):
        """Test scanning text for PII patterns."""
        text = "Contact John at 555-123-4567 or john@example.com. SSN: 123-45-6789"
        
        findings = pii_service.scan_for_pii_patterns(text)
        
        assert "phone" in findings
        assert "email" in findings
        assert "ssn" in findings
        
        assert "555-123-4567" in findings["phone"]
        assert "john@example.com" in findings["email"]
        assert "123-45-6789" in findings["ssn"]
    
    def test_sanitize_for_logging(self, pii_service):
        """Test data sanitization for logging."""
        data = {
            "transaction_id": "TXN-123",
            "customer_name": "John Doe",
            "account_number": "1234567890",
            "amount": 1000.50
        }
        
        sanitized = pii_service.sanitize_for_logging(data)
        
        # Should be same as mask_pii_data
        expected = pii_service.mask_pii_data(data)
        assert sanitized == expected
    
    def test_create_pii_audit_record(self, pii_service):
        """Test PII audit record creation."""
        record = pii_service.create_pii_audit_record(
            operation="decrypt",
            field_names=["customer_name", "account_number"],
            user_id="user123"
        )
        
        assert record["operation"] == "decrypt"
        assert record["pii_fields_accessed"] == ["customer_name", "account_number"]
        assert record["user_id"] == "user123"
        assert record["service"] == "sentinel-aml-pii-protection"
        assert "timestamp" in record
    
    def test_pii_masking_disabled(self, pii_service):
        """Test behavior when PII masking is disabled."""
        # Mock settings to disable PII masking
        pii_service.settings.pii_masking_enabled = False
        
        data = {
            "customer_name": "John Doe",
            "account_number": "1234567890"
        }
        
        masked = pii_service.mask_pii_data(data)
        
        # Should return original data unchanged
        assert masked == data


class TestPIIProtectionConvenienceFunctions:
    """Test convenience functions for PII protection."""
    
    def test_mask_pii_data_function(self):
        """Test mask_pii_data convenience function."""
        data = {
            "customer_name": "John Doe",
            "account_number": "1234567890",
            "amount": 1000.50
        }
        
        masked = mask_pii_data(data)
        
        assert masked["amount"] == 1000.50  # Non-PII unchanged
        assert masked["customer_name"] != "John Doe"  # PII masked
        assert masked["account_number"] != "1234567890"
    
    def test_redact_sensitive_fields_function(self):
        """Test redact_sensitive_fields convenience function."""
        data = {
            "customer_name": "John Doe",
            "account_number": "1234567890",
            "amount": 1000.50
        }
        
        redacted = redact_sensitive_fields(data, redaction_level='full')
        
        assert redacted["amount"] == 1000.50  # Non-PII unchanged
        assert redacted["customer_name"] == "[REDACTED]"  # PII redacted
        assert redacted["account_number"] == "[REDACTED]"