"""Comprehensive unit tests for all security components."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from sentinel_aml.security.data_at_rest_encryption import get_data_at_rest_encryption_service
from sentinel_aml.security.security_validator import get_security_validator
from sentinel_aml.security.encryption import get_encryption_service
from sentinel_aml.security.access_control import get_access_control_service, Role, Permission, User
from sentinel_aml.core.exceptions import ProcessingError, ValidationError


class TestDataAtRestEncryption:
    """Test data-at-rest encryption service."""
    
    @pytest.fixture
    def mock_s3_client(self):
        """Mock S3 client for testing."""
        mock_client = Mock()
        mock_client.put_object.return_value = {'ETag': '"test-etag"'}
        mock_client.get_object.return_value = {
            'Body': Mock(read=Mock(return_value=b'test data')),
            'ServerSideEncryption': 'aws:kms',
            'SSEKMSKeyId': 'test-key-id'
        }
        return mock_client
    
    @pytest.fixture
    def mock_dynamodb_table(self):
        """Mock DynamoDB table for testing."""
        mock_table = Mock()
        mock_table.put_item.return_value = {}
        mock_table.get_item.return_value = {
            'Item': {
                'customer_name': 'encrypted_name',
                'account_number': 'encrypted_account',
                'amount': 1000.00,
                '_encryption_metadata': {
                    'encrypted_at': datetime.now(timezone.utc).isoformat(),
                    'encryption_version': '1.0'
                }
            }
        }
        return mock_table
    
    @pytest.fixture
    def encryption_service(self, mock_s3_client, mock_dynamodb_table):
        """Create encryption service with mocked dependencies."""
        with patch('boto3.client', return_value=mock_s3_client):
            with patch('boto3.resource') as mock_resource:
                mock_dynamodb = Mock()
                mock_dynamodb.Table.return_value = mock_dynamodb_table
                mock_resource.return_value = mock_dynamodb
                
                with patch('sentinel_aml.security.data_at_rest_encryption.get_settings') as mock_settings:
                    mock_settings.return_value.encryption_key_id = 'test-key-id'
                    mock_settings.return_value.aws_region = 'us-east-1'
                    
                    service = get_data_at_rest_encryption_service()
                    # Clear cache to get fresh instance
                    get_data_at_rest_encryption_service.cache_clear()
                    return service
    
    def test_encrypt_s3_object_string(self, encryption_service, mock_s3_client):
        """Test S3 object encryption with string data."""
        bucket = "test-bucket"
        key = "test-key"
        data = "sensitive financial data"
        
        etag = encryption_service.encrypt_s3_object(bucket, key, data)
        
        assert etag == "test-etag"
        mock_s3_client.put_object.assert_called_once()
        
        # Verify encryption parameters
        call_args = mock_s3_client.put_object.call_args[1]
        assert call_args['Bucket'] == bucket
        assert call_args['Key'] == key
        assert call_args['ServerSideEncryption'] == 'aws:kms'
        assert call_args['SSEKMSKeyId'] == 'test-key-id'
    
    def test_encrypt_s3_object_dict(self, encryption_service, mock_s3_client):
        """Test S3 object encryption with dictionary data."""
        bucket = "test-bucket"
        key = "test-key"
        data = {"customer_name": "John Doe", "amount": 1000.00}
        
        etag = encryption_service.encrypt_s3_object(bucket, key, data)
        
        assert etag == "test-etag"
        
        # Verify JSON serialization
        call_args = mock_s3_client.put_object.call_args[1]
        assert call_args['ContentType'] == 'application/json'
    
    def test_decrypt_s3_object(self, encryption_service, mock_s3_client):
        """Test S3 object decryption."""
        bucket = "test-bucket"
        key = "test-key"
        
        result = encryption_service.decrypt_s3_object(bucket, key, return_type='str')
        
        assert result == "test data"
        mock_s3_client.get_object.assert_called_once_with(Bucket=bucket, Key=key)
    
    def test_encrypt_dynamodb_item(self, encryption_service, mock_dynamodb_table):
        """Test DynamoDB item encryption."""
        table_name = "test-table"
        item = {
            "customer_name": "Jane Smith",
            "account_number": "1234567890",
            "amount": 500.00
        }
        pii_fields = ["customer_name", "account_number"]
        
        with patch.object(encryption_service.encryption_service, 'encrypt_field') as mock_encrypt:
            mock_encrypt.side_effect = lambda field, value: f"encrypted_{value}"
            
            result = encryption_service.encrypt_dynamodb_item(table_name, item, pii_fields)
            
            # Verify PII fields were encrypted
            assert result["customer_name"] == "encrypted_Jane Smith"
            assert result["account_number"] == "encrypted_1234567890"
            assert result["amount"] == 500.00  # Non-PII unchanged
            assert "_encryption_metadata" in result
            
            mock_dynamodb_table.put_item.assert_called_once()
    
    def test_decrypt_dynamodb_item(self, encryption_service, mock_dynamodb_table):
        """Test DynamoDB item decryption."""
        table_name = "test-table"
        key = {"id": "test-id"}
        pii_fields = ["customer_name", "account_number"]
        
        with patch.object(encryption_service.encryption_service, 'decrypt_field') as mock_decrypt:
            mock_decrypt.side_effect = lambda field, value: value.replace("encrypted_", "")
            
            result = encryption_service.decrypt_dynamodb_item(table_name, key, pii_fields)
            
            # Verify decryption
            assert "customer_name" in result
            assert "_encryption_metadata" not in result  # Metadata removed
            
            mock_dynamodb_table.get_item.assert_called_once_with(Key=key)
    
    def test_configure_s3_bucket_encryption(self, encryption_service, mock_s3_client):
        """Test S3 bucket encryption configuration."""
        bucket_name = "test-bucket"
        
        result = encryption_service.configure_s3_bucket_encryption(bucket_name)
        
        assert result is True
        
        # Verify encryption configuration
        mock_s3_client.put_bucket_encryption.assert_called_once()
        encryption_call = mock_s3_client.put_bucket_encryption.call_args[1]
        
        assert encryption_call['Bucket'] == bucket_name
        rules = encryption_call['ServerSideEncryptionConfiguration']['Rules']
        assert rules[0]['ApplyServerSideEncryptionByDefault']['SSEAlgorithm'] == 'aws:kms'
        
        # Verify public access block
        mock_s3_client.put_public_access_block.assert_called_once()
    
    def test_verify_encryption_compliance(self, encryption_service):
        """Test encryption compliance verification."""
        with patch.object(encryption_service, '_check_s3_encryption_compliance', return_value=True):
            with patch.object(encryption_service, '_check_dynamodb_encryption_compliance', return_value=True):
                
                report = encryption_service.verify_encryption_compliance()
                
                assert report["overall_compliant"] is True
                assert "s3" in report["services"]
                assert "dynamodb" in report["services"]
                assert report["services"]["s3"]["compliant"] is True
                assert report["services"]["dynamodb"]["compliant"] is True


class TestSecurityValidator:
    """Test security validation service."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all service dependencies."""
        with patch('sentinel_aml.security.security_validator.get_encryption_service') as mock_enc:
            with patch('sentinel_aml.security.security_validator.get_tls_config') as mock_tls:
                with patch('sentinel_aml.security.security_validator.get_access_control_service') as mock_ac:
                    with patch('sentinel_aml.security.security_validator.get_pii_service') as mock_pii:
                        with patch('sentinel_aml.security.security_validator.get_audit_logger') as mock_audit:
                            
                            # Configure mocks
                            mock_enc.return_value = Mock()
                            mock_tls.return_value = Mock()
                            mock_ac.return_value = Mock()
                            mock_pii.return_value = Mock()
                            mock_audit.return_value = Mock()
                            
                            yield {
                                'encryption': mock_enc.return_value,
                                'tls': mock_tls.return_value,
                                'access_control': mock_ac.return_value,
                                'pii': mock_pii.return_value,
                                'audit': mock_audit.return_value
                            }
    
    @pytest.fixture
    def validator(self, mock_dependencies):
        """Create security validator with mocked dependencies."""
        with patch('boto3.client'):
            with patch('sentinel_aml.security.security_validator.get_settings') as mock_settings:
                mock_settings.return_value.encryption_key_id = 'test-key-id'
                mock_settings.return_value.aws_region = 'us-east-1'
                mock_settings.return_value.pii_masking_enabled = True
                mock_settings.return_value.audit_log_retention_days = 2555
                
                validator = get_security_validator()
                # Clear cache to get fresh instance
                get_security_validator.cache_clear()
                return validator
    
    def test_validate_encryption_implementation_success(self, validator, mock_dependencies):
        """Test successful encryption validation."""
        # Mock successful encryption test
        mock_dependencies['encryption'].encrypt_data.return_value = "encrypted_data"
        mock_dependencies['encryption'].decrypt_data.return_value = "test encryption data"
        mock_dependencies['encryption'].encrypt_pii_record.return_value = {
            "customer_name": "encrypted_name",
            "account_number": "encrypted_account",
            "amount": 1000.00
        }
        mock_dependencies['encryption'].decrypt_pii_record.return_value = {
            "customer_name": "Test User",
            "account_number": "1234567890",
            "amount": 1000.00
        }
        
        with patch.object(validator.kms_client, 'describe_key'):
            result = validator.validate_encryption_implementation()
            
            assert result["status"] == "PASS"
            assert result["checks"]["kms_key_configured"] is True
            assert result["checks"]["kms_key_accessible"] is True
            assert result["checks"]["encryption_functional"] is True
            assert result["checks"]["pii_encryption_functional"] is True
    
    def test_validate_encryption_implementation_failure(self, validator, mock_dependencies):
        """Test encryption validation with failures."""
        # Mock encryption failure
        mock_dependencies['encryption'].encrypt_data.side_effect = Exception("Encryption failed")
        
        with patch.object(validator.kms_client, 'describe_key'):
            result = validator.validate_encryption_implementation()
            
            assert result["status"] == "FAIL"
            assert "Encryption test failed" in str(result["issues"])
    
    def test_validate_tls_configuration_success(self, validator, mock_dependencies):
        """Test successful TLS validation."""
        import ssl
        
        # Mock SSL context
        mock_context = Mock()
        mock_context.minimum_version = ssl.TLSVersion.TLSv1_3
        mock_context.verify_mode = ssl.CERT_REQUIRED
        mock_context.check_hostname = True
        
        mock_dependencies['tls'].create_ssl_context.return_value = mock_context
        mock_dependencies['tls'].create_secure_session.return_value = Mock()
        
        result = validator.validate_tls_configuration()
        
        assert result["status"] == "PASS"
        assert result["checks"]["tls_1_3_enforced"] is True
        assert result["checks"]["certificate_verification"] is True
        assert result["checks"]["hostname_verification"] is True
        assert result["checks"]["secure_session_creation"] is True
    
    def test_validate_access_control_success(self, validator, mock_dependencies):
        """Test successful access control validation."""
        # Mock role permissions
        mock_dependencies['access_control'].role_permissions = {
            Role.AML_ANALYST: {Permission.TRANSACTION_READ, Permission.SAR_READ},
            Role.SYSTEM_ADMIN: {Permission.SYSTEM_CONFIG, Permission.USER_MANAGEMENT},
            Role.INVESTIGATOR: {Permission.PII_DECRYPT},
            Role.AUDITOR: {Permission.AUDIT_READ},
            Role.COMPLIANCE_OFFICER: {Permission.SAR_REVIEW},
            Role.DATA_SCIENTIST: {Permission.MODEL_DEPLOY},
            Role.READONLY_USER: {Permission.TRANSACTION_READ}
        }
        
        result = validator.validate_access_control()
        
        assert result["status"] == "PASS"
        assert result["checks"]["permission_separation"] is True
        assert result["checks"]["admin_permissions"] is True
        assert result["checks"]["pii_access_control"] is True
    
    def test_validate_pii_protection_success(self, validator, mock_dependencies):
        """Test successful PII protection validation."""
        # Mock PII masking
        mock_dependencies['pii'].mask_pii_data.return_value = {
            "customer_name": "J*** D**",
            "account_number": "************3456",
            "ssn": "***-**-6789",
            "email": "j***e@example.com",
            "amount": 1000.00
        }
        
        # Mock pattern detection
        mock_dependencies['pii'].scan_for_pii_patterns.return_value = {
            "ssn": ["123-45-6789"],
            "email": ["john@example.com"]
        }
        
        result = validator.validate_pii_protection()
        
        assert result["status"] == "PASS"
        assert result["checks"]["pii_masking_functional"] is True
        assert result["checks"]["pii_pattern_detection"] is True
        assert result["checks"]["pii_masking_enabled"] is True
    
    def test_validate_audit_logging_success(self, validator, mock_dependencies):
        """Test successful audit logging validation."""
        # Mock audit logging
        mock_dependencies['audit'].log_event.return_value = "test-event-id"
        
        result = validator.validate_audit_logging()
        
        assert result["status"] == "PASS"
        assert result["checks"]["audit_logging_functional"] is True
        assert result["checks"]["audit_retention_compliant"] is True
        assert result["checks"]["audit_pii_protection"] is True
    
    def test_validate_all_security_measures_success(self, validator):
        """Test comprehensive security validation success."""
        # Mock all validation methods to return success
        with patch.object(validator, 'validate_encryption_implementation') as mock_enc:
            with patch.object(validator, 'validate_tls_configuration') as mock_tls:
                with patch.object(validator, 'validate_access_control') as mock_ac:
                    with patch.object(validator, 'validate_pii_protection') as mock_pii:
                        with patch.object(validator, 'validate_audit_logging') as mock_audit:
                            
                            # Configure all validations to pass
                            mock_enc.return_value = {"status": "PASS", "issues": []}
                            mock_tls.return_value = {"status": "PASS", "issues": []}
                            mock_ac.return_value = {"status": "PASS", "issues": []}
                            mock_pii.return_value = {"status": "PASS", "issues": []}
                            mock_audit.return_value = {"status": "PASS", "issues": []}
                            
                            result = validator.validate_all_security_measures()
                            
                            assert result["overall_status"] == "PASS"
                            assert len(result["critical_issues"]) == 0
                            assert "validations" in result
                            assert "recommendations" in result
    
    def test_validate_all_security_measures_failure(self, validator):
        """Test comprehensive security validation with failures."""
        # Mock some validation methods to fail
        with patch.object(validator, 'validate_encryption_implementation') as mock_enc:
            with patch.object(validator, 'validate_tls_configuration') as mock_tls:
                with patch.object(validator, 'validate_access_control') as mock_ac:
                    with patch.object(validator, 'validate_pii_protection') as mock_pii:
                        with patch.object(validator, 'validate_audit_logging') as mock_audit:
                            
                            # Configure some validations to fail
                            mock_enc.return_value = {"status": "FAIL", "issues": ["Encryption failed"]}
                            mock_tls.return_value = {"status": "PASS", "issues": []}
                            mock_ac.return_value = {"status": "FAIL", "issues": ["Access control failed"]}
                            mock_pii.return_value = {"status": "PASS", "issues": []}
                            mock_audit.return_value = {"status": "PASS", "issues": []}
                            
                            result = validator.validate_all_security_measures()
                            
                            assert result["overall_status"] == "FAIL"
                            assert len(result["critical_issues"]) == 2
                            assert "Encryption failed" in result["critical_issues"]
                            assert "Access control failed" in result["critical_issues"]
    
    def test_generate_security_compliance_report(self, validator):
        """Test security compliance report generation."""
        # Mock validation results
        with patch.object(validator, 'validate_all_security_measures') as mock_validate:
            mock_validate.return_value = {
                "overall_status": "PASS",
                "validations": {
                    "encryption": {"status": "PASS", "checks": {"test": True}},
                    "tls": {"status": "PASS", "checks": {"test": True}},
                    "access_control": {"status": "PASS", "checks": {"test": True}},
                    "pii_protection": {"status": "PASS", "checks": {"test": True}},
                    "audit_logging": {"status": "PASS", "checks": {"test": True}}
                },
                "critical_issues": [],
                "recommendations": ["Test recommendation"]
            }
            
            report = validator.generate_security_compliance_report()
            
            assert "report_metadata" in report
            assert "executive_summary" in report
            assert "detailed_results" in report
            assert "compliance_frameworks" in report
            
            # Check executive summary
            summary = report["executive_summary"]
            assert summary["overall_compliance_status"] == "PASS"
            assert summary["total_checks"] == 5
            assert summary["passed_checks"] == 5
            
            # Check compliance frameworks
            frameworks = report["compliance_frameworks"]
            assert "BSA_AML" in frameworks
            assert "SOX" in frameworks
            assert "PCI_DSS" in frameworks
            
            # All should be compliant
            assert frameworks["BSA_AML"]["data_protection"] is True
            assert frameworks["SOX"]["access_controls"] is True
            assert frameworks["PCI_DSS"]["encryption"] is True


