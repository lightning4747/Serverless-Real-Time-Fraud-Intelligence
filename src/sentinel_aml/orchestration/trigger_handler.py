"""
Lambda handler for triggering Step Functions orchestration workflow.

This handler receives transaction events and triggers the Step Functions
state machine for the Transaction → GNN Analysis → SAR Generation pipeline.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError

from ..core.config import get_config
from ..core.logging_config import setup_logging
from ..core.exceptions import OrchestrationError

# Setup logging
logger = setup_logging(__name__)

# Initialize AWS clients
stepfunctions_client = boto3.client('stepfunctions')


class OrchestrationTrigger:
    """Handles triggering of Step Functions workflows for transaction processing."""
    
    def __init__(self):
        """Initialize the orchestration trigger."""
        self.config = get_config()
        self.state_machine_arn = os.getenv(
            'STATE_MACHINE_ARN',
            f"arn:aws:states:{self.config.aws_region}:{self.config.aws_account_id}:stateMachine:sentinel-aml-processing-workflow"
        )
        
    def trigger_workflow(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger Step Functions workflow for transaction processing.
        
        Args:
            transaction_data: Transaction data to process
            
        Returns:
            Dict containing execution details
            
        Raises:
            OrchestrationError: If workflow trigger fails
        """
        try:
            # Generate correlation ID for tracking
            correlation_id = str(uuid.uuid4())
            
            # Prepare input for Step Functions
            workflow_input = {
                "transaction_data": transaction_data,
                "account_id": transaction_data.get("from_account_id"),
                "correlation_id": correlation_id,
                "timestamp": datetime.utcnow().isoformat(),
                "trigger_source": "transaction_ingestion"
            }
            
            # Start Step Functions execution
            response = stepfunctions_client.start_execution(
                stateMachineArn=self.state_machine_arn,
                name=f"transaction-{transaction_data.get('transaction_id', correlation_id)}-{int(datetime.utcnow().timestamp())}",
                input=json.dumps(workflow_input)
            )
            
            logger.info(
                f"Started Step Functions execution",
                extra={
                    "correlation_id": correlation_id,
                    "execution_arn": response["executionArn"],
                    "transaction_id": transaction_data.get("transaction_id"),
                    "account_id": transaction_data.get("from_account_id")
                }
            )
            
            return {
                "status": "triggered",
                "execution_arn": response["executionArn"],
                "correlation_id": correlation_id,
                "started_at": response["startDate"].isoformat()
            }
            
        except ClientError as e:
            error_msg = f"Failed to trigger Step Functions workflow: {e}"
            logger.error(error_msg, extra={"correlation_id": correlation_id})
            raise OrchestrationError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error triggering workflow: {e}"
            logger.error(error_msg, extra={"correlation_id": correlation_id})
            raise OrchestrationError(error_msg) from e
    
    def check_execution_status(self, execution_arn: str) -> Dict[str, Any]:
        """
        Check the status of a Step Functions execution.
        
        Args:
            execution_arn: ARN of the execution to check
            
        Returns:
            Dict containing execution status details
        """
        try:
            response = stepfunctions_client.describe_execution(
                executionArn=execution_arn
            )
            
            return {
                "status": response["status"],
                "started_at": response["startDate"].isoformat(),
                "stopped_at": response.get("stopDate", {}).isoformat() if response.get("stopDate") else None,
                "input": json.loads(response["input"]),
                "output": json.loads(response.get("output", "{}")) if response.get("output") else None
            }
            
        except ClientError as e:
            logger.error(f"Failed to check execution status: {e}")
            raise OrchestrationError(f"Failed to check execution status: {e}") from e


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for orchestration trigger.
    
    Handles both direct invocation and event-driven triggers from:
    - API Gateway (transaction ingestion)
    - EventBridge (scheduled processing)
    - SQS (batch processing)
    
    Args:
        event: Lambda event data
        context: Lambda context
        
    Returns:
        Response dict with status and execution details
    """
    try:
        logger.info("Orchestration trigger invoked", extra={"event_source": event.get("source", "direct")})
        
        orchestrator = OrchestrationTrigger()
        
        # Handle different event sources
        if "Records" in event:
            # SQS batch processing
            results = []
            for record in event["Records"]:
                if record.get("eventSource") == "aws:sqs":
                    transaction_data = json.loads(record["body"])
                    result = orchestrator.trigger_workflow(transaction_data)
                    results.append(result)
            
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": f"Triggered {len(results)} workflows",
                    "results": results
                })
            }
            
        elif "httpMethod" in event:
            # API Gateway direct trigger
            if event["httpMethod"] == "POST":
                transaction_data = json.loads(event.get("body", "{}"))
                result = orchestrator.trigger_workflow(transaction_data)
                
                return {
                    "statusCode": 202,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*"
                    },
                    "body": json.dumps(result)
                }
            
            elif event["httpMethod"] == "GET":
                # Check execution status
                execution_arn = event.get("queryStringParameters", {}).get("execution_arn")
                if not execution_arn:
                    return {
                        "statusCode": 400,
                        "body": json.dumps({"error": "execution_arn parameter required"})
                    }
                
                status = orchestrator.check_execution_status(execution_arn)
                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*"
                    },
                    "body": json.dumps(status)
                }
        
        elif "source" in event and event["source"] == "aws.events":
            # EventBridge scheduled trigger
            # This could be used for batch processing or maintenance tasks
            logger.info("EventBridge scheduled trigger - implementing batch processing")
            
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "Scheduled processing completed"})
            }
        
        else:
            # Direct invocation with transaction data
            transaction_data = event.get("transaction_data", event)
            result = orchestrator.trigger_workflow(transaction_data)
            
            return {
                "statusCode": 200,
                "body": json.dumps(result)
            }
            
    except OrchestrationError as e:
        logger.error(f"Orchestration error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Orchestration failed",
                "message": str(e)
            })
        }
    
    except Exception as e:
        logger.error(f"Unexpected error in orchestration trigger: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Internal server error",
                "message": "An unexpected error occurred"
            })
        }