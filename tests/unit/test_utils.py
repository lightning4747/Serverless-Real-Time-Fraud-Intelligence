"""Unit tests for utility functions."""

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from sentinel_aml.core.utils import (
    validate_account_id,
    validate_transaction_amount,
    validate_currency_code,
    is_high_risk_jurisdiction,
    calculate_velocity_score,
    detect_round_dollar_pattern,
    format_currency,
    mask_account_number,
    mask_email,
    hash_pii,
    sanitize_for_logging,
    generate_correlation_id,
    generate_transaction_id,
    generate_case_id
)
from sentinel_aml.core.exceptions import ValidationError


class TestAccountIdValidation:
    """Test account ID validation function."""
    
    def test_valid_account_ids(self):
        """Test valid account ID formats."""
        valid_ids = [
            "ACC12345",      # 8 characters
            "ACC123456789",  # 12 characters
            "A" * 20,        # 20 characters (maximum)
            "12345678",      # All numeric
            "ABCDEFGH",      # All alphabetic
            "acc123456789",  # Lowercase
            "MixedCase123"   # Mixed case
        ]
        
        for account_id in valid_ids:
            assert validate_account_id(account_id) is True
    
    def test_invalid_account_ids(self):
        """Test invalid account ID formats."""
        invalid_ids = [
            "ACC123",        # Too short (7 characters)
            "A" * 21,        # Too long (21 characters)
            "ACC-123456",    # Contains hyphen
            "ACC 123456",    # Contains space
            "ACC@123456",    # Contains special character
            "",              # Empty string
            "ACC123.456",    # Contains period
            "ACC123_456"     # Contains underscore
        ]
        
        for account_id in invalid_ids:
            assert validate_account_id(account_id) is False


class TestTransactionAmountValidation:
    """Test transaction amount validation function."""
    
    def test_valid_amounts(self):
        """Test valid transaction amounts."""
        valid_amounts = [
            ("0", Decimal("0.00")),
            ("0.01", Decimal("0.01")),
            ("100", Decimal("100.00")),
            ("100.50", Decimal("100.50")),
            ("999999999.99", Decimal("999999999.99")),
            (100, Decimal("100.00")),
            (100.50, Decimal("100.50")),
            (Decimal("100.50"), Decimal("100.50"))
        ]
        
        for input_amount, expected in valid_amounts:
            result = validate_transaction_amount(input_amount)
            assert result == expected
    
    def test_amount_rounding(self):
        """Test amount rounding to 2 decimal places."""
        test_cases = [
            ("100.123", Decimal("100.12")),
            ("100.125", Decimal("100.13")),  # Banker's rounding
            ("100.126", Decimal("100.13")),
            ("100.999", Decimal("101.00")),
            ("0.001", Decimal("0.00")),
            ("0.009", Decimal("0.01"))
        ]
        
        for input_amount, expected in test_cases:
            result = validate_transaction_amount(input_amount)
            assert result == expected
    
    def test_invalid_amounts(self):
        """Test invalid transaction amounts."""
        invalid_amounts = [
            "-100",           # Negative
            "-0.01",          # Negative small
            "1000000000",     # Too large
            "invalid",        # Non-numeric string
            None,             # None value
            [],               # List
            {}                # Dict
        ]
        
        for invalid_amount in invalid_amounts:
            with pytest.raises(ValueError):
                validate_transaction_amount(invalid_amount)
    
    def test_scientific_notation(self):
        """Test scientific notation handling."""
        scientific_amounts = [
            ("1e2", Decimal("100.00")),      # 100
            ("1.5e3", Decimal("1500.00")),   # 1500
            ("1.23e-1", Decimal("0.12")),    # 0.123 rounded to 0.12
            ("5e-3", Decimal("0.01"))        # 0.005 rounded to 0.01
        ]
        
        for input_amount, expected in scientific_amounts:
            result = validate_transaction_amount(input_amount)
            assert result == expected


class TestCurrencyCodeValidation:
    """Test currency code validation function."""
    
    def test_valid_currencies(self):
        """Test valid currency codes."""
        valid_currencies = [
            ("USD", "USD"),
            ("EUR", "EUR"),
            ("GBP", "GBP"),
            ("JPY", "JPY"),
            ("usd", "USD"),  # Lowercase conversion
            ("eur", "EUR"),
            ("gbp", "GBP")
        ]
        
        for input_currency, expected in valid_currencies:
            result = validate_currency_code(input_currency)
            assert result == expected
    
    def test_invalid_currencies(self):
        """Test invalid currency codes."""
        invalid_currencies = [
            "INVALID",
            "US",          # Too short
            "USDD",        # Too long
            "",            # Empty
            "123",         # Numeric
            "XYZ"          # Not in valid list
        ]
        
        for invalid_currency in invalid_currencies:
            with pytest.raises(ValueError, match="Invalid currency code"):
                validate_currency_code(invalid_currency)


