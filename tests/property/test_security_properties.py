"""Property-based tests for security components."""

import pytest
from hypothesis import given, strategies as st, assume, settings
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch
import re

from sentinel_aml.security.encryption import EncryptionService
from sentinel_aml.security.pii_protection import PIIProtectionService
from sentinel_aml.security.access_control import AccessControlService, Role, Permission, User


class TestEncryptionProperties:
    """Property-based tests for encryption service."""
    
    @pytest.fixture
    def mock_encryption_service(self):
        """Create mocked encryption service."""
        mock_kms = Mock()
        mock_kms.generate_data_key.return_value = {
            'Plaintext': b'test_key_32_bytes_long_for_aes256',
            'CiphertextBlob': b'encrypted_key_data'
        }
        
        with patch('boto3.client', return_value=mock_kms):
            with patch('sentinel_aml.security.encryption.get_settings') as mock_settings:
                mock_settings.return_value.encryption_key_id = 'test-key'
                mock_settings.return_value.aws_region = 'us-east-1'
                return EncryptionService()
    
    @given(st.text(min_size=1, max_size=1000))
    def test_encryption_roundtrip_property(self, mock_encryption_service, plaintext):
        """Property: Encryption followed by decryption returns original data."""
        assume(len(plaintext.encode('utf-8')) > 0)  # Non-empty after encoding
        
        # Encrypt then decrypt
        encrypted = mock_encryption_service.encrypt_data(plaintext)
        decrypted = mock_encryption_service.decrypt_data(encrypted)
        
        # Should get back original data
        assert decrypted == plaintext
    
    @given(st.text(min_size=1, max_size=1000))
    def test_encryption_deterministic_property(self, mock_encryption_service, plaintext):
        """Property: Same plaintext with same context produces different ciphertext (due to IV)."""
        assume(len(plaintext.encode('utf-8')) > 0)
        
        # Encrypt same data twice
        encrypted1 = mock_encryption_service.encrypt_data(plaintext)
        encrypted2 = mock_encryption_service.encrypt_data(plaintext)
        
        # Should produce different ciphertext (due to random IV)
        assert encrypted1 != encrypted2
        
        # But both should decrypt to same plaintext
        decrypted1 = mock_encryption_service.decrypt_data(encrypted1)
        decrypted2 = mock_encryption_service.decrypt_data(encrypted2)
        assert decrypted1 == decrypted2 == plaintext
    
    @given(st.dictionaries(
        keys=st.sampled_from(['customer_name', 'account_number', 'ssn', 'email', 'transaction_id', 'amount']),
        values=st.one_of(st.text(min_size=1, max_size=100), st.floats(min_value=0, max_value=1000000)),
        min_size=1,
        max_size=10
    ))
    def test_pii_encryption_preserves_non_pii_property(self, mock_encryption_service, record):
        """Property: PII encryption preserves non-PII fields unchanged."""
        # Define PII fields
        pii_fields = {'customer_name', 'account_number', 'ssn', 'email'}
        
        # Encrypt PII record
        encrypted_record = mock_encryption_service.encrypt_pii_record(record)
        
        # Non-PII fields should remain unchanged
        for field, value in record.items():
            if field not in pii_fields:
                assert encrypted_record[field] == value
        
        # PII fields should be different (if they exist and are strings)
        for field, value in record.items():
            if field in pii_fields and isinstance(value, str) and value:
                assert encrypted_record[field] != value


