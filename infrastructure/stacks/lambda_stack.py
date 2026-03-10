"""Lambda stack for Sentinel-AML processing functions."""

from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_neptune as neptune,
    aws_kms as kms,
    aws_iam as iam,
    aws_ec2 as ec2,
    Duration,
)
from constructs import Construct
import os


class LambdaStack(Stack):
    """Lambda functions stack for Sentinel-AML."""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        neptune_cluster: neptune.CfnDBCluster,
        kms_key: kms.Key,
        lambda_role: iam.Role,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Get VPC from Neptune stack (assuming it's passed or referenced)
        # For now, we'll create a reference - in real deployment, this would be passed
        vpc = ec2.Vpc.from_lookup(self, "VPC", is_default=False)
        
        # Common Lambda configuration
        common_lambda_props = {
            "runtime": _lambda.Runtime.PYTHON_3_11,
            "timeout": Duration.minutes(5),
            "memory_size": 512,
            "role": lambda_role,
            "environment": {
                "NEPTUNE_ENDPOINT": neptune_cluster.attr_endpoint,
                "NEPTUNE_PORT": "8182",
                "KMS_KEY_ID": kms_key.key_id,
                "LOG_LEVEL": "INFO",
                "ENVIRONMENT": os.getenv("ENVIRONMENT", "development")
            },
            "vpc": vpc,
            "vpc_subnets": ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            )
        }
        
        # Transaction processor Lambda
        self.transaction_processor = _lambda.Function(
            self, "TransactionProcessor",
            function_name="sentinel-aml-transaction-processor",
            description="Process incoming transactions and store in Neptune",
            code=_lambda.Code.from_asset("../src"),
            handler="sentinel_aml.api.transaction_handler.lambda_handler",
            **common_lambda_props
        )
        
        # GNN fraud scorer Lambda
        self.fraud_scorer = _lambda.Function(
            self, "FraudScorer", 
            function_name="sentinel-aml-fraud-scorer",
            description="Analyze transaction patterns using GNN for fraud detection",
            code=_lambda.Code.from_asset("../src"),
            handler="sentinel_aml.models.gnn_scorer.lambda_handler",
            timeout=Duration.minutes(10),  # Longer timeout for ML processing
            memory_size=1024,  # More memory for ML workloads
            **{k: v for k, v in common_lambda_props.items() if k not in ['timeout', 'memory_size']}
        )
        
        # SAR generator Lambda
        self.sar_generator = _lambda.Function(
            self, "SARGenerator",
            function_name="sentinel-aml-sar-generator", 
            description="Generate Suspicious Activity Reports using Bedrock",
            code=_lambda.Code.from_asset("../src"),
            handler="sentinel_aml.agents.sar_generator.lambda_handler",
            timeout=Duration.minutes(3),  # Timeout for Bedrock API calls
            memory_size=256,  # Less memory needed for text generation
            environment={
                **common_lambda_props["environment"],
                "BEDROCK_MODEL_ID": "anthropic.claude-3-sonnet-20240229-v1:0",
                "BEDROCK_REGION": "us-east-1"
            },
            **{k: v for k, v in common_lambda_props.items() if k not in ['timeout', 'memory_size', 'environment']}
        )
        
        # Alert manager Lambda
        self.alert_manager = _lambda.Function(
            self, "AlertManager",
            function_name="sentinel-aml-alert-manager",
            description="Manage alerts and notifications for suspicious activities",
            code=_lambda.Code.from_asset("../src"),
            handler="sentinel_aml.api.alert_handler.lambda_handler",
            **common_lambda_props
        )
        
        # Report retriever Lambda
        self.report_retriever = _lambda.Function(
            self, "ReportRetriever",
            function_name="sentinel-aml-report-retriever",
            description="Retrieve and serve generated SAR reports",
            code=_lambda.Code.from_asset("../src"),
            handler="sentinel_aml.api.report_handler.lambda_handler",
            **common_lambda_props
        )
        
        # Health check Lambda
        self.health_checker = _lambda.Function(
            self, "HealthChecker",
            function_name="sentinel-aml-health-checker",
            description="Health check for system components",
            code=_lambda.Code.from_asset("../src"),
            handler="sentinel_aml.api.health_handler.lambda_handler",
            timeout=Duration.seconds(30),
            memory_size=128,
            **{k: v for k, v in common_lambda_props.items() if k not in ['timeout', 'memory_size']}
        )
        
        # Orchestrator trigger Lambda
        self.orchestrator_trigger = _lambda.Function(
            self, "OrchestratorTrigger",
            function_name="sentinel-aml-orchestrator-trigger",
            description="Trigger Step Functions workflow for transaction processing",
            code=_lambda.Code.from_asset("../src"),
            handler="sentinel_aml.orchestration.trigger_handler.lambda_handler",
            **common_lambda_props
        )
        
        # Store Lambda functions for other stacks
        self.lambda_functions = {
            "transaction_processor": self.transaction_processor,
            "fraud_scorer": self.fraud_scorer,
            "sar_generator": self.sar_generator,
            "alert_manager": self.alert_manager,
            "report_retriever": self.report_retriever,
            "health_checker": self.health_checker,
            "orchestrator_trigger": self.orchestrator_trigger
        }
        
        # Grant KMS permissions to all Lambda functions
        for function in self.lambda_functions.values():
            kms_key.grant_encrypt_decrypt(function)
        
        # Add Lambda layers for common dependencies (optional optimization)
        # This would contain common packages like boto3, pydantic, etc.
        # self.common_layer = _lambda.LayerVersion(
        #     self, "CommonLayer",
        #     code=_lambda.Code.from_asset("../layers/common"),
        #     compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
        #     description="Common dependencies for Sentinel-AML Lambda functions"
        # )