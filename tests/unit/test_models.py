"""Unit tests for data models."""

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


class TestAccount:
    """Test Account model validation, serialization, and edge cases."""
    
    def test_valid_account_creation(self, sample_account):
        """Test creating a valid account."""
        assert sample_account.account_id == "ACC123456789"
        assert sample_account.customer_name == "John Doe"
        assert sample_account.account_type == AccountType.CHECKING
        assert sample_account.risk_score == 0.2
    
    def test_invalid_account_id_formats(self):
        """Test various invalid account ID formats."""
        invalid_ids = [
            "123",          # Too short
            "A" * 21,       # Too long
            "ACC-123-456",  # Contains hyphens
            "ACC 123456",   # Contains spaces
            "ACC@123456",   # Contains special characters
            "",             # Empty string
            "acc123456789", # Valid format but lowercase (should still work)
        ]
        
        for invalid_id in invalid_ids[:-1]:  # Exclude the last one (lowercase)
            with pytest.raises(ValidationError, match="Invalid account ID format"):
                Account(
                    account_id=invalid_id,
                    customer_name="John Doe",
                    account_type="checking"
                )
    
    def test_account_id_case_sensitivity(self):
        """Test that account IDs are case-sensitive but valid."""
        # Lowercase should work (alphanumeric)
        account = Account(
            account_id="acc123456789",
            customer_name="John Doe",
            account_type="checking"
        )
        assert account.account_id == "acc123456789"
    
    def test_risk_score_bounds(self):
        """Test risk score validation bounds."""
        # Valid risk scores
        valid_scores = [0.0, 0.5, 1.0, 0.123456]
        for score in valid_scores:
            account = Account(
                account_id="ACC123456789",
                customer_name="John Doe",
                account_type="checking",
                risk_score=score
            )
            assert account.risk_score == score
        
        # Invalid risk scores
        invalid_scores = [-0.1, 1.1, -1.0, 2.0]
        for score in invalid_scores:
            with pytest.raises(ValidationError):
                Account(
                    account_id="ACC123456789",
                    customer_name="John Doe",
                    account_type="checking",
                    risk_score=score
                )
    
    def test_invalid_currency_codes(self):
        """Test invalid currency code validation."""
        invalid_currencies = [
            "INVALID",  # Not in valid list
            "US",       # Too short
            "USDD",     # Too long
            "usd",      # Lowercase (should be converted to uppercase)
            "",         # Empty string
            "123",      # Numeric
        ]
        
        for currency in invalid_currencies[:-3]:  # Exclude lowercase, empty, and numeric
            with pytest.raises(ValidationError, match="Invalid currency code"):
                Account(
                    account_id="ACC123456789",
                    customer_name="John Doe",
                    account_type="checking",
                    currency=currency
                )
    
    def test_currency_case_normalization(self):
        """Test that currency codes are normalized to uppercase."""
        account = Account(
            account_id="ACC123456789",
            customer_name="John Doe",
            account_type="checking",
            currency="usd"
        )
        assert account.currency == "USD"
    
    def test_country_code_validation(self):
        """Test country code validation and normalization."""
        # Valid country codes
        valid_codes = ["US", "GB", "CA", "DE", "FR"]
        for code in valid_codes:
            account = Account(
                account_id="ACC123456789",
                customer_name="John Doe",
                account_type="checking",
                country_code=code
            )
            assert account.country_code == code.upper()
        
        # Test lowercase normalization
        account = Account(
            account_id="ACC123456789",
            customer_name="John Doe",
            account_type="checking",
            country_code="us"
        )
        assert account.country_code == "US"
        
        # Invalid country codes
        invalid_codes = ["USA", "U", "", "123"]
        for code in invalid_codes:
            with pytest.raises(ValidationError, match="Country code must be 2 characters"):
                Account(
                    account_id="ACC123456789",
                    customer_name="John Doe",
                    account_type="checking",
                    country_code=code
                )
    
    def test_account_serialization(self, sample_account):
        """Test account JSON serialization."""
        json_data = sample_account.model_dump()
        
        # Check required fields are present
        assert "account_id" in json_data
        assert "customer_name" in json_data
        assert "account_type" in json_data
        assert "risk_score" in json_data
        assert "creation_date" in json_data
        
        # Check data types
        assert isinstance(json_data["risk_score"], float)
        assert isinstance(json_data["is_pep"], bool)
        assert isinstance(json_data["is_active"], bool)
    
    def test_account_deserialization(self):
        """Test account creation from JSON data."""
        json_data = {
            "account_id": "ACC123456789",
            "customer_name": "Jane Smith",
            "account_type": "savings",
            "risk_score": 0.3,
            "customer_id": "CUST002",
            "country_code": "CA",
            "is_pep": True,
            "kyc_status": "pending",
            "balance": "5000.50",
            "currency": "CAD",
            "is_active": True
        }
        
        account = Account(**json_data)
        assert account.account_id == "ACC123456789"
        assert account.customer_name == "Jane Smith"
        assert account.account_type == AccountType.SAVINGS
        assert account.risk_score == 0.3
        assert account.country_code == "CA"
        assert account.is_pep is True
        assert account.balance == Decimal("5000.50")
        assert account.currency == "CAD"
    
    def test_account_json_round_trip(self, sample_account):
        """Test JSON serialization and deserialization round trip."""
        # Serialize to JSON
        json_str = sample_account.model_dump_json()
        json_data = json.loads(json_str)
        
        # Deserialize back to Account
        restored_account = Account(**json_data)
        
        # Compare key fields (excluding auto-generated timestamps)
        assert restored_account.account_id == sample_account.account_id
        assert restored_account.customer_name == sample_account.customer_name
        assert restored_account.account_type == sample_account.account_type
        assert restored_account.risk_score == sample_account.risk_score
        assert restored_account.currency == sample_account.currency
    
    def test_account_defaults(self):
        """Test account default values."""
        account = Account(
            account_id="ACC123456789",
            customer_name="Test User",
            account_type="checking"
        )
        
        # Check defaults
        assert account.risk_score == 0.0
        assert account.currency == "USD"
        assert account.is_pep is False
        assert account.kyc_status == "pending"
        assert account.is_active is True
        assert account.creation_date is not None
        assert account.last_activity_date is None
    
    def test_account_balance_precision(self):
        """Test account balance decimal precision."""
        account = Account(
            account_id="ACC123456789",
            customer_name="Test User",
            account_type="checking",
            balance="1234.567"  # More than 2 decimal places
        )
        
        # Balance should maintain precision as Decimal
        assert isinstance(account.balance, Decimal)
        assert account.balance == Decimal("1234.567")


