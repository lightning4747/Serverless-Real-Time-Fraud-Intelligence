"""Role-based access control (RBAC) system for Sentinel-AML."""

from enum import Enum
from functools import lru_cache, wraps
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timezone

from pydantic import BaseModel

from sentinel_aml.core.config import get_settings
from sentinel_aml.core.exceptions import ValidationError
from sentinel_aml.core.logging import get_logger
from sentinel_aml.compliance.audit_logger import AuditEventType, get_audit_logger

logger = get_logger(__name__)


class Permission(str, Enum):
    """System permissions for RBAC."""
    
    # Transaction permissions
    TRANSACTION_READ = "transaction:read"
    TRANSACTION_WRITE = "transaction:write"
    TRANSACTION_DELETE = "transaction:delete"
    
    # Risk assessment permissions
    RISK_ANALYSIS_READ = "risk_analysis:read"
    RISK_ANALYSIS_EXECUTE = "risk_analysis:execute"
    RISK_THRESHOLD_MODIFY = "risk_threshold:modify"
    
    # SAR permissions
    SAR_READ = "sar:read"
    SAR_WRITE = "sar:write"
    SAR_REVIEW = "sar:review"
    SAR_FILE = "sar:file"
    
    # PII permissions
    PII_READ = "pii:read"
    PII_DECRYPT = "pii:decrypt"
    PII_MASK = "pii:mask"
    
    # System administration
    SYSTEM_CONFIG = "system:config"
    USER_MANAGEMENT = "user:management"
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"
    
    # Model management
    MODEL_DEPLOY = "model:deploy"
    MODEL_RETRAIN = "model:retrain"
    MODEL_MONITOR = "model:monitor"


class Role(str, Enum):
    """Predefined roles with specific permission sets."""
    
    AML_ANALYST = "aml_analyst"
    COMPLIANCE_OFFICER = "compliance_officer"
    SYSTEM_ADMIN = "system_admin"
    INVESTIGATOR = "investigator"
    AUDITOR = "auditor"
    DATA_SCIENTIST = "data_scientist"
    READONLY_USER = "readonly_user"


class User(BaseModel):
    """User model with role and permission information."""
    
    user_id: str
    username: str
    email: str
    roles: List[Role]
    additional_permissions: List[Permission] = []
    is_active: bool = True
    created_at: datetime
    last_login: Optional[datetime] = None
    session_timeout_minutes: int = 480  # 8 hours default