class TestPIIProtectionProperties:
    """Property-based tests for PII protection service."""
    
    @pytest.fixture
    def pii_service(self):
        """Create PII protection service."""
        return PIIProtectionService()
    
    @given(st.text(min_size=16, max_size=20, alphabet=st.characters(whitelist_categories=('Nd',))))
    def test_account_masking_property(self, pii_service, account_number):
        """Property: Account number masking always shows last 4 digits."""
        assume(len(account_number) >= 4)
        
        masked = pii_service.mask_account_number(account_number)
        
        # Should end with last 4 digits of original
        assert masked.endswith(account_number[-4:])
        
        # Should contain asterisks for hidden digits
        if len(account_number) > 4:
            assert '*' in masked
        
        # Should be same length as original
        assert len(masked) == len(account_number)
    
    @given(st.text(min_size=9, max_size=11, alphabet=st.characters(whitelist_categories=('Nd', 'Pd'))))
    def test_ssn_masking_property(self, pii_service, ssn_like):
        """Property: SSN masking preserves format and shows last 4 digits."""
        # Filter to SSN-like patterns
        digits_only = re.sub(r'[^\d]', '', ssn_like)
        assume(len(digits_only) == 9)  # Valid SSN has 9 digits
        
        masked = pii_service.mask_ssn(ssn_like)
        
        # Should end with last 4 digits
        assert masked.endswith(digits_only[-4:])
        
        # Should contain asterisks
        assert '*' in masked
        
        # Should maintain SSN format
        assert len(masked.split('-')) == 3 or '*' in masked
    
    @given(st.emails())
    def test_email_masking_property(self, pii_service, email):
        """Property: Email masking preserves domain and @ symbol."""
        masked = pii_service.mask_email(email)
        
        # Should contain @ symbol
        assert '@' in masked
        
        # Domain should be preserved
        original_domain = email.split('@')[1]
        masked_domain = masked.split('@')[1]
        assert masked_domain == original_domain
        
        # Local part should contain asterisks (unless very short)
        local_part = masked.split('@')[0]
        if len(email.split('@')[0]) > 2:
            assert '*' in local_part
    
    @given(st.dictionaries(
        keys=st.sampled_from([
            'customer_name', 'account_number', 'ssn', 'email', 'phone',
            'transaction_id', 'amount', 'currency', 'timestamp'
        ]),
        values=st.one_of(
            st.text(min_size=1, max_size=50),
            st.floats(min_value=0, max_value=1000000),
            st.integers(min_value=0, max_value=1000000)
        ),
        min_size=1,
        max_size=10
    ))
    def test_pii_masking_preserves_structure_property(self, pii_service, data):
        """Property: PII masking preserves data structure and non-PII fields."""
        with patch('sentinel_aml.security.pii_protection.get_settings') as mock_settings:
            mock_settings.return_value.pii_masking_enabled = True
            
            masked_data = pii_service.mask_pii_data(data)
            
            # Should have same keys
            assert set(masked_data.keys()) == set(data.keys())
            
            # Non-PII fields should be unchanged
            non_pii_fields = {'transaction_id', 'amount', 'currency', 'timestamp'}
            for field in non_pii_fields:
                if field in data:
                    assert masked_data[field] == data[field]
            
            # All values should be non-None if original was non-None
            for key, value in data.items():
                if value is not None:
                    assert masked_data[key] is not None


