"""
AWS Lambda handler for fraud scoring with GNN analysis.

This Lambda function is triggered by transaction events and performs
real-time fraud scoring using trained GNN models.
"""

import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import boto3
from dataclasses import asdict

from ..core.logging import setup_lambda_logging, get_logger
from ..core.config import get_config
from ..core.exceptions import ValidationError, ProcessingError
from .fraud_scorer import GnnFraudScorer, FraudScoringRequest, ClusterAnalysisResult


class FraudScoringLambdaHandler:
    """Lambda handler for fraud scoring operations."""
    
    def __init__(self):
        """Initialize fraud scoring handler."""
        setup_lambda_logging()
        self.logger = get_logger(__name__)
        self.config = get_config()
        self.fraud_scorer = GnnFraudScorer()
        
        # Initialize AWS clients
        self.eventbridge = boto3.client('events')
        self.sns = boto3.client('sns')
        
        # Configuration
        self.alert_topic_arn = self.config.get('aws.sns.alert_topic_arn')
        self.step_functions_arn = self.config.get('aws.step_functions.orchestrator_arn')
    
    async def handle_transaction_cluster_analysis(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle transaction cluster analysis request.
        
        This is triggered when a cluster of related transactions needs analysis.
        """
        self.logger.info("Processing transaction cluster analysis", event_source=event.get('source'))
        
        try:
            # Extract cluster information from event
            detail = event.get('detail', {})
            cluster_id = detail.get('cluster_id')
            account_ids = detail.get('account_ids', [])
            trigger_transaction_id = detail.get('trigger_transaction_id')
            
            if not cluster_id or not account_ids:
                raise ValidationError("Missing cluster_id or account_ids in event")
            
            self.logger.info(
                "Analyzing transaction cluster",
                cluster_id=cluster_id,
                account_count=len(account_ids),
                trigger_transaction=trigger_transaction_id
            )
            
            # Perform cluster analysis
            result = await self.fraud_scorer.analyze_transaction_cluster(
                cluster_id=cluster_id,
                account_ids=account_ids,
                lookback_days=30
            )
            
            # Check if cluster is suspicious
            suspicious_accounts = [
                score for score in result.account_scores 
                if score.is_suspicious
            ]
            
            response_data = {
                'cluster_id': cluster_id,
                'analysis_result': asdict(result),
                'suspicious_account_count': len(suspicious_accounts),
                'requires_investigation': len(suspicious_accounts) > 0,
                'cluster_risk_score': result.cluster_risk_score,
                'processing_timestamp': datetime.utcnow().isoformat()
            }
            
            # Send alerts for suspicious clusters
            if suspicious_accounts:
                await self._send_cluster_alert(result)
                
                # Trigger SAR generation workflow if highly suspicious
                if result.cluster_risk_score > 0.8:
                    await self._trigger_sar_generation(result)
            
            self.logger.info(
                "Cluster analysis completed",
                cluster_id=cluster_id,
                cluster_risk_score=result.cluster_risk_score,
                suspicious_accounts=len(suspicious_accounts)
            )
            
            return {
                'statusCode': 200,
                'body': json.dumps(response_data, default=str)
            }
            
        except ValidationError as e:
            self.logger.error("Validation error in cluster analysis", error=str(e))
            return {
                'statusCode': 400,
                'body': json.dumps({'error': str(e)})
            }
        except Exception as e:
            self.logger.error("Unexpected error in cluster analysis", error=str(e))
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Internal server error'})
            }
    
    async def handle_real_time_scoring(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle real-time fraud scoring for individual transactions.
        
        This is triggered by new transaction events for immediate scoring.
        """
        self.logger.info("Processing real-time fraud scoring", event_source=event.get('source'))
        
        try:
            # Extract transaction information
            detail = event.get('detail', {})
            account_id = detail.get('account_id')
            transaction_id = detail.get('transaction_id')
            amount = detail.get('amount')
            
            if not account_id:
                raise ValidationError("Missing account_id in event")
            
            self.logger.info(
                "Scoring account for fraud risk",
                account_id=account_id,
                transaction_id=transaction_id,
                amount=amount
            )
            
            # Score the account
            results = await self.fraud_scorer.score_accounts(
                account_ids=[account_id],
                lookback_days=30,
                include_feature_importance=True
            )
            
            if not results:
                raise ProcessingError(f"Failed to score account {account_id}")
            
            result = results[0]
            
            response_data = {
                'account_id': account_id,
                'transaction_id': transaction_id,
                'scoring_result': asdict(result),
                'requires_investigation': result.is_suspicious,
                'processing_timestamp': datetime.utcnow().isoformat()
            }
            
            # Send alert if suspicious
            if result.is_suspicious:
                await self._send_account_alert(result, transaction_id)
            
            self.logger.info(
                "Real-time scoring completed",
                account_id=account_id,
                risk_score=result.risk_score,
                is_suspicious=result.is_suspicious
            )
            
            return {
                'statusCode': 200,
                'body': json.dumps(response_data, default=str)
            }
            
        except ValidationError as e:
            self.logger.error("Validation error in real-time scoring", error=str(e))
            return {
                'statusCode': 400,
                'body': json.dumps({'error': str(e)})
            }
        except Exception as e:
            self.logger.error("Unexpected error in real-time scoring", error=str(e))
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Internal server error'})
            }
    
    async def _send_cluster_alert(self, cluster_result: ClusterAnalysisResult) -> None:
        """Send alert for suspicious transaction cluster."""
        try:
            alert_message = {
                'alert_type': 'suspicious_cluster',
                'cluster_id': cluster_result.cluster_id,
                'risk_score': cluster_result.cluster_risk_score,
                'affected_accounts': len(cluster_result.account_scores),
                'suspicious_accounts': len([s for s in cluster_result.account_scores if s.is_suspicious]),
                'total_volume': cluster_result.total_volume,
                'transaction_count': cluster_result.transaction_count,
                'suspicious_patterns': cluster_result.suspicious_patterns,
                'timestamp': cluster_result.analysis_timestamp.isoformat(),
                'priority': 'HIGH' if cluster_result.cluster_risk_score > 0.8 else 'MEDIUM'
            }
            
            # Send to SNS topic
            if self.alert_topic_arn:
                await self._publish_to_sns(
                    topic_arn=self.alert_topic_arn,
                    message=alert_message,
                    subject=f"Suspicious Transaction Cluster Detected: {cluster_result.cluster_id}"
                )
            
            # Send to EventBridge for workflow orchestration
            await self._publish_to_eventbridge(
                source='sentinel-aml.fraud-scorer',
                detail_type='Suspicious Cluster Detected',
                detail=alert_message
            )
            
            self.logger.info(
                "Cluster alert sent",
                cluster_id=cluster_result.cluster_id,
                risk_score=cluster_result.cluster_risk_score
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to send cluster alert",
                cluster_id=cluster_result.cluster_id,
                error=str(e)
            )
    
    async def _send_account_alert(self, scoring_result, transaction_id: Optional[str] = None) -> None:
        """Send alert for suspicious account activity."""
        try:
            alert_message = {
                'alert_type': 'suspicious_account',
                'account_id': scoring_result.account_id,
                'transaction_id': transaction_id,
                'risk_score': scoring_result.risk_score,
                'confidence': scoring_result.confidence,
                'patterns_detected': scoring_result.patterns_detected,
                'feature_importance': scoring_result.feature_importance,
                'model_version': scoring_result.model_version,
                'timestamp': scoring_result.timestamp.isoformat(),
                'priority': 'HIGH' if scoring_result.risk_score > 0.8 else 'MEDIUM'
            }
            
            # Send to SNS topic
            if self.alert_topic_arn:
                await self._publish_to_sns(
                    topic_arn=self.alert_topic_arn,
                    message=alert_message,
                    subject=f"Suspicious Account Activity: {scoring_result.account_id}"
                )
            
            # Send to EventBridge
            await self._publish_to_eventbridge(
                source='sentinel-aml.fraud-scorer',
                detail_type='Suspicious Account Activity',
                detail=alert_message
            )
            
            self.logger.info(
                "Account alert sent",
                account_id=scoring_result.account_id,
                risk_score=scoring_result.risk_score
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to send account alert",
                account_id=scoring_result.account_id,
                error=str(e)
            )
    
    async def _trigger_sar_generation(self, cluster_result: ClusterAnalysisResult) -> None:
        """Trigger SAR generation workflow for highly suspicious clusters."""
        try:
            sar_request = {
                'cluster_id': cluster_result.cluster_id,
                'account_ids': [score.account_id for score in cluster_result.account_scores if score.is_suspicious],
                'risk_score': cluster_result.cluster_risk_score,
                'suspicious_patterns': cluster_result.suspicious_patterns,
                'total_volume': cluster_result.total_volume,
                'analysis_timestamp': cluster_result.analysis_timestamp.isoformat()
            }
            
            # Send to EventBridge to trigger SAR generation
            await self._publish_to_eventbridge(
                source='sentinel-aml.fraud-scorer',
                detail_type='SAR Generation Required',
                detail=sar_request
            )
            
            self.logger.info(
                "SAR generation triggered",
                cluster_id=cluster_result.cluster_id,
                risk_score=cluster_result.cluster_risk_score
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to trigger SAR generation",
                cluster_id=cluster_result.cluster_id,
                error=str(e)
            )
    
    async def _publish_to_sns(self, topic_arn: str, message: Dict[str, Any], subject: str) -> None:
        """Publish message to SNS topic."""
        try:
            response = self.sns.publish(
                TopicArn=topic_arn,
                Message=json.dumps(message, default=str),
                Subject=subject
            )
            self.logger.debug("Message published to SNS", message_id=response['MessageId'])
        except Exception as e:
            self.logger.error("Failed to publish to SNS", error=str(e))
            raise
    
    async def _publish_to_eventbridge(
        self,
        source: str,
        detail_type: str,
        detail: Dict[str, Any]
    ) -> None:
        """Publish event to EventBridge."""
        try:
            response = self.eventbridge.put_events(
                Entries=[
                    {
                        'Source': source,
                        'DetailType': detail_type,
                        'Detail': json.dumps(detail, default=str),
                        'Time': datetime.utcnow()
                    }
                ]
            )
            
            if response['FailedEntryCount'] > 0:
                self.logger.error("Failed to publish some events to EventBridge", failures=response['Entries'])
            else:
                self.logger.debug("Event published to EventBridge")
                
        except Exception as e:
            self.logger.error("Failed to publish to EventBridge", error=str(e))
            raise


# Lambda handler instance
handler = FraudScoringLambdaHandler()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda entry point for fraud scoring.
    
    Routes different types of events to appropriate handlers.
    """
    try:
        # Determine event type and route accordingly
        event_source = event.get('source', '')
        detail_type = event.get('detail-type', '')
        
        if 'cluster' in detail_type.lower() or 'cluster_id' in event.get('detail', {}):
            # Transaction cluster analysis
            return asyncio.run(handler.handle_transaction_cluster_analysis(event))
        elif 'transaction' in event_source.lower() or 'account_id' in event.get('detail', {}):
            # Real-time transaction scoring
            return asyncio.run(handler.handle_real_time_scoring(event))
        elif event.get('httpMethod'):
            # Direct HTTP API call
            from .fraud_scorer import handle_fraud_scoring_request
            return asyncio.run(handle_fraud_scoring_request(event))
        else:
            # Default to fraud scoring request
            from .fraud_scorer import handle_fraud_scoring_request
            return asyncio.run(handle_fraud_scoring_request(event))
            
    except Exception as e:
        logger = get_logger(__name__)
        logger.error("Unhandled error in Lambda handler", error=str(e))
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }