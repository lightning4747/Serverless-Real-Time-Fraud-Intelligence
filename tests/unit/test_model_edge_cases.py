"""Additional edge case tests for data models."""

import pytest
import json
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import ValidationError

from sentinel_aml.data.models import (
    Account, 
    Transaction, 
    TransactionEdge,
    RiskScore,
    Alert,
    SuspiciousActivityReport,
    AccountType,
    TransactionType,
    RiskLevel,
    AlertStatus
)
from sentinel_aml.core.exceptions import ValidationError as SentinelValidationError


class TestModelValidationEdgeCases:
    """Test edge cases for model validation."""
    
    def test_account_id_edge_cases(self):
        """Test account ID validation edge cases."""
        # Minimum length (8 characters)
        account = Account(
            account_id="ACC12345",
            customer_name="John Doe",
            account_type="checking"
        )
        assert account.account_id == "ACC12345"
        
        # Maximum length (20 characters)
        account = Account(
            account_id="A" * 20,
            customer_name="John Doe",
            account_type="checking"
        )
        assert len(account.account_id) == 20
        
        # Too short (7 characters)
        with pytest.raises(ValidationError, match="Invalid account ID format"):
            Account(
                account_id="ACC1234",
                customer_name="John Doe",
                account_type="checking"
            )
        
        # Too long (21 characters)
        with pytest.raises(ValidationError, match="Invalid account ID format"):
            Account(
                account_id="A" * 21,
                customer_name="John Doe",
                account_type="checking"
            )
    
    def test_transaction_amount_edge_cases(self):
        """Test transaction amount validation edge cases."""
        # Zero amount (should be allowed)
        transaction = Transaction(
            amount="0.00",
            transaction_type="deposit"
        )
        assert transaction.amount == Decimal("0.00")
        
        # Very small amount
        transaction = Transaction(
            amount="0.01",
            transaction_type="deposit"
        )
        assert transaction.amount == Decimal("0.01")
        
        # Maximum allowed amount
        transaction = Transaction(
            amount="999999999.99",
            transaction_type="deposit"
        )
        assert transaction.amount == Decimal("999999999.99")
        
        # Amount with many decimal places (should be rounded)
        transaction = Transaction(
            amount="123.456789",
            transaction_type="deposit"
        )
        assert transaction.amount == Decimal("123.46")
        
        # Scientific notation
        transaction = Transaction(
            amount="1.23e3",  # 1230.0
            transaction_type="deposit"
        )
        assert transaction.amount == Decimal("1230.00")
    
    def test_currency_code_edge_cases(self):
        """Test currency code validation edge cases."""
        # All supported currencies
        supported_currencies = [
            "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", 
            "HKD", "SGD", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF",
            "RUB", "BRL", "MXN", "INR", "KRW", "THB", "MYR", "IDR"
        ]
        
        for currency in supported_currencies:
            account = Account(
                account_id="ACC123456789",
                customer_name="John Doe",
                account_type="checking",
                currency=currency
            )
            assert account.currency == currency
        
        # Lowercase should be converted to uppercase
        account = Account(
            account_id="ACC123456789",
            customer_name="John Doe",
            account_type="checking",
            currency="eur"
        )
        assert account.currency == "EUR"
    
    def test_risk_score_precision(self):
        """Test risk score precision handling."""
        # Very precise risk scores
        precise_scores = [
            0.123456789,
            0.999999999,
            0.000000001
        ]
        
        for score in precise_scores:
            risk_score = RiskScore(
                entity_id="ACC123456789",
                entity_type="account",
                risk_score=score,
                model_name="test_model",
                model_version="v1.0"
            )
            assert risk_score.risk_score == score
    
    def test_datetime_handling(self):
        """Test datetime handling in various scenarios."""
        # Naive datetime (no timezone)
        naive_dt = datetime(2024, 1, 1, 12, 0, 0)
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            timestamp=naive_dt
        )
        assert transaction.timestamp == naive_dt
        
        # UTC datetime
        utc_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            timestamp=utc_dt
        )
        assert transaction.timestamp == utc_dt
        
        # Future datetime (should be allowed)
        future_dt = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            timestamp=future_dt
        )
        assert transaction.timestamp == future_dt
    
    def test_list_field_edge_cases(self):
        """Test list field edge cases."""
        # Very long list
        long_list = [f"flag_{i}" for i in range(1000)]
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            risk_flags=long_list
        )
        assert len(transaction.risk_flags) == 1000
        
        # List with duplicate values
        duplicate_list = ["flag1", "flag2", "flag1", "flag3", "flag2"]
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            risk_flags=duplicate_list
        )
        assert transaction.risk_flags == duplicate_list  # Duplicates preserved
        
        # List with empty strings
        empty_string_list = ["", "flag1", "", "flag2"]
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            risk_flags=empty_string_list
        )
        assert transaction.risk_flags == empty_string_list
    
    def test_string_field_edge_cases(self):
        """Test string field edge cases."""
        # Very long strings
        long_description = "A" * 10000
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            description=long_description
        )
        assert len(transaction.description) == 10000
        
        # Special characters
        special_chars = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            description=special_chars
        )
        assert transaction.description == special_chars
        
        # Unicode characters
        unicode_text = "测试 🏦 💰 Тест العربية"
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            description=unicode_text
        )
        assert transaction.description == unicode_text


