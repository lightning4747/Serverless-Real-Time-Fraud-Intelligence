"""Unit tests for core utility functions."""

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from sentinel_aml.core.utils import (
    generate_correlation_id,
    generate_transaction_id,
    generate_case_id,
    hash_pii,
    mask_account_number,
    mask_email,
    validate_account_id,
    validate_transaction_amount,
    validate_currency_code,
    is_high_risk_jurisdiction,
    calculate_velocity_score,
    detect_round_dollar_pattern,
    format_currency,
    sanitize_for_logging
)
from sentinel_aml.core.exceptions import ValidationError


class TestIDGeneration:
    """Test ID generation functions."""
    
    def test_generate_correlation_id(self):
        """Test correlation ID generation."""
        id1 = generate_correlation_id()
        id2 = generate_correlation_id()
        
        assert len(id1) == 36  # UUID format
        assert id1 != id2  # Should be unique
        assert "-" in id1  # UUID format
    
    def test_generate_transaction_id(self):
        """Test transaction ID generation."""
        id1 = generate_transaction_id()
        id2 = generate_transaction_id()
        
        assert id1.startswith("TXN-")
        assert id1 != id2  # Should be unique
        assert len(id1) > 15  # Should have timestamp and unique part
    
    def test_generate_case_id(self):
        """Test case ID generation."""
        id1 = generate_case_id()
        id2 = generate_case_id()
        
        assert id1.startswith("CASE-")
        assert id1 != id2  # Should be unique
        assert len(id1) > 15  # Should have date and unique part


class TestPIIHandling:
    """Test PII handling functions."""
    
    def test_hash_pii(self):
        """Test PII hashing."""
        data = "sensitive_data"
        hash1 = hash_pii(data)
        hash2 = hash_pii(data)
        
        assert hash1 == hash2  # Same input should produce same hash
        assert hash1 != data  # Should be different from original
        assert len(hash1) == 64  # SHA256 hex length
    
    def test_hash_pii_with_salt(self):
        """Test PII hashing with custom salt."""
        data = "sensitive_data"
        salt1 = "salt1"
        salt2 = "salt2"
        
        hash1 = hash_pii(data, salt1)
        hash2 = hash_pii(data, salt2)
        
        assert hash1 != hash2  # Different salts should produce different hashes
    
    def test_mask_account_number(self):
        """Test account number masking."""
        # Long account number
        account = "1234567890123456"
        masked = mask_account_number(account)
        assert masked == "************3456"
        
        # Short account number
        short_account = "123"
        masked_short = mask_account_number(short_account)
        assert masked_short == "***"
        
        # Exactly 4 characters
        four_char = "1234"
        masked_four = mask_account_number(four_char)
        assert masked_four == "1234"  # Should show last 4
    
    def test_mask_email(self):
        """Test email masking."""
        # Normal email
        email = "john.doe@example.com"
        masked = mask_email(email)
        assert masked == "j*****e@example.com"
        
        # Short local part
        short_email = "ab@example.com"
        masked_short = mask_email(short_email)
        assert masked_short == "**@example.com"
        
        # Invalid email (no @)
        invalid_email = "notanemail"
        masked_invalid = mask_email(invalid_email)
        assert masked_invalid == "*" * len(invalid_email)


class TestValidation:
    """Test validation functions."""
    
    def test_validate_account_id(self):
        """Test account ID validation."""
        # Valid account IDs
        assert validate_account_id("ACC123456789")
        assert validate_account_id("12345678")
        assert validate_account_id("ABCDEFGHIJ1234567890")
        
        # Invalid account IDs
        assert not validate_account_id("123")  # Too short
        assert not validate_account_id("A" * 25)  # Too long
        assert not validate_account_id("ACC-123")  # Contains hyphen
        assert not validate_account_id("ACC 123")  # Contains space
    
    def test_validate_transaction_amount(self):
        """Test transaction amount validation."""
        # Valid amounts
        assert validate_transaction_amount("100.50") == Decimal("100.50")
        assert validate_transaction_amount(100.50) == Decimal("100.50")
        assert validate_transaction_amount(Decimal("100.50")) == Decimal("100.50")
        
        # Precision handling
        assert validate_transaction_amount("100.567") == Decimal("100.57")
        
        # Invalid amounts
        with pytest.raises(ValidationError):
            validate_transaction_amount("-100.00")  # Negative
        
        with pytest.raises(ValidationError):
            validate_transaction_amount("9999999999.99")  # Too large
        
        with pytest.raises(ValidationError):
            validate_transaction_amount("invalid")  # Not a number
    
    def test_validate_currency_code(self):
        """Test currency code validation."""
        # Valid currencies
        assert validate_currency_code("USD") == "USD"
        assert validate_currency_code("eur") == "EUR"  # Should uppercase
        assert validate_currency_code("GBP") == "GBP"
        
        # Invalid currencies
        with pytest.raises(ValidationError):
            validate_currency_code("INVALID")
        
        with pytest.raises(ValidationError):
            validate_currency_code("US")  # Too short
    
    def test_is_high_risk_jurisdiction(self):
        """Test high-risk jurisdiction detection."""
        # High-risk countries
        assert is_high_risk_jurisdiction("IR")  # Iran
        assert is_high_risk_jurisdiction("KP")  # North Korea
        assert is_high_risk_jurisdiction("ir")  # Case insensitive
        
        # Low-risk countries
        assert not is_high_risk_jurisdiction("US")
        assert not is_high_risk_jurisdiction("GB")
        assert not is_high_risk_jurisdiction("CA")