class TestHighRiskJurisdiction:
    """Test high-risk jurisdiction checking."""
    
    def test_high_risk_countries(self):
        """Test high-risk country identification."""
        high_risk_countries = ["IR", "KP", "MM"]
        
        for country in high_risk_countries:
            assert is_high_risk_jurisdiction(country) is True
            assert is_high_risk_jurisdiction(country.lower()) is True
    
    def test_low_risk_countries(self):
        """Test low-risk country identification."""
        low_risk_countries = ["US", "GB", "CA", "DE", "FR", "AU"]
        
        for country in low_risk_countries:
            assert is_high_risk_jurisdiction(country) is False
            assert is_high_risk_jurisdiction(country.lower()) is False


class TestVelocityScore:
    """Test velocity score calculation."""
    
    def test_empty_transactions(self):
        """Test velocity score with empty transaction list."""
        assert calculate_velocity_score([]) == 0.0
    
    def test_single_transaction(self):
        """Test velocity score with single transaction."""
        transactions = [{"timestamp": 1000}]
        assert calculate_velocity_score(transactions) == 0.0
    
    def test_normal_velocity(self):
        """Test normal transaction velocity."""
        # 2 transactions over 1 hour (2 txns/hour)
        base_time = 1000
        transactions = [
            {"timestamp": base_time},
            {"timestamp": base_time + 3600}  # 1 hour later
        ]
        score = calculate_velocity_score(transactions)
        assert score == 0.1  # Low velocity
    
    def test_high_velocity(self):
        """Test high transaction velocity."""
        # 20 transactions in 1 hour (20 txns/hour)
        base_time = 1000
        transactions = [
            {"timestamp": base_time + i * 180}  # Every 3 minutes
            for i in range(20)
        ]
        score = calculate_velocity_score(transactions)
        assert score >= 0.8  # High velocity
    
    def test_simultaneous_transactions(self):
        """Test simultaneous transactions (suspicious)."""
        # Multiple transactions at same time
        base_time = 1000
        transactions = [
            {"timestamp": base_time},
            {"timestamp": base_time},
            {"timestamp": base_time}
        ]
        score = calculate_velocity_score(transactions)
        assert score == 1.0  # Maximum suspicion


class TestRoundDollarPattern:
    """Test round dollar pattern detection."""
    
    def test_no_amounts(self):
        """Test with empty amount list."""
        assert detect_round_dollar_pattern([]) == 0.0
    
    def test_all_round_amounts(self):
        """Test with all round dollar amounts."""
        amounts = [100, 200, 500, 1000, 2000]
        score = detect_round_dollar_pattern(amounts)
        assert score == 0.9  # High suspicion
    
    def test_mixed_amounts(self):
        """Test with mixed round and non-round amounts."""
        amounts = [100, 123.45, 200, 567.89, 500]  # 3/5 are round (60%)
        score = detect_round_dollar_pattern(amounts)
        assert score == 0.6
    
    def test_no_round_amounts(self):
        """Test with no round amounts."""
        amounts = [123.45, 567.89, 234.56, 789.12]
        score = detect_round_dollar_pattern(amounts)
        assert score == 0.1  # Low suspicion
    
    def test_decimal_amounts(self):
        """Test with Decimal amounts."""
        amounts = [Decimal("100.00"), Decimal("123.45"), Decimal("200.00")]
        score = detect_round_dollar_pattern(amounts)
        assert score == 0.6  # 2/3 are round


class TestCurrencyFormatting:
    """Test currency formatting function."""
    
    def test_usd_formatting(self):
        """Test USD currency formatting."""
        test_cases = [
            (100, "$100.00"),
            (1234.56, "$1,234.56"),
            (1000000, "$1,000,000.00"),
            (0.01, "$0.01")
        ]
        
        for amount, expected in test_cases:
            result = format_currency(amount, "USD")
            assert result == expected
    
    def test_other_currencies(self):
        """Test other currency formatting."""
        assert format_currency(100, "EUR") == "€100.00"
        assert format_currency(100, "GBP") == "£100.00"
        assert format_currency(100, "JPY") == "100.00 JPY"
    
    def test_decimal_input(self):
        """Test with Decimal input."""
        amount = Decimal("1234.56")
        result = format_currency(amount, "USD")
        assert result == "$1,234.56"


class TestDataMasking:
    """Test data masking functions."""
    
    def test_account_number_masking(self):
        """Test account number masking."""
        test_cases = [
            ("1234567890", "******7890"),
            ("1234", "****"),
            ("12", "**"),
            ("", ""),
            ("123456789012345", "***********2345")
        ]
        
        for account_number, expected in test_cases:
            result = mask_account_number(account_number)
            assert result == expected
    
    def test_email_masking(self):
        """Test email masking."""
        test_cases = [
            ("john.doe@example.com", "j*****e@example.com"),
            ("a@example.com", "*@example.com"),
            ("ab@example.com", "**@example.com"),
            ("test@example.com", "t**t@example.com"),
            ("invalid-email", "************")  # No @ symbol
        ]
        
        for email, expected in test_cases:
            result = mask_email(email)
            assert result == expected