class TestTransaction:
    """Test Transaction model validation, serialization, and edge cases."""
    
    def test_valid_transaction_creation(self, sample_transaction):
        """Test creating a valid transaction."""
        assert sample_transaction.amount == Decimal("1500.00")
        assert sample_transaction.transaction_type == TransactionType.TRANSFER
        assert sample_transaction.currency == "USD"
    
    def test_negative_amount_validation(self):
        """Test that negative amounts are rejected."""
        with pytest.raises(ValidationError, match="Transaction amount cannot be negative"):
            Transaction(
                amount=Decimal("-100.00"),
                transaction_type="deposit",
                currency="USD"
            )
    
    def test_zero_amount_validation(self):
        """Test that zero amounts are allowed."""
        transaction = Transaction(
            amount=Decimal("0.00"),
            transaction_type="deposit",
            currency="USD"
        )
        assert transaction.amount == Decimal("0.00")
    
    def test_amount_precision_handling(self):
        """Test amount precision handling and rounding."""
        test_cases = [
            ("1234.567", Decimal("1234.57")),  # Round down
            ("1234.565", Decimal("1234.57")),  # Round up (banker's rounding)
            ("1234.50", Decimal("1234.50")),   # Exact
            ("1234", Decimal("1234.00")),      # Integer
            ("0.001", Decimal("0.00")),        # Very small amount
        ]
        
        for input_amount, expected in test_cases:
            transaction = Transaction(
                amount=input_amount,
                transaction_type="deposit",
                currency="USD"
            )
            assert transaction.amount == expected
    
    def test_maximum_amount_validation(self):
        """Test maximum amount validation."""
        # Valid large amount
        transaction = Transaction(
            amount="999999999.99",
            transaction_type="deposit",
            currency="USD"
        )
        assert transaction.amount == Decimal("999999999.99")
        
        # Invalid - exceeds maximum
        with pytest.raises(ValidationError, match="Transaction amount exceeds maximum limit"):
            Transaction(
                amount="1000000000.00",
                transaction_type="deposit",
                currency="USD"
            )
    
    def test_amount_type_conversion(self):
        """Test amount conversion from different types."""
        # String input
        transaction1 = Transaction(
            amount="100.50",
            transaction_type="deposit",
            currency="USD"
        )
        assert transaction1.amount == Decimal("100.50")
        
        # Float input (should work but may have precision issues)
        transaction2 = Transaction(
            amount=100.50,
            transaction_type="deposit",
            currency="USD"
        )
        assert transaction2.amount == Decimal("100.50")
        
        # Integer input
        transaction3 = Transaction(
            amount=100,
            transaction_type="deposit",
            currency="USD"
        )
        assert transaction3.amount == Decimal("100.00")
    
    def test_invalid_amount_types(self):
        """Test invalid amount types."""
        invalid_amounts = [
            "invalid",
            None,
            [],
            {},
            "100.50.50",  # Multiple decimal points
        ]
        
        for invalid_amount in invalid_amounts:
            with pytest.raises(ValidationError):
                Transaction(
                    amount=invalid_amount,
                    transaction_type="deposit",
                    currency="USD"
                )
    
    def test_currency_validation_and_normalization(self):
        """Test currency validation and case normalization."""
        # Valid currencies (should be normalized to uppercase)
        valid_currencies = ["usd", "EUR", "gbp", "JPY"]
        expected_currencies = ["USD", "EUR", "GBP", "JPY"]
        
        for input_curr, expected_curr in zip(valid_currencies, expected_currencies):
            transaction = Transaction(
                amount="100.00",
                transaction_type="deposit",
                currency=input_curr
            )
            assert transaction.currency == expected_curr
        
        # Invalid currencies
        invalid_currencies = ["INVALID", "US", "USDD", "", "123"]
        for invalid_curr in invalid_currencies:
            with pytest.raises(ValidationError, match="Invalid currency code"):
                Transaction(
                    amount="100.00",
                    transaction_type="deposit",
                    currency=invalid_curr
                )
    
    def test_transaction_id_generation(self):
        """Test automatic transaction ID generation."""
        transaction1 = Transaction(
            amount="100.00",
            transaction_type="deposit",
            currency="USD"
        )
        
        transaction2 = Transaction(
            amount="200.00",
            transaction_type="withdrawal",
            currency="USD"
        )
        
        # IDs should be unique
        assert transaction1.transaction_id != transaction2.transaction_id
        assert len(transaction1.transaction_id) > 0
        assert len(transaction2.transaction_id) > 0
    
    def test_transaction_serialization(self, sample_transaction):
        """Test transaction JSON serialization."""
        json_data = sample_transaction.model_dump()
        
        # Check required fields
        assert "transaction_id" in json_data
        assert "amount" in json_data
        assert "timestamp" in json_data
        assert "transaction_type" in json_data
        assert "currency" in json_data
        
        # Check data types after serialization
        assert isinstance(json_data["amount"], float)  # Decimal converted to float
        assert isinstance(json_data["is_cash"], bool)
        assert isinstance(json_data["is_international"], bool)
        assert isinstance(json_data["risk_flags"], list)
    
    def test_transaction_deserialization(self):
        """Test transaction creation from JSON data."""
        json_data = {
            "transaction_id": "TXN987654321",
            "amount": 2500.75,
            "transaction_type": "wire",
            "currency": "EUR",
            "description": "International wire transfer",
            "is_cash": False,
            "is_international": True,
            "country_code": "DE",
            "city": "Berlin",
            "risk_flags": ["high_amount", "international"]
        }
        
        transaction = Transaction(**json_data)
        assert transaction.transaction_id == "TXN987654321"
        assert transaction.amount == Decimal("2500.75")
        assert transaction.transaction_type == TransactionType.WIRE
        assert transaction.currency == "EUR"
        assert transaction.is_international is True
        assert "high_amount" in transaction.risk_flags
    
    def test_transaction_json_round_trip(self, sample_transaction):
        """Test JSON serialization and deserialization round trip."""
        # Serialize to JSON
        json_str = sample_transaction.model_dump_json()
        json_data = json.loads(json_str)
        
        # Deserialize back to Transaction
        restored_transaction = Transaction(**json_data)
        
        # Compare key fields
        assert restored_transaction.transaction_id == sample_transaction.transaction_id
        assert restored_transaction.amount == sample_transaction.amount
        assert restored_transaction.transaction_type == sample_transaction.transaction_type
        assert restored_transaction.currency == sample_transaction.currency
        assert restored_transaction.is_cash == sample_transaction.is_cash
    
    def test_transaction_defaults(self):
        """Test transaction default values."""
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit"
        )
        
        # Check defaults
        assert transaction.currency == "USD"
        assert transaction.is_cash is False
        assert transaction.is_international is False
        assert transaction.risk_flags == []
        assert transaction.timestamp is not None
        assert transaction.transaction_id is not None
    
    def test_risk_flags_handling(self):
        """Test risk flags list handling."""
        # Empty risk flags
        transaction1 = Transaction(
            amount="100.00",
            transaction_type="deposit",
            risk_flags=[]
        )
        assert transaction1.risk_flags == []
        
        # Multiple risk flags
        risk_flags = ["high_amount", "unusual_time", "high_risk_country"]
        transaction2 = Transaction(
            amount="100.00",
            transaction_type="deposit",
            risk_flags=risk_flags
        )
        assert transaction2.risk_flags == risk_flags
        assert len(transaction2.risk_flags) == 3


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


