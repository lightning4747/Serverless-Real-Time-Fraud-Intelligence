"""
Integration tests for Step Functions orchestration workflow.

Tests the complete end-to-end workflow execution including error scenarios
and retry behavior in the Sentinel-AML system.
"""

import json
import uuid
import time
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

import pytest
import boto3
from moto import mock_stepfunctions, mock_lambda, mock_iam, mock_logs
from botocore.exceptions import ClientError

from src.sentinel_aml.orchestration.trigger_handler import OrchestrationTrigger, lambda_handler
from src.sentinel_aml.orchestration.workflow_manager import WorkflowManager, WorkflowStatus
from src.sentinel_aml.orchestration.status_tracker import StatusTracker
from src.sentinel_aml.core.exceptions import OrchestrationError


@pytest.fixture
def sample_transaction():
    """Sample transaction data for testing."""
    return {
        "transaction_id": str(uuid.uuid4()),
        "from_account_id": "ACC123456789",
        "to_account_id": "ACC987654321", 
        "amount": 15000.0,
        "currency": "USD",
        "timestamp": datetime.utcnow().isoformat(),
        "transaction_type": "transfer"
    }


@pytest.fixture
def sample_high_risk_transaction():
    """Sample high-risk transaction that should trigger SAR generation."""
    return {
        "transaction_id": str(uuid.uuid4()),
        "from_account_id": "ACC999888777",
        "to_account_id": "ACC111222333",
        "amount": 9999.99,  # Just under $10k threshold - suspicious structuring
        "currency": "USD",
        "timestamp": datetime.utcnow().isoformat(),
        "transaction_type": "transfer",
        "risk_indicators": ["structuring", "high_velocity"]
    }


@pytest.fixture
def mock_lambda_functions():
    """Mock Lambda function responses for Step Functions tasks."""
    return {
        "fraud_scorer": {
            "StatusCode": 200,
            "Payload": json.dumps({
                "risk_score": 0.85,
                "risk_level": "high",
                "suspicious_patterns": ["structuring", "velocity"],
                "confidence": 0.92
            })
        },
        "sar_generator": {
            "StatusCode": 200,
            "Payload": json.dumps({
                "sar_id": "SAR-2024-001234",
                "report_status": "generated",
                "confidence_score": 0.88,
                "filing_required": True
            })
        },
        "alert_manager": {
            "StatusCode": 200,
            "Payload": json.dumps({
                "alert_id": "ALERT-2024-005678",
                "alert_status": "created",
                "priority": "high",
                "assigned_to": "compliance_team"
            })
        }
    }


