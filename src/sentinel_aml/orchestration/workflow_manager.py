"""
Workflow manager for Step Functions orchestration.

Provides utilities for managing, monitoring, and tracking Step Functions
workflow executions in the Sentinel-AML system.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum

import boto3
from botocore.exceptions import ClientError

from ..core.config import get_config
from ..core.logging_config import setup_logging
from ..core.exceptions import OrchestrationError

logger = setup_logging(__name__)


class WorkflowStatus(Enum):
    """Workflow execution status enumeration."""
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    ABORTED = "ABORTED"


class WorkflowManager:
    """Manages Step Functions workflow executions and monitoring."""
    
    def __init__(self):
        """Initialize the workflow manager."""
        self.config = get_config()
        self.stepfunctions_client = boto3.client('stepfunctions')
        self.cloudwatch_client = boto3.client('cloudwatch')
        
    def list_executions(
        self, 
        status_filter: Optional[WorkflowStatus] = None,
        max_results: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        List Step Functions executions with optional filtering.
        
        Args:
            status_filter: Filter by execution status
            max_results: Maximum number of results to return
            start_time: Filter executions started after this time
            end_time: Filter executions started before this time
            
        Returns:
            List of execution details
        """
        try:
            params = {
                'stateMachineArn': self.config.state_machine_arn,
                'maxResults': max_results
            }
            
            if status_filter:
                params['statusFilter'] = status_filter.value
            
            response = self.stepfunctions_client.list_executions(**params)
            
            executions = []
            for execution in response['executions']:
                # Apply time filtering if specified
                start_date = execution['startDate']
                if start_time and start_date < start_time:
                    continue
                if end_time and start_date > end_time:
                    continue
                
                executions.append({
                    'execution_arn': execution['executionArn'],
                    'name': execution['name'],
                    'status': execution['status'],
                    'started_at': start_date.isoformat(),
                    'stopped_at': execution.get('stopDate', {}).isoformat() if execution.get('stopDate') else None
                })
            
            return executions
            
        except ClientError as e:
            logger.error(f"Failed to list executions: {e}")
            raise OrchestrationError(f"Failed to list executions: {e}") from e
    
    def get_execution_details(self, execution_arn: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific execution.
        
        Args:
            execution_arn: ARN of the execution
            
        Returns:
            Detailed execution information
        """
        try:
            # Get execution details
            execution_response = self.stepfunctions_client.describe_execution(
                executionArn=execution_arn
            )
            
            # Get execution history for step-by-step details
            history_response = self.stepfunctions_client.get_execution_history(
                executionArn=execution_arn,
                maxResults=100,
                reverseOrder=True
            )
            
            # Parse input and output
            input_data = json.loads(execution_response.get('input', '{}'))
            output_data = json.loads(execution_response.get('output', '{}')) if execution_response.get('output') else None
            
            # Extract correlation ID for tracking
            correlation_id = input_data.get('correlation_id', 'unknown')
            
            return {
                'execution_arn': execution_arn,
                'name': execution_response['name'],
                'status': execution_response['status'],
                'started_at': execution_response['startDate'].isoformat(),
                'stopped_at': execution_response.get('stopDate', {}).isoformat() if execution_response.get('stopDate') else None,
                'input': input_data,
                'output': output_data,
                'correlation_id': correlation_id,
                'transaction_id': input_data.get('transaction_data', {}).get('transaction_id'),
                'account_id': input_data.get('account_id'),
                'history': [
                    {
                        'timestamp': event['timestamp'].isoformat(),
                        'type': event['type'],
                        'id': event['id'],
                        'details': event.get('stateEnteredEventDetails', event.get('stateExitedEventDetails', {}))
                    }
                    for event in history_response['events'][:10]  # Last 10 events
                ]
            }
            
        except ClientError as e:
            logger.error(f"Failed to get execution details: {e}")
            raise OrchestrationError(f"Failed to get execution details: {e}") from e
    
    def stop_execution(self, execution_arn: str, cause: str = "Manual stop") -> Dict[str, Any]:
        """
        Stop a running execution.
        
        Args:
            execution_arn: ARN of the execution to stop
            cause: Reason for stopping the execution
            
        Returns:
            Stop execution response
        """
        try:
            response = self.stepfunctions_client.stop_execution(
                executionArn=execution_arn,
                cause=cause
            )
            
            logger.info(f"Stopped execution {execution_arn}", extra={"cause": cause})
            
            return {
                'stopped_at': response['stopDate'].isoformat(),
                'cause': cause
            }
            
        except ClientError as e:
            logger.error(f"Failed to stop execution: {e}")
            raise OrchestrationError(f"Failed to stop execution: {e}") from e
    
    def get_workflow_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get workflow execution metrics for the specified time period.
        
        Args:
            hours: Number of hours to look back for metrics
            
        Returns:
            Workflow metrics summary
        """
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)
            
            # Get executions in the time period
            executions = self.list_executions(start_time=start_time, end_time=end_time)
            
            # Calculate metrics
            total_executions = len(executions)
            successful_executions = len([e for e in executions if e['status'] == 'SUCCEEDED'])
            failed_executions = len([e for e in executions if e['status'] == 'FAILED'])
            running_executions = len([e for e in executions if e['status'] == 'RUNNING'])
            
            success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0
            
            # Calculate average execution time for completed executions
            completed_executions = [e for e in executions if e['stopped_at']]
            avg_execution_time = 0
            if completed_executions:
                total_time = sum([
                    (datetime.fromisoformat(e['stopped_at']) - datetime.fromisoformat(e['started_at'])).total_seconds()
                    for e in completed_executions
                ])
                avg_execution_time = total_time / len(completed_executions)
            
            return {
                'time_period_hours': hours,
                'total_executions': total_executions,
                'successful_executions': successful_executions,
                'failed_executions': failed_executions,
                'running_executions': running_executions,
                'success_rate_percent': round(success_rate, 2),
                'average_execution_time_seconds': round(avg_execution_time, 2),
                'metrics_generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get workflow metrics: {e}")
            raise OrchestrationError(f"Failed to get workflow metrics: {e}") from e
    
    def publish_custom_metrics(self, metrics: Dict[str, float]) -> None:
        """
        Publish custom metrics to CloudWatch.
        
        Args:
            metrics: Dictionary of metric names and values
        """
        try:
            metric_data = []
            
            for metric_name, value in metrics.items():
                metric_data.append({
                    'MetricName': metric_name,
                    'Value': value,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                })
            
            self.cloudwatch_client.put_metric_data(
                Namespace='SentinelAML/Orchestration',
                MetricData=metric_data
            )
            
            logger.info(f"Published {len(metric_data)} custom metrics to CloudWatch")
            
        except ClientError as e:
            logger.error(f"Failed to publish custom metrics: {e}")
            # Don't raise exception for metrics publishing failures