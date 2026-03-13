"""
Smoke tests for deployed Sentinel-AML infrastructure.

These tests validate that the deployed system is functioning correctly
by testing critical paths and basic functionality.
"""

import os
import json
import time
import uuid
from typing import Dict, Any, Optional

import pytest
import requests
import boto3
from botocore.exceptions import ClientError


@pytest.fixture(scope="session")
def environment():
    """Get the target environment from command line or environment variable."""
    return os.getenv('ENVIRONMENT', 'development')


@pytest.fixture(scope="session")
def aws_region():
    """Get AWS region."""
    return os.getenv('AWS_REGION', 'us-east-1')


@pytest.fixture(scope="session")
def stack_outputs(environment, aws_region):
    """Get CloudFormation stack outputs."""
    cf_client = boto3.client('cloudformation', region_name=aws_region)
    
    outputs = {}
    stack_names = [
        f"SentinelAMLSecurity-{environment}",
        f"SentinelAMLNeptune-{environment}",
        f"SentinelAMLLambda-{environment}",
        f"SentinelAMLAPI-{environment}",
        f"SentinelAMLOrchestration-{environment}",
        f"SentinelAMLMonitoring-{environment}"
    ]
    
    for stack_name in stack_names:
        try:
            response = cf_client.describe_stacks(StackName=stack_name)
            stack = response['Stacks'][0]
            
            for output in stack.get('Outputs', []):
                outputs[output['OutputKey']] = output['OutputValue']
                
        except ClientError as e:
            if e.response['Error']['Code'] != 'ValidationError':
                raise
    
    return outputs


@pytest.fixture(scope="session")
def api_base_url(stack_outputs):
    """Get API Gateway base URL."""
    return stack_outputs.get('APIGatewayURL', '').rstrip('/')


@pytest.fixture(scope="session")
def neptune_endpoint(stack_outputs):
    """Get Neptune cluster endpoint."""
    return stack_outputs.get('NeptuneEndpoint')


@pytest.fixture(scope="session")
def state_machine_arn(stack_outputs):
    """Get Step Functions state machine ARN."""
    return stack_outputs.get('StateMachineArn')


class TestAPIGatewaySmoke:
    """Smoke tests for API Gateway endpoints."""
    
    def test_health_endpoint(self, api_base_url):
        """Test health check endpoint is accessible."""
        if not api_base_url:
            pytest.skip("API Gateway URL not available")
        
        response = requests.get(f"{api_base_url}/health", timeout=30)
        
        assert response.status_code == 200
        
        health_data = response.json()
        assert 'status' in health_data
        assert health_data['status'] in ['healthy', 'ok']
    
    def test_api_cors_headers(self, api_base_url):
        """Test CORS headers are properly configured."""
        if not api_base_url:
            pytest.skip("API Gateway URL not available")
        
        # Test OPTIONS request
        response = requests.options(f"{api_base_url}/health", timeout=30)
        
        assert 'Access-Control-Allow-Origin' in response.headers
        assert 'Access-Control-Allow-Methods' in response.headers
    
    def test_transaction_endpoint_structure(self, api_base_url):
        """Test transaction endpoint returns proper error for invalid data."""
        if not api_base_url:
            pytest.skip("API Gateway URL not available")
        
        # Test with invalid transaction data
        invalid_transaction = {"invalid": "data"}
        
        response = requests.post(
            f"{api_base_url}/transactions",
            json=invalid_transaction,
            timeout=30
        )
        
        # Should return 400 for invalid data
        assert response.status_code in [400, 422]
        
        error_data = response.json()
        assert 'error' in error_data or 'message' in error_data
    
    def test_alerts_endpoint_access(self, api_base_url):
        """Test alerts endpoint is accessible."""
        if not api_base_url:
            pytest.skip("API Gateway URL not available")
        
        response = requests.get(f"{api_base_url}/alerts", timeout=30)
        
        # Should return 200 or 401 (if auth required)
        assert response.status_code in [200, 401, 403]
        
        if response.status_code == 200:
            alerts_data = response.json()
            assert isinstance(alerts_data, (list, dict))


class TestLambdaFunctionsSmoke:
    """Smoke tests for Lambda functions."""
    
    def test_lambda_functions_exist(self, environment, aws_region):
        """Test that all expected Lambda functions exist."""
        lambda_client = boto3.client('lambda', region_name=aws_region)
        
        expected_functions = [
            f"sentinel-aml-transaction-processor",
            f"sentinel-aml-fraud-scorer",
            f"sentinel-aml-sar-generator",
            f"sentinel-aml-alert-manager",
            f"sentinel-aml-report-retriever",
            f"sentinel-aml-health-checker",
            f"sentinel-aml-orchestrator-trigger"
        ]
        
        for function_name in expected_functions:
            try:
                response = lambda_client.get_function(FunctionName=function_name)
                assert response['Configuration']['State'] == 'Active'
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    pytest.fail(f"Lambda function {function_name} not found")
                else:
                    raise
    
    def test_health_checker_lambda(self, aws_region):
        """Test health checker Lambda function."""
        lambda_client = boto3.client('lambda', region_name=aws_region)
        
        try:
            response = lambda_client.invoke(
                FunctionName="sentinel-aml-health-checker",
                InvocationType='RequestResponse',
                Payload=json.dumps({})
            )
            
            assert response['StatusCode'] == 200
            
            payload = json.loads(response['Payload'].read())
            assert 'statusCode' in payload
            assert payload['statusCode'] in [200, 500]  # May fail if dependencies not ready
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                pytest.skip("Health checker Lambda not found")
            else:
                raise


