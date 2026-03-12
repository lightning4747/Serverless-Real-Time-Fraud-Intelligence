"""AES-256 encryption service using AWS KMS for key management."""

import base64
import json
import os
from functools import lru_cache
from typing import Any, Dict, Optional, Union

import boto3
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from sentinel_aml.core.config import get_settings
from sentinel_aml.core.exceptions import ProcessingError
from sentinel_aml.core.logging import get_logger

logger = get_logger(__name__)


class EncryptionService:
    """AES-256 encryption service with AWS KMS integration."""
    
    def __init__(self, kms_key_id: Optional[str] = None):
        """Initialize encryption service with KMS key."""
        self.settings = get_settings()
        self.kms_key_id = kms_key_id or self.settings.encryption_key_id
        
        if not self.kms_key_id:
            raise ValueError("KMS key ID must be provided for encryption")
        
        # Initialize AWS KMS client
        self.kms_client = boto3.client('kms', region_name=self.settings.aws_region)
        
        # Cache for data encryption keys
        self._dek_cache: Dict[str, bytes] = {}
        
    def _get_data_encryption_key(self, context: Optional[Dict[str, str]] = None) -> bytes:
        """Get or generate a data encryption key from KMS."""
        try:
            # Create cache key from context
            cache_key = json.dumps(context or {}, sort_keys=True)
            
            if cache_key in self._dek_cache:
                return self._dek_cache[cache_key]
            
            # Generate new data key from KMS
            response = self.kms_client.generate_data_key(
                KeyId=self.kms_key_id,
                KeySpec='AES_256',
                EncryptionContext=context or {}
            )
            
            # Cache the plaintext key (in memory only)
            plaintext_key = response['Plaintext']
            self._dek_cache[cache_key] = plaintext_key
            
            logger.info("Generated new data encryption key from KMS")
            return plaintext_key
            
        except Exception as e:
            logger.error(f"Failed to get data encryption key: {e}")
            raise ProcessingError(f"Encryption key generation failed: {e}")
    
    def encrypt_data(
        self, 
        data: Union[str, bytes, Dict[str, Any]], 
        context: Optional[Dict[str, str]] = None
    ) -> str:
        """Encrypt data using AES-256 with KMS-managed keys.
        
        Args:
            data: Data to encrypt (string, bytes, or dict)
            context: Encryption context for KMS
            
        Returns:
            Base64-encoded encrypted data
        """
        try:
            # Convert data to bytes
            if isinstance(data, dict):
                data_bytes = json.dumps(data).encode('utf-8')
            elif isinstance(data, str):
                data_bytes = data.encode('utf-8')
            else:
                data_bytes = data
            
            # Get data encryption key
            dek = self._get_data_encryption_key(context)
            
            # Create Fernet cipher with the DEK
            fernet = Fernet(base64.urlsafe_b64encode(dek[:32]))
            
            # Encrypt the data
            encrypted_data = fernet.encrypt(data_bytes)
            
            # Return base64-encoded result
            return base64.b64encode(encrypted_data).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Data encryption failed: {e}")
            raise ProcessingError(f"Failed to encrypt data: {e}")
    
    def decrypt_data(
        self, 
        encrypted_data: str, 
        context: Optional[Dict[str, str]] = None,
        return_type: str = 'str'
    ) -> Union[str, bytes, Dict[str, Any]]:
        """Decrypt data using AES-256 with KMS-managed keys.
        
        Args:
            encrypted_data: Base64-encoded encrypted data
            context: Encryption context for KMS
            return_type: Type to return ('str', 'bytes', 'dict')
            
        Returns:
            Decrypted data in specified format
        """
        try:
            # Decode base64
            encrypted_bytes = base64.b64decode(encrypted_data.encode('utf-8'))
            
            # Get data encryption key
            dek = self._get_data_encryption_key(context)
            
            # Create Fernet cipher with the DEK
            fernet = Fernet(base64.urlsafe_b64encode(dek[:32]))
            
            # Decrypt the data
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            
            # Return in requested format
            if return_type == 'bytes':
                return decrypted_bytes
            elif return_type == 'dict':
                return json.loads(decrypted_bytes.decode('utf-8'))
            else:
                return decrypted_bytes.decode('utf-8')
                
        except Exception as e:
            logger.error(f"Data decryption failed: {e}")
            raise ProcessingError(f"Failed to decrypt data: {e}")
    
    def encrypt_field(self, field_name: str, value: Any) -> str:
        """Encrypt a specific field with field-specific context."""
        context = {
            'field_name': field_name,
            'service': 'sentinel-aml'
        }
        return self.encrypt_data(value, context)
    
    def decrypt_field(self, field_name: str, encrypted_value: str) -> str:
        """Decrypt a specific field with field-specific context."""
        context = {
            'field_name': field_name,
            'service': 'sentinel-aml'
        }
        return self.decrypt_data(encrypted_value, context)
    
    def encrypt_pii_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt PII fields in a record while preserving structure."""
        # Fields that should be encrypted
        pii_fields = {
            'customer_name', 'beneficiary_name', 'account_number', 
            'ssn', 'tax_id', 'phone', 'email', 'address',
            'routing_number', 'swift_code'
        }
        
        encrypted_record = record.copy()
        
        for field_name, value in record.items():
            if field_name.lower() in pii_fields and value is not None:
                try:
                    encrypted_record[field_name] = self.encrypt_field(field_name, value)
                    logger.debug(f"Encrypted field: {field_name}")
                except Exception as e:
                    logger.warning(f"Failed to encrypt field {field_name}: {e}")
                    # Keep original value if encryption fails
                    encrypted_record[field_name] = value
        
        return encrypted_record
    
    def decrypt_pii_record(self, encrypted_record: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt PII fields in a record."""
        pii_fields = {
            'customer_name', 'beneficiary_name', 'account_number',
            'ssn', 'tax_id', 'phone', 'email', 'address',
            'routing_number', 'swift_code'
        }
        
        decrypted_record = encrypted_record.copy()
        
        for field_name, value in encrypted_record.items():
            if field_name.lower() in pii_fields and value is not None:
                try:
                    decrypted_record[field_name] = self.decrypt_field(field_name, value)
                    logger.debug(f"Decrypted field: {field_name}")
                except Exception as e:
                    logger.warning(f"Failed to decrypt field {field_name}: {e}")
                    # Keep encrypted value if decryption fails
                    decrypted_record[field_name] = value
        
        return decrypted_record


@lru_cache()
def get_encryption_service() -> EncryptionService:
    """Get cached encryption service instance."""
    return EncryptionService()


def encrypt_data(
    data: Union[str, bytes, Dict[str, Any]], 
    context: Optional[Dict[str, str]] = None
) -> str:
    """Convenience function to encrypt data."""
    service = get_encryption_service()
    return service.encrypt_data(data, context)


def decrypt_data(
    encrypted_data: str, 
    context: Optional[Dict[str, str]] = None,
    return_type: str = 'str'
) -> Union[str, bytes, Dict[str, Any]]:
    """Convenience function to decrypt data."""
    service = get_encryption_service()
    return service.decrypt_data(encrypted_data, context, return_type)