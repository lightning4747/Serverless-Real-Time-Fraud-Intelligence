"""Integration tests for security and compliance features."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

from sentinel_aml.security.encryption import get_encryption_service
from sentinel_aml.security.pii_protection import get_pii_service
from sentinel_aml.security.access_control import get_access_control_service, Role, Permission, User
from sentinel_aml.security.iam_integration import get_iam_integration_service
from sentinel_aml.compliance.audit_logger import get_audit_logger, AuditEventType


class TestSecurityIntegration:
    """Test integration between security components."""
    
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
    def mock_iam_client(self):
        """Mock IAM client for testing."""
        mock_client = Mock()
        mock_client.create_role.return_value = {
            'Role': {
                'Arn': 'arn:aws:iam::123456789012:role/test-role'
            }
        }
        mock_client.create_policy.return_value = {
            'Policy': {
                'Arn': 'arn:aws:iam::123456789012:policy/test-policy'
            }
        }
        return mock_client
    
    def test_end_to_end_pii_protection(self, mock_kms_client):
        """Test complete PII protection workflow."""
        with patch('boto3.client', return_value=mock_kms_client):
            with patch('sentinel_aml.security.encryption.get_settings') as mock_settings:
                mock_settings.return_value.encryption_key_id = 'test-key'
                mock_settings.return_value.aws_region = 'us-east-1'
                mock_settings.return_value.pii_masking_enabled = True
                
                # Original sensitive data
                sensitive_data = {
                    "transaction_id": "TXN-123456",
                    "customer_name": "John Doe",
                    "account_number": "1234567890123456",
                    "ssn": "123-45-6789",
                    "email": "john.doe@example.com",
                    "amount": 10000.00,
                    "currency": "USD"
                }
                
                # Get services
                encryption_service = get_encryption_service()
                pii_service = get_pii_service()
                
                # Step 1: Encrypt PII fields
                encrypted_data = encryption_service.encrypt_pii_record(sensitive_data)
                
                # Verify PII fields are encrypted
                assert encrypted_data["customer_name"] != sensitive_data["customer_name"]
                assert encrypted_data["account_number"] != sensitive_data["account_number"]
                assert encrypted_data["ssn"] != sensitive_data["ssn"]
                assert encrypted_data["email"] != sensitive_data["email"]
                
                # Non-PII fields should remain unchanged
                assert encrypted_data["transaction_id"] == sensitive_data["transaction_id"]
                assert encrypted_data["amount"] == sensitive_data["amount"]
                assert encrypted_data["currency"] == sensitive_data["currency"]
                
                # Step 2: Decrypt for authorized access
                decrypted_data = encryption_service.decrypt_pii_record(encrypted_data)
                assert decrypted_data == sensitive_data
                
                # Step 3: Mask for logging/display
                masked_data = pii_service.mask_pii_data(sensitive_data)
                
                # Verify masking
                assert masked_data["customer_name"] == "J*** D**"
                assert masked_data["account_number"] == "************3456"
                assert "***-**-6789" == masked_data["ssn"]
                assert masked_data["email"] == "j***e@example.com"
    
    def test_encryption_with_audit_logging(self, mock_kms_client):
        """Test that encryption operations are properly audited."""
        with patch('boto3.client', return_value=mock_kms_client):
            with patch('sentinel_aml.security.encryption.get_settings') as mock_settings:
                with patch('sentinel_aml.compliance.audit_storage.get_audit_storage') as mock_storage:
                    mock_settings.return_value.encryption_key_id = 'test-key'
                    mock_settings.return_value.aws_region = 'us-east-1'
                    
                    mock_storage_instance = Mock()
                    mock_storage.return_value = mock_storage_instance
                    
                    encryption_service = get_encryption_service()
                    
                    # Encrypt PII record
                    sensitive_data = {
                        "customer_name": "Jane Smith",
                        "account_number": "9876543210",
                        "amount": 5000.00
                    }
                    
                    encrypted_data = encryption_service.encrypt_pii_record(sensitive_data)
                    
                    # Verify audit log was created
                    assert mock_storage_instance.store_audit_record.called
                    
                    # Get the stored event
                    stored_event = mock_storage_instance.store_audit_record.call_args[0][0]
                    
                    # Verify encryption audit details
                    assert stored_event.event_type == AuditEventType.DATA_ENCRYPTED
                    assert stored_event.action == "encrypt_pii_record"
                    assert "encrypted_fields" in stored_event.details
                    assert "encryption_algorithm" in stored_event.details
                    assert stored_event.details["encryption_algorithm"] == "AES-256-GCM"
    
    def test_audit_logging_with_pii_protection(self):
        """Test audit logging automatically protects PII."""
        with patch('sentinel_aml.compliance.audit_storage.get_audit_storage') as mock_storage:
            mock_storage_instance = Mock()
            mock_storage.return_value = mock_storage_instance
            
            audit_logger = get_audit_logger()
            
            # Log event with PII data
            sensitive_details = {
                "customer_name": "Jane Smith",
                "account_number": "9876543210",
                "transaction_amount": 5000.00
            }
            
            event_id = audit_logger.log_event(
                event_type=AuditEventType.TRANSACTION_RECEIVED,
                action="process_transaction",
                details=sensitive_details,
                user_id="analyst123"
            )
            
            # Verify audit record was stored
            assert mock_storage_instance.store_audit_record.called
            
            # Get the stored event
            stored_event = mock_storage_instance.store_audit_record.call_args[0][0]
            
            # Verify PII was masked in the stored details
            assert stored_event.details["customer_name"] == "J*** S****"
            assert stored_event.details["account_number"] == "******3210"
            assert stored_event.details["transaction_amount"] == 5000.00  # Non-PII unchanged
            
            # Verify PII flag was set
            assert stored_event.contains_pii == True
    
    def test_access_control_with_audit_logging(self):
        """Test access control decisions are properly audited."""
        with patch('sentinel_aml.compliance.audit_storage.get_audit_storage') as mock_storage:
            mock_storage_instance = Mock()
            mock_storage.return_value = mock_storage_instance
            
            access_service = get_access_control_service()
            
            # Create test user with limited permissions
            from sentinel_aml.security.access_control import User
            test_user = User(
                user_id="test_user",
                username="testuser",
                email="test@example.com",
                roles=[Role.READONLY_USER],
                created_at=datetime.now(timezone.utc)
            )
            access_service._users["test_user"] = test_user
            
            # Test function that requires higher permissions
            @access_service.require_permission(Permission.SYSTEM_CONFIG)
            def admin_function(user_id=None):
                return "admin operation completed"
            
            # Attempt access (should fail and be audited)
            with pytest.raises(Exception):  # ValidationError
                admin_function(user_id="test_user")
            
            # Verify audit log was created for permission denial
            assert mock_storage_instance.store_audit_record.called
            
            # Check the audit event details
            stored_event = mock_storage_instance.store_audit_record.call_args[0][0]
            assert stored_event.action == "permission_denied"
            assert stored_event.outcome == "FAILURE"
            assert stored_event.user_id == "test_user"
    
    def test_compliance_report_generation(self):
        """Test compliance report generation with security metrics."""
        with patch('sentinel_aml.compliance.audit_storage.get_audit_storage') as mock_storage:
            mock_storage_instance = Mock()
            mock_storage.return_value = mock_storage_instance
            
            # Mock audit events
            mock_events = [
                Mock(event_data={
                    'event_type': 'transaction_received',
                    'outcome': 'SUCCESS',
                    'resource_type': 'transaction'
                }),
                Mock(event_data={
                    'event_type': 'pii_accessed',
                    'outcome': 'SUCCESS',
                    'user_id': 'analyst1'
                }),
                Mock(event_data={
                    'event_type': 'data_encrypted',
                    'outcome': 'SUCCESS'
                }),
                Mock(event_data={
                    'event_type': 'sar_generated',
                    'outcome': 'SUCCESS',
                    'resource_type': 'sar'
                })
            ]
            
            audit_logger = get_audit_logger()
            audit_logger.get_audit_trail = Mock(return_value=mock_events)
            
            from sentinel_aml.compliance.compliance_reporter import get_compliance_reporter
            reporter = get_compliance_reporter()
            
            # Generate compliance report
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
            end_date = datetime.now(timezone.utc)
            
            report = reporter.generate_audit_report(start_date, end_date)
            
            # Verify report structure
            assert "report_metadata" in report
            assert "executive_summary" in report
            assert "pii_access_log" in report
            assert "system_security" in report
            assert "compliance_metrics" in report
            
            # Verify security metrics
            security_section = report["system_security"]
            assert "encryption_operations" in security_section
            assert "tls_compliance" in security_section
            
            # Verify PII access tracking
            pii_section = report["pii_access_log"]
            assert "total_pii_access_events" in pii_section
    
    def test_data_retention_compliance(self):
        """Test data retention policies are enforced."""
        with patch('sentinel_aml.compliance.audit_storage.get_audit_storage') as mock_storage:
            mock_storage_instance = Mock()
            mock_storage.return_value = mock_storage_instance
            
            from sentinel_aml.compliance.audit_storage import ImmutableAuditRecord
            from sentinel_aml.compliance.audit_logger import AuditEvent
            
            # Create test audit event
            test_event = AuditEvent(
                event_type=AuditEventType.TRANSACTION_RECEIVED,
                action="test_action",
                outcome="SUCCESS"
            )
            
            # Create immutable record
            record = ImmutableAuditRecord.create_from_event(test_event)
            
            # Verify retention period is set correctly (7 years)
            retention_days = (record.retention_until - record.timestamp).days
            assert retention_days >= 2555  # 7 years minimum
            
            # Verify checksum for integrity
            assert record.checksum is not None
            assert len(record.checksum) == 64  # SHA-256 hex string


class TestSecurityConfiguration:
    """Test security configuration and settings."""
    
    def test_tls_configuration(self):
        """Test TLS 1.3 configuration."""
        from sentinel_aml.security.tls_config import get_tls_config
        
        tls_config = get_tls_config()
        
        # Create SSL context
        ssl_context = tls_config.create_ssl_context()
        
        # Verify TLS 1.3 is enforced
        import ssl
        assert ssl_context.minimum_version == ssl.TLSVersion.TLSv1_3
        assert ssl_context.maximum_version == ssl.TLSVersion.TLSv1_3
        
        # Verify security settings
        assert ssl_context.check_hostname == True
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
    
    def test_secure_session_creation(self):
        """Test secure HTTP session creation."""
        from sentinel_aml.security.tls_config import create_secure_session
        
        session = create_secure_session()
        
        # Verify session has security headers
        assert 'User-Agent' in session.headers
        assert 'Sentinel-AML' in session.headers['User-Agent']
        
        # Verify HTTPS adapter is configured
        https_adapter = session.get_adapter('https://')
        assert https_adapter is not None


class TestComplianceIntegration:
    """Test compliance features integration."""
    
    def test_regulatory_reporting_workflow(self):
        """Test complete regulatory reporting workflow."""
        with patch('sentinel_aml.compliance.audit_storage.get_audit_storage') as mock_storage:
            mock_storage_instance = Mock()
            mock_storage.return_value = mock_storage_instance
            
            # Simulate transaction processing with full audit trail
            audit_logger = get_audit_logger()
            
            # Step 1: Transaction received
            audit_logger.log_transaction_event(
                transaction_id="TXN-REG-001",
                event_type=AuditEventType.TRANSACTION_RECEIVED,
                action="receive_transaction",
                amount=15000.00,
                currency="USD"
            )
            
            # Step 2: Risk analysis
            audit_logger.log_event(
                event_type=AuditEventType.RISK_ANALYSIS_STARTED,
                action="analyze_risk",
                resource_type="transaction",
                resource_id="TXN-REG-001"
            )
            
            # Step 3: Suspicious activity flagged
            audit_logger.log_event(
                event_type=AuditEventType.SUSPICIOUS_ACTIVITY_FLAGGED,
                action="flag_suspicious",
                resource_type="transaction",
                resource_id="TXN-REG-001",
                risk_score=0.85
            )
            
            # Step 4: SAR generation
            audit_logger.log_sar_event(
                sar_id="SAR-REG-001",
                event_type=AuditEventType.SAR_GENERATED,
                action="generate_sar",
                confidence_score=0.92
            )
            
            # Verify all events were logged
            assert mock_storage_instance.store_audit_record.call_count == 4
            
            # Verify each event has proper structure
            for call in mock_storage_instance.store_audit_record.call_args_list:
                event = call[0][0]
                assert event.event_id is not None
                assert event.timestamp is not None
                assert event.event_type is not None
                assert event.action is not None