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
                   created_by: str,
                   additional_permissions: Optional[List[Permission]] = None) -> User:
        """Create new user with specified roles."""
        
        # Verify creator has user management permission
        if not self.has_permission(created_by, Permission.USER_MANAGEMENT):
            raise ValidationError("Permission denied: user management required")
        
        # Validate email format
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise ValidationError("Invalid email format")
        
        # Check if user already exists
        if user_id in self._users:
            raise ValidationError(f"User already exists: {user_id}")
        
        user = User(
            user_id=user_id,
            username=username,
            email=email,
            roles=roles,
            additional_permissions=additional_permissions or [],
            created_at=datetime.now(timezone.utc)
        )
        
        self._users[user_id] = user
        
        # Log user creation
        self.audit_logger.log_event(
            event_type=AuditEventType.CONFIGURATION_CHANGED,
            action="user_created",
            outcome="SUCCESS",
            user_id=created_by,
            resource_type="user",
            resource_id=user_id,
            details={
                "new_user": username,
                "email": email,
                "assigned_roles": [role.value for role in roles],
                "additional_permissions": [perm.value for perm in (additional_permissions or [])]
            },
            data_classification="confidential"
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
    
    def deactivate_user(self, user_id: str, deactivated_by: str, reason: str = "Administrative action"):
        """Deactivate a user account."""
        
        if not self.has_permission(deactivated_by, Permission.USER_MANAGEMENT):
            raise ValidationError("Permission denied: user management required")
        
        user = self._users.get(user_id)
        if not user:
            raise ValidationError(f"User not found: {user_id}")
        
        if not user.is_active:
            raise ValidationError(f"User {user_id} is already inactive")
        
        user.is_active = False
        
        # Invalidate any active sessions
        self._invalidate_user_sessions(user_id)
        
        # Log user deactivation
        self.audit_logger.log_event(
            event_type=AuditEventType.CONFIGURATION_CHANGED,
            action="user_deactivated",
            outcome="SUCCESS",
            user_id=deactivated_by,
            resource_type="user",
            resource_id=user_id,
            details={
                "deactivated_user": user.username,
                "reason": reason,
                "sessions_invalidated": True
            },
            data_classification="confidential"
        )
    
    def reactivate_user(self, user_id: str, reactivated_by: str):
        """Reactivate a user account."""
        
        if not self.has_permission(reactivated_by, Permission.USER_MANAGEMENT):
            raise ValidationError("Permission denied: user management required")
        
        user = self._users.get(user_id)
        if not user:
            raise ValidationError(f"User not found: {user_id}")
        
        if user.is_active:
            raise ValidationError(f"User {user_id} is already active")
        
        user.is_active = True
        
        # Log user reactivation
        self.audit_logger.log_event(
            event_type=AuditEventType.CONFIGURATION_CHANGED,
            action="user_reactivated",
            outcome="SUCCESS",
            user_id=reactivated_by,
            resource_type="user",
            resource_id=user_id,
            details={
                "reactivated_user": user.username
            },
            data_classification="confidential"
        )
    
    def update_user_permissions(self, 
                              user_id: str, 
                              additional_permissions: List[Permission],
                              updated_by: str):
        """Update user's additional permissions."""
        
        if not self.has_permission(updated_by, Permission.USER_MANAGEMENT):
            raise ValidationError("Permission denied: user management required")
        
        user = self._users.get(user_id)
        if not user:
            raise ValidationError(f"User not found: {user_id}")
        
        old_permissions = user.additional_permissions.copy()
        user.additional_permissions = additional_permissions
        
        # Log permission update
        self.audit_logger.log_event(
            event_type=AuditEventType.CONFIGURATION_CHANGED,
            action="user_permissions_updated",
            outcome="SUCCESS",
            user_id=updated_by,
            resource_type="user",
            resource_id=user_id,
            details={
                "target_user": user.username,
                "old_permissions": [perm.value for perm in old_permissions],
                "new_permissions": [perm.value for perm in additional_permissions]
            },
            data_classification="confidential"
        )
    
    def list_users(self, 
                   requester_id: str,
                   include_inactive: bool = False) -> List[Dict[str, Any]]:
        """List all users (requires appropriate permissions)."""
        
        if not self.has_permission(requester_id, Permission.USER_MANAGEMENT):
            # Allow users to see limited info if they have audit read permission
            if not self.has_permission(requester_id, Permission.AUDIT_READ):
                raise ValidationError("Permission denied: insufficient permissions to list users")
        
        users_list = []
        for user in self._users.values():
            if not include_inactive and not user.is_active:
                continue
            
            # Return limited info for non-admin users
            if self.has_permission(requester_id, Permission.USER_MANAGEMENT):
                user_info = {
                    "user_id": user.user_id,
                    "username": user.username,
                    "email": user.email,
                    "roles": [role.value for role in user.roles],
                    "additional_permissions": [perm.value for perm in user.additional_permissions],
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat(),
                    "last_login": user.last_login.isoformat() if user.last_login else None
                }
            else:
                # Limited info for audit read users
                user_info = {
                    "user_id": user.user_id,
                    "username": user.username,
                    "roles": [role.value for role in user.roles],
                    "is_active": user.is_active
                }
            
            users_list.append(user_info)
        
        # Log user listing
        self.audit_logger.log_event(
            event_type=AuditEventType.AUDIT_READ,
            action="list_users",
            outcome="SUCCESS",
            user_id=requester_id,
            details={
                "users_returned": len(users_list),
                "include_inactive": include_inactive
            }
        )
        
        return users_list
    
    def get_user_info(self, user_id: str, requester_id: str) -> Dict[str, Any]:
        """Get detailed user information."""
        
        # Users can view their own info, or need user management permission
        if user_id != requester_id and not self.has_permission(requester_id, Permission.USER_MANAGEMENT):
            raise ValidationError("Permission denied: can only view own user info")
        
        user = self._users.get(user_id)
        if not user:
            raise ValidationError(f"User not found: {user_id}")
        
        user_info = {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "roles": [role.value for role in user.roles],
            "additional_permissions": [perm.value for perm in user.additional_permissions],
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "session_timeout_minutes": user.session_timeout_minutes,
            "effective_permissions": [perm.value for perm in self.get_user_permissions(user_id)]
        }
        
        # Log user info access
        self.audit_logger.log_event(
            event_type=AuditEventType.AUDIT_READ,
            action="get_user_info",
            outcome="SUCCESS",
            user_id=requester_id,
            resource_type="user",
            resource_id=user_id,
            details={
                "target_user": user.username,
                "self_access": user_id == requester_id
            }
        )
        
        return user_info
    
    def create_session(self, user_id: str, source_ip: Optional[str] = None, user_agent: Optional[str] = None) -> str:
        """Create a new user session."""
        
        user = self._users.get(user_id)
        if not user or not user.is_active:
            raise ValidationError("Invalid user or user is inactive")
        
        # Generate session ID
        import uuid
        session_id = str(uuid.uuid4())
        
        # Create session
        session_data = {
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
            "last_activity": datetime.now(timezone.utc),
            "source_ip": source_ip,
            "user_agent": user_agent,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=user.session_timeout_minutes)
        }
        
        self._active_sessions[session_id] = session_data
        
        # Update user last login
        user.last_login = datetime.now(timezone.utc)
        
        # Log session creation
        self.audit_logger.log_event(
            event_type=AuditEventType.USER_LOGIN,
            action="session_created",
            outcome="SUCCESS",
            user_id=user_id,
            session_id=session_id,
            source_ip=source_ip,
            user_agent=user_agent,
            details={
                "session_timeout_minutes": user.session_timeout_minutes
            }
        )
        
        return session_id
    
    def validate_session(self, session_id: str) -> Optional[str]:
        """Validate a session and return user_id if valid."""
        
        session_data = self._active_sessions.get(session_id)
        if not session_data:
            return None
        
        # Check if session has expired
        if datetime.now(timezone.utc) > session_data["expires_at"]:
            self._invalidate_session(session_id)
            return None
        
        # Update last activity
        session_data["last_activity"] = datetime.now(timezone.utc)
        
        return session_data["user_id"]
    
    def invalidate_session(self, session_id: str, user_id: Optional[str] = None):
        """Invalidate a specific session."""
        
        session_data = self._active_sessions.get(session_id)
        if session_data:
            actual_user_id = session_data["user_id"]
            
            # Log session invalidation
            self.audit_logger.log_event(
                event_type=AuditEventType.USER_LOGOUT,
                action="session_invalidated",
                outcome="SUCCESS",
                user_id=user_id or actual_user_id,
                session_id=session_id,
                details={
                    "invalidated_by": user_id or "system",
                    "session_duration_minutes": (
                        datetime.now(timezone.utc) - session_data["created_at"]
                    ).total_seconds() / 60
                }
            )
        
        self._invalidate_session(session_id)
    
    def _invalidate_session(self, session_id: str):
        """Internal method to remove session."""
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
    
    def _invalidate_user_sessions(self, user_id: str):
        """Invalidate all sessions for a user."""
        sessions_to_remove = []
        
        for session_id, session_data in self._active_sessions.items():
            if session_data["user_id"] == user_id:
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            self._invalidate_session(session_id)
    
    def cleanup_expired_sessions(self):
        """Clean up expired sessions (should be called periodically)."""
        
        current_time = datetime.now(timezone.utc)
        expired_sessions = []
        
        for session_id, session_data in self._active_sessions.items():
            if current_time > session_data["expires_at"]:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            self._invalidate_session(session_id)
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")


@lru_cache()
def get_access_control_service() -> AccessControlService:
    """Get cached access control service instance."""
    return AccessControlService()


def require_permission(permission: Permission):
    """Convenience decorator for permission checking."""
    service = get_access_control_service()
    return service.require_permission(permission)