class TestRiskScore:
    """Test RiskScore model validation and serialization."""
    
    def test_valid_risk_score_creation(self):
        """Test creating a valid risk score."""
        risk_score = RiskScore(
            entity_id="ACC123456789",
            entity_type="account",
            risk_score=0.75,
            model_name="gnn_fraud_detector",
            model_version="v1.2.3"
        )
        
        assert risk_score.entity_id == "ACC123456789"
        assert risk_score.entity_type == "account"
        assert risk_score.risk_score == 0.75
        assert risk_score.model_name == "gnn_fraud_detector"
        assert risk_score.model_version == "v1.2.3"
    
    def test_risk_score_bounds_validation(self):
        """Test risk score bounds validation."""
        # Valid scores
        valid_scores = [0.0, 0.5, 1.0, 0.123456]
        for score in valid_scores:
            risk_score = RiskScore(
                entity_id="ACC123456789",
                entity_type="account",
                risk_score=score,
                model_name="test_model",
                model_version="v1.0"
            )
            assert risk_score.risk_score == score
        
        # Invalid scores
        invalid_scores = [-0.1, 1.1, -1.0, 2.0]
        for score in invalid_scores:
            with pytest.raises(ValidationError):
                RiskScore(
                    entity_id="ACC123456789",
                    entity_type="account",
                    risk_score=score,
                    model_name="test_model",
                    model_version="v1.0"
                )
    
    def test_confidence_score_bounds_validation(self):
        """Test confidence score bounds validation."""
        # Valid confidence scores
        valid_confidences = [None, 0.0, 0.5, 1.0, 0.95]
        for confidence in valid_confidences:
            risk_score = RiskScore(
                entity_id="ACC123456789",
                entity_type="account",
                risk_score=0.5,
                model_name="test_model",
                model_version="v1.0",
                confidence=confidence
            )
            assert risk_score.confidence == confidence
        
        # Invalid confidence scores
        invalid_confidences = [-0.1, 1.1, 2.0]
        for confidence in invalid_confidences:
            with pytest.raises(ValidationError):
                RiskScore(
                    entity_id="ACC123456789",
                    entity_type="account",
                    risk_score=0.5,
                    model_name="test_model",
                    model_version="v1.0",
                    confidence=confidence
                )
    
    def test_risk_score_serialization(self):
        """Test risk score JSON serialization."""
        risk_score = RiskScore(
            entity_id="TXN123456789",
            entity_type="transaction",
            risk_score=0.85,
            model_name="smurfing_detector",
            model_version="v2.1.0",
            feature_scores={"velocity": 0.9, "amount_pattern": 0.8},
            explanation="High velocity transactions with round amounts",
            confidence=0.92,
            risk_factors=["high_velocity", "round_amounts"],
            pattern_matches=["smurfing_pattern_1", "velocity_spike"]
        )
        
        json_data = risk_score.model_dump()
        
        # Check all fields are present
        assert "entity_id" in json_data
        assert "risk_score" in json_data
        assert "feature_scores" in json_data
        assert "risk_factors" in json_data
        assert "pattern_matches" in json_data
        
        # Check data types
        assert isinstance(json_data["risk_score"], float)
        assert isinstance(json_data["confidence"], float)
        assert isinstance(json_data["feature_scores"], dict)
        assert isinstance(json_data["risk_factors"], list)
    
    def test_risk_score_defaults(self):
        """Test risk score default values."""
        risk_score = RiskScore(
            entity_id="ACC123456789",
            entity_type="account",
            risk_score=0.5,
            model_name="test_model",
            model_version="v1.0"
        )
        
        # Check defaults
        assert risk_score.feature_scores == {}
        assert risk_score.explanation is None
        assert risk_score.confidence is None
        assert risk_score.risk_factors == []
        assert risk_score.pattern_matches == []
        assert risk_score.prediction_timestamp is not None


class TestAlert:
    """Test Alert model validation and serialization."""
    
    def test_valid_alert_creation(self):
        """Test creating a valid alert."""
        alert = Alert(
            title="Suspicious Transaction Pattern",
            description="Multiple transactions below reporting threshold",
            risk_level=RiskLevel.HIGH,
            risk_score=0.85,
            account_ids=["ACC123456789", "ACC987654321"],
            transaction_ids=["TXN001", "TXN002", "TXN003"],
            suspicious_patterns=["smurfing", "velocity_spike"]
        )
        
        assert alert.title == "Suspicious Transaction Pattern"
        assert alert.risk_level == RiskLevel.HIGH
        assert alert.risk_score == 0.85
        assert len(alert.account_ids) == 2
        assert len(alert.transaction_ids) == 3
        assert "smurfing" in alert.suspicious_patterns
    
    def test_alert_risk_score_bounds(self):
        """Test alert risk score validation."""
        # Valid risk scores
        valid_scores = [0.0, 0.5, 1.0, 0.999]
        for score in valid_scores:
            alert = Alert(
                title="Test Alert",
                description="Test description",
                risk_level=RiskLevel.MEDIUM,
                risk_score=score
            )
            assert alert.risk_score == score
        
        # Invalid risk scores
        invalid_scores = [-0.1, 1.1, 2.0]
        for score in invalid_scores:
            with pytest.raises(ValidationError):
                Alert(
                    title="Test Alert",
                    description="Test description",
                    risk_level=RiskLevel.MEDIUM,
                    risk_score=score
                )
    
    def test_alert_status_transitions(self):
        """Test alert status enum values."""
        alert = Alert(
            title="Test Alert",
            description="Test description",
            risk_level=RiskLevel.MEDIUM,
            risk_score=0.5
        )
        
        # Default status
        assert alert.status == AlertStatus.OPEN
        
        # Test all valid statuses
        valid_statuses = [
            AlertStatus.OPEN,
            AlertStatus.INVESTIGATING,
            AlertStatus.CLOSED,
            AlertStatus.ESCALATED,
            AlertStatus.FALSE_POSITIVE
        ]
        
        for status in valid_statuses:
            alert.status = status
            assert alert.status == status
    
    def test_alert_serialization(self):
        """Test alert JSON serialization."""
        alert = Alert(
            case_id="CASE-20241201-ABC123",
            title="High Risk Transaction Cluster",
            description="Detected potential money laundering activity",
            risk_level=RiskLevel.CRITICAL,
            status=AlertStatus.INVESTIGATING,
            account_ids=["ACC123", "ACC456"],
            transaction_ids=["TXN001", "TXN002"],
            risk_score=0.95,
            suspicious_patterns=["layering", "integration"],
            investigator_id="INV001",
            investigation_notes="Initial review completed"
        )
        
        json_data = alert.model_dump()
        
        # Check required fields
        assert "alert_id" in json_data
        assert "title" in json_data
        assert "risk_level" in json_data
        assert "risk_score" in json_data
        assert "created_at" in json_data
        
        # Check data types
        assert isinstance(json_data["account_ids"], list)
        assert isinstance(json_data["transaction_ids"], list)
        assert isinstance(json_data["suspicious_patterns"], list)
        assert isinstance(json_data["risk_score"], float)
    
    def test_alert_defaults(self):
        """Test alert default values."""
        alert = Alert(
            title="Test Alert",
            description="Test description",
            risk_level=RiskLevel.LOW,
            risk_score=0.3
        )
        
        # Check defaults
        assert alert.status == AlertStatus.OPEN
        assert alert.account_ids == []
        assert alert.transaction_ids == []
        assert alert.suspicious_patterns == []
        assert alert.case_id is None
        assert alert.investigator_id is None
        assert alert.investigation_notes is None
        assert alert.investigated_at is None
        assert alert.closed_at is None
        assert alert.created_at is not None
        assert alert.updated_at is not None
    
    def test_alert_id_generation(self):
        """Test automatic alert ID generation."""
        alert1 = Alert(
            title="Alert 1",
            description="Description 1",
            risk_level=RiskLevel.LOW,
            risk_score=0.3
        )
        
        alert2 = Alert(
            title="Alert 2",
            description="Description 2",
            risk_level=RiskLevel.HIGH,
            risk_score=0.8
        )
        
        # IDs should be unique
        assert alert1.alert_id != alert2.alert_id
        assert len(alert1.alert_id) > 0
        assert len(alert2.alert_id) > 0