class TestAccessControlProperties:
    """Property-based tests for access control service."""
    
    @pytest.fixture
    def access_service(self):
        """Create access control service."""
        with patch('sentinel_aml.compliance.audit_storage.get_audit_storage'):
            return AccessControlService()
    
    @given(st.sampled_from(list(Role)))
    def test_role_permissions_consistency_property(self, access_service, role):
        """Property: Every role has a consistent set of permissions."""
        permissions = access_service.role_permissions.get(role, set())
        
        # Should have at least one permission (except for potential empty roles)
        # Most roles should have permissions
        if role != Role.READONLY_USER:  # Readonly might have minimal permissions
            assert len(permissions) > 0
        
        # All permissions should be valid Permission enum values
        for perm in permissions:
            assert isinstance(perm, Permission)
    
    @given(
        st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
        st.text(min_size=3, max_size=30, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
        st.emails(),
        st.lists(st.sampled_from(list(Role)), min_size=1, max_size=3, unique=True)
    )
    def test_user_creation_property(self, access_service, user_id, username, email, roles):
        """Property: Valid user creation always succeeds with admin permissions."""
        # Create admin user first
        admin_user = User(
            user_id="admin",
            username="admin",
            email="admin@example.com",
            roles=[Role.SYSTEM_ADMIN],
            created_at=datetime.now(timezone.utc)
        )
        access_service._users["admin"] = admin_user
        
        # Assume valid inputs
        assume(user_id not in access_service._users)  # User doesn't already exist
        assume('@' in email and '.' in email)  # Basic email validation
        
        # Create user should succeed
        created_user = access_service.create_user(
            user_id=user_id,
            username=username,
            email=email,
            roles=roles,
            created_by="admin"
        )
        
        # Verify user properties
        assert created_user.user_id == user_id
        assert created_user.username == username
        assert created_user.email == email
        assert set(created_user.roles) == set(roles)
        assert created_user.is_active == True
        assert created_user.created_at is not None
    
    @given(
        st.sampled_from(list(Role)),
        st.lists(st.sampled_from(list(Permission)), min_size=0, max_size=5, unique=True)
    )
    def test_permission_calculation_property(self, access_service, role, additional_perms):
        """Property: User permissions are union of role permissions and additional permissions."""
        # Create test user
        user = User(
            user_id="test_user",
            username="testuser",
            email="test@example.com",
            roles=[role],
            additional_permissions=additional_perms,
            created_at=datetime.now(timezone.utc)
        )
        access_service._users["test_user"] = user
        
        # Get calculated permissions
        user_permissions = access_service.get_user_permissions("test_user")
        
        # Should include all role permissions
        role_permissions = access_service.role_permissions.get(role, set())
        for perm in role_permissions:
            assert perm in user_permissions
        
        # Should include all additional permissions
        for perm in additional_perms:
            assert perm in user_permissions
        
        # Should not have permissions not granted by role or additional
        expected_permissions = role_permissions.union(set(additional_perms))
        assert user_permissions == expected_permissions
    
    @given(st.integers(min_value=1, max_value=1440))  # 1 minute to 24 hours
    def test_session_timeout_property(self, access_service, timeout_minutes):
        """Property: Sessions expire after specified timeout."""
        # Create test user with custom timeout
        user = User(
            user_id="timeout_user",
            username="timeoutuser",
            email="timeout@example.com",
            roles=[Role.AML_ANALYST],
            session_timeout_minutes=timeout_minutes,
            created_at=datetime.now(timezone.utc)
        )
        access_service._users["timeout_user"] = user
        
        # Create session
        session_id = access_service.create_session("timeout_user")
        
        # Session should be valid initially
        assert access_service.validate_session(session_id) == "timeout_user"
        
        # Simulate timeout by modifying session expiration
        session_data = access_service._active_sessions[session_id]
        session_data["expires_at"] = datetime.now(timezone.utc) - timedelta(minutes=1)
        
        # Session should now be invalid
        assert access_service.validate_session(session_id) is None


@settings(max_examples=50, deadline=5000)  # Reduce examples for faster testing
class TestSecurityInvariants:
    """Test security invariants that must always hold."""
    
    @given(st.text(min_size=1, max_size=100))
    def test_pii_masking_never_reveals_full_data(self, original_data):
        """Invariant: PII masking never reveals the complete original data."""
        pii_service = PIIProtectionService()
        
        # Test different masking functions
        if len(original_data) > 4:
            masked_account = pii_service.mask_account_number(original_data)
            assert masked_account != original_data
            
        masked_name = pii_service.mask_name(original_data)
        if len(original_data) > 1:
            assert masked_name != original_data
    
    @given(st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.text(min_size=1, max_size=100),
        min_size=1,
        max_size=10
    ))
    def test_encryption_never_returns_plaintext(self, data_dict):
        """Invariant: Encryption never returns plaintext data."""
        mock_kms = Mock()
        mock_kms.generate_data_key.return_value = {
            'Plaintext': b'test_key_32_bytes_long_for_aes256',
            'CiphertextBlob': b'encrypted_key_data'
        }
        
        with patch('boto3.client', return_value=mock_kms):
            with patch('sentinel_aml.security.encryption.get_settings') as mock_settings:
                mock_settings.return_value.encryption_key_id = 'test-key'
                mock_settings.return_value.aws_region = 'us-east-1'
                
                encryption_service = EncryptionService()
                
                for key, value in data_dict.items():
                    if value:  # Non-empty values
                        encrypted = encryption_service.encrypt_data(value)
                        # Encrypted data should never equal original
                        assert encrypted != value
                        # Encrypted data should be base64 encoded string
                        assert isinstance(encrypted, str)
                        # Should be longer than original (due to encryption overhead)
                        assert len(encrypted) > len(value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])