"""Security stack for Sentinel-AML - KMS, IAM roles, and security policies."""

from aws_cdk import (
    Stack,
    aws_kms as kms,
    aws_iam as iam,
    RemovalPolicy,
    Duration,
)
from constructs import Construct


class SecurityStack(Stack):
    """Security infrastructure stack for Sentinel-AML."""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # KMS key for encryption
        self.kms_key = kms.Key(
            self, "SentinelAMLKey",
            description="KMS key for Sentinel-AML data encryption",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,  # For development
            alias="sentinel-aml-key"
        )
        
        # Lambda execution role
        self.lambda_execution_role = iam.Role(
            self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole"),
            ],
            inline_policies={
                "NeptuneAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "neptune-db:*",
                                "neptune:*"
                            ],
                            resources=["*"]
                        )
                    ]
                ),
                "BedrockAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock:InvokeModel",
                                "bedrock:InvokeModelWithResponseStream"
                            ],
                            resources=["*"]
                        )
                    ]
                ),
                "KMSAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "kms:Decrypt",
                                "kms:Encrypt",
                                "kms:GenerateDataKey",
                                "kms:DescribeKey"
                            ],
                            resources=[self.kms_key.key_arn]
                        )
                    ]
                ),
                "AuditAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "dynamodb:PutItem",
                                "dynamodb:GetItem",
                                "dynamodb:Query",
                                "dynamodb:Scan"
                            ],
                            resources=[
                                self.audit_table.table_arn,
                                f"{self.audit_table.table_arn}/index/*"
                            ]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:PutObject",
                                "s3:GetObject",
                                "s3:ListBucket"
                            ],
                            resources=[
                                self.audit_bucket.bucket_arn,
                                f"{self.audit_bucket.bucket_arn}/*"
                            ]
                        )
                    ]
                ),
                "CloudWatchAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                                "cloudwatch:PutMetricData"
                            ],
                            resources=["*"]
                        )
                    ]
                )
            }
        )
        
        # Step Functions execution role
        self.step_functions_role = iam.Role(
            self, "StepFunctionsRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            inline_policies={
                "LambdaInvoke": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "lambda:InvokeFunction"
                            ],
                            resources=["*"]
                        )
                    ]
                ),
                "CloudWatchLogs": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogDelivery",
                                "logs:GetLogDelivery",
                                "logs:UpdateLogDelivery",
                                "logs:DeleteLogDelivery",
                                "logs:ListLogDeliveries",
                                "logs:PutResourcePolicy",
                                "logs:DescribeResourcePolicies",
                                "logs:DescribeLogGroups"
                            ],
                            resources=["*"]
                        )
                    ]
                )
            }
        )
        
        # API Gateway execution role
        self.api_gateway_role = iam.Role(
            self, "ApiGatewayRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonAPIGatewayPushToCloudWatchLogs")
            ],
            inline_policies={
                "LambdaInvoke": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "lambda:InvokeFunction"
                            ],
                            resources=["*"]
                        )
                    ]
                )
            }
        )
        
        # Neptune ML role (for future ML integration)
        self.neptune_ml_role = iam.Role(
            self, "NeptuneMLRole",
            assumed_by=iam.ServicePrincipal("neptune.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("NeptuneFullAccess")
            ],
            inline_policies={
                "SageMakerAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "sagemaker:CreateTrainingJob",
                                "sagemaker:DescribeTrainingJob",
                                "sagemaker:CreateModel",
                                "sagemaker:CreateEndpointConfig",
                                "sagemaker:CreateEndpoint",
                                "sagemaker:DescribeEndpoint",
                                "sagemaker:InvokeEndpoint"
                            ],
                            resources=["*"]
                        )
                    ]
                ),
                "S3Access": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:GetObject",
                                "s3:PutObject",
                                "s3:DeleteObject",
                                "s3:ListBucket"
                            ],
                            resources=["*"]
                        )
                    ]
                )
            }
        )
        
        # Audit logging infrastructure
        self.audit_table = self._create_audit_table()
        self.audit_bucket = self._create_audit_bucket()
        
        # Grant KMS key access to all roles
        self.kms_key.grant_encrypt_decrypt(self.lambda_execution_role)
        self.kms_key.grant_encrypt_decrypt(self.step_functions_role)
        self.kms_key.grant_encrypt_decrypt(self.api_gateway_role)
        self.kms_key.grant_encrypt_decrypt(self.neptune_ml_role)
    
    def _create_audit_table(self):
        """Create DynamoDB table for audit logs."""
        from aws_cdk import aws_dynamodb as dynamodb
        
        table = dynamodb.Table(
            self, "AuditTable",
            table_name=f"sentinel-aml-audit-{self.node.try_get_context('environment') or 'dev'}",
            partition_key=dynamodb.Attribute(
                name="record_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.kms_key,
            removal_policy=RemovalPolicy.RETAIN,  # Retain for compliance
            point_in_time_recovery=True,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES
        )
        
        # Add GSI for querying by user_id
        table.add_global_secondary_index(
            index_name="user-id-index",
            partition_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            )
        )
        
        # Add GSI for querying by resource
        table.add_global_secondary_index(
            index_name="resource-index",
            partition_key=dynamodb.Attribute(
                name="resource_type",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="resource_id",
                type=dynamodb.AttributeType.STRING
            )
        )
        
        return table
    
    def _create_audit_bucket(self):
        """Create S3 bucket for long-term audit log storage."""
        from aws_cdk import aws_s3 as s3
        
        bucket = s3.Bucket(
            self, "AuditBucket",
            bucket_name=f"sentinel-aml-audit-logs-{self.node.try_get_context('environment') or 'dev'}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.kms_key,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,  # Retain for compliance
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="audit-log-lifecycle",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30)
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90)
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.DEEP_ARCHIVE,
                            transition_after=Duration.days(365)
                        )
                    ],
                    expiration=Duration.days(2555)  # 7 years retention
                )
            ]
        )
        
        # Block public access
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:*"],
                resources=[bucket.bucket_arn, f"{bucket.bucket_arn}/*"],
                conditions={
                    "Bool": {
                        "aws:SecureTransport": "false"
                    }
                }
            )
        )
        
        return bucket