class TestSuspiciousActivityReport:
    """Test SuspiciousActivityReport model validation and serialization."""
    
    def test_valid_sar_creation(self):
        """Test creating a valid SAR."""
        sar = SuspiciousActivityReport(
            case_id="CASE-20241201-ABC123",
            subject_accounts=["ACC123456789", "ACC987654321"],
            subject_names=["hash1", "hash2"],
            activity_description="Structured deposits to avoid CTR reporting",
            suspicious_patterns=["smurfing", "structuring"],
            transaction_summary="Multiple cash deposits under $10,000",
            total_amount=Decimal("95000.00"),
            date_range_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            date_range_end=datetime(2024, 1, 31, tzinfo=timezone.utc),
            reporting_reason="Potential money laundering activity"
        )
        
        assert sar.case_id == "CASE-20241201-ABC123"
        assert len(sar.subject_accounts) == 2
        assert sar.total_amount == Decimal("95000.00")
        assert "smurfing" in sar.suspicious_patterns
        assert sar.currency == "USD"  # Default
    
    def test_sar_amount_validation(self):
        """Test SAR total amount validation."""
        # Valid amounts
        valid_amounts = ["0.01", "1000.00", "999999999.99"]
        for amount in valid_amounts:
            sar = SuspiciousActivityReport(
                case_id="CASE-TEST",
                subject_accounts=["ACC123"],
                subject_names=["hash1"],
                activity_description="Test activity",
                suspicious_patterns=["test_pattern"],
                transaction_summary="Test summary",
                total_amount=amount,
                date_range_start=datetime.now(timezone.utc),
                date_range_end=datetime.now(timezone.utc),
                reporting_reason="Test reason"
            )
            assert sar.total_amount == Decimal(amount)
        
        # Invalid amounts (negative)
        with pytest.raises(ValidationError, match="Transaction amount cannot be negative"):
            SuspiciousActivityReport(
                case_id="CASE-TEST",
                subject_accounts=["ACC123"],
                subject_names=["hash1"],
                activity_description="Test activity",
                suspicious_patterns=["test_pattern"],
                transaction_summary="Test summary",
                total_amount="-1000.00",
                date_range_start=datetime.now(timezone.utc),
                date_range_end=datetime.now(timezone.utc),
                reporting_reason="Test reason"
            )
    
    def test_sar_currency_validation(self):
        """Test SAR currency validation."""
        # Valid currencies
        valid_currencies = ["USD", "EUR", "GBP", "usd"]  # lowercase should be normalized
        expected_currencies = ["USD", "EUR", "GBP", "USD"]
        
        for input_curr, expected_curr in zip(valid_currencies, expected_currencies):
            sar = SuspiciousActivityReport(
                case_id="CASE-TEST",
                subject_accounts=["ACC123"],
                subject_names=["hash1"],
                activity_description="Test activity",
                suspicious_patterns=["test_pattern"],
                transaction_summary="Test summary",
                total_amount="1000.00",
                currency=input_curr,
                date_range_start=datetime.now(timezone.utc),
                date_range_end=datetime.now(timezone.utc),
                reporting_reason="Test reason"
            )
            assert sar.currency == expected_curr
        
        # Invalid currency
        with pytest.raises(ValidationError, match="Invalid currency code"):
            SuspiciousActivityReport(
                case_id="CASE-TEST",
                subject_accounts=["ACC123"],
                subject_names=["hash1"],
                activity_description="Test activity",
                suspicious_patterns=["test_pattern"],
                transaction_summary="Test summary",
                total_amount="1000.00",
                currency="INVALID",
                date_range_start=datetime.now(timezone.utc),
                date_range_end=datetime.now(timezone.utc),
                reporting_reason="Test reason"
            )
    
    def test_sar_ai_confidence_bounds(self):
        """Test SAR AI confidence score validation."""
        # Valid confidence scores
        valid_confidences = [None, 0.0, 0.5, 1.0, 0.95]
        for confidence in valid_confidences:
            sar = SuspiciousActivityReport(
                case_id="CASE-TEST",
                subject_accounts=["ACC123"],
                subject_names=["hash1"],
                activity_description="Test activity",
                suspicious_patterns=["test_pattern"],
                transaction_summary="Test summary",
                total_amount="1000.00",
                date_range_start=datetime.now(timezone.utc),
                date_range_end=datetime.now(timezone.utc),
                reporting_reason="Test reason",
                ai_confidence=confidence
            )
            assert sar.ai_confidence == confidence
        
        # Invalid confidence scores
        invalid_confidences = [-0.1, 1.1, 2.0]
        for confidence in invalid_confidences:
            with pytest.raises(ValidationError):
                SuspiciousActivityReport(
                    case_id="CASE-TEST",
                    subject_accounts=["ACC123"],
                    subject_names=["hash1"],
                    activity_description="Test activity",
                    suspicious_patterns=["test_pattern"],
                    transaction_summary="Test summary",
                    total_amount="1000.00",
                    date_range_start=datetime.now(timezone.utc),
                    date_range_end=datetime.now(timezone.utc),
                    reporting_reason="Test reason",
                    ai_confidence=confidence
                )
    
    def test_sar_serialization(self):
        """Test SAR JSON serialization."""
        sar = SuspiciousActivityReport(
            case_id="CASE-20241201-ABC123",
            report_number="SAR-2024-001",
            subject_accounts=["ACC123", "ACC456"],
            subject_names=["hash1", "hash2"],
            activity_description="Suspicious structuring activity",
            suspicious_patterns=["smurfing", "layering"],
            transaction_summary="Multiple deposits under reporting threshold",
            total_amount=Decimal("85000.50"),
            currency="USD",
            date_range_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            date_range_end=datetime(2024, 1, 31, tzinfo=timezone.utc),
            regulation_violated=["BSA", "AML"],
            reporting_reason="Potential money laundering",
            generated_by_ai=True,
            ai_model_version="claude-3-sonnet-v1",
            ai_confidence=0.92
        )
        
        json_data = sar.model_dump()
        
        # Check required fields
        assert "sar_id" in json_data
        assert "case_id" in json_data
        assert "subject_accounts" in json_data
        assert "total_amount" in json_data
        assert "created_at" in json_data
        
        # Check data types after serialization
        assert isinstance(json_data["total_amount"], float)  # Decimal converted to float
        assert isinstance(json_data["subject_accounts"], list)
        assert isinstance(json_data["suspicious_patterns"], list)
        assert isinstance(json_data["regulation_violated"], list)
        assert isinstance(json_data["generated_by_ai"], bool)
    
    def test_sar_defaults(self):
        """Test SAR default values."""
        sar = SuspiciousActivityReport(
            case_id="CASE-TEST",
            subject_accounts=["ACC123"],
            subject_names=["hash1"],
            activity_description="Test activity",
            suspicious_patterns=["test_pattern"],
            transaction_summary="Test summary",
            total_amount="1000.00",
            date_range_start=datetime.now(timezone.utc),
            date_range_end=datetime.now(timezone.utc),
            reporting_reason="Test reason"
        )
        
        # Check defaults
        assert sar.currency == "USD"
        assert sar.status == "draft"
        assert sar.regulation_violated == []
        assert sar.generated_by_ai is True
        assert sar.ai_model_version is None
        assert sar.ai_confidence is None
        assert sar.report_number is None
        assert sar.filing_date is None
        assert sar.created_at is not None
        assert sar.updated_at is not None
    
    def test_sar_id_generation(self):
        """Test automatic SAR ID generation."""
        sar1 = SuspiciousActivityReport(
            case_id="CASE-001",
            subject_accounts=["ACC123"],
            subject_names=["hash1"],
            activity_description="Activity 1",
            suspicious_patterns=["pattern1"],
            transaction_summary="Summary 1",
            total_amount="1000.00",
            date_range_start=datetime.now(timezone.utc),
            date_range_end=datetime.now(timezone.utc),
            reporting_reason="Reason 1"
        )
        
        sar2 = SuspiciousActivityReport(
            case_id="CASE-002",
            subject_accounts=["ACC456"],
            subject_names=["hash2"],
            activity_description="Activity 2",
            suspicious_patterns=["pattern2"],
            transaction_summary="Summary 2",
            total_amount="2000.00",
            date_range_start=datetime.now(timezone.utc),
            date_range_end=datetime.now(timezone.utc),
            reporting_reason="Reason 2"
        )
        
        # IDs should be unique
        assert sar1.sar_id != sar2.sar_id
        assert len(sar1.sar_id) > 0
        assert len(sar2.sar_id) > 0


