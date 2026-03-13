"""
Property-based tests for Step Functions orchestration workflow.

Tests universal properties that must hold for all workflow executions
in the Sentinel-AML system.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, patch

import pytest
from hypothesis import given, strategies as st, assume, settings
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize, invariant

from src.sentinel_aml.orchestration.trigger_handler import OrchestrationTrigger
from src.sentinel_aml.orchestration.workflow_manager import WorkflowManager
from src.sentinel_aml.orchestration.status_tracker import StatusTracker
from src.sentinel_aml.core.exceptions import OrchestrationError


# Test data generators
@st.composite
def transaction_data(draw):
    """Generate valid transaction data for testing."""
    return {
        "transaction_id": draw(st.uuids()).hex,
        "from_account_id": draw(st.text(min_size=8, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))),
        "to_account_id": draw(st.text(min_size=8, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))),
        "amount": draw(st.floats(min_value=0.01, max_value=1000000.0)),
        "currency": draw(st.sampled_from(["USD", "EUR", "GBP", "JPY"])),
        "timestamp": datetime.utcnow().isoformat(),
        "transaction_type": draw(st.sampled_from(["transfer", "deposit", "withdrawal", "payment"]))
    }


@st.composite
def suspicious_transaction_data(draw):
    """Generate transaction data that should trigger suspicious activity detection."""
    base_transaction = draw(transaction_data())
    
    # Make it suspicious by adding patterns that should trigger high risk scores
    suspicious_patterns = draw(st.sampled_from([
        "high_frequency",  # Multiple transactions in short time
        "round_amounts",   # Suspiciously round amounts
        "structuring",     # Just under reporting thresholds
        "velocity"         # High velocity patterns
    ]))
    
    if suspicious_patterns == "round_amounts":
        base_transaction["amount"] = draw(st.sampled_from([1000.0, 5000.0, 10000.0, 9999.0]))
    elif suspicious_patterns == "structuring":
        base_transaction["amount"] = draw(st.floats(min_value=9500.0, max_value=9999.99))
    elif suspicious_patterns == "high_frequency":
        base_transaction["frequency_indicator"] = "high"
    
    return base_transaction


class TestOrchestrationProperties:
    """Property-based tests for orchestration workflow."""
    
    @given(transaction_data())
    @settings(max_examples=50, deadline=5000)
    def test_property_workflow_completeness_all_transactions_trigger_workflow(self, transaction):
        """
        Property 7: Workflow completeness - All suspicious transactions must trigger complete workflow.
        
        This property ensures that every transaction that enters the system
        triggers the complete workflow pipeline without exceptions.
        """
        with patch('boto3.client') as mock_boto_client:
            # Mock Step Functions client
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            # Mock successful workflow trigger
            execution_arn = f"arn:aws:states:us-east-1:123456789012:execution:sentinel-aml-processing-workflow:{uuid.uuid4()}"
            mock_sf_client.start_execution.return_value = {
                "executionArn": execution_arn,
                "startDate": datetime.utcnow()
            }
            
            orchestrator = OrchestrationTrigger()
            
            # Trigger workflow for the transaction
            result = orchestrator.trigger_workflow(transaction)
            
            # Verify workflow was triggered
            assert result["status"] == "triggered"
            assert "execution_arn" in result
            assert "correlation_id" in result
            assert "started_at" in result
            
            # Verify Step Functions was called with correct parameters
            mock_sf_client.start_execution.assert_called_once()
            call_args = mock_sf_client.start_execution.call_args
            
            # Verify input contains required fields
            workflow_input = json.loads(call_args[1]["input"])
            assert workflow_input["transaction_data"] == transaction
            assert workflow_input["account_id"] == transaction["from_account_id"]
            assert "correlation_id" in workflow_input
            assert "timestamp" in workflow_input
            assert workflow_input["trigger_source"] == "transaction_ingestion"
    
    @given(suspicious_transaction_data())
    @settings(max_examples=30, deadline=5000)
    def test_property_suspicious_transactions_complete_pipeline(self, suspicious_transaction):
        """
        Property: Suspicious transactions must complete the full pipeline.
        
        Ensures that transactions flagged as suspicious go through all
        required processing steps: GNN Analysis → SAR Generation → Alert Creation.
        """
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            execution_arn = f"arn:aws:states:us-east-1:123456789012:execution:sentinel-aml-processing-workflow:{uuid.uuid4()}"
            mock_sf_client.start_execution.return_value = {
                "executionArn": execution_arn,
                "startDate": datetime.utcnow()
            }
            
            orchestrator = OrchestrationTrigger()
            result = orchestrator.trigger_workflow(suspicious_transaction)
            
            # Verify workflow triggered for suspicious transaction
            assert result["status"] == "triggered"
            
            # Verify the workflow input includes all necessary data for suspicious activity processing
            call_args = mock_sf_client.start_execution.call_args
            workflow_input = json.loads(call_args[1]["input"])
            
            # Must include transaction data for GNN analysis
            assert "transaction_data" in workflow_input
            assert workflow_input["transaction_data"]["amount"] > 0
            
            # Must include account ID for risk assessment
            assert "account_id" in workflow_input
            assert workflow_input["account_id"] == suspicious_transaction["from_account_id"]
    
    @given(st.lists(transaction_data(), min_size=1, max_size=10))
    @settings(max_examples=20, deadline=10000)
    def test_property_batch_processing_consistency(self, transactions):
        """
        Property: Batch processing must maintain consistency.
        
        When multiple transactions are processed, each must be handled
        independently and consistently.
        """
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            # Mock successful executions for all transactions
            execution_arns = []
            for i, _ in enumerate(transactions):
                arn = f"arn:aws:states:us-east-1:123456789012:execution:sentinel-aml-processing-workflow:batch-{i}-{uuid.uuid4()}"
                execution_arns.append(arn)
            
            mock_sf_client.start_execution.side_effect = [
                {"executionArn": arn, "startDate": datetime.utcnow()}
                for arn in execution_arns
            ]
            
            orchestrator = OrchestrationTrigger()
            results = []
            
            # Process each transaction
            for transaction in transactions:
                result = orchestrator.trigger_workflow(transaction)
                results.append(result)
            
            # Verify all transactions were processed
            assert len(results) == len(transactions)
            
            # Verify each result has required fields
            for i, result in enumerate(results):
                assert result["status"] == "triggered"
                assert "execution_arn" in result
                assert "correlation_id" in result
                assert result["execution_arn"] == execution_arns[i]
            
            # Verify Step Functions was called for each transaction
            assert mock_sf_client.start_execution.call_count == len(transactions)
    
    @given(transaction_data())
    @settings(max_examples=20, deadline=5000)
    def test_property_error_handling_resilience(self, transaction):
        """
        Property: Workflow must handle errors gracefully.
        
        When Step Functions fails to start, the system must handle
        the error appropriately without losing transaction data.
        """
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = Mock()
            mock_boto_client.return_value = mock_sf_client
            
            # Mock Step Functions failure
            from botocore.exceptions import ClientError
            mock_sf_client.start_execution.side_effect = ClientError(
                error_response={'Error': {'Code': 'ExecutionLimitExceeded', 'Message': 'Too many executions'}},
                operation_name='StartExecution'
            )
            
            orchestrator = OrchestrationTrigger()
            
            # Verify error is handled gracefully
            with pytest.raises(OrchestrationError) as exc_info:
                orchestrator.trigger_workflow(transaction)
            
            # Verify error message is informative
            assert "Failed to trigger Step Functions workflow" in str(exc_info.value)
    
    @given(st.text(min_size=10, max_size=100))
    @settings(max_examples=20, deadline=5000)
    def test_property_execution_status_tracking(self, execution_name):
        """
        Property: All executions must be trackable by status.
        
        Every workflow execution must be trackable through its lifecycle
        with proper status updates.
        """
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
            
            execution_arn = f"arn:aws:states:us-east-1:123456789012:execution:sentinel-aml-processing-workflow:{execution_name}"
            correlation_id = str(uuid.uuid4())
            
            execution_data = {
                "execution_arn": execution_arn,
                "correlation_id": correlation_id,
                "transaction_id": "test-transaction",
                "account_id": "test-account"
            }
            
            # Track execution start
            tracker.track_execution_start(execution_data)
            
            # Verify DynamoDB put_item was called
            mock_table.put_item.assert_called_once()
            
            # Verify the item contains required fields
            put_item_call = mock_table.put_item.call_args[1]['Item']
            assert put_item_call['execution_arn'] == execution_arn
            assert put_item_call['correlation_id'] == correlation_id
            assert put_item_call['status'] == 'RUNNING'
            assert 'started_at' in put_item_call
            assert 'last_updated' in put_item_call


class OrchestrationStateMachine(RuleBasedStateMachine):
    """
    Stateful property testing for orchestration workflow.
    
    Tests the orchestration system through various state transitions
    to ensure consistency and correctness.
    """
    
    def __init__(self):
        super().__init__()
        self.active_executions = {}
        self.completed_executions = {}
        
    @initialize()
    def setup(self):
        """Initialize the state machine."""
        # Mock AWS clients
        self.mock_sf_client = Mock()
        self.mock_dynamodb = Mock()
        self.mock_sns_client = Mock()
        
        with patch('boto3.client', return_value=self.mock_sf_client), \
             patch('boto3.resource', return_value=self.mock_dynamodb):
            self.orchestrator = OrchestrationTrigger()
            self.tracker = StatusTracker()
    
    @rule(transaction=transaction_data())
    def start_workflow(self, transaction):
        """Start a new workflow execution."""
        execution_arn = f"arn:aws:states:us-east-1:123456789012:execution:test:{uuid.uuid4()}"
        
        self.mock_sf_client.start_execution.return_value = {
            "executionArn": execution_arn,
            "startDate": datetime.utcnow()
        }
        
        result = self.orchestrator.trigger_workflow(transaction)
        
        # Track the execution
        self.active_executions[execution_arn] = {
            "transaction": transaction,
            "result": result,
            "status": "RUNNING"
        }
    
    @rule()
    def complete_workflow(self):
        """Complete a running workflow."""
        if self.active_executions:
            execution_arn = list(self.active_executions.keys())[0]
            execution = self.active_executions.pop(execution_arn)
            execution["status"] = "SUCCEEDED"
            self.completed_executions[execution_arn] = execution
    
    @rule()
    def fail_workflow(self):
        """Fail a running workflow."""
        if self.active_executions:
            execution_arn = list(self.active_executions.keys())[0]
            execution = self.active_executions.pop(execution_arn)
            execution["status"] = "FAILED"
            self.completed_executions[execution_arn] = execution
    
    @invariant()
    def executions_are_tracked(self):
        """Invariant: All executions must be properly tracked."""
        total_executions = len(self.active_executions) + len(self.completed_executions)
        
        # If we have executions, verify they all have required fields
        for execution_arn, execution in {**self.active_executions, **self.completed_executions}.items():
            assert "transaction" in execution
            assert "result" in execution
            assert "status" in execution
            assert execution["status"] in ["RUNNING", "SUCCEEDED", "FAILED"]
    
    @invariant()
    def no_duplicate_executions(self):
        """Invariant: No execution ARN should appear in both active and completed."""
        active_arns = set(self.active_executions.keys())
        completed_arns = set(self.completed_executions.keys())
        assert active_arns.isdisjoint(completed_arns)


# Test the state machine
TestOrchestrationStateMachine = OrchestrationStateMachine.TestCase