class TestSecurityIntegrationScenarios:
    """Test security integration scenarios."""
    
    def test_end_to_end_transaction_security(self):
        """Test complete transaction security workflow."""
        # This would test the full security workflow:
        # 1. Transaction received with PII
        # 2. PII encrypted before storage
        # 3. Access control enforced for retrieval
        # 4. Audit logging throughout
        # 5. TLS for all communications
        
        # Mock transaction data
        transaction_data = {
            "transaction_id": "TXN-SEC-001",
            "customer_name": "John Doe",
            "account_number": "1234567890123456",
            "amount": 15000.00,
            "currency": "USD"
        }
        
        # This test would verify the complete security chain
        # For now, we'll just verify the components exist
        assert get_encryption_service() is not None
        assert get_security_validator() is not None
        assert get_data_at_rest_encryption_service() is not None
    
    def test_compliance_audit_scenario(self):
        """Test compliance audit scenario."""
        # This would test:
        # 1. Auditor requests compliance report
        # 2. Access control validates auditor permissions
        # 3. Security validator runs all checks
        # 4. Report generated with PII masked
        # 5. All actions logged for audit trail
        
        validator = get_security_validator()
        
        # Mock successful validation
        with patch.object(validator, 'validate_all_security_measures') as mock_validate:
            mock_validate.return_value = {
                "overall_status": "PASS",
                "validations": {},
                "critical_issues": [],
                "recommendations": []
            }
            
            report = validator.generate_security_compliance_report()
            assert report is not None
            assert "compliance_frameworks" in report
    
    def test_security_incident_response(self):
        """Test security incident response scenario."""
        # This would test:
        # 1. Security incident detected
        # 2. Immediate audit logging
        # 3. Access revocation if needed
        # 4. Encryption key rotation
        # 5. Compliance notification
        
        # For now, verify audit logging works
        from sentinel_aml.compliance.audit_logger import get_audit_logger, AuditEventType
        
        audit_logger = get_audit_logger()
        
        # Mock audit storage
        with patch('sentinel_aml.compliance.audit_storage.get_audit_storage') as mock_storage:
            mock_storage_instance = Mock()
            mock_storage.return_value = mock_storage_instance
            
            # Log security incident
            event_id = audit_logger.log_event(
                event_type=AuditEventType.SUSPICIOUS_ACTIVITY_FLAGGED,
                action="security_incident_detected",
                outcome="SUCCESS",
                details={"incident_type": "unauthorized_access_attempt"}
            )
            
            assert event_id is not None
            assert mock_storage_instance.store_audit_record.called