class TestModelEdgeCases:
    """Test edge cases and error conditions across all models."""
    
    def test_empty_string_validation(self):
        """Test handling of empty strings in required fields."""
        # Account with empty customer name should fail
        with pytest.raises(ValidationError):
            Account(
                account_id="ACC123456789",
                customer_name="",  # Empty string
                account_type="checking"
            )
        
        # Transaction with empty description should be allowed (optional field)
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            description=""  # Empty string in optional field
        )
        assert transaction.description == ""
    
    def test_whitespace_handling(self):
        """Test handling of whitespace in string fields."""
        # Account with whitespace-only customer name
        with pytest.raises(ValidationError):
            Account(
                account_id="ACC123456789",
                customer_name="   ",  # Whitespace only
                account_type="checking"
            )
    
    def test_unicode_string_handling(self):
        """Test handling of unicode characters in string fields."""
        # Unicode characters in customer name
        account = Account(
            account_id="ACC123456789",
            customer_name="José María González",
            account_type="checking"
        )
        assert account.customer_name == "José María González"
        
        # Unicode in transaction description
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            description="Transferência bancária"
        )
        assert transaction.description == "Transferência bancária"
    
    def test_very_large_decimal_precision(self):
        """Test handling of very high precision decimal values."""
        # Transaction with many decimal places
        transaction = Transaction(
            amount="100.123456789",
            transaction_type="deposit"
        )
        # Should be rounded to 2 decimal places
        assert transaction.amount == Decimal("100.12")
    
    def test_list_field_edge_cases(self):
        """Test edge cases for list fields."""
        # Empty lists should work
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            risk_flags=[]
        )
        assert transaction.risk_flags == []
        
        # Large lists should work
        large_risk_flags = [f"flag_{i}" for i in range(100)]
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            risk_flags=large_risk_flags
        )
        assert len(transaction.risk_flags) == 100
    
    def test_datetime_timezone_handling(self):
        """Test datetime timezone handling."""
        # Datetime without timezone should work (will use UTC)
        naive_datetime = datetime(2024, 1, 1, 12, 0, 0)
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            timestamp=naive_datetime
        )
        assert transaction.timestamp == naive_datetime
        
        # Datetime with timezone should work
        aware_datetime = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        transaction = Transaction(
            amount="100.00",
            transaction_type="deposit",
            timestamp=aware_datetime
        )
        assert transaction.timestamp == aware_datetime