class TestModelSerializationEdgeCases:
    """Test serialization edge cases."""
    
    def test_decimal_serialization_precision(self):
        """Test decimal serialization maintains precision."""
        # High precision decimal
        precise_amount = Decimal("123.456789123456789")
        transaction = Transaction(
            amount=precise_amount,
            transaction_type="deposit"
        )
        
        # Serialize to JSON
        json_data = transaction.model_dump()
        
        # Amount should be converted to float for JSON
        assert isinstance(json_data["amount"], float)
        
        # Deserialize back
        restored_transaction = Transaction(**json_data)
        
        # Should be rounded to 2 decimal places due to validation
        assert restored_transaction.amount == Decimal("123.46")
    
    def test_datetime_serialization_formats(self):
        """Test datetime serialization in different formats."""
        # Create transaction with specific datetime
        dt = datetime(2024, 1, 15, 14, 30, 45, 123456, tzinfo=timezone.utc)
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            timestamp=dt
        )
        
        # Serialize to JSON
        json_str = transaction.model_dump_json()
        json_data = json.loads(json_str)
        
        # Timestamp should be ISO format string
        assert isinstance(json_data["timestamp"], str)
        assert "2024-01-15T14:30:45.123456+00:00" in json_data["timestamp"]
    
    def test_nested_dict_serialization(self):
        """Test serialization of nested dictionaries."""
        # Create risk score with complex feature scores
        complex_features = {
            "velocity_metrics": {
                "hourly_rate": 0.8,
                "daily_rate": 0.6,
                "weekly_rate": 0.4
            },
            "amount_patterns": {
                "round_amounts": 0.9,
                "threshold_avoidance": 0.7,
                "clustering": 0.5
            },
            "geographic_risk": {
                "high_risk_countries": 0.8,
                "cross_border": 0.6
            }
        }
        
        risk_score = RiskScore(
            entity_id="ACC123456789",
            entity_type="account",
            risk_score=0.75,
            model_name="complex_model",
            model_version="v1.0",
            feature_scores=complex_features
        )
        
        # Serialize and deserialize
        json_str = risk_score.model_dump_json()
        json_data = json.loads(json_str)
        restored_risk_score = RiskScore(**json_data)
        
        # Nested structure should be preserved
        assert restored_risk_score.feature_scores == complex_features
    
    def test_model_with_none_values(self):
        """Test serialization of models with None values."""
        account = Account(
            account_id="ACC123456789",
            customer_name="John Doe",
            account_type="checking",
            customer_id=None,
            country_code=None,
            balance=None,
            last_activity_date=None
        )
        
        # Serialize
        json_data = account.model_dump()
        
        # None values should be preserved
        assert json_data["customer_id"] is None
        assert json_data["country_code"] is None
        assert json_data["balance"] is None
        assert json_data["last_activity_date"] is None
        
        # Deserialize
        restored_account = Account(**json_data)
        assert restored_account.customer_id is None
        assert restored_account.country_code is None
        assert restored_account.balance is None
        assert restored_account.last_activity_date is None


