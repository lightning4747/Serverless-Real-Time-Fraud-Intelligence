"""Step Functions stack for Sentinel-AML orchestration."""

from aws_cdk import (
    Stack,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_logs as logs,
    Duration,
    RemovalPolicy,
)
from constructs import Construct
from typing import Dict


class StepFunctionsStack(Stack):
    """Step Functions orchestration stack for Sentinel-AML."""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str,
        lambda_functions: Dict[str, _lambda.Function],
        step_functions_role: iam.Role,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # CloudWatch log group for Step Functions
        self.log_group = logs.LogGroup(
            self, "StepFunctionsLogGroup",
            log_group_name="/aws/stepfunctions/sentinel-aml",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Define Lambda tasks
        fraud_scoring_task = tasks.LambdaInvoke(
            self, "FraudScoringTask",
            lambda_function=lambda_functions["fraud_scorer"],
            payload=sfn.TaskInput.from_object({
                "transaction_data.$": "$.transaction_data",
                "account_id.$": "$.account_id",
                "correlation_id.$": "$.correlation_id"
            }),
            result_path="$.fraud_analysis",
            retry_on_service_exceptions=True,
            timeout=Duration.minutes(10)
        )
        
        sar_generation_task = tasks.LambdaInvoke(
            self, "SARGenerationTask",
            lambda_function=lambda_functions["sar_generator"],
            payload=sfn.TaskInput.from_object({
                "fraud_analysis.$": "$.fraud_analysis",
                "transaction_data.$": "$.transaction_data",
                "correlation_id.$": "$.correlation_id"
            }),
            result_path="$.sar_report",
            retry_on_service_exceptions=True,
            timeout=Duration.minutes(5)
        )
        
        alert_creation_task = tasks.LambdaInvoke(
            self, "AlertCreationTask",
            lambda_function=lambda_functions["alert_manager"],
            payload=sfn.TaskInput.from_object({
                "fraud_analysis.$": "$.fraud_analysis",
                "sar_report.$": "$.sar_report",
                "transaction_data.$": "$.transaction_data",
                "correlation_id.$": "$.correlation_id",
                "action": "create_alert"
            }),
            result_path="$.alert_result",
            retry_on_service_exceptions=True
        )
        
        # Define choice states
        risk_evaluation = sfn.Choice(self, "RiskEvaluation")
        
        # Define conditions
        high_risk_condition = sfn.Condition.number_greater_than("$.fraud_analysis.Payload.risk_score", 0.7)
        medium_risk_condition = sfn.Condition.and_(
            sfn.Condition.number_greater_than("$.fraud_analysis.Payload.risk_score", 0.4),
            sfn.Condition.number_less_than_equals("$.fraud_analysis.Payload.risk_score", 0.7)
        )
        
        # Define end states
        low_risk_end = sfn.Pass(
            self, "LowRiskEnd",
            comment="Transaction flagged as low risk - no further action needed",
            result=sfn.Result.from_object({
                "status": "completed",
                "risk_level": "low",
                "action_taken": "none"
            })
        )
        
        medium_risk_end = sfn.Pass(
            self, "MediumRiskEnd", 
            comment="Transaction flagged as medium risk - alert created for review",
            result=sfn.Result.from_object({
                "status": "completed",
                "risk_level": "medium",
                "action_taken": "alert_created"
            })
        )
        
        high_risk_end = sfn.Pass(
            self, "HighRiskEnd",
            comment="Transaction flagged as high risk - SAR generated and alert created",
            result=sfn.Result.from_object({
                "status": "completed", 
                "risk_level": "high",
                "action_taken": "sar_generated_and_alert_created"
            })
        )
        
        # Define parallel processing for high-risk cases
        high_risk_parallel = sfn.Parallel(
            self, "HighRiskProcessing",
            comment="Process high-risk transactions with SAR generation and alerting"
        )
        
        high_risk_parallel.branch(sar_generation_task)
        high_risk_parallel.branch(alert_creation_task)
        
        # Error handling
        error_handler = sfn.Pass(
            self, "ErrorHandler",
            comment="Handle processing errors",
            result=sfn.Result.from_object({
                "status": "error",
                "message": "Processing failed - manual review required"
            })
        )
        
        # Retry configuration
        retry_config = sfn.Retry(
            errors=["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"],
            interval_seconds=2,
            max_attempts=3,
            backoff_rate=2.0
        )
        
        # Catch configuration
        catch_config = sfn.Catch(
            errors=["States.ALL"],
            handler=error_handler,
            result_path="$.error"
        )
        
        # Add retry and catch to tasks
        fraud_scoring_task.add_retry(retry_config)
        fraud_scoring_task.add_catch(catch_config)
        
        sar_generation_task.add_retry(retry_config)
        sar_generation_task.add_catch(catch_config)
        
        alert_creation_task.add_retry(retry_config)
        alert_creation_task.add_catch(catch_config)
        
        # Build the state machine definition
        definition = fraud_scoring_task.next(
            risk_evaluation
            .when(
                high_risk_condition,
                high_risk_parallel.next(high_risk_end)
            )
            .when(
                medium_risk_condition,
                alert_creation_task.next(medium_risk_end)
            )
            .otherwise(low_risk_end)
        )
        
        # Create the state machine
        self.state_machine = sfn.StateMachine(
            self, "SentinelAMLStateMachine",
            state_machine_name="sentinel-aml-processing-workflow",
            definition=definition,
            role=step_functions_role,
            timeout=Duration.minutes(15),
            
            # Logging configuration
            logs=sfn.LogOptions(
                destination=self.log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True
            ),
            
            # Tracing
            tracing_enabled=True
        )
        
        # Grant Step Functions permission to invoke Lambda functions
        for function in lambda_functions.values():
            function.grant_invoke(step_functions_role)
        
        # Store important attributes
        self.state_machine_arn = self.state_machine.state_machine_arn
        self.state_machine_name = self.state_machine.state_machine_name