class AccessControlService:
    """Role-based access control service."""
    
    def __init__(self):
        """Initialize access control service."""
        self.settings = get_settings()
        self.audit_logger = get_audit_logger()
        
        # Define role permissions
        self.role_permissions = {
            Role.AML_ANALYST: {
                Permission.TRANSACTION_READ,
                Permission.RISK_ANALYSIS_READ,
                Permission.RISK_ANALYSIS_EXECUTE,
                Permission.SAR_READ,
                Permission.SAR_WRITE,
                Permission.PII_READ,
                Permission.PII_MASK,
            },
            Role.COMPLIANCE_OFFICER: {
                Permission.TRANSACTION_READ,
                Permission.RISK_ANALYSIS_READ,
                Permission.SAR_READ,
                Permission.SAR_REVIEW,
                Permission.SAR_FILE,
                Permission.PII_READ,
                Permission.AUDIT_READ,
                Permission.AUDIT_EXPORT,
            },
            Role.SYSTEM_ADMIN: {
                Permission.SYSTEM_CONFIG,
                Permission.USER_MANAGEMENT,
                Permission.AUDIT_READ,
                Permission.MODEL_DEPLOY,
                Permission.MODEL_MONITOR,
            },
            Role.INVESTIGATOR: {
                Permission.TRANSACTION_READ,
                Permission.RISK_ANALYSIS_READ,
                Permission.SAR_READ,
                Permission.PII_READ,
                Permission.PII_DECRYPT,  # Special permission for investigations
            },
            Role.AUDITOR: {
                Permission.AUDIT_READ,
                Permission.AUDIT_EXPORT,
                Permission.TRANSACTION_READ,
                Permission.SAR_READ,
                Permission.PII_MASK,  # Can see masked data only
            },
            Role.DATA_SCIENTIST: {
                Permission.MODEL_DEPLOY,
                Permission.MODEL_RETRAIN,
                Permission.MODEL_MONITOR,
                Permission.RISK_ANALYSIS_READ,
                Permission.TRANSACTION_READ,  # Aggregated data only
            },
            Role.READONLY_USER: {
                Permission.TRANSACTION_READ,
                Permission.RISK_ANALYSIS_READ,
                Permission.SAR_READ,
                Permission.PII_MASK,  # Masked data only
            }
        }
        
        # User storage (in production, this would be a database)
        self._users: Dict[str, User] = {}
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
    
    def get_user_permissions(self, user_id: str) -> Set[Permission]:
        """Get all permissions for a user based on roles."""
        user = self._users.get(user_id)
        if not user or not user.is_active:
            return set()
        
        permissions = set()
        
        # Add role-based permissions
        for role in user.roles:
            permissions.update(self.role_permissions.get(role, set()))
        
        # Add additional permissions
        permissions.update(user.additional_permissions)
        
        return permissions
    
    def has_permission(self, user_id: str, permission: Permission) -> bool:
        """Check if user has specific permission."""
        user_permissions = self.get_user_permissions(user_id)
        return permission in user_permissions
    
    def require_permission(self, permission: Permission):
        """Decorator to require specific permission for function access."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Extract user_id from kwargs or context
                user_id = kwargs.get('user_id') or self._get_current_user_id()
                
                if not user_id:
                    raise ValidationError("User authentication required")
                
                if not self.has_permission(user_id, permission):
                    self.audit_logger.log_event(
                        event_type=AuditEventType.USER_LOGIN,  # Using closest available type
                        action="permission_denied",
                        outcome="FAILURE",
                        user_id=user_id,
                        details={
                            "required_permission": permission.value,
                            "function": func.__name__
                        }
                    )
                    raise ValidationError(f"Permission denied: {permission.value}")
                
                # Log successful access
                self.audit_logger.log_event(
                    event_type=AuditEventType.USER_LOGIN,
                    action="permission_granted",
                    user_id=user_id,
                    details={
                        "permission": permission.value,
                        "function": func.__name__
                    }
                )
                
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def create_user(self, 
                   user_id: str,
                   username: str,
                   email: str,
                   roles: List[Role],
                   created_by: str) -> User:
        """Create new user with specified roles."""
        
        # Verify creator has user management permission
        if not self.has_permission(created_by, Permission.USER_MANAGEMENT):
            raise ValidationError("Permission denied: user management required")
        
        user = User(
            user_id=user_id,
            username=username,
            email=email,
            roles=roles,
            created_at=datetime.now(timezone.utc)
        )
        
        self._users[user_id] = user
        
        # Log user creation
        self.audit_logger.log_event(
            event_type=AuditEventType.CONFIGURATION_CHANGED,
            action="user_created",
            user_id=created_by,
            resource_type="user",
            resource_id=user_id,
            details={
                "new_user": username,
                "assigned_roles": [role.value for role in roles]
            }
        )
        
        return user
    
    def assign_role(self, user_id: str, role: Role, assigned_by: str):
        """Assign role to user."""
        
        if not self.has_permission(assigned_by, Permission.USER_MANAGEMENT):
            raise ValidationError("Permission denied: user management required")
        
        user = self._users.get(user_id)
        if not user:
            raise ValidationError(f"User not found: {user_id}")
        
        if role not in user.roles:
            user.roles.append(role)
            
            # Log role assignment
            self.audit_logger.log_event(
                event_type=AuditEventType.CONFIGURATION_CHANGED,
                action="role_assigned",
                user_id=assigned_by,
                resource_type="user",
                resource_id=user_id,
                details={
                    "role_assigned": role.value,
                    "target_user": user.username
                }
            )
    
    def revoke_role(self, user_id: str, role: Role, revoked_by: str):
        """Revoke role from user."""
        
        if not self.has_permission(revoked_by, Permission.USER_MANAGEMENT):
            raise ValidationError("Permission denied: user management required")
        
        user = self._users.get(user_id)
        if not user:
            raise ValidationError(f"User not found: {user_id}")
        
        if role in user.roles:
            user.roles.remove(role)
            
            # Log role revocation
            self.audit_logger.log_event(
                event_type=AuditEventType.CONFIGURATION_CHANGED,
                action="role_revoked",
                user_id=revoked_by,
                resource_type="user",
                resource_id=user_id,
                details={
                    "role_revoked": role.value,
                    "target_user": user.username
                }
            )
    
    def _get_current_user_id(self) -> Optional[str]:
        """Get current user ID from context (implementation depends on auth system)."""
        # This would integrate with your authentication system
        # For now, return None to require explicit user_id
        return None


@lru_cache()
def get_access_control_service() -> AccessControlService:
    """Get cached access control service instance."""
    return AccessControlService()


def require_permission(permission: Permission):
    """Convenience decorator for permission checking."""
    service = get_access_control_service()
    return service.require_permission(permission)