class TestPIIHashing:
    """Test PII hashing function."""
    
    def test_consistent_hashing(self):
        """Test that hashing is consistent."""
        data = "sensitive_data"
        hash1 = hash_pii(data)
        hash2 = hash_pii(data)
        assert hash1 == hash2
    
    def test_different_data_different_hash(self):
        """Test that different data produces different hashes."""
        hash1 = hash_pii("data1")
        hash2 = hash_pii("data2")
        assert hash1 != hash2
    
    def test_salt_effect(self):
        """Test that different salts produce different hashes."""
        data = "sensitive_data"
        hash1 = hash_pii(data, "salt1")
        hash2 = hash_pii(data, "salt2")
        assert hash1 != hash2
    
    def test_hash_length(self):
        """Test that hash has expected length."""
        data = "test_data"
        hash_result = hash_pii(data)
        assert len(hash_result) == 64  # SHA-256 produces 64-character hex string


class TestDataSanitization:
    """Test data sanitization for logging."""
    
    def test_sensitive_field_sanitization(self):
        """Test that sensitive fields are sanitized."""
        data = {
            "account_number": "1234567890",
            "email": "john@example.com",
            "name": "John Doe",
            "amount": 1000.00,
            "transaction_id": "TXN123"
        }
        
        sanitized = sanitize_for_logging(data)
        
        assert sanitized["account_number"] == "******7890"
        assert sanitized["email"] == "j**n@example.com"
        assert sanitized["name"] == "[REDACTED]"
        assert sanitized["amount"] == 1000.00  # Not sensitive
        assert sanitized["transaction_id"] == "TXN123"  # Not sensitive
    
    def test_case_insensitive_sanitization(self):
        """Test that sanitization is case-insensitive."""
        data = {
            "ACCOUNT_NUMBER": "1234567890",
            "Email": "john@example.com",
            "Customer_Name": "John Doe"
        }
        
        sanitized = sanitize_for_logging(data)
        
        assert sanitized["ACCOUNT_NUMBER"] == "******7890"
        assert sanitized["Email"] == "j**n@example.com"
        assert sanitized["Customer_Name"] == "[REDACTED]"


class TestIDGeneration:
    """Test ID generation functions."""
    
    def test_correlation_id_generation(self):
        """Test correlation ID generation."""
        id1 = generate_correlation_id()
        id2 = generate_correlation_id()
        
        # Should be unique
        assert id1 != id2
        
        # Should be valid UUIDs (36 characters with hyphens)
        assert len(id1) == 36
        assert len(id2) == 36
        assert "-" in id1
        assert "-" in id2
    
    def test_transaction_id_generation(self):
        """Test transaction ID generation."""
        id1 = generate_transaction_id()
        id2 = generate_transaction_id()
        
        # Should be unique
        assert id1 != id2
        
        # Should start with TXN-
        assert id1.startswith("TXN-")
        assert id2.startswith("TXN-")
        
        # Should contain timestamp
        assert len(id1) > 20  # TXN- + timestamp + unique part
        assert len(id2) > 20
    
    def test_case_id_generation(self):
        """Test case ID generation."""
        id1 = generate_case_id()
        id2 = generate_case_id()
        
        # Should be unique
        assert id1 != id2
        
        # Should start with CASE-
        assert id1.startswith("CASE-")
        assert id2.startswith("CASE-")
        
        # Should contain date
        assert len(id1) > 15  # CASE- + date + unique part
        assert len(id2) > 15
    
    def test_id_format_consistency(self):
        """Test that generated IDs follow consistent format."""
        # Generate multiple IDs and check format consistency
        correlation_ids = [generate_correlation_id() for _ in range(10)]
        transaction_ids = [generate_transaction_id() for _ in range(10)]
        case_ids = [generate_case_id() for _ in range(10)]
        
        # All correlation IDs should be valid UUIDs
        for cid in correlation_ids:
            assert len(cid) == 36
            assert cid.count("-") == 4
        
        # All transaction IDs should follow TXN-YYYYMMDDHHMMSS-XXXXXXXX format
        for tid in transaction_ids:
            parts = tid.split("-")
            assert len(parts) == 3
            assert parts[0] == "TXN"
            assert len(parts[1]) == 14  # YYYYMMDDHHMMSS
            assert len(parts[2]) == 8   # 8-character unique ID
        
        # All case IDs should follow CASE-YYYYMMDD-XXXXXXXX format
        for cid in case_ids:
            parts = cid.split("-")
            assert len(parts) == 3
            assert parts[0] == "CASE"
            assert len(parts[1]) == 8   # YYYYMMDD
            assert len(parts[2]) == 8   # 8-character unique ID