class TestModelSerialization:
    """Test comprehensive serialization and deserialization scenarios."""
    
    def test_nested_model_serialization(self):
        """Test serialization of models with complex nested data."""
        # Create a risk score with complex nested data
        risk_score = RiskScore(
            entity_id="ACC123456789",
            entity_type="account",
            risk_score=0.85,
            model_name="complex_model",
            model_version="v1.0",
            feature_scores={
                "velocity": 0.9,
                "amount_patterns": 0.8,
                "geographic_risk": 0.7,
                "temporal_patterns": 0.6
            },
            risk_factors=["high_velocity", "unusual_amounts", "high_risk_jurisdiction"],
            pattern_matches=["pattern_1", "pattern_2", "pattern_3"]
        )
        
        # Serialize and deserialize
        json_str = risk_score.model_dump_json()
        json_data = json.loads(json_str)
        restored_risk_score = RiskScore(**json_data)
        
        # Verify complex nested data is preserved
        assert restored_risk_score.feature_scores == risk_score.feature_scores
        assert restored_risk_score.risk_factors == risk_score.risk_factors
        assert restored_risk_score.pattern_matches == risk_score.pattern_matches
    
    def test_model_with_all_optional_fields(self):
        """Test serialization of models with all optional fields populated."""
        account = Account(
            account_id="ACC123456789",
            customer_name="John Doe",
            account_type="checking",
            risk_score=0.5,
            customer_id="CUST001",
            country_code="US",
            is_pep=True,
            kyc_status="verified",
            balance=Decimal("10000.00"),
            currency="USD",
            is_active=True,
            last_activity_date=datetime.now(timezone.utc)
        )
        
        # Serialize and verify all fields are present
        json_data = account.model_dump()
        expected_fields = [
            "account_id", "customer_name", "account_type", "risk_score",
            "creation_date", "last_activity_date", "customer_id", "country_code",
            "is_pep", "kyc_status", "balance", "currency", "is_active"
        ]
        
        for field in expected_fields:
            assert field in json_data
    
    def test_partial_model_updates(self):
        """Test partial model updates and validation."""
        # Create base account
        account_data = {
            "account_id": "ACC123456789",
            "customer_name": "John Doe",
            "account_type": "checking"
        }
        account = Account(**account_data)
        
        # Update with additional data
        updated_data = account.model_dump()
        updated_data.update({
            "risk_score": 0.8,
            "is_pep": True,
            "balance": "5000.00"
        })
        
        updated_account = Account(**updated_data)
        assert updated_account.risk_score == 0.8
        assert updated_account.is_pep is True
        assert updated_account.balance == Decimal("5000.00")


