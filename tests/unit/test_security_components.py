"""Unit tests for security components."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch
import json

from sentinel_aml.security.encryption import EncryptionService
from sentinel_aml.security.pii_protection import PIIProtectionService
from sentinel_aml.security.access_control import AccessControlService, Role, Permission, User
from sentinel_aml.core.exceptions import ValidationError


class TestEncryptionService:
    """Unit tests for encryption service."""
    
    @pytest.fixture
    def mock_kms_client(self):
        """Mock KMS client for testing."""
        mock_client = Mock()
        mock_client.generate_data_key.return_value = {
            'Plaintext': b'test_key_32_bytes_long_for_aes256',
            'CiphertextBlob': b'encrypted_key_data'
        }
        return mock_client
    
    @pytest.fixture
    def encryption_service(self, mock_kms_client):
        """Create encryption service with mocked KMS."""
        with patch('boto3.client', return_value=mock_kms_client):
            with patch('sentinel_aml.security.encryption.get_settings') as mock_settings:
                mock_settings.return_value.encryption_key_id = 'test-key-id'
                mock_settings.return_value.aws_region = 'us-east-1'
                return EncryptionService()
    
    def test_encrypt_decrypt_string(self, encryption_service):
        """Test basic string encryption and decryption."""
        original_data = "sensitive information"
        
        # Encrypt
        encrypted = encryption_service.encrypt_data(original_data)
        assert encrypted != original_data
        assert isinstance(encrypted, str)
        
        # Decrypt
        decrypted = encryption_service.decrypt_data(encrypted)
        assert decrypted == original_data
    
    def test_encrypt_decrypt_dict(self, encryption_service):
        """Test dictionary encryption and decryption."""
        original_data = {"name": "John Doe", "ssn": "123-45-6789"}
        
        # Encrypt
        encrypted = encryption_service.encrypt_data(original_data)
        assert encrypted != str(original_data)
        
        # Decrypt
        decrypted = encryption_service.decrypt_data(encrypted, return_type='dict')
        assert decrypted == original_data
    
    def test_field_specific_encryption(self, encryption_service):
        """Test field-specific encryption with context."""
        field_name = "ssn"
        value = "123-45-6789"
        
        # Encrypt field
        encrypted = encryption_service.encrypt_field(field_name, value)
        assert encrypted != value
        
        # Decrypt field
        decrypted = encryption_service.decrypt_field(field_name, encrypted)
        assert decrypted == value
    def test_pii_record_encryption(self, encryption_service):
        """Test PII record encryption and decryption."""
        pii_record = {
            "transaction_id": "TXN-001",
            "customer_name": "Jane Smith",
            "account_number": "9876543210",
            "amount": 5000.00,
            "currency": "USD"
        }
        
        # Encrypt PII fields
        encrypted_record = encryption_service.encrypt_pii_record(pii_record)
        
        # Non-PII fields should remain unchanged
        assert encrypted_record["transaction_id"] == pii_record["transaction_id"]
        assert encrypted_record["amount"] == pii_record["amount"]
        assert encrypted_record["currency"] == pii_record["currency"]
        
        # PII fields should be encrypted
        assert encrypted_record["customer_name"] != pii_record["customer_name"]
        assert encrypted_record["account_number"] != pii_record["account_number"]
        
        # Decrypt PII fields
        decrypted_record = encryption_service.decrypt_pii_record(encrypted_record)
        assert decrypted_record == pii_record
    
    def test_encryption_with_invalid_key(self):
        """Test encryption service with invalid KMS key."""
        with pytest.raises(ValueError, match="KMS key ID must be provided"):
            EncryptionService(kms_key_id=None)


class TestPIIProtectionService:
    """Unit tests for PII protection service."""
    
    @pytest.fixture
    def pii_service(self):
        """Create PII protection service."""
        return PIIProtectionService()
    
    def test_is_pii_field_detection(self, pii_service):
        """Test PII field detection."""
        # Should detect PII fields
        assert pii_service.is_pii_field("customer_name") == True
        assert pii_service.is_pii_field("ssn") == True
        assert pii_service.is_pii_field("email") == True
        assert pii_service.is_pii_field("account_number") == True
        
        # Should not detect non-PII fields
        assert pii_service.is_pii_field("transaction_id") == False
        assert pii_service.is_pii_field("amount") == False
        assert pii_service.is_pii_field("currency") == False
    
    def test_mask_account_number(self, pii_service):
        """Test account number masking."""
        # Normal account number
        account = "1234567890123456"
        masked = pii_service.mask_account_number(account)
        assert masked == "************3456"
        
        # Short account number
        short_account = "1234"
        masked_short = pii_service.mask_account_number(short_account)
        assert masked_short == "1234"  # Too short to mask
        
        # Empty account number
        empty_masked = pii_service.mask_account_number("")
        assert empty_masked == ""
    
    def test_mask_ssn(self, pii_service):
        """Test SSN masking."""
        # Formatted SSN
        ssn = "123-45-6789"
        masked = pii_service.mask_ssn(ssn)
        assert masked == "***-**-6789"
        
        # Unformatted SSN
        unformatted_ssn = "123456789"
        masked_unformatted = pii_service.mask_ssn(unformatted_ssn)
        assert masked_unformatted == "***-**-6789"
        
        # Invalid SSN
        invalid_ssn = "12345"
        masked_invalid = pii_service.mask_ssn(invalid_ssn)
        assert masked_invalid == "*****"
    
    def test_mask_email(self, pii_service):
        """Test email masking."""
        # Normal email
        email = "john.doe@example.com"
        masked = pii_service.mask_email(email)
        assert masked == "j*****e@example.com"
        
        # Short email
        short_email = "a@b.com"
        masked_short = pii_service.mask_email(short_email)
        assert masked_short == "**@b.com"
        
        # Invalid email
        invalid_email = "notanemail"
        masked_invalid = pii_service.mask_email(invalid_email)
        assert len(masked_invalid) <= 12
        assert "*" in masked_invalid
    
    def test_mask_pii_data(self, pii_service):
        """Test complete PII data masking."""
        with patch('sentinel_aml.security.pii_protection.get_settings') as mock_settings:
            mock_settings.return_value.pii_masking_enabled = True
            
            data = {
                "transaction_id": "TXN-001",
                "customer_name": "John Doe",
                "account_number": "1234567890123456",
                "ssn": "123-45-6789",
                "email": "john@example.com",
                "amount": 1000.00
            }
            
            masked_data = pii_service.mask_pii_data(data)
            
            # Non-PII should remain unchanged
            assert masked_data["transaction_id"] == data["transaction_id"]
            assert masked_data["amount"] == data["amount"]
            
            # PII should be masked
            assert masked_data["customer_name"] != data["customer_name"]
            assert masked_data["account_number"] != data["account_number"]
            assert masked_data["ssn"] != data["ssn"]
            assert masked_data["email"] != data["email"]
            
            # Verify specific masking patterns
            assert "***" in masked_data["customer_name"]
            assert "***" in masked_data["ssn"]
            assert "@" in masked_data["email"]  # Domain should be preserved


class TestAccessControlService:
    """Unit tests for access control service."""
    
    @pytest.fixture
    def access_service(self):
        """Create access control service."""
        with patch('sentinel_aml.compliance.audit_storage.get_audit_storage'):
            return AccessControlService()
    
    def test_role_permissions_mapping(self, access_service):
        """Test role to permissions mapping."""
        # AML Analyst should have transaction and risk permissions
        analyst_perms = access_service.role_permissions[Role.AML_ANALYST]
        assert Permission.TRANSACTION_READ in analyst_perms
        assert Permission.RISK_ANALYSIS_READ in analyst_perms
        assert Permission.SAR_READ in analyst_perms
        
        # System Admin should have system permissions
        admin_perms = access_service.role_permissions[Role.SYSTEM_ADMIN]
        assert Permission.SYSTEM_CONFIG in admin_perms
        assert Permission.USER_MANAGEMENT in admin_perms
        
        # Readonly user should have limited permissions
        readonly_perms = access_service.role_permissions[Role.READONLY_USER]
        assert Permission.TRANSACTION_READ in readonly_perms
        assert Permission.SYSTEM_CONFIG not in readonly_perms
    
    def test_user_creation(self, access_service):
        """Test user creation with proper validation."""
        # Create admin user first
        admin_user = User(
            user_id="admin",
            username="admin",
            email="admin@example.com",
            roles=[Role.SYSTEM_ADMIN],
            created_at=datetime.now(timezone.utc)
        )
        access_service._users["admin"] = admin_user
        
        # Create new user
        new_user = access_service.create_user(
            user_id="test_user",
            username="testuser",
            email="test@example.com",
            roles=[Role.AML_ANALYST],
            created_by="admin"
        )
        
        assert new_user.user_id == "test_user"
        assert new_user.username == "testuser"
        assert new_user.email == "test@example.com"
        assert Role.AML_ANALYST in new_user.roles
        assert new_user.is_active == True
    
    def test_user_creation_validation(self, access_service):
        """Test user creation validation."""
        # Create admin user
        admin_user = User(
            user_id="admin",
            username="admin",
            email="admin@example.com",
            roles=[Role.SYSTEM_ADMIN],
            created_at=datetime.now(timezone.utc)
        )
        access_service._users["admin"] = admin_user
        
        # Test invalid email
        with pytest.raises(ValidationError, match="Invalid email format"):
            access_service.create_user(
                user_id="test_user",
                username="testuser",
                email="invalid-email",
                roles=[Role.AML_ANALYST],
                created_by="admin"
            )
        
        # Test unauthorized creation
        with pytest.raises(ValidationError, match="Permission denied"):
            access_service.create_user(
                user_id="test_user2",
                username="testuser2",
                email="test2@example.com",
                roles=[Role.AML_ANALYST],
                created_by="unauthorized_user"
            )
    
    def test_permission_checking(self, access_service):
        """Test permission checking logic."""
        # Create test user
        test_user = User(
            user_id="test_user",
            username="testuser",
            email="test@example.com",
            roles=[Role.AML_ANALYST],
            additional_permissions=[Permission.SAR_REVIEW],
            created_at=datetime.now(timezone.utc)
        )
        access_service._users["test_user"] = test_user
        
        # Should have role-based permissions
        assert access_service.has_permission("test_user", Permission.TRANSACTION_READ) == True
        assert access_service.has_permission("test_user", Permission.RISK_ANALYSIS_READ) == True
        
        # Should have additional permissions
        assert access_service.has_permission("test_user", Permission.SAR_REVIEW) == True
        
        # Should not have admin permissions
        assert access_service.has_permission("test_user", Permission.SYSTEM_CONFIG) == False
        assert access_service.has_permission("test_user", Permission.USER_MANAGEMENT) == False
    
    def test_session_management(self, access_service):
        """Test session creation and validation."""
        # Create test user
        test_user = User(
            user_id="session_user",
            username="sessionuser",
            email="session@example.com",
            roles=[Role.AML_ANALYST],
            created_at=datetime.now(timezone.utc)
        )
        access_service._users["session_user"] = test_user
        
        # Create session
        session_id = access_service.create_session(
            user_id="session_user",
            source_ip="192.168.1.100"
        )
        
        assert session_id is not None
        assert len(session_id) > 0
        
        # Validate session
        validated_user = access_service.validate_session(session_id)
        assert validated_user == "session_user"
        
        # Invalidate session
        access_service.invalidate_session(session_id)
        
        # Session should no longer be valid
        validated_user = access_service.validate_session(session_id)
        assert validated_user is None
    
    def test_user_deactivation(self, access_service):
        """Test user deactivation."""
        # Create admin and regular user
        admin_user = User(
            user_id="admin",
            username="admin",
            email="admin@example.com",
            roles=[Role.SYSTEM_ADMIN],
            created_at=datetime.now(timezone.utc)
        )
        access_service._users["admin"] = admin_user
        
        regular_user = User(
            user_id="regular",
            username="regular",
            email="regular@example.com",
            roles=[Role.AML_ANALYST],
            created_at=datetime.now(timezone.utc)
        )
        access_service._users["regular"] = regular_user
        
        # Deactivate user
        access_service.deactivate_user(
            user_id="regular",
            deactivated_by="admin",
            reason="Test deactivation"
        )
        
        # User should be inactive
        assert access_service._users["regular"].is_active == False
        
        # Inactive user should have no permissions
        permissions = access_service.get_user_permissions("regular")
        assert len(permissions) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])