class TestStepFunctionsIntegration:
    """Integration tests for Step Functions workflow."""
    
    def test_orchestration_trigger_direct_invocation(self, sample_transaction):
        """Test direct Lambda invocation for orchestration trigger."""
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            execution_arn = f"arn:aws:states:us-east-1:123456789012:execution:sentinel-aml-processing-workflow:{uuid.uuid4()}"
            mock_sf_client.start_execution.return_value = {
                "executionArn": execution_arn,
                "startDate": datetime.utcnow()
            }
            
            # Test direct invocation
            event = {"transaction_data": sample_transaction}
            context = Mock()
            
            response = lambda_handler(event, context)
            
            assert response["statusCode"] == 200
            result = json.loads(response["body"])
            assert result["status"] == "triggered"
            assert "execution_arn" in result
            assert "correlation_id" in result
    
    def test_orchestration_trigger_api_gateway_event(self, sample_transaction):
        """Test API Gateway event handling for orchestration trigger."""
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            execution_arn = f"arn:aws:states:us-east-1:123456789012:execution:sentinel-aml-processing-workflow:{uuid.uuid4()}"
            mock_sf_client.start_execution.return_value = {
                "executionArn": execution_arn,
                "startDate": datetime.utcnow()
            }
            
            # Test API Gateway POST event
            event = {
                "httpMethod": "POST",
                "body": json.dumps(sample_transaction),
                "headers": {"Content-Type": "application/json"}
            }
            context = Mock()
            
            response = lambda_handler(event, context)
            
            assert response["statusCode"] == 202
            assert "Access-Control-Allow-Origin" in response["headers"]
            result = json.loads(response["body"])
            assert result["status"] == "triggered"
    
    def test_orchestration_trigger_sqs_batch_event(self, sample_transaction):
        """Test SQS batch event handling for orchestration trigger."""
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            execution_arn = f"arn:aws:states:us-east-1:123456789012:execution:sentinel-aml-processing-workflow:{uuid.uuid4()}"
            mock_sf_client.start_execution.return_value = {
                "executionArn": execution_arn,
                "startDate": datetime.utcnow()
            }
            
            # Test SQS batch event
            event = {
                "Records": [
                    {
                        "eventSource": "aws:sqs",
                        "body": json.dumps(sample_transaction)
                    },
                    {
                        "eventSource": "aws:sqs", 
                        "body": json.dumps({**sample_transaction, "transaction_id": str(uuid.uuid4())})
                    }
                ]
            }
            context = Mock()
            
            response = lambda_handler(event, context)
            
            assert response["statusCode"] == 200
            result = json.loads(response["body"])
            assert "Triggered 2 workflows" in result["message"]
            assert len(result["results"]) == 2
    
    def test_workflow_manager_list_executions(self):
        """Test workflow manager execution listing functionality."""
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            # Mock list_executions response
            mock_sf_client.list_executions.return_value = {
                "executions": [
                    {
                        "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test:exec1",
                        "name": "transaction-test-1",
                        "status": "SUCCEEDED",
                        "startDate": datetime.utcnow(),
                        "stopDate": datetime.utcnow()
                    },
                    {
                        "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test:exec2",
                        "name": "transaction-test-2", 
                        "status": "RUNNING",
                        "startDate": datetime.utcnow()
                    }
                ]
            }
            
            manager = WorkflowManager()
            executions = manager.list_executions(status_filter=None, max_results=10)
            
            assert len(executions) == 2
            assert executions[0]["status"] == "SUCCEEDED"
            assert executions[1]["status"] == "RUNNING"
            assert "execution_arn" in executions[0]
            assert "started_at" in executions[0]
    
    def test_workflow_manager_execution_details(self):
        """Test workflow manager execution details retrieval."""
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            execution_arn = "arn:aws:states:us-east-1:123456789012:execution:test:exec1"
            correlation_id = str(uuid.uuid4())
            
            # Mock describe_execution response
            mock_sf_client.describe_execution.return_value = {
                "executionArn": execution_arn,
                "name": "transaction-test-1",
                "status": "SUCCEEDED",
                "startDate": datetime.utcnow(),
                "stopDate": datetime.utcnow(),
                "input": json.dumps({
                    "correlation_id": correlation_id,
                    "transaction_data": {"transaction_id": "test-123"},
                    "account_id": "ACC123"
                }),
                "output": json.dumps({
                    "status": "completed",
                    "risk_level": "high",
                    "action_taken": "sar_generated_and_alert_created"
                })
            }
            
            # Mock get_execution_history response
            mock_sf_client.get_execution_history.return_value = {
                "events": [
                    {
                        "timestamp": datetime.utcnow(),
                        "type": "ExecutionStarted",
                        "id": 1,
                        "executionStartedEventDetails": {}
                    },
                    {
                        "timestamp": datetime.utcnow(),
                        "type": "TaskStateEntered",
                        "id": 2,
                        "stateEnteredEventDetails": {"name": "FraudScoringTask"}
                    }
                ]
            }
            
            manager = WorkflowManager()
            details = manager.get_execution_details(execution_arn)
            
            assert details["execution_arn"] == execution_arn
            assert details["status"] == "SUCCEEDED"
            assert details["correlation_id"] == correlation_id
            assert details["transaction_id"] == "test-123"
            assert details["account_id"] == "ACC123"
            assert len(details["history"]) == 2
    
    def test_workflow_manager_metrics_calculation(self):
        """Test workflow manager metrics calculation."""
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_cloudwatch_client = Mock()
            mock_boto_client.side_effect = [mock_sf_client, mock_cloudwatch_client]
            
            # Mock recent executions
            recent_time = datetime.utcnow()
            mock_sf_client.list_executions.return_value = {
                "executions": [
                    {
                        "executionArn": f"arn:aws:states:us-east-1:123456789012:execution:test:exec{i}",
                        "name": f"transaction-test-{i}",
                        "status": "SUCCEEDED" if i < 8 else "FAILED",
                        "startDate": recent_time,
                        "stopDate": recent_time
                    }
                    for i in range(10)
                ]
            }
            
            manager = WorkflowManager()
            metrics = manager.get_workflow_metrics(hours=24)
            
            assert metrics["total_executions"] == 10
            assert metrics["successful_executions"] == 8
            assert metrics["failed_executions"] == 2
            assert metrics["success_rate_percent"] == 80.0
            assert "average_execution_time_seconds" in metrics
    
    def test_status_tracker_execution_lifecycle(self):
        """Test status tracker through complete execution lifecycle."""
        with patch('boto3.resource') as mock_boto_resource, \
             patch('boto3.client') as mock_boto_client:
            
            # Mock DynamoDB table
            mock_table = Mock()
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            
            # Mock SNS client
            mock_sns_client = Mock()
            mock_boto_client.return_value = mock_sns_client
            
            tracker = StatusTracker()
            
            execution_arn = "arn:aws:states:us-east-1:123456789012:execution:test:lifecycle"
            correlation_id = str(uuid.uuid4())
            
            execution_data = {
                "execution_arn": execution_arn,
                "correlation_id": correlation_id,
                "transaction_id": "test-transaction",
                "account_id": "test-account"
            }
            
            # Test execution start tracking
            tracker.track_execution_start(execution_data)
            mock_table.put_item.assert_called_once()
            
            # Test status update
            tracker.update_execution_status(
                execution_arn, 
                "RUNNING", 
                current_step="fraud_scoring",
                step_result={"step": "fraud_scoring", "completed_at": datetime.utcnow().isoformat()}
            )
            mock_table.update_item.assert_called()
            
            # Test completion with notification
            tracker.update_execution_status(execution_arn, "SUCCEEDED")
            
            # Verify SNS notification was sent
            mock_sns_client.publish.assert_called()
            notification_call = mock_sns_client.publish.call_args
            assert "sentinel-aml-notifications" in notification_call[1]["TopicArn"]
    
    def test_error_handling_step_functions_failure(self, sample_transaction):
        """Test error handling when Step Functions fails to start."""
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            # Mock Step Functions failure
            mock_sf_client.start_execution.side_effect = ClientError(
                error_response={
                    'Error': {
                        'Code': 'ExecutionLimitExceeded',
                        'Message': 'Maximum number of executions exceeded'
                    }
                },
                operation_name='StartExecution'
            )
            
            orchestrator = OrchestrationTrigger()
            
            with pytest.raises(OrchestrationError) as exc_info:
                orchestrator.trigger_workflow(sample_transaction)
            
            assert "Failed to trigger Step Functions workflow" in str(exc_info.value)
    
    def test_retry_behavior_transient_failures(self, sample_transaction):
        """Test retry behavior for transient failures."""
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            # First call fails, second succeeds
            execution_arn = f"arn:aws:states:us-east-1:123456789012:execution:sentinel-aml-processing-workflow:{uuid.uuid4()}"
            mock_sf_client.start_execution.side_effect = [
                ClientError(
                    error_response={'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
                    operation_name='StartExecution'
                ),
                {
                    "executionArn": execution_arn,
                    "startDate": datetime.utcnow()
                }
            ]
            
            orchestrator = OrchestrationTrigger()
            
            # First attempt should fail
            with pytest.raises(OrchestrationError):
                orchestrator.trigger_workflow(sample_transaction)
            
            # Second attempt should succeed
            result = orchestrator.trigger_workflow(sample_transaction)
            assert result["status"] == "triggered"
    
    def test_end_to_end_workflow_simulation(self, sample_high_risk_transaction, mock_lambda_functions):
        """Test complete end-to-end workflow simulation."""
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            execution_arn = f"arn:aws:states:us-east-1:123456789012:execution:sentinel-aml-processing-workflow:{uuid.uuid4()}"
            
            # Mock Step Functions execution
            mock_sf_client.start_execution.return_value = {
                "executionArn": execution_arn,
                "startDate": datetime.utcnow()
            }
            
            # Mock execution status progression
            status_progression = [
                {"status": "RUNNING"},
                {"status": "RUNNING"},  # Still processing
                {
                    "status": "SUCCEEDED",
                    "output": json.dumps({
                        "status": "completed",
                        "risk_level": "high", 
                        "action_taken": "sar_generated_and_alert_created",
                        "fraud_analysis": {"Payload": {"risk_score": 0.85}},
                        "sar_report": {"Payload": {"sar_id": "SAR-2024-001234"}},
                        "alert_result": {"Payload": {"alert_id": "ALERT-2024-005678"}}
                    })
                }
            ]
            
            mock_sf_client.describe_execution.side_effect = [
                {
                    "executionArn": execution_arn,
                    "name": "high-risk-transaction-test",
                    "status": status["status"],
                    "startDate": datetime.utcnow(),
                    "stopDate": datetime.utcnow() if status["status"] == "SUCCEEDED" else None,
                    "input": json.dumps({
                        "transaction_data": sample_high_risk_transaction,
                        "correlation_id": str(uuid.uuid4())
                    }),
                    "output": status.get("output")
                }
                for status in status_progression
            ]
            
            orchestrator = OrchestrationTrigger()
            
            # Start the workflow
            result = orchestrator.trigger_workflow(sample_high_risk_transaction)
            assert result["status"] == "triggered"
            
            # Check status progression
            for i, expected_status in enumerate(["RUNNING", "RUNNING", "SUCCEEDED"]):
                status = orchestrator.check_execution_status(result["execution_arn"])
                assert status["status"] == expected_status
                
                if status["status"] == "SUCCEEDED":
                    # Verify final output contains all required components
                    output = status["output"]
                    assert output["risk_level"] == "high"
                    assert output["action_taken"] == "sar_generated_and_alert_created"
                    assert "fraud_analysis" in output
                    assert "sar_report" in output
                    assert "alert_result" in output
    
    def test_workflow_timeout_handling(self, sample_transaction):
        """Test handling of workflow timeouts."""
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            execution_arn = f"arn:aws:states:us-east-1:123456789012:execution:sentinel-aml-processing-workflow:{uuid.uuid4()}"
            
            mock_sf_client.start_execution.return_value = {
                "executionArn": execution_arn,
                "startDate": datetime.utcnow()
            }
            
            # Mock timeout status
            mock_sf_client.describe_execution.return_value = {
                "executionArn": execution_arn,
                "name": "timeout-test",
                "status": "TIMED_OUT",
                "startDate": datetime.utcnow(),
                "stopDate": datetime.utcnow(),
                "input": json.dumps({
                    "transaction_data": sample_transaction,
                    "correlation_id": str(uuid.uuid4())
                })
            }
            
            orchestrator = OrchestrationTrigger()
            
            # Start workflow
            result = orchestrator.trigger_workflow(sample_transaction)
            
            # Check timeout status
            status = orchestrator.check_execution_status(result["execution_arn"])
            assert status["status"] == "TIMED_OUT"
    
    def test_concurrent_workflow_execution(self, sample_transaction):
        """Test handling of concurrent workflow executions."""
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            # Mock multiple concurrent executions
            execution_arns = [
                f"arn:aws:states:us-east-1:123456789012:execution:sentinel-aml-processing-workflow:concurrent-{i}-{uuid.uuid4()}"
                for i in range(5)
            ]
            
            mock_sf_client.start_execution.side_effect = [
                {"executionArn": arn, "startDate": datetime.utcnow()}
                for arn in execution_arns
            ]
            
            orchestrator = OrchestrationTrigger()
            
            # Start multiple concurrent workflows
            results = []
            for i in range(5):
                transaction = {**sample_transaction, "transaction_id": f"concurrent-{i}"}
                result = orchestrator.trigger_workflow(transaction)
                results.append(result)
            
            # Verify all workflows started successfully
            assert len(results) == 5
            for i, result in enumerate(results):
                assert result["status"] == "triggered"
                assert result["execution_arn"] == execution_arns[i]
            
            # Verify Step Functions was called 5 times
            assert mock_sf_client.start_execution.call_count == 5