class TestModelBusinessLogicEdgeCases:
    """Test business logic edge cases."""
    
    def test_sar_date_range_validation(self):
        """Test SAR date range business logic."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)
        
        # Normal case - end after start
        sar = SuspiciousActivityReport(
            case_id="CASE-TEST",
            subject_accounts=["ACC123"],
            subject_names=["hash1"],
            activity_description="Test activity",
            suspicious_patterns=["test_pattern"],
            transaction_summary="Test summary",
            total_amount="1000.00",
            date_range_start=start_date,
            date_range_end=end_date,
            reporting_reason="Test reason"
        )
        assert sar.date_range_start < sar.date_range_end
        
        # Edge case - same start and end date (should be allowed)
        same_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        sar = SuspiciousActivityReport(
            case_id="CASE-TEST",
            subject_accounts=["ACC123"],
            subject_names=["hash1"],
            activity_description="Test activity",
            suspicious_patterns=["test_pattern"],
            transaction_summary="Test summary",
            total_amount="1000.00",
            date_range_start=same_date,
            date_range_end=same_date,
            reporting_reason="Test reason"
        )
        assert sar.date_range_start == sar.date_range_end
    
    def test_alert_risk_level_consistency(self):
        """Test alert risk level and score consistency."""
        # High risk level with high score
        alert = Alert(
            title="High Risk Alert",
            description="High risk activity detected",
            risk_level=RiskLevel.CRITICAL,
            risk_score=0.95
        )
        assert alert.risk_level == RiskLevel.CRITICAL
        assert alert.risk_score >= 0.9
        
        # Low risk level with low score
        alert = Alert(
            title="Low Risk Alert",
            description="Low risk activity detected",
            risk_level=RiskLevel.LOW,
            risk_score=0.1
        )
        assert alert.risk_level == RiskLevel.LOW
        assert alert.risk_score <= 0.3
    
    def test_transaction_edge_consistency(self):
        """Test transaction edge consistency with transaction data."""
        # Create transaction
        transaction = Transaction(
            transaction_id="TXN123456789",
            amount="1500.00",
            transaction_type="transfer",
            currency="USD"
        )
        
        # Create edge with same data
        edge = TransactionEdge(
            from_account_id="ACC123456789",
            to_account_id="ACC987654321",
            transaction_id=transaction.transaction_id,
            amount=transaction.amount,
            timestamp=transaction.timestamp,
            transaction_type=transaction.transaction_type
        )
        
        # Data should match
        assert edge.transaction_id == transaction.transaction_id
        assert edge.amount == transaction.amount
        assert edge.transaction_type == transaction.transaction_type
    
    def test_model_id_uniqueness(self):
        """Test that model IDs are unique."""
        # Create multiple instances
        alerts = [
            Alert(
                title=f"Alert {i}",
                description=f"Description {i}",
                risk_level=RiskLevel.MEDIUM,
                risk_score=0.5
            )
            for i in range(10)
        ]
        
        # All IDs should be unique
        alert_ids = [alert.alert_id for alert in alerts]
        assert len(set(alert_ids)) == len(alert_ids)
        
        # Same for SARs
        sars = [
            SuspiciousActivityReport(
                case_id=f"CASE-{i}",
                subject_accounts=[f"ACC{i}"],
                subject_names=[f"hash{i}"],
                activity_description=f"Activity {i}",
                suspicious_patterns=[f"pattern{i}"],
                transaction_summary=f"Summary {i}",
                total_amount="1000.00",
                date_range_start=datetime.now(timezone.utc),
                date_range_end=datetime.now(timezone.utc),
                reporting_reason=f"Reason {i}"
            )
            for i in range(10)
        ]
        
        sar_ids = [sar.sar_id for sar in sars]
        assert len(set(sar_ids)) == len(sar_ids)


class TestModelPerformanceEdgeCases:
    """Test model performance with large data."""
    
    def test_large_feature_scores_dict(self):
        """Test performance with large feature scores dictionary."""
        # Create large feature scores dictionary
        large_features = {f"feature_{i}": float(i % 100) / 100 for i in range(1000)}
        
        risk_score = RiskScore(
            entity_id="ACC123456789",
            entity_type="account",
            risk_score=0.5,
            model_name="large_model",
            model_version="v1.0",
            feature_scores=large_features
        )
        
        assert len(risk_score.feature_scores) == 1000
        
        # Serialization should still work
        json_data = risk_score.model_dump()
        assert len(json_data["feature_scores"]) == 1000
    
    def test_large_list_fields(self):
        """Test performance with large list fields."""
        # Large risk factors list
        large_risk_factors = [f"risk_factor_{i}" for i in range(500)]
        large_patterns = [f"pattern_{i}" for i in range(500)]
        
        risk_score = RiskScore(
            entity_id="ACC123456789",
            entity_type="account",
            risk_score=0.5,
            model_name="large_model",
            model_version="v1.0",
            risk_factors=large_risk_factors,
            pattern_matches=large_patterns
        )
        
        assert len(risk_score.risk_factors) == 500
        assert len(risk_score.pattern_matches) == 500
        
        # Serialization should work
        json_str = risk_score.model_dump_json()
        assert len(json_str) > 10000  # Should be a large JSON string
    
    def test_bulk_model_creation(self):
        """Test creating many model instances."""
        # Create many accounts
        accounts = []
        for i in range(100):
            account = Account(
                account_id=f"ACC{i:010d}",
                customer_name=f"Customer {i}",
                account_type="checking",
                risk_score=float(i % 100) / 100
            )
            accounts.append(account)
        
        assert len(accounts) == 100
        
        # All should have unique IDs and proper data
        account_ids = [acc.account_id for acc in accounts]
        assert len(set(account_ids)) == 100
        
        # Create many transactions
        transactions = []
        for i in range(100):
            transaction = Transaction(
                amount=f"{(i + 1) * 10}.00",
                transaction_type="deposit",
                description=f"Transaction {i}"
            )
            transactions.append(transaction)
        
        assert len(transactions) == 100
        
        # All should have unique IDs
        txn_ids = [txn.transaction_id for txn in transactions]
        assert len(set(txn_ids)) == 100