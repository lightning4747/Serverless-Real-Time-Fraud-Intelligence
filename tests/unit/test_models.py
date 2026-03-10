"""Unit tests for data models."""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from pydantic import ValidationError

from sentinel_aml.data.models import (
    Account, 
    Transaction, 
    TransactionEdge,
    AccountType,
    TransactionType,
    RiskLevel
)


class TestAccount:
    """Test Account model."""
    
    def test_valid_account_creation(self, sample_account):
        """Test creating a valid account."""
        assert sample_account.account_id == "ACC123456789"
        assert sample_account.customer_name == "John Doe"
        assert sample_account.account_type == AccountType.CHECKING
        assert sample_account.risk_score == 0.2
    
    def test_invalid_account_id(self):
        """Test account with invalid ID format."""
        with pytest.raises(ValidationError):
            Account(
                account_id="123",  # Too short
                customer_name="John Doe",
                account_type="checking"
            )
    
    def test_invalid_currency(self):
        """Test account with invalid currency."""
        with pytest.raises(ValidationError):
            Account(
                account_id="ACC123456789",
                customer_name="John Doe", 
                account_type="checking",
                currency="INVALID"
            )
    
    def test_country_code_validation(self):
        """Test country code validation."""
        # Valid country code
        account = Account(
            account_id="ACC123456789",
            customer_name="John Doe",
            account_type="checking",
            country_code="US"
        )
        assert account.country_code == "US"
        
        # Invalid country code (too long)
        with pytest.raises(ValidationError):
            Account(
                account_id="ACC123456789",
                customer_name="John Doe",
                account_type="checking",
                country_code="USA"
            )


class TestTransaction:
    """Test Transaction model."""
    
    def test_valid_transaction_creation(self, sample_transaction):
        """Test creating a valid transaction."""
        assert sample_transaction.amount == Decimal("1500.00")
        assert sample_transaction.transaction_type == TransactionType.TRANSFER
        assert sample_transaction.currency == "USD"
    
    def test_negative_amount_validation(self):
        """Test that negative amounts are rejected."""
        with pytest.raises(ValidationError):
            Transaction(
                amount=Decimal("-100.00"),
                transaction_type="deposit",
                currency="USD"
            )
    
    def test_amount_precision(self):
        """Test amount precision handling."""
        transaction = Transaction(
            amount="1234.567",  # More than 2 decimal places
            transaction_type="deposit",
            currency="USD"
        )
        # Should be rounded to 2 decimal places
        assert transaction.amount == Decimal("1234.57")
    
    def test_large_amount_validation(self):
        """Test very large amount validation."""
        with pytest.raises(ValidationError):
            Transaction(
                amount="9999999999.99",  # Exceeds maximum
                transaction_type="deposit",
                currency="USD"
            )
    
    def test_currency_validation(self):
        """Test currency code validation."""
        # Valid currency
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            currency="EUR"
        )
        assert transaction.currency == "EUR"
        
        # Invalid currency
        with pytest.raises(ValidationError):
            Transaction(
                amount="100.00",
                transaction_type="deposit",
                currency="INVALID"
            )


class TestTransactionEdge:
    """Test TransactionEdge model."""
    
    def test_valid_edge_creation(self, sample_transaction_edge):
        """Test creating a valid transaction edge."""
        assert sample_transaction_edge.from_account_id == "ACC123456789"
        assert sample_transaction_edge.to_account_id == "ACC987654321"
        assert sample_transaction_edge.amount == Decimal("1500.00")
    
    def test_edge_with_transaction_data(self, sample_transaction):
        """Test edge creation with transaction data."""
        edge = TransactionEdge(
            from_account_id="ACC123456789",
            to_account_id="ACC987654321",
            transaction_id=sample_transaction.transaction_id,
            amount=sample_transaction.amount,
            timestamp=sample_transaction.timestamp,
            transaction_type=sample_transaction.transaction_type
        )
        
        assert edge.transaction_id == sample_transaction.transaction_id
        assert edge.amount == sample_transaction.amount
        assert edge.transaction_type == sample_transaction.transaction_type


class TestEnums:
    """Test enum values."""
    
    def test_account_type_enum(self):
        """Test AccountType enum values."""
        assert AccountType.CHECKING == "checking"
        assert AccountType.SAVINGS == "savings"
        assert AccountType.BUSINESS == "business"
    
    def test_transaction_type_enum(self):
        """Test TransactionType enum values."""
        assert TransactionType.DEPOSIT == "deposit"
        assert TransactionType.WITHDRAWAL == "withdrawal"
        assert TransactionType.TRANSFER == "transfer"
    
    def test_risk_level_enum(self):
        """Test RiskLevel enum values."""
        assert RiskLevel.LOW == "low"
        assert RiskLevel.MEDIUM == "medium"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.CRITICAL == "critical"