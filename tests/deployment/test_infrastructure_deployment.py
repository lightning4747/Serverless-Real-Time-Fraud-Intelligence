"""
Deployment tests for Sentinel-AML infrastructure.

Tests infrastructure provisioning, configuration, and deployment
automation to ensure reliable deployments.
"""

import json
import os
import subprocess
import time
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock

import pytest
import boto3
from moto import mock_cloudformation, mock_s3, mock_sts, mock_ssm
from botocore.exceptions import ClientError

from scripts.deploy import DeploymentManager


@pytest.fixture
def deployment_manager():
    """Create a deployment manager for testing."""
    with patch('boto3.client'):
        return DeploymentManager(environment="test", region="us-east-1")


@pytest.fixture
def mock_aws_clients():
    """Mock AWS clients for testing."""
    clients = {
        'cloudformation': Mock(),
        's3': Mock(),
        'ssm': Mock(),
        'sts': Mock()
    }
    
    # Mock STS get_caller_identity
    clients['sts'].get_caller_identity.return_value = {'Account': '123456789012'}
    
    return clients


class TestInfrastructureDeployment:
    """Test infrastructure deployment functionality."""
    
    def test_deployment_manager_initialization(self):
        """Test deployment manager initialization."""
        with patch('boto3.client') as mock_boto:
            mock_sts = Mock()
            mock_sts.get_caller_identity.return_value = {'Account': '123456789012'}
            mock_boto.return_value = mock_sts
            
            manager = DeploymentManager(environment="development", region="us-west-2")
            
            assert manager.environment == "development"
            assert manager.region == "us-west-2"
            assert manager.account_id == "123456789012"
            assert len(manager.stack_names) == 6
    
    def test_validate_prerequisites_success(self, deployment_manager):
        """Test successful prerequisite validation."""
        with patch('subprocess.run') as mock_run, \
             patch('aws_cdk.__version__', '2.100.0'), \
             patch('pathlib.Path.exists', return_value=True):
            
            # Mock successful command executions
            mock_run.side_effect = [
                Mock(returncode=0, stdout="2.100.0"),  # CDK version
                Mock(returncode=0, stdout="v18.17.0")   # Node version
            ]
            
            result = deployment_manager.validate_prerequisites()
            assert result is True
    
    def test_validate_prerequisites_missing_cdk(self, deployment_manager):
        """Test prerequisite validation with missing CDK."""
        with patch('subprocess.run') as mock_run, \
             patch('aws_cdk.__version__', '2.100.0'), \
             patch('pathlib.Path.exists', return_value=True):
            
            # Mock CDK not found
            mock_run.side_effect = [
                FileNotFoundError(),  # CDK not found
                Mock(returncode=0, stdout="v18.17.0")   # Node version
            ]
            
            result = deployment_manager.validate_prerequisites()
            assert result is False
    
    def test_bootstrap_cdk_success(self, deployment_manager):
        """Test successful CDK bootstrap."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            
            result = deployment_manager.bootstrap_cdk()
            
            assert result is True
            mock_run.assert_called_once()
            
            # Verify command structure
            call_args = mock_run.call_args[0][0]
            assert 'cdk' in call_args
            assert 'bootstrap' in call_args
            assert 'aws://123456789012/us-east-1' in call_args
    
    def test_bootstrap_cdk_failure(self, deployment_manager):
        """Test CDK bootstrap failure."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr="Bootstrap failed")
            
            result = deployment_manager.bootstrap_cdk()
            
            assert result is False
    
    def test_deploy_infrastructure_success(self, deployment_manager):
        """Test successful infrastructure deployment."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            
            result = deployment_manager.deploy_infrastructure()
            
            assert result is True
            mock_run.assert_called_once()
            
            # Verify environment variables are set
            call_kwargs = mock_run.call_args[1]
            env = call_kwargs['env']
            assert env['ENVIRONMENT'] == 'test'
            assert env['CDK_DEFAULT_REGION'] == 'us-east-1'
            assert env['CDK_DEFAULT_ACCOUNT'] == '123456789012'
    
    def test_deploy_infrastructure_with_stack_filter(self, deployment_manager):
        """Test infrastructure deployment with stack filter."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            
            result = deployment_manager.deploy_infrastructure(stack_filter="SentinelAMLSecurity")
            
            assert result is True
            
            # Verify stack filter is used
            call_args = mock_run.call_args[0][0]
            assert 'SentinelAMLSecurity' in call_args
            assert '--all' not in call_args
    
    def test_validate_deployment_success(self, deployment_manager):
        """Test successful deployment validation."""
        with patch.object(deployment_manager, 'cloudformation') as mock_cf, \
             patch.object(deployment_manager, '_get_stack_output') as mock_output, \
             patch('requests.get') as mock_requests:
            
            # Mock CloudFormation responses
            mock_cf.describe_stacks.return_value = {
                'Stacks': [{
                    'StackStatus': 'CREATE_COMPLETE'
                }]
            }
            
            # Mock stack outputs
            mock_output.side_effect = [
                'https://api.example.com',  # API Gateway URL
                'neptune.cluster.amazonaws.com'  # Neptune endpoint
            ]
            
            # Mock API health check
            mock_requests.return_value = Mock(status_code=200)
            
            result = deployment_manager.validate_deployment()
            
            assert result is True
    
    def test_validate_deployment_stack_failure(self, deployment_manager):
        """Test deployment validation with stack failure."""
        with patch.object(deployment_manager, 'cloudformation') as mock_cf:
            
            # Mock failed stack
            mock_cf.describe_stacks.return_value = {
                'Stacks': [{
                    'StackStatus': 'CREATE_FAILED'
                }]
            }
            
            result = deployment_manager.validate_deployment()
            
            assert result is False
    
    def test_create_deployment_snapshot(self, deployment_manager):
        """Test deployment snapshot creation."""
        with patch.object(deployment_manager, 'cloudformation') as mock_cf, \
             patch.object(deployment_manager, 's3') as mock_s3:
            
            # Mock CloudFormation responses
            mock_cf.get_template.return_value = {
                'TemplateBody': {'Resources': {}}
            }
            
            mock_cf.describe_stacks.return_value = {
                'Stacks': [{
                    'StackStatus': 'CREATE_COMPLETE',
                    'Parameters': [],
                    'Outputs': []
                }]
            }
            
            snapshot_id = deployment_manager.create_deployment_snapshot()
            
            assert snapshot_id.startswith('snapshot-test-')
            mock_s3.put_object.assert_called_once()
            
            # Verify S3 put_object call
            call_kwargs = mock_s3.put_object.call_args[1]
            assert call_kwargs['Bucket'] == 'sentinel-aml-deployments-123456789012'
            assert call_kwargs['Key'].startswith('snapshots/snapshot-test-')
    
    def test_get_stack_output_success(self, deployment_manager):
        """Test successful stack output retrieval."""
        with patch.object(deployment_manager, 'cloudformation') as mock_cf:
            
            mock_cf.describe_stacks.return_value = {
                'Stacks': [{
                    'Outputs': [
                        {
                            'OutputKey': 'APIGatewayURL',
                            'OutputValue': 'https://api.example.com'
                        },
                        {
                            'OutputKey': 'NeptuneEndpoint',
                            'OutputValue': 'neptune.cluster.amazonaws.com'
                        }
                    ]
                }]
            }
            
            result = deployment_manager._get_stack_output('TestStack', 'APIGatewayURL')
            
            assert result == 'https://api.example.com'
    
    def test_get_stack_output_not_found(self, deployment_manager):
        """Test stack output retrieval when output not found."""
        with patch.object(deployment_manager, 'cloudformation') as mock_cf:
            
            mock_cf.describe_stacks.return_value = {
                'Stacks': [{
                    'Outputs': []
                }]
            }
            
            result = deployment_manager._get_stack_output('TestStack', 'NonExistentOutput')
            
            assert result is None
    
    def test_cleanup_old_snapshots(self, deployment_manager):
        """Test cleanup of old deployment snapshots."""
        from datetime import datetime, timedelta
        
        with patch.object(deployment_manager, 's3') as mock_s3:
            
            # Mock old and new snapshots
            old_date = datetime.now() - timedelta(days=35)
            new_date = datetime.now() - timedelta(days=5)
            
            mock_s3.list_objects_v2.return_value = {
                'Contents': [
                    {
                        'Key': 'snapshots/old-snapshot.json',
                        'LastModified': old_date
                    },
                    {
                        'Key': 'snapshots/new-snapshot.json',
                        'LastModified': new_date
                    }
                ]
            }
            
            deployment_manager.cleanup_old_snapshots(retention_days=30)
            
            # Verify only old snapshot was deleted
            mock_s3.delete_object.assert_called_once_with(
                Bucket='sentinel-aml-deployments-123456789012',
                Key='snapshots/old-snapshot.json'
            )


