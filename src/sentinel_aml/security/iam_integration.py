"""AWS IAM integration for role-based access control."""

import json
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

import boto3
from botocore.exceptions import ClientError

from sentinel_aml.core.config import get_settings
from sentinel_aml.core.exceptions import ValidationError
from sentinel_aml.core.logging import get_logger
from sentinel_aml.security.access_control import Role, Permission, get_access_control_service
from sentinel_aml.compliance.audit_logger import get_audit_logger, AuditEventType

logger = get_logger(__name__)


class IAMIntegrationService:
    """AWS IAM integration for Sentinel-AML access control."""
    
    def __init__(self):
        """Initialize IAM integration service."""
        self.settings = get_settings()
        self.iam_client = boto3.client('iam', region_name=self.settings.aws_region)
        self.sts_client = boto3.client('sts', region_name=self.settings.aws_region)
        self.access_control = get_access_control_service()
        self.audit_logger = get_audit_logger()
        
        # IAM role prefix for Sentinel-AML
        self.role_prefix = f"SentinelAML-{self.settings.environment}-"
        
        # Policy ARN prefix
        self.policy_arn_prefix = f"arn:aws:iam::{self._get_account_id()}:policy/{self.role_prefix}"
    
    def _get_account_id(self) -> str:
        """Get AWS account ID."""
        try:
            response = self.sts_client.get_caller_identity()
            return response['Account']
        except Exception as e:
            logger.error(f"Failed to get AWS account ID: {e}")
            return "000000000000"  # Fallback
    
    def create_iam_roles_for_sentinel_aml(self) -> Dict[str, str]:
        """Create IAM roles for all Sentinel-AML roles."""
        
        created_roles = {}
        
        for role in Role:
            try:
                role_name = f"{self.role_prefix}{role.value.replace('_', '-')}"
                
                # Create IAM role
                trust_policy = self._create_trust_policy()
                
                response = self.iam_client.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(trust_policy),
                    Description=f"Sentinel-AML role for {role.value}",
                    MaxSessionDuration=28800,  # 8 hours
                    Tags=[
                        {'Key': 'Service', 'Value': 'Sentinel-AML'},
                        {'Key': 'Environment', 'Value': self.settings.environment},
                        {'Key': 'Role', 'Value': role.value}
                    ]
                )
                
                role_arn = response['Role']['Arn']
                created_roles[role.value] = role_arn
                
                # Attach policies to role
                self._attach_policies_to_role(role_name, role)
                
                logger.info(f"Created IAM role: {role_name}")
                
                # Log role creation
                self.audit_logger.log_event(
                    event_type=AuditEventType.CONFIGURATION_CHANGED,
                    action="iam_role_created",
                    outcome="SUCCESS",
                    resource_type="iam_role",
                    resource_id=role_name,
                    details={
                        "role_arn": role_arn,
                        "sentinel_role": role.value,
                        "max_session_duration": 28800
                    }
                )
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'EntityAlreadyExists':
                    logger.info(f"IAM role already exists: {role_name}")
                    # Get existing role ARN
                    try:
                        response = self.iam_client.get_role(RoleName=role_name)
                        created_roles[role.value] = response['Role']['Arn']
                    except Exception:
                        pass
                else:
                    logger.error(f"Failed to create IAM role {role_name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error creating IAM role {role.value}: {e}")
        
        return created_roles
    
    def _create_trust_policy(self) -> Dict[str, Any]:
        """Create trust policy for Sentinel-AML roles."""
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": [
                            "lambda.amazonaws.com",
                            "apigateway.amazonaws.com"
                        ]
                    },
                    "Action": "sts:AssumeRole"
                },
                {
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": f"arn:aws:iam::{self._get_account_id()}:root"
                    },
                    "Action": "sts:AssumeRole",
                    "Condition": {
                        "StringEquals": {
                            "sts:ExternalId": self.settings.external_id
                        }
                    }
                }
            ]
        }
    
    def _attach_policies_to_role(self, role_name: str, role: Role):
        """Attach appropriate policies to IAM role."""
        
        # Get permissions for this role
        permissions = self.access_control.role_permissions.get(role, set())
        
        # Create custom policy for this role
        policy_document = self._create_policy_document(permissions)
        policy_name = f"{role_name}-Policy"
        
        try:
            # Create the policy
            policy_response = self.iam_client.create_policy(
                PolicyName=policy_name,
                PolicyDocument=json.dumps(policy_document),
                Description=f"Custom policy for Sentinel-AML {role.value} role"
            )
            
            policy_arn = policy_response['Policy']['Arn']
            
            # Attach policy to role
            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn=policy_arn
            )
            
            logger.info(f"Attached policy {policy_name} to role {role_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                # Policy exists, attach it
                policy_arn = f"{self.policy_arn_prefix}{policy_name}"
                try:
                    self.iam_client.attach_role_policy(
                        RoleName=role_name,
                        PolicyArn=policy_arn
                    )
                except Exception as attach_error:
                    logger.warning(f"Failed to attach existing policy: {attach_error}")
            else:
                logger.error(f"Failed to create policy {policy_name}: {e}")
        
        # Attach AWS managed policies
        managed_policies = self._get_managed_policies_for_role(role)
        for policy_arn in managed_policies:
            try:
                self.iam_client.attach_role_policy(
                    RoleName=role_name,
                    PolicyArn=policy_arn
                )
                logger.info(f"Attached managed policy {policy_arn} to {role_name}")
            except Exception as e:
                logger.warning(f"Failed to attach managed policy {policy_arn}: {e}")
    
    def _create_policy_document(self, permissions: Set[Permission]) -> Dict[str, Any]:
        """Create IAM policy document from Sentinel-AML permissions."""
        
        statements = []
        
        # Map Sentinel-AML permissions to AWS actions
        permission_mappings = {
            Permission.TRANSACTION_READ: [
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "neptune-db:ReadDataViaQuery"
            ],
            Permission.TRANSACTION_WRITE: [
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "neptune-db:WriteDataViaQuery"
            ],
            Permission.TRANSACTION_DELETE: [
                "dynamodb:DeleteItem",
                "neptune-db:DeleteDataViaQuery"
            ],
            Permission.SAR_READ: [
                "s3:GetObject",
                "dynamodb:GetItem",
                "dynamodb:Query"
            ],
            Permission.SAR_WRITE: [
                "s3:PutObject",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem"
            ],
            Permission.PII_DECRYPT: [
                "kms:Decrypt",
                "kms:DescribeKey"
            ],
            Permission.SYSTEM_CONFIG: [
                "ssm:GetParameter",
                "ssm:PutParameter",
                "ssm:GetParameters"
            ],
            Permission.AUDIT_READ: [
                "dynamodb:Query",
                "dynamodb:Scan",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            Permission.MODEL_DEPLOY: [
                "sagemaker:CreateModel",
                "sagemaker:CreateEndpoint",
                "sagemaker:UpdateEndpoint"
            ]
        }
        
        # Collect all required actions
        all_actions = set()
        for permission in permissions:
            actions = permission_mappings.get(permission, [])
            all_actions.update(actions)
        
        if all_actions:
            statements.append({
                "Effect": "Allow",
                "Action": list(all_actions),
                "Resource": "*",  # Would be more specific in production
                "Condition": {
                    "StringEquals": {
                        "aws:RequestedRegion": self.settings.aws_region
                    }
                }
            })
        
        # Add logging permissions for all roles
        statements.append({
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": f"arn:aws:logs:{self.settings.aws_region}:{self._get_account_id()}:*"
        })
        
        return {
            "Version": "2012-10-17",
            "Statement": statements
        }
    
    def _get_managed_policies_for_role(self, role: Role) -> List[str]:
        """Get AWS managed policies for specific roles."""
        
        base_policies = [
            "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
        ]
        
        role_specific_policies = {
            Role.SYSTEM_ADMIN: [
                "arn:aws:iam::aws:policy/IAMReadOnlyAccess"
            ],
            Role.DATA_SCIENTIST: [
                "arn:aws:iam::aws:policy/AmazonSageMakerReadOnly"
            ],
            Role.AUDITOR: [
                "arn:aws:iam::aws:policy/CloudWatchReadOnlyAccess"
            ]
        }
        
        return base_policies + role_specific_policies.get(role, [])
    
    def assume_role_for_user(self, user_id: str, role: Role, session_name: Optional[str] = None) -> Dict[str, Any]:
        """Assume IAM role for a user session."""
        
        # Verify user has the role
        if not self.access_control.has_permission(user_id, Permission.SYSTEM_CONFIG):
            # Check if user has the specific role
            user = self.access_control._users.get(user_id)
            if not user or role not in user.roles:
                raise ValidationError(f"User {user_id} does not have role {role.value}")
        
        role_name = f"{self.role_prefix}{role.value.replace('_', '-')}"
        session_name = session_name or f"SentinelAML-{user_id}-{role.value}"
        
        try:
            response = self.sts_client.assume_role(
                RoleArn=f"arn:aws:iam::{self._get_account_id()}:role/{role_name}",
                RoleSessionName=session_name,
                DurationSeconds=28800,  # 8 hours
                ExternalId=self.settings.external_id
            )
            
            credentials = response['Credentials']
            
            # Log role assumption
            self.audit_logger.log_event(
                event_type=AuditEventType.USER_LOGIN,
                action="assume_iam_role",
                outcome="SUCCESS",
                user_id=user_id,
                details={
                    "role_assumed": role.value,
                    "session_name": session_name,
                    "session_duration": 28800
                }
            )
            
            return {
                'AccessKeyId': credentials['AccessKeyId'],
                'SecretAccessKey': credentials['SecretAccessKey'],
                'SessionToken': credentials['SessionToken'],
                'Expiration': credentials['Expiration'].isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to assume role {role_name} for user {user_id}: {e}")
            
            # Log failed assumption
            self.audit_logger.log_event(
                event_type=AuditEventType.USER_LOGIN,
                action="assume_iam_role",
                outcome="FAILURE",
                user_id=user_id,
                details={
                    "role_requested": role.value,
                    "error": str(e)
                }
            )
            
            raise ValidationError(f"Failed to assume role: {e}")
    
    def create_service_linked_roles(self) -> Dict[str, str]:
        """Create service-linked roles for AWS services used by Sentinel-AML."""
        
        service_roles = {}
        
        # Lambda execution role
        lambda_role = self._create_lambda_execution_role()
        if lambda_role:
            service_roles['lambda_execution'] = lambda_role
        
        # API Gateway role
        api_gateway_role = self._create_api_gateway_role()
        if api_gateway_role:
            service_roles['api_gateway'] = api_gateway_role
        
        # Step Functions role
        step_functions_role = self._create_step_functions_role()
        if step_functions_role:
            service_roles['step_functions'] = step_functions_role
        
        return service_roles
    
    def _create_lambda_execution_role(self) -> Optional[str]:
        """Create Lambda execution role for Sentinel-AML functions."""
        
        role_name = f"{self.role_prefix}LambdaExecution"
        
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "lambda.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        try:
            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="Lambda execution role for Sentinel-AML functions"
            )
            
            role_arn = response['Role']['Arn']
            
            # Attach necessary policies
            policies = [
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
                "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
            ]
            
            for policy_arn in policies:
                self.iam_client.attach_role_policy(
                    RoleName=role_name,
                    PolicyArn=policy_arn
                )
            
            logger.info(f"Created Lambda execution role: {role_name}")
            return role_arn
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                logger.info(f"Lambda execution role already exists: {role_name}")
                try:
                    response = self.iam_client.get_role(RoleName=role_name)
                    return response['Role']['Arn']
                except Exception:
                    return None
            else:
                logger.error(f"Failed to create Lambda execution role: {e}")
                return None
    
    def _create_api_gateway_role(self) -> Optional[str]:
        """Create API Gateway role for Sentinel-AML."""
        
        role_name = f"{self.role_prefix}ApiGateway"
        
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "apigateway.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        try:
            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="API Gateway role for Sentinel-AML"
            )
            
            role_arn = response['Role']['Arn']
            
            # Attach CloudWatch logs policy
            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
            )
            
            logger.info(f"Created API Gateway role: {role_name}")
            return role_arn
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                logger.info(f"API Gateway role already exists: {role_name}")
                try:
                    response = self.iam_client.get_role(RoleName=role_name)
                    return response['Role']['Arn']
                except Exception:
                    return None
            else:
                logger.error(f"Failed to create API Gateway role: {e}")
                return None
    
    def _create_step_functions_role(self) -> Optional[str]:
        """Create Step Functions role for Sentinel-AML."""
        
        role_name = f"{self.role_prefix}StepFunctions"
        
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "states.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        try:
            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="Step Functions role for Sentinel-AML workflows"
            )
            
            role_arn = response['Role']['Arn']
            
            # Attach Lambda invoke policy
            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaRole"
            )
            
            logger.info(f"Created Step Functions role: {role_name}")
            return role_arn
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                logger.info(f"Step Functions role already exists: {role_name}")
                try:
                    response = self.iam_client.get_role(RoleName=role_name)
                    return response['Role']['Arn']
                except Exception:
                    return None
            else:
                logger.error(f"Failed to create Step Functions role: {e}")
                return None


@lru_cache()
def get_iam_integration_service() -> IAMIntegrationService:
    """Get cached IAM integration service instance."""
    return IAMIntegrationService()


def setup_iam_roles() -> Dict[str, str]:
    """Convenience function to set up all IAM roles."""
    service = get_iam_integration_service()
    
    # Create Sentinel-AML roles
    sentinel_roles = service.create_iam_roles_for_sentinel_aml()
    
    # Create service-linked roles
    service_roles = service.create_service_linked_roles()
    
    # Combine results
    all_roles = {**sentinel_roles, **service_roles}
    
    logger.info(f"Set up {len(all_roles)} IAM roles for Sentinel-AML")
    return all_roles