class TestRiskCalculation:
    """Test risk calculation functions."""
    
    def test_calculate_velocity_score_empty(self):
        """Test velocity score with empty transactions."""
        assert calculate_velocity_score([]) == 0.0
    
    def test_calculate_velocity_score_single(self):
        """Test velocity score with single transaction."""
        transactions = [{"timestamp": 1000}]
        assert calculate_velocity_score(transactions) == 0.0
    
    def test_calculate_velocity_score_normal(self):
        """Test velocity score with normal frequency."""
        base_time = 1000
        transactions = [
            {"timestamp": base_time},
            {"timestamp": base_time + 3600},  # 1 hour later
            {"timestamp": base_time + 7200},  # 2 hours later
        ]
        score = calculate_velocity_score(transactions)
        assert 0.0 <= score <= 1.0
        assert score < 0.5  # Should be low for normal frequency
    
    def test_calculate_velocity_score_high(self):
        """Test velocity score with high frequency."""
        base_time = 1000
        transactions = []
        
        # 20 transactions in 1 hour (very high frequency)
        for i in range(20):
            transactions.append({"timestamp": base_time + (i * 180)})  # Every 3 minutes
        
        score = calculate_velocity_score(transactions)
        assert score > 0.5  # Should be high for suspicious frequency
    
    def test_detect_round_dollar_pattern_empty(self):
        """Test round dollar detection with empty amounts."""
        assert detect_round_dollar_pattern([]) == 0.0
    
    def test_detect_round_dollar_pattern_all_round(self):
        """Test round dollar detection with all round amounts."""
        amounts = [100.00, 200.00, 300.00, 500.00]
        score = detect_round_dollar_pattern(amounts)
        assert score >= 0.8  # High score for all round amounts
    
    def test_detect_round_dollar_pattern_mixed(self):
        """Test round dollar detection with mixed amounts."""
        amounts = [100.00, 150.50, 200.00, 175.25]
        score = detect_round_dollar_pattern(amounts)
        assert 0.0 < score < 0.8  # Medium score for mixed amounts
    
    def test_detect_round_dollar_pattern_no_round(self):
        """Test round dollar detection with no round amounts."""
        amounts = [100.50, 150.75, 200.25, 175.99]
        score = detect_round_dollar_pattern(amounts)
        assert score <= 0.2  # Low score for no round amounts


class TestFormatting:
    """Test formatting functions."""
    
    def test_format_currency_usd(self):
        """Test USD currency formatting."""
        assert format_currency(1234.56, "USD") == "$1,234.56"
        assert format_currency(1000000, "USD") == "$1,000,000.00"
    
    def test_format_currency_eur(self):
        """Test EUR currency formatting."""
        assert format_currency(1234.56, "EUR") == "€1,234.56"
    
    def test_format_currency_gbp(self):
        """Test GBP currency formatting."""
        assert format_currency(1234.56, "GBP") == "£1,234.56"
    
    def test_format_currency_other(self):
        """Test other currency formatting."""
        assert format_currency(1234.56, "JPY") == "1,234.56 JPY"
    
    def test_sanitize_for_logging(self):
        """Test data sanitization for logging."""
        data = {
            "account_number": "1234567890",
            "amount": 1000.00,
            "ssn": "123-45-6789",
            "email": "user@example.com",
            "transaction_id": "TXN123"
        }
        
        sanitized = sanitize_for_logging(data)
        
        assert sanitized["account_number"] == "******7890"
        assert sanitized["amount"] == 1000.00  # Not sensitive
        assert sanitized["ssn"] == "[REDACTED]"
        assert sanitized["email"] == "u***@example.com"
        assert sanitized["transaction_id"] == "TXN123"  # Not sensitive