class TestEnums:
    """Test enum values and validation."""
    
    def test_account_type_enum(self):
        """Test AccountType enum values."""
        assert AccountType.CHECKING == "checking"
        assert AccountType.SAVINGS == "savings"
        assert AccountType.BUSINESS == "business"
        assert AccountType.INVESTMENT == "investment"
        assert AccountType.CREDIT == "credit"
        assert AccountType.LOAN == "loan"
    
    def test_transaction_type_enum(self):
        """Test TransactionType enum values."""
        assert TransactionType.DEPOSIT == "deposit"
        assert TransactionType.WITHDRAWAL == "withdrawal"
        assert TransactionType.TRANSFER == "transfer"
        assert TransactionType.PAYMENT == "payment"
        assert TransactionType.WIRE == "wire"
        assert TransactionType.ACH == "ach"
        assert TransactionType.CHECK == "check"
        assert TransactionType.CARD == "card"
    
    def test_risk_level_enum(self):
        """Test RiskLevel enum values."""
        assert RiskLevel.LOW == "low"
        assert RiskLevel.MEDIUM == "medium"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.CRITICAL == "critical"
    
    def test_alert_status_enum(self):
        """Test AlertStatus enum values."""
        assert AlertStatus.OPEN == "open"
        assert AlertStatus.INVESTIGATING == "investigating"
        assert AlertStatus.CLOSED == "closed"
        assert AlertStatus.ESCALATED == "escalated"
        assert AlertStatus.FALSE_POSITIVE == "false_positive"
    
    def test_enum_case_sensitivity(self):
        """Test enum case sensitivity in model creation."""
        # Should work with exact enum values
        account = Account(
            account_id="ACC123456789",
            customer_name="John Doe",
            account_type=AccountType.CHECKING
        )
        assert account.account_type == AccountType.CHECKING
        
        # Should work with string values
        account = Account(
            account_id="ACC123456789",
            customer_name="John Doe",
            account_type="savings"
        )
        assert account.account_type == AccountType.SAVINGS
        
        # Should fail with invalid enum values
        with pytest.raises(ValidationError):
            Account(
                account_id="ACC123456789",
                customer_name="John Doe",
                account_type="invalid_type"
            )