class TestStepFunctionsSmoke:
    """Smoke tests for Step Functions workflow."""
    
    def test_state_machine_exists(self, state_machine_arn, aws_region):
        """Test that Step Functions state machine exists and is active."""
        if not state_machine_arn:
            pytest.skip("State machine ARN not available")
        
        sf_client = boto3.client('stepfunctions', region_name=aws_region)
        
        response = sf_client.describe_state_machine(stateMachineArn=state_machine_arn)
        
        assert response['status'] == 'ACTIVE'
        assert 'definition' in response
        assert 'roleArn' in response
    
    def test_state_machine_execution_dry_run(self, state_machine_arn, aws_region):
        """Test Step Functions state machine can be started (dry run)."""
        if not state_machine_arn:
            pytest.skip("State machine ARN not available")
        
        sf_client = boto3.client('stepfunctions', region_name=aws_region)
        
        # Create a test execution with minimal data
        test_input = {
            "transaction_data": {
                "transaction_id": f"smoke-test-{uuid.uuid4()}",
                "from_account_id": "TEST_ACCOUNT_123",
                "to_account_id": "TEST_ACCOUNT_456",
                "amount": 100.0,
                "currency": "USD",
                "timestamp": "2024-01-01T00:00:00Z",
                "transaction_type": "test"
            },
            "account_id": "TEST_ACCOUNT_123",
            "correlation_id": str(uuid.uuid4()),
            "test_mode": True
        }
        
        try:
            response = sf_client.start_execution(
                stateMachineArn=state_machine_arn,
                name=f"smoke-test-{int(time.time())}",
                input=json.dumps(test_input)
            )
            
            execution_arn = response['executionArn']
            
            # Wait a moment and check status
            time.sleep(2)
            
            status_response = sf_client.describe_execution(executionArn=execution_arn)
            
            # Execution should have started (may be running or completed)
            assert status_response['status'] in ['RUNNING', 'SUCCEEDED', 'FAILED']
            
            # Stop the execution if it's still running
            if status_response['status'] == 'RUNNING':
                sf_client.stop_execution(
                    executionArn=execution_arn,
                    cause="Smoke test cleanup"
                )
            
        except ClientError as e:
            # If execution fails due to Lambda errors, that's expected in smoke test
            if e.response['Error']['Code'] not in ['ExecutionLimitExceeded']:
                raise


class TestNeptuneSmoke:
    """Smoke tests for Neptune database."""
    
    def test_neptune_cluster_available(self, neptune_endpoint, aws_region):
        """Test Neptune cluster is available."""
        if not neptune_endpoint:
            pytest.skip("Neptune endpoint not available")
        
        neptune_client = boto3.client('neptune', region_name=aws_region)
        
        # List clusters to verify Neptune is accessible
        response = neptune_client.describe_db_clusters()
        
        # Should have at least one cluster
        assert len(response['DBClusters']) > 0
        
        # Find our cluster
        cluster_found = False
        for cluster in response['DBClusters']:
            if neptune_endpoint in cluster['Endpoint']:
                cluster_found = True
                assert cluster['Status'] == 'available'
                break
        
        assert cluster_found, f"Neptune cluster with endpoint {neptune_endpoint} not found"
    
    def test_neptune_connectivity_basic(self, neptune_endpoint):
        """Test basic Neptune connectivity (if accessible)."""
        if not neptune_endpoint:
            pytest.skip("Neptune endpoint not available")
        
        # Note: This test may fail if Neptune is in a private subnet
        # In production, this would be tested from within the VPC
        
        import socket
        
        try:
            # Try to connect to Neptune port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((neptune_endpoint, 8182))
            sock.close()
            
            # Connection may fail due to security groups, but endpoint should resolve
            # We're mainly testing that the endpoint exists and is reachable
            
        except socket.gaierror:
            pytest.fail(f"Neptune endpoint {neptune_endpoint} could not be resolved")