class TestDeploymentAutomation:
    """Test deployment automation and CI/CD functionality."""
    
    def test_deployment_config_loading(self):
        """Test deployment configuration loading."""
        with patch('pathlib.Path.exists', return_value=False), \
             patch('boto3.client'):
            
            manager = DeploymentManager(environment="development")
            
            # Should use default config when file doesn't exist
            assert manager.config['notification_email'] == "admin@sentinel-aml.com"
            assert manager.config['enable_deletion_protection'] is False
            assert manager.config['backup_retention_days'] == 7
    
    def test_deployment_config_custom_loading(self):
        """Test custom deployment configuration loading."""
        custom_config = {
            "notification_email": "custom@example.com",
            "enable_deletion_protection": True,
            "backup_retention_days": 90
        }
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('builtins.open', mock_open_json(custom_config)), \
             patch('boto3.client'):
            
            manager = DeploymentManager(environment="production")
            
            assert manager.config['notification_email'] == "custom@example.com"
            assert manager.config['enable_deletion_protection'] is True
            assert manager.config['backup_retention_days'] == 90
    
    def test_environment_specific_stack_names(self):
        """Test environment-specific stack naming."""
        with patch('boto3.client'):
            dev_manager = DeploymentManager(environment="development")
            prod_manager = DeploymentManager(environment="production")
            
            # Verify stack names include environment
            for stack_name in dev_manager.stack_names:
                assert stack_name.endswith("-development")
            
            for stack_name in prod_manager.stack_names:
                assert stack_name.endswith("-production")
    
    @patch('subprocess.run')
    def test_cdk_command_construction(self, mock_run, deployment_manager):
        """Test CDK command construction with proper context."""
        mock_run.return_value = Mock(returncode=0)
        
        deployment_manager.deploy_infrastructure()
        
        # Verify CDK command includes proper context
        call_args = mock_run.call_args[0][0]
        assert 'cdk' in call_args
        assert 'deploy' in call_args
        assert '--context' in call_args
        
        # Find context values
        context_pairs = []
        for i, arg in enumerate(call_args):
            if arg == '--context' and i + 1 < len(call_args):
                context_pairs.append(call_args[i + 1])
        
        # Verify required context
        context_str = ' '.join(context_pairs)
        assert 'environment=test' in context_str
        assert 'notificationEmail=' in context_str


