#!/usr/bin/env python3
"""AWS CDK app for Sentinel-AML infrastructure."""

import os
import aws_cdk as cdk
from constructs import Construct

from stacks.neptune_stack import NeptuneStack
from stacks.lambda_stack import LambdaStack
from stacks.api_gateway_stack import ApiGatewayStack
from stacks.step_functions_stack import StepFunctionsStack
from stacks.monitoring_stack import MonitoringStack
from stacks.security_stack import SecurityStack


class SentinelAMLApp(cdk.App):
    """Main CDK application for Sentinel-AML."""
    
    def __init__(self):
        super().__init__()
        
        # Get environment configuration
        env = cdk.Environment(
            account=os.getenv('CDK_DEFAULT_ACCOUNT'),
            region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
        )
        
        # Common tags for all resources
        common_tags = {
            'Project': 'Sentinel-AML',
            'Environment': os.getenv('ENVIRONMENT', 'development'),
            'Owner': 'AML-Team',
            'CostCenter': 'Compliance',
            'Purpose': 'Anti-Money-Laundering-Detection'
        }
        
        # Security stack (KMS, IAM roles, etc.)
        security_stack = SecurityStack(
            self, 
            "SentinelAMLSecurity",
            env=env,
            tags=common_tags
        )
        
        # Neptune graph database stack
        neptune_stack = NeptuneStack(
            self,
            "SentinelAMLNeptune",
            kms_key=security_stack.kms_key,
            env=env,
            tags=common_tags
        )
        
        # Lambda functions stack
        lambda_stack = LambdaStack(
            self,
            "SentinelAMLLambda",
            neptune_cluster=neptune_stack.neptune_cluster,
            kms_key=security_stack.kms_key,
            lambda_role=security_stack.lambda_execution_role,
            env=env,
            tags=common_tags
        )
        
        # API Gateway stack
        api_stack = ApiGatewayStack(
            self,
            "SentinelAMLAPI",
            lambda_functions=lambda_stack.lambda_functions,
            kms_key=security_stack.kms_key,
            env=env,
            tags=common_tags
        )
        
        # Step Functions orchestration stack
        step_functions_stack = StepFunctionsStack(
            self,
            "SentinelAMLOrchestration",
            lambda_functions=lambda_stack.lambda_functions,
            step_functions_role=security_stack.step_functions_role,
            env=env,
            tags=common_tags
        )
        
        # Monitoring and observability stack
        monitoring_stack = MonitoringStack(
            self,
            "SentinelAMLMonitoring",
            neptune_cluster=neptune_stack.neptune_cluster,
            lambda_functions=lambda_stack.lambda_functions,
            api_gateway=api_stack.api_gateway,
            state_machine=step_functions_stack.state_machine,
            env=env,
            tags=common_tags
        )
        
        # Set up stack dependencies
        lambda_stack.add_dependency(security_stack)
        lambda_stack.add_dependency(neptune_stack)
        api_stack.add_dependency(lambda_stack)
        step_functions_stack.add_dependency(lambda_stack)
        monitoring_stack.add_dependency(neptune_stack)
        monitoring_stack.add_dependency(lambda_stack)
        monitoring_stack.add_dependency(api_stack)
        monitoring_stack.add_dependency(step_functions_stack)
        
        # Output important values
        cdk.CfnOutput(
            self,
            "NeptuneEndpoint",
            value=neptune_stack.neptune_cluster.cluster_endpoint.hostname,
            description="Neptune cluster endpoint"
        )
        
        cdk.CfnOutput(
            self,
            "APIGatewayURL",
            value=api_stack.api_gateway.url,
            description="API Gateway URL"
        )
        
        cdk.CfnOutput(
            self,
            "StateMachineArn",
            value=step_functions_stack.state_machine.state_machine_arn,
            description="Step Functions state machine ARN"
        )


if __name__ == "__main__":
    app = SentinelAMLApp()
    app.synth()