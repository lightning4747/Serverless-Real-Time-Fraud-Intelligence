"""Monitoring and observability stack for Sentinel-AML."""

from aws_cdk import (
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_lambda as _lambda,
    aws_apigateway as apigateway,
    aws_stepfunctions as sfn,
    aws_neptune as neptune,
    aws_logs as logs,
    Duration,
)
from constructs import Construct
from typing import Dict


class MonitoringStack(Stack):
    """Monitoring and observability stack for Sentinel-AML."""
    
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        neptune_cluster: neptune.CfnDBCluster,
        lambda_functions: Dict[str, _lambda.Function],
        api_gateway: apigateway.RestApi,
        state_machine: sfn.StateMachine,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # SNS topic for alerts
        self.alert_topic = sns.Topic(
            self, "SentinelAMLAlerts",
            topic_name="sentinel-aml-alerts",
            display_name="Sentinel-AML System Alerts"
        )
        
        # Email subscription (replace with actual email)
        self.alert_topic.add_subscription(
            subscriptions.EmailSubscription("admin@sentinel-aml.com")
        )
        
        # CloudWatch Dashboard
        self.dashboard = cloudwatch.Dashboard(
            self, "SentinelAMLDashboard",
            dashboard_name="Sentinel-AML-System-Metrics"
        )
        
        # Lambda function metrics
        lambda_widgets = []
        for name, function in lambda_functions.items():
            # Duration metric
            duration_metric = function.metric_duration(
                statistic="Average",
                period=Duration.minutes(5)
            )
            
            # Error rate metric
            error_metric = function.metric_errors(
                statistic="Sum",
                period=Duration.minutes(5)
            )
            
            # Invocation count metric
            invocation_metric = function.metric_invocations(
                statistic="Sum",
                period=Duration.minutes(5)
            )
            
            # Create widget for this function
            lambda_widgets.append(
                cloudwatch.GraphWidget(
                    title=f"Lambda: {name}",
                    left=[duration_metric],
                    right=[error_metric, invocation_metric],
                    width=12,
                    height=6
                )
            )
            
            # Create alarms for critical functions
            if name in ["transaction_processor", "fraud_scorer"]:
                # High error rate alarm
                error_alarm = cloudwatch.Alarm(
                    self, f"{name}ErrorAlarm",
                    alarm_name=f"sentinel-aml-{name}-errors",
                    metric=error_metric,
                    threshold=5,
                    evaluation_periods=2,
                    comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                    alarm_description=f"High error rate in {name} function"
                )
                error_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
                
                # High duration alarm
                duration_alarm = cloudwatch.Alarm(
                    self, f"{name}DurationAlarm",
                    alarm_name=f"sentinel-aml-{name}-duration",
                    metric=duration_metric,
                    threshold=30000,  # 30 seconds
                    evaluation_periods=3,
                    comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
                    alarm_description=f"High duration in {name} function"
                )
                duration_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
        
        # API Gateway metrics
        api_4xx_metric = api_gateway.metric_client_error(
            statistic="Sum",
            period=Duration.minutes(5)
        )
        
        api_5xx_metric = api_gateway.metric_server_error(
            statistic="Sum", 
            period=Duration.minutes(5)
        )
        
        api_latency_metric = api_gateway.metric_latency(
            statistic="Average",
            period=Duration.minutes(5)
        )
        
        api_count_metric = api_gateway.metric_count(
            statistic="Sum",
            period=Duration.minutes(5)
        )
        
        api_widget = cloudwatch.GraphWidget(
            title="API Gateway Metrics",
            left=[api_latency_metric],
            right=[api_4xx_metric, api_5xx_metric, api_count_metric],
            width=12,
            height=6
        )
        
        # API Gateway alarms
        api_error_alarm = cloudwatch.Alarm(
            self, "APIGatewayErrorAlarm",
            alarm_name="sentinel-aml-api-errors",
            metric=api_5xx_metric,
            threshold=10,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="High 5xx error rate in API Gateway"
        )
        api_error_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
        
        # Step Functions metrics
        sf_execution_failed_metric = state_machine.metric_failed(
            statistic="Sum",
            period=Duration.minutes(5)
        )
        
        sf_execution_succeeded_metric = state_machine.metric_succeeded(
            statistic="Sum",
            period=Duration.minutes(5)
        )
        
        sf_execution_time_metric = state_machine.metric_time(
            statistic="Average",
            period=Duration.minutes(5)
        )
        
        sf_widget = cloudwatch.GraphWidget(
            title="Step Functions Metrics",
            left=[sf_execution_time_metric],
            right=[sf_execution_succeeded_metric, sf_execution_failed_metric],
            width=12,
            height=6
        )
        
        # Step Functions alarm
        sf_failure_alarm = cloudwatch.Alarm(
            self, "StepFunctionsFailureAlarm",
            alarm_name="sentinel-aml-stepfunctions-failures",
            metric=sf_execution_failed_metric,
            threshold=3,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="High failure rate in Step Functions"
        )
        sf_failure_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
        
        # Custom business metrics
        transaction_volume_metric = cloudwatch.Metric(
            namespace="Sentinel-AML/Business",
            metric_name="TransactionVolume",
            statistic="Sum",
            period=Duration.minutes(5)
        )
        
        fraud_detection_rate_metric = cloudwatch.Metric(
            namespace="Sentinel-AML/Business",
            metric_name="FraudDetectionRate",
            statistic="Average",
            period=Duration.minutes(15)
        )
        
        sar_generation_count_metric = cloudwatch.Metric(
            namespace="Sentinel-AML/Business",
            metric_name="SARGenerationCount",
            statistic="Sum",
            period=Duration.hours(1)
        )
        
        business_widget = cloudwatch.GraphWidget(
            title="Business Metrics",
            left=[transaction_volume_metric, fraud_detection_rate_metric],
            right=[sar_generation_count_metric],
            width=12,
            height=6
        )
        
        # Neptune metrics (if available)
        neptune_widget = cloudwatch.GraphWidget(
            title="Neptune Database Metrics",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Neptune",
                    metric_name="DatabaseConnections",
                    dimensions_map={"DBClusterIdentifier": neptune_cluster.ref},
                    statistic="Average",
                    period=Duration.minutes(5)
                )
            ],
            right=[
                cloudwatch.Metric(
                    namespace="AWS/Neptune",
                    metric_name="GremlinRequestsPerSec",
                    dimensions_map={"DBClusterIdentifier": neptune_cluster.ref},
                    statistic="Average",
                    period=Duration.minutes(5)
                )
            ],
            width=12,
            height=6
        )
        
        # Add widgets to dashboard
        self.dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown="# Sentinel-AML System Dashboard\n\nReal-time monitoring of the AI-powered Anti-Money Laundering detection platform.",
                width=24,
                height=2
            )
        )
        
        # Add Lambda widgets
        for widget in lambda_widgets:
            self.dashboard.add_widgets(widget)
        
        # Add other widgets
        self.dashboard.add_widgets(
            api_widget,
            sf_widget,
            business_widget,
            neptune_widget
        )
        
        # Log insights queries for common investigations
        self.create_log_insights_queries()
    
    def create_log_insights_queries(self) -> None:
        """Create CloudWatch Logs Insights queries for common investigations."""
        
        # Query for transaction processing errors
        transaction_errors_query = """
        fields @timestamp, @message, correlation_id, account_id, transaction_id, error
        | filter @message like /ERROR/
        | filter @message like /transaction/
        | sort @timestamp desc
        | limit 100
        """
        
        # Query for fraud detection patterns
        fraud_patterns_query = """
        fields @timestamp, @message, risk_score, account_id, suspicious_patterns
        | filter risk_score > 0.7
        | sort @timestamp desc
        | limit 50
        """
        
        # Query for API performance
        api_performance_query = """
        fields @timestamp, @duration, @requestId, @message
        | filter @type = "REPORT"
        | sort @timestamp desc
        | limit 100
        """
        
        # Store queries as custom metrics (these would be used in CloudWatch Insights)
        self.log_queries = {
            "transaction_errors": transaction_errors_query,
            "fraud_patterns": fraud_patterns_query,
            "api_performance": api_performance_query
        }