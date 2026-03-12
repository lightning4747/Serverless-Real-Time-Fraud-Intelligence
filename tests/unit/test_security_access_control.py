"""Unit tests for access control and authorization mechanisms."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from sentinel_aml.security.access_control import (
    AccessControlService, Permission, Role, User, require_permission
)
from sentinel_aml.core.exceptions import ValidationError


class TestAccessControlService:
    """Test access control service functionality."""
    
    @pytest.fixture
    def access_service(self):
        """Create access control service for testing."""
        return AccessControlService()
    
    @pytest.fixture
    def test_user(self):
        """Create test user."""
        return User(
            user_id="test_user_123",
            username="testuser",
            email="test@example.com",
            roles=[Role.AML_ANALYST],
            created_at=datetime.now(timezone.utc)
        )
    
    def test_role_permissions_mapping(self, access_service):
        """Test that roles have correct permissions."""
        # AML Analyst should have transaction and risk permissions
        analyst_perms = access_service.role_permissions[Role.AML_ANALYST]
        assert Permission.TRANSACTION_READ in analyst_perms
        assert Permission.RISK_ANALYSIS_READ in analyst_perms
        assert Permission.SAR_READ in analyst_perms
        assert Permission.PII_READ in analyst_perms
        
        # But not admin permissions
        assert Permission.SYSTEM_CONFIG not in analyst_perms
        assert Permission.USER_MANAGEMENT not in analyst_perms
        
        # System Admin should have admin permissions
        admin_perms = access_service.role_permissions[Role.SYSTEM_ADMIN]
        assert Permission.SYSTEM_CONFIG in admin_perms
        assert Permission.USER_MANAGEMENT in admin_perms
        
        # Auditor should have read-only access
        auditor_perms = access_service.role_permissions[Role.AUDITOR]
        assert Permission.AUDIT_READ in auditor_perms
        assert Permission.TRANSACTION_READ in auditor_perms
        assert Permission.PII_MASK in auditor_perms  # Masked data only
        assert Permission.PII_DECRYPT not in auditor_perms  # No decryption
    
    def test_get_user_permissions(self, access_service, test_user):
        """Test getting user permissions from roles."""
        # Add user to service
        access_service._users[test_user.user_id] = test_user
        
        permissions = access_service.get_user_permissions(test_user.user_id)
        
        # Should have AML Analyst permissions
        assert Permission.TRANSACTION_READ in permissions
        assert Permission.RISK_ANALYSIS_READ in permissions
        assert Permission.SAR_READ in permissions
        
        # Should not have admin permissions
        assert Permission.SYSTEM_CONFIG not in permissions
    
    def test_get_user_permissions_with_additional(self, access_service, test_user):
        """Test user permissions with additional permissions."""
        # Add additional permission
        test_user.additional_permissions = [Permission.AUDIT_READ]
        access_service._users[test_user.user_id] = test_user
        
        permissions = access_service.get_user_permissions(test_user.user_id)
        
        # Should have role permissions plus additional
        assert Permission.TRANSACTION_READ in permissions  # From role
        assert Permission.AUDIT_READ in permissions  # Additional
    
    def test_get_user_permissions_inactive_user(self, access_service, test_user):
        """Test that inactive users have no permissions."""
        test_user.is_active = False
        access_service._users[test_user.user_id] = test_user
        
        permissions = access_service.get_user_permissions(test_user.user_id)
        
        assert len(permissions) == 0
    
    def test_get_user_permissions_nonexistent_user(self, access_service):
        """Test permissions for non-existent user."""
        permissions = access_service.get_user_permissions("nonexistent")
        assert len(permissions) == 0
    
    def test_has_permission(self, access_service, test_user):
        """Test permission checking."""
        access_service._users[test_user.user_id] = test_user
        
        # Should have analyst permissions
        assert access_service.has_permission(test_user.user_id, Permission.TRANSACTION_READ)
        assert access_service.has_permission(test_user.user_id, Permission.SAR_READ)
        
        # Should not have admin permissions
        assert not access_service.has_permission(test_user.user_id, Permission.SYSTEM_CONFIG)
        assert not access_service.has_permission(test_user.user_id, Permission.USER_MANAGEMENT)
    
    def test_create_user_success(self, access_service):
        """Test successful user creation."""
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
            user_id="new_user",
            username="newuser",
            email="new@example.com",
            roles=[Role.AML_ANALYST],
            created_by="admin"
        )
        
        assert new_user.user_id == "new_user"
        assert new_user.username == "newuser"
        assert Role.AML_ANALYST in new_user.roles
        assert "new_user" in access_service._users
    
    def test_create_user_permission_denied(self, access_service, test_user):
        """Test user creation without proper permissions."""
        access_service._users[test_user.user_id] = test_user
        
        with pytest.raises(ValidationError, match="Permission denied"):
            access_service.create_user(
                user_id="new_user",
                username="newuser",
                email="new@example.com",
                roles=[Role.AML_ANALYST],
                created_by=test_user.user_id  # Analyst can't create users
            )
    
    def test_assign_role_success(self, access_service):
        """Test successful role assignment."""
        # Create admin and target user
        admin_user = User(
            user_id="admin",
            username="admin",
            email="admin@example.com",
            roles=[Role.SYSTEM_ADMIN],
            created_at=datetime.now(timezone.utc)
        )
        target_user = User(
            user_id="target",
            username="target",
            email="target@example.com",
            roles=[Role.READONLY_USER],
            created_at=datetime.now(timezone.utc)
        )
        
        access_service._users["admin"] = admin_user
        access_service._users["target"] = target_user
        
        # Assign new role
        access_service.assign_role("target", Role.AML_ANALYST, "admin")
        
        assert Role.AML_ANALYST in target_user.roles
        assert Role.READONLY_USER in target_user.roles  # Original role preserved
    
    def test_assign_role_permission_denied(self, access_service, test_user):
        """Test role assignment without proper permissions."""
        access_service._users[test_user.user_id] = test_user
        
        with pytest.raises(ValidationError, match="Permission denied"):
            access_service.assign_role("target", Role.AML_ANALYST, test_user.user_id)
    
    def test_revoke_role_success(self, access_service):
        """Test successful role revocation."""
        # Create admin and target user
        admin_user = User(
            user_id="admin",
            username="admin",
            email="admin@example.com",
            roles=[Role.SYSTEM_ADMIN],
            created_at=datetime.now(timezone.utc)
        )
        target_user = User(
            user_id="target",
            username="target",
            email="target@example.com",
            roles=[Role.AML_ANALYST, Role.READONLY_USER],
            created_at=datetime.now(timezone.utc)
        )
        
        access_service._users["admin"] = admin_user
        access_service._users["target"] = target_user
        
        # Revoke role
        access_service.revoke_role("target", Role.AML_ANALYST, "admin")
        
        assert Role.AML_ANALYST not in target_user.roles
        assert Role.READONLY_USER in target_user.roles  # Other role preserved
    
    def test_revoke_role_permission_denied(self, access_service, test_user):
        """Test role revocation without proper permissions."""
        access_service._users[test_user.user_id] = test_user
        
        with pytest.raises(ValidationError, match="Permission denied"):
            access_service.revoke_role("target", Role.AML_ANALYST, test_user.user_id)


class TestPermissionDecorator:
    """Test permission decorator functionality."""
    
    @pytest.fixture
    def mock_access_service(self):
        """Mock access control service."""
        service = Mock()
        service.has_permission.return_value = True
        return service
    
    def test_permission_decorator_success(self, mock_access_service):
        """Test successful permission check with decorator."""
        
        @require_permission(Permission.TRANSACTION_READ)
        def protected_function(user_id=None):
            return "success"
        
        with patch('sentinel_aml.security.access_control.get_access_control_service', 
                  return_value=mock_access_service):
            result = protected_function(user_id="test_user")
            assert result == "success"
            mock_access_service.has_permission.assert_called_once_with("test_user", Permission.TRANSACTION_READ)
    
    def test_permission_decorator_denied(self, mock_access_service):
        """Test permission denied with decorator."""
        mock_access_service.has_permission.return_value = False
        
        @require_permission(Permission.SYSTEM_CONFIG)
        def protected_function(user_id=None):
            return "success"
        
        with patch('sentinel_aml.security.access_control.get_access_control_service', 
                  return_value=mock_access_service):
            with pytest.raises(ValidationError, match="Permission denied"):
                protected_function(user_id="test_user")
    
    def test_permission_decorator_no_user(self):
        """Test decorator without user authentication."""
        
        @require_permission(Permission.TRANSACTION_READ)
        def protected_function():
            return "success"
        
        with pytest.raises(ValidationError, match="User authentication required"):
            protected_function()


class TestRoleBasedAccess:
    """Test role-based access scenarios."""
    
    @pytest.fixture
    def access_service_with_users(self):
        """Create access service with test users."""
        service = AccessControlService()
        
        # Create users with different roles
        users = [
            User(
                user_id="analyst1",
                username="analyst1",
                email="analyst1@example.com",
                roles=[Role.AML_ANALYST],
                created_at=datetime.now(timezone.utc)
            ),
            User(
                user_id="officer1",
                username="officer1",
                email="officer1@example.com",
                roles=[Role.COMPLIANCE_OFFICER],
                created_at=datetime.now(timezone.utc)
            ),
            User(
                user_id="admin1",
                username="admin1",
                email="admin1@example.com",
                roles=[Role.SYSTEM_ADMIN],
                created_at=datetime.now(timezone.utc)
            ),
            User(
                user_id="investigator1",
                username="investigator1",
                email="investigator1@example.com",
                roles=[Role.INVESTIGATOR],
                created_at=datetime.now(timezone.utc)
            )
        ]
        
        for user in users:
            service._users[user.user_id] = user
        
        return service
    
    def test_analyst_permissions(self, access_service_with_users):
        """Test AML analyst can access appropriate resources."""
        service = access_service_with_users
        
        # Analyst should be able to read transactions and generate SARs
        assert service.has_permission("analyst1", Permission.TRANSACTION_READ)
        assert service.has_permission("analyst1", Permission.RISK_ANALYSIS_READ)
        assert service.has_permission("analyst1", Permission.SAR_READ)
        assert service.has_permission("analyst1", Permission.SAR_WRITE)
        assert service.has_permission("analyst1", Permission.PII_READ)
        
        # But not admin functions
        assert not service.has_permission("analyst1", Permission.SYSTEM_CONFIG)
        assert not service.has_permission("analyst1", Permission.USER_MANAGEMENT)
    
    def test_compliance_officer_permissions(self, access_service_with_users):
        """Test compliance officer can review and file SARs."""
        service = access_service_with_users
        
        # Officer should be able to review and file SARs
        assert service.has_permission("officer1", Permission.SAR_READ)
        assert service.has_permission("officer1", Permission.SAR_REVIEW)
        assert service.has_permission("officer1", Permission.SAR_FILE)
        assert service.has_permission("officer1", Permission.AUDIT_READ)
        
        # But not write new SARs or admin functions
        assert not service.has_permission("officer1", Permission.SAR_WRITE)
        assert not service.has_permission("officer1", Permission.SYSTEM_CONFIG)
    
    def test_investigator_special_permissions(self, access_service_with_users):
        """Test investigator has special PII decryption access."""
        service = access_service_with_users
        
        # Investigator should have PII decryption for investigations
        assert service.has_permission("investigator1", Permission.PII_READ)
        assert service.has_permission("investigator1", Permission.PII_DECRYPT)
        
        # But not SAR filing or admin functions
        assert not service.has_permission("investigator1", Permission.SAR_FILE)
        assert not service.has_permission("investigator1", Permission.SYSTEM_CONFIG)
    
    def test_admin_permissions(self, access_service_with_users):
        """Test system admin has administrative permissions."""
        service = access_service_with_users
        
        # Admin should have system configuration access
        assert service.has_permission("admin1", Permission.SYSTEM_CONFIG)
        assert service.has_permission("admin1", Permission.USER_MANAGEMENT)
        assert service.has_permission("admin1", Permission.MODEL_DEPLOY)
        
        # But not necessarily all operational permissions
        assert not service.has_permission("admin1", Permission.SAR_FILE)
        assert not service.has_permission("admin1", Permission.PII_DECRYPT)