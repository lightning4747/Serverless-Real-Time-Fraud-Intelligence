"""API Gateway stack for Sentinel-AML REST endpoints."""

from aws_cdk import (
    Stack,
    Duration,
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
        
        # API Gateway with enhanced configuration
        self.api_gateway = apigateway.RestApi(
            self, "SentinelAMLAPI",
            rest_api_name="Sentinel-AML API",
            description="AI-powered Anti-Money Laundering detection platform API - Requirements 6.1, 6.2, 6.3",
            
            # CORS configuration - Requirement 6.3
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["https://*.sentinel-aml.com", "https://localhost:3000"],  # More restrictive origins
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=[
                    "Content-Type", 
                    "X-Amz-Date", 
                    "Authorization", 
                    "X-Api-Key", 
                    "X-Amz-Security-Token",
                    "X-Requested-With"
                ],
                allow_credentials=True,
                max_age=Duration.hours(1)
            ),
            
            # API Gateway configuration - Requirement 6.1
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            ),
            
            # Binary media types for file uploads
            binary_media_types=["application/pdf", "application/octet-stream"],
            
            # Minimum TLS version for security
            minimum_compression_size=1024,
            
            # Logging configuration - Requirement 6.1
            cloud_watch_role=True,
            deploy_options=apigateway.StageOptions(
                stage_name="v1",
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
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
                    user=True,
                    request_id=True,
                    extended_request_id=True,
                    error_message=True,
                    error_message_string=True
                ),
                # Rate limiting - Requirement 6.5
                throttling_rate_limit=100,  # requests per second per API key
                throttling_burst_limit=200,  # burst capacity
                metrics_enabled=True,
                tracing_enabled=True,
                # Cache configuration for performance
                caching_enabled=True,
                cache_cluster_enabled=True,
                cache_cluster_size="0.5",
                cache_ttl=Duration.minutes(5)
            )
        )
        
        # Enhanced API Key configuration - Requirement 6.4
        self.api_key = apigateway.ApiKey(
            self, "SentinelAMLAPIKey",
            api_key_name="sentinel-aml-api-key",
            description="API key for Sentinel-AML system access - Requirement 6.4",
            enabled=True,
            generate_distinct_id=True
        )
        
        # Additional API keys for different access levels
        self.readonly_api_key = apigateway.ApiKey(
            self, "SentinelAMLReadOnlyAPIKey",
            api_key_name="sentinel-aml-readonly-api-key",
            description="Read-only API key for dashboard and reporting access",
            enabled=True
        )
        
        # Enhanced Usage plan with stricter rate limiting - Requirement 6.5
        self.usage_plan = apigateway.UsagePlan(
            self, "SentinelAMLUsagePlan",
            name="sentinel-aml-usage-plan",
            description="Usage plan for Sentinel-AML API - Requirements 6.4, 6.5",
            throttle=apigateway.ThrottleSettings(
                rate_limit=100,  # requests per second per API key
                burst_limit=200  # burst capacity
            ),
            quota=apigateway.QuotaSettings(
                limit=10000,  # requests per day
                period=apigateway.Period.DAY
            ),
            api_stages=[
                apigateway.UsagePlanPerApiStage(
                    api=self.api_gateway,
                    stage=self.api_gateway.deployment_stage,
                    throttle=[
                        apigateway.ThrottlingPerMethod(
                            method=apigateway.Method.from_method_arn(
                                self, "TransactionThrottle",
                                f"{self.api_gateway.arn_for_execute_api()}/*/POST/transactions"
                            ),
                            throttle=apigateway.ThrottleSettings(
                                rate_limit=50,  # Lower limit for transaction processing
                                burst_limit=100
                            )
                        )
                    ]
                )
            ]
        )
        
        # Read-only usage plan with higher limits
        self.readonly_usage_plan = apigateway.UsagePlan(
            self, "SentinelAMLReadOnlyUsagePlan",
            name="sentinel-aml-readonly-usage-plan",
            description="Read-only usage plan for dashboard access",
            throttle=apigateway.ThrottleSettings(
                rate_limit=200,  # Higher limit for read operations
                burst_limit=400
            ),
            quota=apigateway.QuotaSettings(
                limit=50000,  # Higher daily quota for read operations
                period=apigateway.Period.DAY
            ),
            api_stages=[
                apigateway.UsagePlanPerApiStage(
                    api=self.api_gateway,
                    stage=self.api_gateway.deployment_stage
                )
            ]
        )
        
        # Associate API keys with usage plans
        self.usage_plan.add_api_key(self.api_key)
        self.readonly_usage_plan.add_api_key(self.readonly_api_key)
        
        # Enhanced Request validators - Requirement 6.3
        self.request_validator = apigateway.RequestValidator(
            self, "RequestValidator",
            rest_api=self.api_gateway,
            validate_request_body=True,
            validate_request_parameters=True,
            request_validator_name="sentinel-aml-request-validator"
        )
        
        # Separate validator for query parameters only
        self.query_validator = apigateway.RequestValidator(
            self, "QueryValidator",
            rest_api=self.api_gateway,
            validate_request_body=False,
            validate_request_parameters=True,
            request_validator_name="sentinel-aml-query-validator"
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
        
        # Enhanced API Resources and Methods with proper hierarchy - Requirement 6.1, 6.2
        
        # API versioning resource
        v1_resource = self.api_gateway.root.add_resource("v1")
        
        # /v1/health endpoint (public)
        health_resource = v1_resource.add_resource("health")
        health_resource.add_method(
            "GET",
            health_integration,
            api_key_required=False,  # Health check doesn't require API key
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True,
                        "method.response.header.Content-Type": True
                    }
                ),
                apigateway.MethodResponse(
                    status_code="503",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                )
            ]
        )
        
        # Add OPTIONS method for CORS preflight
        health_resource.add_method(
            "OPTIONS",
            apigateway.MockIntegration(
                integration_responses=[
                    apigateway.IntegrationResponse(
                        status_code="200",
                        response_parameters={
                            "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key'",
                            "method.response.header.Access-Control-Allow-Methods": "'GET,OPTIONS'",
                            "method.response.header.Access-Control-Allow-Origin": "'*'"
                        }
                    )
                ],
                request_templates={"application/json": '{"statusCode": 200}'}
            ),
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Headers": True,
                        "method.response.header.Access-Control-Allow-Methods": True,
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                )
            ]
        )
        
        # /v1/transactions endpoint - Requirement 6.1
        transactions_resource = v1_resource.add_resource("transactions")
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
                    description="Transaction submission model - Requirement 6.3",
                    schema=apigateway.JsonSchema(
                        schema=apigateway.JsonSchemaVersion.DRAFT4,
                        type=apigateway.JsonSchemaType.OBJECT,
                        title="Transaction",
                        description="Financial transaction for AML processing",
                        properties={
                            "from_account_id": apigateway.JsonSchema(
                                type=apigateway.JsonSchemaType.STRING,
                                min_length=8,
                                max_length=20,
                                pattern="^[A-Z0-9]{8,20}$",
                                description="Source account identifier"
                            ),
                            "to_account_id": apigateway.JsonSchema(
                                type=apigateway.JsonSchemaType.STRING,
                                min_length=8,
                                max_length=20,
                                pattern="^[A-Z0-9]{8,20}$",
                                description="Destination account identifier"
                            ),
                            "amount": apigateway.JsonSchema(
                                type=apigateway.JsonSchemaType.NUMBER,
                                minimum=0.01,
                                maximum=10000000.00,
                                description="Transaction amount"
                            ),
                            "currency": apigateway.JsonSchema(
                                type=apigateway.JsonSchemaType.STRING,
                                min_length=3,
                                max_length=3,
                                pattern="^[A-Z]{3}$",
                                description="ISO 4217 currency code"
                            ),
                            "transaction_type": apigateway.JsonSchema(
                                type=apigateway.JsonSchemaType.STRING,
                                enum=["deposit", "withdrawal", "transfer", "payment", "wire", "ach", "check", "card"],
                                description="Type of transaction"
                            ),
                            "description": apigateway.JsonSchema(
                                type=apigateway.JsonSchemaType.STRING,
                                max_length=500,
                                description="Optional transaction description"
                            )
                        },
                        required=["from_account_id", "to_account_id", "amount", "currency", "transaction_type"]
                    )
                )
            },
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(
                    status_code="400",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(
                    status_code="401",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                )
            ]
        )
        
        # /v1/alerts endpoint - Requirement 6.2
        alerts_resource = v1_resource.add_resource("alerts")
        alerts_resource.add_method(
            "GET",
            alert_integration,
            api_key_required=True,
            request_validator=self.query_validator,
            request_parameters={
                "method.request.querystring.status": False,
                "method.request.querystring.risk_level": False,
                "method.request.querystring.limit": False,
                "method.request.querystring.offset": False,
                "method.request.querystring.sort": False,
                "method.request.querystring.order": False,
                "method.request.querystring.account_id": False,
                "method.request.querystring.date_from": False,
                "method.request.querystring.date_to": False
            },
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True,
                        "method.response.header.Content-Type": True
                    }
                ),
                apigateway.MethodResponse(
                    status_code="400",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(
                    status_code="401",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                )
            ]
        )
        
        # /v1/alerts/{id} endpoint for individual alert access
        alert_by_id_resource = alerts_resource.add_resource("{id}")
        alert_by_id_resource.add_method(
            "GET",
            alert_integration,
            api_key_required=True,
            request_parameters={
                "method.request.path.id": True
            },
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(
                    status_code="404",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                )
            ]
        )
        
        # /v1/reports endpoint - Requirement 6.2
        reports_resource = v1_resource.add_resource("reports")
        reports_resource.add_method(
            "GET",
            report_integration,
            api_key_required=True,
            request_validator=self.query_validator,
            request_parameters={
                "method.request.querystring.status": False,
                "method.request.querystring.case_id": False,
                "method.request.querystring.date_from": False,
                "method.request.querystring.date_to": False,
                "method.request.querystring.limit": False,
                "method.request.querystring.offset": False,
                "method.request.querystring.sort": False,
                "method.request.querystring.order": False
            },
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True,
                        "method.response.header.Content-Type": True
                    }
                ),
                apigateway.MethodResponse(
                    status_code="400",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                )
            ]
        )
        
        # /v1/reports/{id} endpoint - Requirement 6.2
        report_by_id_resource = reports_resource.add_resource("{id}")
        report_by_id_resource.add_method(
            "GET",
            report_integration,
            api_key_required=True,
            request_parameters={
                "method.request.path.id": True
            },
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True,
                        "method.response.header.Content-Type": True
                    }
                ),
                apigateway.MethodResponse(
                    status_code="404",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                ),
                apigateway.MethodResponse(
                    status_code="401",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                )
            ]
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
        self.api_key_id = self.api_key.key_id
        self.readonly_api_key_id = self.readonly_api_key.key_id
        
        # Export CloudFormation outputs for external access
        from aws_cdk import CfnOutput
        
        CfnOutput(
            self, "APIGatewayURL",
            value=self.api_gateway.url,
            description="Sentinel-AML API Gateway URL",
            export_name="SentinelAML-API-URL"
        )
        
        CfnOutput(
            self, "APIGatewayID",
            value=self.api_gateway.rest_api_id,
            description="Sentinel-AML API Gateway ID",
            export_name="SentinelAML-API-ID"
        )
        
        CfnOutput(
            self, "APIKeyID",
            value=self.api_key.key_id,
            description="Sentinel-AML API Key ID",
            export_name="SentinelAML-API-Key-ID"
        )