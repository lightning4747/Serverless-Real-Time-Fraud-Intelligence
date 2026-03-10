"""API Gateway stack for Sentinel-AML REST endpoints."""

from aws_cdk import (
    Stack,
    aws_apigateway as apigateway,
    aws_lambda as _lambda,
    aws_kms as kms,
    aws_logs as logs,
    RemovalPolicy,
)
from constructs import Construct
from typing import Dict


class ApiGatewayStack(Stack):
    """API Gateway stack for Sentinel-AML REST API."""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str,
        lambda_functions: Dict[str, _lambda.Function],
        kms_key: kms.Key,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # CloudWatch log group for API Gateway
        self.api_log_group = logs.LogGroup(
            self, "APIGatewayLogGroup",
            log_group_name="/aws/apigateway/sentinel-aml",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
            encryption_key=kms_key
        )
        
        # API Gateway
        self.api_gateway = apigateway.RestApi(
            self, "SentinelAMLAPI",
            rest_api_name="Sentinel-AML API",
            description="AI-powered Anti-Money Laundering detection platform API",
            
            # CORS configuration
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"]
            ),
            
            # API Gateway configuration
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            ),
            
            # Logging configuration
            cloud_watch_role=True,
            deploy_options=apigateway.StageOptions(
                stage_name="v1",
                logging_level=apigateway.MethodLoggingLevel.INFO,
                access_log_destination=apigateway.LogGroupLogDestination(self.api_log_group),
                access_log_format=apigateway.AccessLogFormat.json_with_standard_fields(
                    caller=True,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=True
                ),
                throttling_rate_limit=100,  # requests per second
                throttling_burst_limit=200,  # burst capacity
                metrics_enabled=True,
                tracing_enabled=True
            )
        )
        
        # API Key for authentication
        self.api_key = apigateway.ApiKey(
            self, "SentinelAMLAPIKey",
            api_key_name="sentinel-aml-api-key",
            description="API key for Sentinel-AML system access"
        )
        
        # Usage plan
        self.usage_plan = apigateway.UsagePlan(
            self, "SentinelAMLUsagePlan",
            name="sentinel-aml-usage-plan",
            description="Usage plan for Sentinel-AML API",
            throttle=apigateway.ThrottleSettings(
                rate_limit=100,  # requests per second
                burst_limit=200  # burst capacity
            ),
            quota=apigateway.QuotaSettings(
                limit=10000,  # requests per day
                period=apigateway.Period.DAY
            ),
            api_stages=[
                apigateway.UsagePlanPerApiStage(
                    api=self.api_gateway,
                    stage=self.api_gateway.deployment_stage
                )
            ]
        )
        
        # Associate API key with usage plan
        self.usage_plan.add_api_key(self.api_key)
        
        # Request validator
        self.request_validator = apigateway.RequestValidator(
            self, "RequestValidator",
            rest_api=self.api_gateway,
            validate_request_body=True,
            validate_request_parameters=True
        )
        
        # Lambda integrations
        transaction_integration = apigateway.LambdaIntegration(
            lambda_functions["transaction_processor"],
            proxy=True,
            integration_responses=[
                apigateway.IntegrationResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": "'*'"
                    }
                )
            ]
        )
        
        alert_integration = apigateway.LambdaIntegration(
            lambda_functions["alert_manager"],
            proxy=True
        )
        
        report_integration = apigateway.LambdaIntegration(
            lambda_functions["report_retriever"],
            proxy=True
        )
        
        health_integration = apigateway.LambdaIntegration(
            lambda_functions["health_checker"],
            proxy=True
        )
        
        # API Resources and Methods
        
        # /health endpoint
        health_resource = self.api_gateway.root.add_resource("health")
        health_resource.add_method(
            "GET",
            health_integration,
            api_key_required=False,  # Health check doesn't require API key
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                )
            ]
        )
        
        # /transactions endpoint
        transactions_resource = self.api_gateway.root.add_resource("transactions")
        transactions_resource.add_method(
            "POST",
            transaction_integration,
            api_key_required=True,
            request_validator=self.request_validator,
            request_models={
                "application/json": apigateway.Model(
                    self, "TransactionModel",
                    rest_api=self.api_gateway,
                    content_type="application/json",
                    model_name="TransactionModel",
                    schema=apigateway.JsonSchema(
                        schema=apigateway.JsonSchemaVersion.DRAFT4,
                        type=apigateway.JsonSchemaType.OBJECT,
                        properties={
                            "from_account_id": apigateway.JsonSchema(
                                type=apigateway.JsonSchemaType.STRING,
                                min_length=8,
                                max_length=20
                            ),
                            "to_account_id": apigateway.JsonSchema(
                                type=apigateway.JsonSchemaType.STRING,
                                min_length=8,
                                max_length=20
                            ),
                            "amount": apigateway.JsonSchema(
                                type=apigateway.JsonSchemaType.NUMBER,
                                minimum=0.01
                            ),
                            "currency": apigateway.JsonSchema(
                                type=apigateway.JsonSchemaType.STRING,
                                min_length=3,
                                max_length=3
                            ),
                            "transaction_type": apigateway.JsonSchema(
                                type=apigateway.JsonSchemaType.STRING,
                                enum=["deposit", "withdrawal", "transfer", "payment", "wire", "ach", "check", "card"]
                            )
                        },
                        required=["from_account_id", "to_account_id", "amount", "transaction_type"]
                    )
                )
            }
        )
        
        # /alerts endpoint
        alerts_resource = self.api_gateway.root.add_resource("alerts")
        alerts_resource.add_method(
            "GET",
            alert_integration,
            api_key_required=True,
            request_parameters={
                "method.request.querystring.status": False,
                "method.request.querystring.risk_level": False,
                "method.request.querystring.limit": False,
                "method.request.querystring.offset": False
            }
        )
        
        # /reports endpoint
        reports_resource = self.api_gateway.root.add_resource("reports")
        reports_resource.add_method(
            "GET",
            report_integration,
            api_key_required=True
        )
        
        # /reports/{id} endpoint
        report_by_id_resource = reports_resource.add_resource("{id}")
        report_by_id_resource.add_method(
            "GET",
            report_integration,
            api_key_required=True,
            request_parameters={
                "method.request.path.id": True
            }
        )
        
        # Grant Lambda invoke permissions to API Gateway
        for function in lambda_functions.values():
            function.add_permission(
                f"APIGatewayInvoke-{function.function_name}",
                principal=apigateway.ServicePrincipal("apigateway.amazonaws.com"),
                source_arn=f"{self.api_gateway.arn_for_execute_api()}/*/*"
            )
        
        # Store important attributes
        self.api_url = self.api_gateway.url
        self.api_id = self.api_gateway.rest_api_id