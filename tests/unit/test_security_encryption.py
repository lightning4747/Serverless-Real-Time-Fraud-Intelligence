"""Unit tests for encryption and data protection mechanisms."""

import json
import pytest
from unittest.mock import Mock, patch

from sentinel_aml.security.encryption import EncryptionService, encrypt_data, decrypt_data
from sentinel_aml.core.exceptions import ProcessingError


class TestEncryptionService:
    """Test encryption service functionality."""
    
    @pytest.fixture
    def mock_kms_client(self):
        """Mock KMS client for testing."""
        mock_client = Mock()
        mock_client.generate_data_key.return_value = {
            'Plaintext': b'a' * 32,  # 32-byte key for AES-256
            'CiphertextBlob': b'encrypted_key_data'
        }
        return mock_client
    
    @pytest.fixture
    def encryption_service(self, mock_kms_client):
        """Create encryption service with mocked KMS."""
        with patch('boto3.client', return_value=mock_kms_client):
            service = EncryptionService(kms_key_id='test-key-id')
            return service
    
    def test_encrypt_decrypt_string(self, encryption_service):
        """Test string encryption and decryption."""
        original_data = "sensitive customer information"
        
        # Encrypt data
        encrypted = encryption_service.encrypt_data(original_data)
        assert encrypted != original_data
        assert isinstance(encrypted, str)
        
        # Decrypt data
        decrypted = encryption_service.decrypt_data(encrypted)
        assert decrypted == original_data
    
    def test_encrypt_decrypt_dict(self, encryption_service):
        """Test dictionary encryption and decryption."""
        original_data = {
            "customer_name": "John Doe",
            "account_number": "1234567890",
            "amount": 1000.50
        }
        
        # Encrypt data
        encrypted = encryption_service.encrypt_data(original_data)
        assert encrypted != str(original_data)
        
        # Decrypt data
        decrypted = encryption_service.decrypt_data(encrypted, return_type='dict')
        assert decrypted == original_data
    
    def test_encrypt_with_context(self, encryption_service):
        """Test encryption with context for key derivation."""
        data = "test data"
        context = {"field_name": "customer_name", "service": "sentinel-aml"}
        
        encrypted1 = encryption_service.encrypt_data(data, context)
        encrypted2 = encryption_service.encrypt_data(data, context)
        
        # Same context should produce same key (cached)
        # But different encrypted output due to Fernet's built-in randomness
        assert encrypted1 != encrypted2  # Fernet adds randomness
        
        # Both should decrypt to same value
        decrypted1 = encryption_service.decrypt_data(encrypted1, context)
        decrypted2 = encryption_service.decrypt_data(encrypted2, context)
        assert decrypted1 == decrypted2 == data
    
    def test_encrypt_pii_record(self, encryption_service):
        """Test PII record encryption."""
        record = {
            "transaction_id": "TXN-123",
            "customer_name": "Jane Smith",
            "account_number": "9876543210",
            "amount": 500.00,
            "currency": "USD"
        }
        
        encrypted_record = encryption_service.encrypt_pii_record(record)
        
        # Non-PII fields should remain unchanged
        assert encrypted_record["transaction_id"] == record["transaction_id"]
        assert encrypted_record["amount"] == record["amount"]
        assert encrypted_record["currency"] == record["currency"]
        
        # PII fields should be encrypted
        assert encrypted_record["customer_name"] != record["customer_name"]
        assert encrypted_record["account_number"] != record["account_number"]
    
    def test_decrypt_pii_record(self, encryption_service):
        """Test PII record decryption."""
        original_record = {
            "transaction_id": "TXN-123",
            "customer_name": "Jane Smith",
            "account_number": "9876543210",
            "amount": 500.00
        }
        
        # Encrypt then decrypt
        encrypted_record = encryption_service.encrypt_pii_record(original_record)
        decrypted_record = encryption_service.decrypt_pii_record(encrypted_record)
        
        assert decrypted_record == original_record
    
    def test_encryption_failure_handling(self, mock_kms_client):
        """Test handling of encryption failures."""
        mock_kms_client.generate_data_key.side_effect = Exception("KMS error")
        
        with patch('boto3.client', return_value=mock_kms_client):
            service = EncryptionService(kms_key_id='test-key-id')
            
            with pytest.raises(ProcessingError):
                service.encrypt_data("test data")
    
    def test_missing_kms_key_id(self):
        """Test error when KMS key ID is not provided."""
        with pytest.raises(ValueError, match="KMS key ID must be provided"):
            EncryptionService(kms_key_id=None)
    
    def test_convenience_functions(self, mock_kms_client):
        """Test convenience functions for encryption/decryption."""
        with patch('boto3.client', return_value=mock_kms_client):
            with patch('sentinel_aml.security.encryption.get_settings') as mock_settings:
                mock_settings.return_value.encryption_key_id = 'test-key'
                mock_settings.return_value.aws_region = 'us-east-1'
                
                data = "test data"
                encrypted = encrypt_data(data)
                decrypted = decrypt_data(encrypted)
                
                assert decrypted == data


class TestEncryptionIntegration:
    """Integration tests for encryption with other components."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock()
        settings.encryption_key_id = 'test-kms-key-id'
        settings.aws_region = 'us-east-1'
        return settings
    
    def test_field_encryption_with_context(self, encryption_service):
        """Test field-specific encryption with context."""
        field_name = "customer_name"
        value = "John Doe"
        
        encrypted = encryption_service.encrypt_field(field_name, value)
        decrypted = encryption_service.decrypt_field(field_name, encrypted)
        
        assert decrypted == value
    
    def test_different_fields_different_encryption(self, encryption_service):
        """Test that different fields produce different encrypted values."""
        value = "same value"
        
        encrypted1 = encryption_service.encrypt_field("field1", value)
        encrypted2 = encryption_service.encrypt_field("field2", value)
        
        # Different field contexts should produce different encrypted values
        assert encrypted1 != encrypted2
        
        # But both should decrypt to the same original value
        decrypted1 = encryption_service.decrypt_field("field1", encrypted1)
        decrypted2 = encryption_service.decrypt_field("field2", encrypted2)
        
        assert decrypted1 == decrypted2 == value