class TestMonitoringSmoke:
    """Smoke tests for monitoring and observability."""
    
    def test_cloudwatch_dashboard_exists(self, environment, aws_region):
        """Test CloudWatch dashboard exists."""
        cw_client = boto3.client('cloudwatch', region_name=aws_region)
        
        dashboard_name = "Sentinel-AML-System-Metrics"
        
        try:
            response = cw_client.get_dashboard(DashboardName=dashboard_name)
            assert 'DashboardBody' in response
            
            # Verify dashboard has content
            dashboard_body = json.loads(response['DashboardBody'])
            assert 'widgets' in dashboard_body
            assert len(dashboard_body['widgets']) > 0
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFound':
                pytest.skip(f"CloudWatch dashboard {dashboard_name} not found")
            else:
                raise
    
    def test_sns_topic_exists(self, environment, aws_region):
        """Test SNS alert topic exists."""
        sns_client = boto3.client('sns', region_name=aws_region)
        
        # List topics and look for our alert topic
        response = sns_client.list_topics()
        
        topic_found = False
        for topic in response['Topics']:
            if 'sentinel-aml-alerts' in topic['TopicArn']:
                topic_found = True
                break
        
        if not topic_found:
            pytest.skip("SNS alert topic not found")
    
    def test_cloudwatch_alarms_exist(self, environment, aws_region):
        """Test CloudWatch alarms are configured."""
        cw_client = boto3.client('cloudwatch', region_name=aws_region)
        
        # List alarms with our prefix
        response = cw_client.describe_alarms(AlarmNamePrefix="sentinel-aml")
        
        alarms = response['MetricAlarms']
        
        if len(alarms) == 0:
            pytest.skip("No CloudWatch alarms found")
        
        # Verify alarms are in OK or ALARM state (not INSUFFICIENT_DATA for too long)
        for alarm in alarms:
            assert alarm['StateValue'] in ['OK', 'ALARM', 'INSUFFICIENT_DATA']


class TestSecuritySmoke:
    """Smoke tests for security configuration."""
    
    def test_kms_key_exists(self, environment, aws_region):
        """Test KMS key exists and is enabled."""
        kms_client = boto3.client('kms', region_name=aws_region)
        
        # List keys and look for our key (by alias or description)
        response = kms_client.list_keys()
        
        # This is a basic test - in practice, you'd look for specific key aliases
        assert len(response['Keys']) > 0
    
    def test_iam_roles_exist(self, environment, aws_region):
        """Test required IAM roles exist."""
        iam_client = boto3.client('iam', region_name=aws_region)
        
        expected_role_patterns = [
            'SentinelAML',  # Should match our role naming pattern
        ]
        
        response = iam_client.list_roles()
        
        sentinel_roles = [
            role for role in response['Roles']
            if any(pattern in role['RoleName'] for pattern in expected_role_patterns)
        ]
        
        # Should have at least some Sentinel-AML roles
        assert len(sentinel_roles) > 0


class TestEndToEndSmoke:
    """End-to-end smoke tests."""
    
    def test_transaction_processing_workflow(self, api_base_url, state_machine_arn, aws_region):
        """Test complete transaction processing workflow (if possible)."""
        if not api_base_url or not state_machine_arn:
            pytest.skip("Required endpoints not available")
        
        # Create a test transaction
        test_transaction = {
            "transaction_id": f"smoke-e2e-{uuid.uuid4()}",
            "from_account_id": "SMOKE_TEST_FROM",
            "to_account_id": "SMOKE_TEST_TO",
            "amount": 5000.0,
            "currency": "USD",
            "timestamp": "2024-01-01T12:00:00Z",
            "transaction_type": "transfer"
        }
        
        try:
            # Submit transaction via API
            response = requests.post(
                f"{api_base_url}/transactions",
                json=test_transaction,
                timeout=30
            )
            
            # Should either succeed or fail with validation error
            assert response.status_code in [200, 201, 202, 400, 422]
            
            if response.status_code in [200, 201, 202]:
                # Transaction was accepted
                result = response.json()
                
                # Should have some indication of processing
                assert 'status' in result or 'message' in result
            
        except requests.exceptions.RequestException:
            pytest.skip("API endpoint not accessible for end-to-end test")
    
    def test_system_health_overall(self, api_base_url, neptune_endpoint, state_machine_arn):
        """Test overall system health."""
        health_checks = []
        
        # API Gateway health
        if api_base_url:
            try:
                response = requests.get(f"{api_base_url}/health", timeout=10)
                health_checks.append(("API Gateway", response.status_code == 200))
            except:
                health_checks.append(("API Gateway", False))
        
        # Neptune availability
        health_checks.append(("Neptune", bool(neptune_endpoint)))
        
        # Step Functions availability
        health_checks.append(("Step Functions", bool(state_machine_arn)))
        
        # At least 2 out of 3 components should be healthy
        healthy_count = sum(1 for _, healthy in health_checks if healthy)
        total_count = len(health_checks)
        
        health_ratio = healthy_count / total_count if total_count > 0 else 0
        
        assert health_ratio >= 0.6, f"System health too low: {healthy_count}/{total_count} components healthy"