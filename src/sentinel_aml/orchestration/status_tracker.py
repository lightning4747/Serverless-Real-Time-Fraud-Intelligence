"""
Status tracker for Step Functions workflow monitoring and notifications.

Provides real-time tracking of workflow executions and sends notifications
for important status changes in the Sentinel-AML processing pipeline.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum

import boto3
from botocore.exceptions import ClientError

from ..core.config import get_config
from ..core.logging_config import setup_logging
from ..core.exceptions import OrchestrationError

logger = setup_logging(__name__)


class NotificationLevel(Enum):
    """Notification priority levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class StatusTracker:
    """Tracks workflow execution status and sends notifications."""
    
    def __init__(self):
        """Initialize the status tracker."""
        self.config = get_config()
        self.sns_client = boto3.client('sns')
        self.dynamodb = boto3.resource('dynamodb')
        
        # DynamoDB table for tracking execution status
        self.status_table = self.dynamodb.Table(
            self.config.get('status_tracking_table', 'sentinel-aml-execution-status')
        )
        
        # SNS topic for notifications
        self.notification_topic_arn = self.config.get(
            'notification_topic_arn',
            f"arn:aws:sns:{self.config.aws_region}:{self.config.aws_account_id}:sentinel-aml-notifications"
        )
    
    def track_execution_start(self, execution_data: Dict[str, Any]) -> None:
        """
        Track the start of a workflow execution.
        
        Args:
            execution_data: Execution details including ARN, correlation ID, etc.
        """
        try:
            item = {
                'execution_arn': execution_data['execution_arn'],
                'correlation_id': execution_data['correlation_id'],
                'transaction_id': execution_data.get('transaction_id'),
                'account_id': execution_data.get('account_id'),
                'status': 'RUNNING',
                'started_at': datetime.utcnow().isoformat(),
                'last_updated': datetime.utcnow().isoformat(),
                'steps_completed': [],
                'current_step': 'fraud_scoring',
                'retry_count': 0
            }
            
            self.status_table.put_item(Item=item)
            
            logger.info(
                "Tracking execution start",
                extra={
                    "execution_arn": execution_data['execution_arn'],
                    "correlation_id": execution_data['correlation_id']
                }
            )
            
        except ClientError as e:
            logger.error(f"Failed to track execution start: {e}")
            # Don't raise exception for tracking failures
    
    def update_execution_status(
        self, 
        execution_arn: str, 
        status: str,
        current_step: Optional[str] = None,
        step_result: Optional[Dict[str, Any]] = None,
        error_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update the status of a workflow execution.
        
        Args:
            execution_arn: ARN of the execution
            status: Current execution status
            current_step: Current step being executed
            step_result: Result of the completed step
            error_details: Error details if step failed
        """
        try:
            update_expression = "SET #status = :status, last_updated = :last_updated"
            expression_values = {
                ':status': status,
                ':last_updated': datetime.utcnow().isoformat()
            }
            expression_names = {'#status': 'status'}
            
            if current_step:
                update_expression += ", current_step = :current_step"
                expression_values[':current_step'] = current_step
            
            if step_result:
                update_expression += ", steps_completed = list_append(if_not_exists(steps_completed, :empty_list), :step_result)"
                expression_values[':step_result'] = [step_result]
                expression_values[':empty_list'] = []
            
            if error_details:
                update_expression += ", error_details = :error_details"
                expression_values[':error_details'] = error_details
            
            self.status_table.update_item(
                Key={'execution_arn': execution_arn},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
                ExpressionAttributeNames=expression_names
            )
            
            # Send notification for status changes
            self._send_status_notification(execution_arn, status, error_details)
            
            logger.info(
                f"Updated execution status to {status}",
                extra={
                    "execution_arn": execution_arn,
                    "current_step": current_step
                }
            )
            
        except ClientError as e:
            logger.error(f"Failed to update execution status: {e}")
    
    def get_execution_status(self, execution_arn: str) -> Optional[Dict[str, Any]]:
        """
        Get the current status of a workflow execution.
        
        Args:
            execution_arn: ARN of the execution
            
        Returns:
            Execution status details or None if not found
        """
        try:
            response = self.status_table.get_item(
                Key={'execution_arn': execution_arn}
            )
            
            return response.get('Item')
            
        except ClientError as e:
            logger.error(f"Failed to get execution status: {e}")
            return None
    
    def get_executions_by_status(self, status: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get executions by status.
        
        Args:
            status: Status to filter by
            limit: Maximum number of results
            
        Returns:
            List of executions with the specified status
        """
        try:
            # Note: This would require a GSI on status in a real implementation
            # For now, we'll scan the table (not recommended for production)
            response = self.status_table.scan(
                FilterExpression='#status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': status},
                Limit=limit
            )
            
            return response.get('Items', [])
            
        except ClientError as e:
            logger.error(f"Failed to get executions by status: {e}")
            return []
    
    def _send_status_notification(
        self, 
        execution_arn: str, 
        status: str, 
        error_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Send notification for status changes.
        
        Args:
            execution_arn: ARN of the execution
            status: Current status
            error_details: Error details if applicable
        """
        try:
            # Determine notification level
            if status == 'FAILED':
                level = NotificationLevel.ERROR
            elif status == 'TIMED_OUT':
                level = NotificationLevel.WARNING
            elif status == 'SUCCEEDED':
                level = NotificationLevel.INFO
            else:
                return  # Don't send notifications for other statuses
            
            # Get execution details for context
            execution_status = self.get_execution_status(execution_arn)
            
            message = {
                'level': level.value,
                'execution_arn': execution_arn,
                'status': status,
                'timestamp': datetime.utcnow().isoformat(),
                'correlation_id': execution_status.get('correlation_id') if execution_status else None,
                'transaction_id': execution_status.get('transaction_id') if execution_status else None,
                'account_id': execution_status.get('account_id') if execution_status else None
            }
            
            if error_details:
                message['error_details'] = error_details
            
            # Create subject line
            subject = f"Sentinel-AML Workflow {status}: {execution_arn.split(':')[-1]}"
            
            # Send SNS notification
            self.sns_client.publish(
                TopicArn=self.notification_topic_arn,
                Subject=subject,
                Message=json.dumps(message, indent=2)
            )
            
            logger.info(f"Sent {level.value} notification for execution {execution_arn}")
            
        except ClientError as e:
            logger.error(f"Failed to send notification: {e}")
            # Don't raise exception for notification failures
    
    def cleanup_old_executions(self, days_old: int = 30) -> int:
        """
        Clean up old execution records.
        
        Args:
            days_old: Remove records older than this many days
            
        Returns:
            Number of records cleaned up
        """
        try:
            cutoff_date = datetime.utcnow().timestamp() - (days_old * 24 * 60 * 60)
            cutoff_iso = datetime.fromtimestamp(cutoff_date).isoformat()
            
            # Scan for old records
            response = self.status_table.scan(
                FilterExpression='started_at < :cutoff_date',
                ExpressionAttributeValues={':cutoff_date': cutoff_iso}
            )
            
            items_to_delete = response.get('Items', [])
            
            # Delete old records in batches
            deleted_count = 0
            with self.status_table.batch_writer() as batch:
                for item in items_to_delete:
                    batch.delete_item(Key={'execution_arn': item['execution_arn']})
                    deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old execution records")
            return deleted_count
            
        except ClientError as e:
            logger.error(f"Failed to cleanup old executions: {e}")
            return 0
    
    def get_workflow_health_summary(self) -> Dict[str, Any]:
        """
        Get a summary of workflow health metrics.
        
        Returns:
            Health summary with key metrics
        """
        try:
            # Get recent executions (last 24 hours)
            recent_executions = self.get_executions_by_status('SUCCEEDED', 100)
            recent_executions.extend(self.get_executions_by_status('FAILED', 100))
            recent_executions.extend(self.get_executions_by_status('RUNNING', 100))
            
            # Filter to last 24 hours
            cutoff_time = datetime.utcnow().timestamp() - (24 * 60 * 60)
            recent_executions = [
                e for e in recent_executions 
                if datetime.fromisoformat(e['started_at']).timestamp() > cutoff_time
            ]
            
            total_executions = len(recent_executions)
            successful = len([e for e in recent_executions if e['status'] == 'SUCCEEDED'])
            failed = len([e for e in recent_executions if e['status'] == 'FAILED'])
            running = len([e for e in recent_executions if e['status'] == 'RUNNING'])
            
            success_rate = (successful / total_executions * 100) if total_executions > 0 else 0
            
            return {
                'total_executions_24h': total_executions,
                'successful_executions': successful,
                'failed_executions': failed,
                'running_executions': running,
                'success_rate_percent': round(success_rate, 2),
                'health_status': 'healthy' if success_rate >= 95 else 'degraded' if success_rate >= 80 else 'unhealthy',
                'last_updated': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get workflow health summary: {e}")
            return {
                'health_status': 'unknown',
                'error': str(e),
                'last_updated': datetime.utcnow().isoformat()
            }