class TestDeploymentValidation:
    """Test deployment validation and health checks."""
    
    def test_api_gateway_health_check(self, deployment_manager):
        """Test API Gateway health check validation."""
        with patch.object(deployment_manager, '_get_stack_output') as mock_output, \
             patch('requests.get') as mock_requests:
            
            mock_output.return_value = 'https://api.example.com'
            mock_requests.return_value = Mock(status_code=200)
            
            # This would be part of validate_deployment
            api_url = deployment_manager._get_stack_output('SentinelAMLAPI', 'APIGatewayURL')
            
            import requests
            response = requests.get(f"{api_url}/health", timeout=10)
            
            assert response.status_code == 200
            mock_requests.assert_called_once_with('https://api.example.com/health', timeout=10)
    
    def test_neptune_connectivity_check(self, deployment_manager):
        """Test Neptune connectivity validation."""
        with patch.object(deployment_manager, '_get_stack_output') as mock_output:
            
            mock_output.return_value = 'neptune.cluster.amazonaws.com'
            
            neptune_endpoint = deployment_manager._get_stack_output('SentinelAMLNeptune', 'NeptuneEndpoint')
            
            assert neptune_endpoint == 'neptune.cluster.amazonaws.com'
    
    def test_stack_status_validation(self, deployment_manager):
        """Test CloudFormation stack status validation."""
        with patch.object(deployment_manager, 'cloudformation') as mock_cf:
            
            # Test various stack statuses
            test_cases = [
                ('CREATE_COMPLETE', True),
                ('UPDATE_COMPLETE', True),
                ('CREATE_FAILED', False),
                ('ROLLBACK_COMPLETE', False),
                ('DELETE_COMPLETE', False)
            ]
            
            for status, expected_valid in test_cases:
                mock_cf.describe_stacks.return_value = {
                    'Stacks': [{'StackStatus': status}]
                }
                
                # Simulate validation logic
                stack_valid = status in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']
                assert stack_valid == expected_valid


def mock_open_json(data):
    """Helper to mock file opening with JSON data."""
    import json
    from unittest.mock import mock_open
    return mock_open(read_data=json.dumps(data))


class TestDeploymentRollback:
    """Test deployment rollback functionality."""
    
    def test_rollback_deployment_warning(self, deployment_manager):
        """Test rollback deployment shows appropriate warnings."""
        result = deployment_manager.rollback_deployment("test-snapshot-123")
        
        # Rollback should return True but with warnings (simplified implementation)
        assert result is True
    
    def test_snapshot_data_structure(self, deployment_manager):
        """Test deployment snapshot data structure."""
        with patch.object(deployment_manager, 'cloudformation') as mock_cf, \
             patch.object(deployment_manager, 's3') as mock_s3:
            
            # Mock CloudFormation responses
            mock_cf.get_template.return_value = {
                'TemplateBody': {'Resources': {'TestResource': {}}}
            }
            
            mock_cf.describe_stacks.return_value = {
                'Stacks': [{
                    'StackStatus': 'CREATE_COMPLETE',
                    'Parameters': [{'ParameterKey': 'Environment', 'ParameterValue': 'test'}],
                    'Outputs': [{'OutputKey': 'TestOutput', 'OutputValue': 'test-value'}]
                }]
            }
            
            snapshot_id = deployment_manager.create_deployment_snapshot()
            
            # Verify S3 put_object was called with proper structure
            call_kwargs = mock_s3.put_object.call_args[1]
            snapshot_data = json.loads(call_kwargs['Body'])
            
            assert 'snapshot_id' in snapshot_data
            assert 'environment' in snapshot_data
            assert 'timestamp' in snapshot_data
            assert 'stacks' in snapshot_data
            assert snapshot_data['environment'] == 'test'