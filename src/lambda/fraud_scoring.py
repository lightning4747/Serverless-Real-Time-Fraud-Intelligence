"""
Fraud Scoring Lambda Function for Sentinel-AML
Implements GNN-based fraud scoring with Neptune ML integration.
"""

import json
import logging
import boto3
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import os
from gremlin_python.driver import client
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T, P, Order

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class FraudScoringConfig:
    """Configuration for fraud scoring Lambda."""
    neptune_endpoint: str
    neptune_port: int = 8182
    model_endpoint: str = ""
    suspicious_threshold: float = 0.7
    high_risk_threshold: float = 0.9
    batch_size: int = 100
    max_processing_time: int = 300  # 5 minutes
    enable_explainability: bool = True

@dataclass
class TransactionCluster:
    """Represents a cluster of related transactions for analysis."""
    cluster_id: str
    account_ids: List[str]
    transaction_ids: List[str]
    total_amount: float
    transaction_count: int
    time_span_hours: float
    cluster_type: str  # 'temporal', 'amount', 'network'

@dataclass
class FraudScore:
    """Fraud scoring result."""
    cluster_id: str
    risk_score: float
    confidence: float
    risk_level: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    pattern_indicators: List[str]
    feature_importance: Dict[str, float]
    explanation: str
    timestamp: str
class FraudScoringEngine:
    """Main fraud scoring engine using GNN models."""
    
    def __init__(self, config: FraudScoringConfig):
        self.config = config
        self.neptune_client = boto3.client('neptune')
        self.sagemaker_runtime = boto3.client('sagemaker-runtime')
        self.bedrock_runtime = boto3.client('bedrock-runtime')
        
        # Initialize Neptune connection
        self.connection = DriverRemoteConnection(
            f'wss://{config.neptune_endpoint}:{config.neptune_port}/gremlin',
            'g'
        )
        self.g = traversal().withRemote(self.connection)
        
        # Initialize model endpoint
        self.model_endpoint = config.model_endpoint or self._get_latest_model_endpoint()
    
    def score_transaction_cluster(self, cluster: TransactionCluster) -> FraudScore:
        """Score a transaction cluster for fraud risk."""
        logger.info(f"Scoring cluster {cluster.cluster_id}")
        
        try:
            # Extract features for the cluster
            features = self._extract_cluster_features(cluster)
            
            # Get GNN prediction
            gnn_score, confidence = self._get_gnn_prediction(features)
            
            # Validate score bounds (Property 3)
            gnn_score = max(0.0, min(1.0, gnn_score))
            
            # Analyze pattern indicators
            pattern_indicators = self._analyze_pattern_indicators(cluster, features)
            
            # Calculate feature importance
            feature_importance = self._calculate_feature_importance(features, gnn_score)
            
            # Generate explanation if enabled
            explanation = ""
            if self.config.enable_explainability:
                explanation = self._generate_explanation(cluster, gnn_score, pattern_indicators)
            
            # Determine risk level
            risk_level = self._classify_risk_level(gnn_score)
            
            fraud_score = FraudScore(
                cluster_id=cluster.cluster_id,
                risk_score=gnn_score,
                confidence=confidence,
                risk_level=risk_level,
                pattern_indicators=pattern_indicators,
                feature_importance=feature_importance,
                explanation=explanation,
                timestamp=datetime.utcnow().isoformat()
            )
            
            logger.info(f"Cluster {cluster.cluster_id} scored: {gnn_score:.3f} ({risk_level})")
            return fraud_score
            
        except Exception as e:
            logger.error(f"Failed to score cluster {cluster.cluster_id}: {str(e)}")
            raise
    
    def _extract_cluster_features(self, cluster: TransactionCluster) -> Dict[str, Any]:
        """Extract features for GNN model input."""
        logger.debug(f"Extracting features for cluster {cluster.cluster_id}")
        
        # Account-level features
        account_features = self._get_account_features(cluster.account_ids)
        
        # Transaction-level features
        transaction_features = self._get_transaction_features(cluster.transaction_ids)
        
        # Network features
        network_features = self._get_network_features(cluster.account_ids)
        
        # Temporal features
        temporal_features = self._get_temporal_features(cluster.transaction_ids)
        
        # Aggregate cluster features
        cluster_features = {
            'total_amount': cluster.total_amount,
            'transaction_count': cluster.transaction_count,
            'time_span_hours': cluster.time_span_hours,
            'avg_amount': cluster.total_amount / max(cluster.transaction_count, 1),
            'amount_velocity': cluster.total_amount / max(cluster.time_span_hours, 1),
            'account_count': len(cluster.account_ids),
            'cluster_density': len(cluster.transaction_ids) / max(len(cluster.account_ids), 1)
        }
        
        return {
            'account_features': account_features,
            'transaction_features': transaction_features,
            'network_features': network_features,
            'temporal_features': temporal_features,
            'cluster_features': cluster_features
        }
    
    def _get_account_features(self, account_ids: List[str]) -> List[Dict[str, float]]:
        """Get account-level features."""
        account_features = []
        
        for account_id in account_ids:
            # Query account statistics
            account_stats = (self.g.V()
                           .has('account_id', account_id)
                           .project('account_id', 'total_tx', 'total_amount', 
                                   'avg_amount', 'unique_counterparties', 'account_age',
                                   'small_tx_count', 'large_tx_count')
                           .by('account_id')
                           .by(__.bothE('SENT_TO').count())
                           .by(__.bothE('SENT_TO').values('amount').sum())
                           .by(__.bothE('SENT_TO').values('amount').mean())
                           .by(__.bothE('SENT_TO').otherV().dedup().count())
                           .by(__.values('creation_date'))
                           .by(__.bothE('SENT_TO').has('amount', P.lt(10000)).count())
                           .by(__.bothE('SENT_TO').has('amount', P.gte(50000)).count())
                           .next())
            
            # Calculate derived features
            total_tx = int(account_stats['total_tx'])
            total_amount = float(account_stats['total_amount'] or 0)
            small_tx_count = int(account_stats['small_tx_count'])
            large_tx_count = int(account_stats['large_tx_count'])
            
            # Risk indicators
            small_tx_ratio = small_tx_count / max(total_tx, 1)
            large_tx_ratio = large_tx_count / max(total_tx, 1)
            
            # Account age in days
            creation_date = datetime.fromisoformat(account_stats['account_age'])
            account_age_days = (datetime.utcnow() - creation_date).days
            
            features = {
                'account_id': account_id,
                'total_transactions': total_tx,
                'total_amount': total_amount,
                'avg_amount': float(account_stats['avg_amount'] or 0),
                'unique_counterparties': int(account_stats['unique_counterparties']),
                'account_age_days': account_age_days,
                'small_transaction_ratio': small_tx_ratio,
                'large_transaction_ratio': large_tx_ratio,
                'transaction_velocity': total_tx / max(account_age_days, 1)
            }
            
            account_features.append(features)
        
        return account_features
    
    def _get_transaction_features(self, transaction_ids: List[str]) -> List[Dict[str, float]]:
        """Get transaction-level features."""
        transaction_features = []
        
        for tx_id in transaction_ids:
            # Query transaction details
            tx_details = (self.g.E()
                         .has('transaction_id', tx_id)
                         .project('transaction_id', 'amount', 'timestamp', 
                                 'transaction_type', 'currency')
                         .by('transaction_id')
                         .by('amount')
                         .by('timestamp')
                         .by('transaction_type')
                         .by('currency')
                         .next())
            
            # Extract temporal features
            tx_time = datetime.fromisoformat(tx_details['timestamp'])
            hour_of_day = tx_time.hour
            day_of_week = tx_time.weekday()
            
            # Amount features
            amount = float(tx_details['amount'])
            
            features = {
                'transaction_id': tx_id,
                'amount': amount,
                'amount_log': np.log10(max(amount, 1)),
                'hour_of_day': hour_of_day,
                'day_of_week': day_of_week,
                'is_weekend': int(day_of_week >= 5),
                'is_business_hours': int(9 <= hour_of_day <= 17),
                'is_round_amount': int(amount % 1000 == 0),
                'is_below_ctr_threshold': int(amount < 10000),
                'is_above_large_threshold': int(amount >= 50000)
            }
            
            transaction_features.append(features)
        
        return transaction_features
    
    def _get_network_features(self, account_ids: List[str]) -> Dict[str, float]:
        """Get network-level features for the account cluster."""
        # Calculate network density
        total_possible_edges = len(account_ids) * (len(account_ids) - 1)
        
        if total_possible_edges == 0:
            return {'network_density': 0.0, 'clustering_coefficient': 0.0}
        
        # Count actual edges between accounts in cluster
        actual_edges = 0
        for i, account1 in enumerate(account_ids):
            for account2 in account_ids[i+1:]:
                edge_exists = (self.g.V()
                             .has('account_id', account1)
                             .bothE('SENT_TO')
                             .otherV()
                             .has('account_id', account2)
                             .hasNext())
                if edge_exists:
                    actual_edges += 2  # Bidirectional
        
        network_density = actual_edges / total_possible_edges
        
        # Simplified clustering coefficient
        clustering_coefficient = network_density  # Simplified for now
        
        return {
            'network_density': network_density,
            'clustering_coefficient': clustering_coefficient,
            'account_count': len(account_ids)
        }
    
    def _get_temporal_features(self, transaction_ids: List[str]) -> Dict[str, float]:
        """Get temporal features for transaction cluster."""
        if not transaction_ids:
            return {'time_span_hours': 0.0, 'transaction_frequency': 0.0}
        
        # Get all timestamps
        timestamps = []
        for tx_id in transaction_ids:
            timestamp = (self.g.E()
                        .has('transaction_id', tx_id)
                        .values('timestamp')
                        .next())
            timestamps.append(datetime.fromisoformat(timestamp))
        
        timestamps.sort()
        
        # Calculate time span
        if len(timestamps) > 1:
            time_span = (timestamps[-1] - timestamps[0]).total_seconds() / 3600  # hours
        else:
            time_span = 0.0
        
        # Calculate transaction frequency
        frequency = len(transaction_ids) / max(time_span, 1)
        
        return {
            'time_span_hours': time_span,
            'transaction_frequency': frequency,
            'transaction_count': len(transaction_ids)
        }
    def _get_gnn_prediction(self, features: Dict[str, Any]) -> Tuple[float, float]:
        """Get prediction from Neptune ML GNN model."""
        logger.debug("Getting GNN prediction")
        
        try:
            # Prepare input for Neptune ML model
            model_input = self._prepare_model_input(features)
            
            # Call Neptune ML endpoint
            response = self.sagemaker_runtime.invoke_endpoint(
                EndpointName=self.model_endpoint,
                ContentType='application/json',
                Body=json.dumps(model_input)
            )
            
            # Parse response
            result = json.loads(response['Body'].read().decode())
            
            # Extract risk score and confidence
            risk_score = float(result.get('predictions', [0.0])[0])
            confidence = float(result.get('confidence', 0.5))
            
            return risk_score, confidence
            
        except Exception as e:
            logger.warning(f"GNN prediction failed, using fallback: {str(e)}")
            # Fallback to rule-based scoring
            return self._fallback_scoring(features)
    
    def _prepare_model_input(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare features for Neptune ML model input."""
        # Flatten and normalize features for model input
        model_features = []
        
        # Account features (aggregated)
        account_features = features['account_features']
        if account_features:
            avg_total_tx = np.mean([acc['total_transactions'] for acc in account_features])
            avg_total_amount = np.mean([acc['total_amount'] for acc in account_features])
            avg_small_tx_ratio = np.mean([acc['small_transaction_ratio'] for acc in account_features])
            avg_velocity = np.mean([acc['transaction_velocity'] for acc in account_features])
            
            model_features.extend([avg_total_tx, avg_total_amount, avg_small_tx_ratio, avg_velocity])
        else:
            model_features.extend([0.0, 0.0, 0.0, 0.0])
        
        # Transaction features (aggregated)
        transaction_features = features['transaction_features']
        if transaction_features:
            avg_amount = np.mean([tx['amount'] for tx in transaction_features])
            weekend_ratio = np.mean([tx['is_weekend'] for tx in transaction_features])
            round_amount_ratio = np.mean([tx['is_round_amount'] for tx in transaction_features])
            below_ctr_ratio = np.mean([tx['is_below_ctr_threshold'] for tx in transaction_features])
            
            model_features.extend([avg_amount, weekend_ratio, round_amount_ratio, below_ctr_ratio])
        else:
            model_features.extend([0.0, 0.0, 0.0, 0.0])
        
        # Network features
        network_features = features['network_features']
        model_features.extend([
            network_features['network_density'],
            network_features['clustering_coefficient'],
            network_features['account_count']
        ])
        
        # Temporal features
        temporal_features = features['temporal_features']
        model_features.extend([
            temporal_features['time_span_hours'],
            temporal_features['transaction_frequency'],
            temporal_features['transaction_count']
        ])
        
        # Cluster features
        cluster_features = features['cluster_features']
        model_features.extend([
            cluster_features['total_amount'],
            cluster_features['avg_amount'],
            cluster_features['amount_velocity'],
            cluster_features['cluster_density']
        ])
        
        return {
            'instances': [model_features],
            'configuration': {
                'k': 1,  # Top-k predictions
                'threshold': self.config.suspicious_threshold
            }
        }
    
    def _fallback_scoring(self, features: Dict[str, Any]) -> Tuple[float, float]:
        """Fallback rule-based scoring when GNN model is unavailable."""
        logger.info("Using fallback rule-based scoring")
        
        score = 0.0
        confidence = 0.3  # Lower confidence for rule-based
        
        # Rule 1: High small transaction ratio
        account_features = features['account_features']
        if account_features:
            avg_small_tx_ratio = np.mean([acc['small_transaction_ratio'] for acc in account_features])
            if avg_small_tx_ratio > 0.8:
                score += 0.4
        
        # Rule 2: High transaction frequency
        temporal_features = features['temporal_features']
        if temporal_features['transaction_frequency'] > 10:  # More than 10 tx per hour
            score += 0.3
        
        # Rule 3: High network density (potential circular flows)
        network_features = features['network_features']
        if network_features['network_density'] > 0.7:
            score += 0.2
        
        # Rule 4: Round amounts
        transaction_features = features['transaction_features']
        if transaction_features:
            round_amount_ratio = np.mean([tx['is_round_amount'] for tx in transaction_features])
            if round_amount_ratio > 0.5:
                score += 0.1
        
        return min(score, 1.0), confidence
    
    def _analyze_pattern_indicators(self, cluster: TransactionCluster, 
                                   features: Dict[str, Any]) -> List[str]:
        """Analyze and identify specific suspicious patterns."""
        indicators = []
        
        # Check for smurfing patterns
        if self._detect_smurfing_pattern(features):
            indicators.append("SMURFING_PATTERN")
        
        # Check for layering patterns
        if self._detect_layering_pattern(features):
            indicators.append("LAYERING_PATTERN")
        
        # Check for rapid fire transactions
        if self._detect_rapid_fire_pattern(features):
            indicators.append("RAPID_FIRE_PATTERN")
        
        # Check for round amount clustering
        if self._detect_round_amount_pattern(features):
            indicators.append("ROUND_AMOUNT_PATTERN")
        
        # Check for off-hours activity
        if self._detect_off_hours_pattern(features):
            indicators.append("OFF_HOURS_PATTERN")
        
        # Check for circular flows
        if self._detect_circular_flow_pattern(features):
            indicators.append("CIRCULAR_FLOW_PATTERN")
        
        return indicators
    
    def _detect_smurfing_pattern(self, features: Dict[str, Any]) -> bool:
        """Detect smurfing (structuring) patterns."""
        transaction_features = features['transa account_ids=["ACC001", "ACC002", "ACC003"],
        transaction_ids=["TX001", "TX002", "TX003", "TX004"],
        total_amount=35000.0,
        transaction_count=4,
        time_span_hours=2.5,
        cluster_type="temporal"
    )
    
    config = FraudScoringConfig(
        neptune_endpoint="localhost",
        model_endpoint="test-endpoint"
    )
    
    engine = FraudScoringEngine(config)
    result = engine.score_transaction_cluster(test_cluster)
    print(json.dumps(asdict(result), indent=2))
                TopicArn=topic_arn,
                Message=json.dumps(message),
                Subject=f'Suspicious Activity Alert - Risk Score: {fraud_score.risk_score:.3f}'
            )
            
            logger.info(f"Alert published for cluster {fraud_score.cluster_id}")
    
    except Exception as e:
        logger.error(f"Failed to trigger alert: {str(e)}")

if __name__ == "__main__":
    # For local testing
    test_cluster = TransactionCluster(
        cluster_id="test-cluster-001",
       ('ALERT_TOPIC_ARN')
        
        if topic_arn:
            message = {
                'alert_type': 'SUSPICIOUS_ACTIVITY',
                'cluster_id': fraud_score.cluster_id,
                'risk_score': fraud_score.risk_score,
                'risk_level': fraud_score.risk_level,
                'pattern_indicators': fraud_score.pattern_indicators,
                'explanation': fraud_score.explanation,
                'timestamp': fraud_score.timestamp
            }
            
            sns.publish(body': json.dumps({
                'error': str(e),
                'message': 'Fraud scoring failed'
            })
        }
    
    finally:
        if 'scoring_engine' in locals():
            scoring_engine.close()

def _trigger_alert(fraud_score: FraudScore):
    """Trigger alert for suspicious activity."""
    logger.info(f"Triggering alert for cluster {fraud_score.cluster_id}")
    
    try:
        # Publish to SNS topic for alerts
        sns = boto3.client('sns')
        topic_arn = os.environ.getre = scoring_engine.score_transaction_cluster(cluster)
            
            # Trigger alert if suspicious
            if fraud_score.risk_score >= config.suspicious_threshold:
                _trigger_alert(fraud_score)
            
            return {
                'statusCode': 200,
                'body': json.dumps(asdict(fraud_score))
            }
    
    except Exception as e:
        logger.error(f"Fraud scoring failed: {str(e)}")
        return {
            'statusCode': 500,
            '           _trigger_alert(fraud_score)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'Processed {len(results)} clusters',
                    'results': results
                })
            }
        
        else:
            # Direct invocation
            cluster_data = event.get('cluster', {})
            cluster = TransactionCluster(**cluster_data)
            
            # Score the cluster
            fraud_sco       results = []
            for record in event['Records']:
                cluster_data = json.loads(record['body'])
                cluster = TransactionCluster(**cluster_data)
                
                # Score the cluster
                fraud_score = scoring_engine.score_transaction_cluster(cluster)
                results.append(asdict(fraud_score))
                
                # Trigger alert if suspicious
                if fraud_score.risk_score >= config.suspicious_threshold:
         iron.get('MODEL_ENDPOINT', ''),
            suspicious_threshold=float(os.environ.get('SUSPICIOUS_THRESHOLD', 0.7)),
            high_risk_threshold=float(os.environ.get('HIGH_RISK_THRESHOLD', 0.9)),
            enable_explainability=os.environ.get('ENABLE_EXPLAINABILITY', 'true').lower() == 'true'
        )
        
        # Initialize fraud scoring engine
        scoring_engine = FraudScoringEngine(config)
        
        # Parse input event
        if 'Records' in event:
            # SQS/SNS event
     
        """Close Neptune connection."""
        if hasattr(self, 'connection'):
            self.connection.close()

def lambda_handler(event, context):
    """AWS Lambda handler for fraud scoring."""
    logger.info("Starting fraud scoring Lambda")
    
    try:
        # Parse configuration from environment variables
        config = FraudScoringConfig(
            neptune_endpoint=os.environ['NEPTUNE_ENDPOINT'],
            neptune_port=int(os.environ.get('NEPTUNE_PORT', 8182)),
            model_endpoint=os.env not models:
                raise ValueError("No Neptune ML models found")
            
            # Sort by creation time and get the latest
            latest_model = sorted(models, key=lambda x: x['creationTimeInMillis'], reverse=True)[0]
            
            return latest_model['modelEndpoint']
            
        except Exception as e:
            logger.warning(f"Failed to get model endpoint: {str(e)}")
            return "sentinel-aml-gnn-endpoint"  # Default endpoint name
    
    def close(self):CRITICAL'
        elif risk_score >= self.config.suspicious_threshold:
            return 'HIGH'
        elif risk_score >= 0.5:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _get_latest_model_endpoint(self) -> str:
        """Get the latest Neptune ML model endpoint."""
        try:
            # List Neptune ML models and get the latest one
            response = self.neptune_client.list_ml_models()
            models = response.get('models', [])
            
            if       - Pattern indicators: {', '.join(pattern_indicators) if pattern_indicators else 'None'}
        
        Provide a clear, concise explanation in 2-3 sentences that a compliance officer would understand.
        Focus on the specific suspicious patterns and why they indicate potential money laundering.
        """
    
    def _classify_risk_level(self, risk_score: float) -> str:
        """Classify risk level based on score."""
        if risk_score >= self.config.high_risk_threshold:
            return 'r]) -> str:
        """Create prompt for Bedrock explanation generation."""
        return f"""
        As an AML expert, explain why this transaction cluster received a fraud risk score of {risk_score:.3f}.
        
        Cluster Details:
        - Cluster ID: {cluster.cluster_id}
        - Number of accounts: {len(cluster.account_ids)}
        - Number of transactions: {cluster.transaction_count}
        - Total amount: ${cluster.total_amount:,.2f}
        - Time span: {cluster.time_span_hours:.1f} hours
 esult = json.loads(response['body'].read())
            explanation = result['content'][0]['text']
            
            return explanation
            
        except Exception as e:
            logger.warning(f"Failed to generate explanation: {str(e)}")
            return f"Risk score: {risk_score:.3f}. Patterns detected: {', '.join(pattern_indicators)}"
    
    def _create_explanation_prompt(self, cluster: TransactionCluster, risk_score: float, 
                                 pattern_indicators: List[st
                contentType='application/json',
                accept='application/json',
                body=json.dumps({
                    'anthropic_version': 'bedrock-2023-05-31',
                    'max_tokens': 500,
                    'messages': [
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ]
                })
            )
            
            # Parse response
            r      pattern_indicators: List[str]) -> str:
        """Generate human-readable explanation using Bedrock."""
        if not self.config.enable_explainability:
            return ""
        
        try:
            # Prepare explanation prompt
            prompt = self._create_explanation_prompt(cluster, risk_score, pattern_indicators)
            
            # Call Bedrock Claude 3
            response = self.bedrock_runtime.invoke_model(
                modelId='anthropic.claude-3-sonnet-20240229-v1:0',features['network_density'] * risk_score
        importance['clustering_coefficient'] = network_features['clustering_coefficient'] * risk_score
        
        # Temporal features importance
        temporal_features = features['temporal_features']
        importance['transaction_frequency'] = min(temporal_features['transaction_frequency'] * 0.1 * risk_score, 1.0)
        
        return importance
    
    def _generate_explanation(self, cluster: TransactionCluster, risk_score: float, 
                       np.mean([acc['small_transaction_ratio'] for acc in account_features])
            importance['small_transaction_ratio'] = min(avg_small_tx_ratio * risk_score, 1.0)
            
            avg_velocity = np.mean([acc['transaction_velocity'] for acc in account_features])
            importance['transaction_velocity'] = min(avg_velocity * risk_score * 0.1, 1.0)
        
        # Network features importance
        network_features = features['network_features']
        importance['network_density'] = network_ows
        return (network_features['clustering_coefficient'] > 0.8 and 
                network_features['account_count'] >= 3)
    
    def _calculate_feature_importance(self, features: Dict[str, Any], 
                                    risk_score: float) -> Dict[str, float]:
        """Calculate feature importance scores."""
        importance = {}
        
        # Account features importance
        account_features = features['account_features']
        if account_features:
            avg_small_tx_ratio =       
        off_hours_ratio = 1 - np.mean([tx['is_business_hours'] for tx in transaction_features])
        weekend_ratio = np.mean([tx['is_weekend'] for tx in transaction_features])
        
        return off_hours_ratio > 0.7 or weekend_ratio > 0.5
    
    def _detect_circular_flow_pattern(self, features: Dict[str, Any]) -> bool:
        """Detect circular money flow patterns."""
        network_features = features['network_features']
        
        # High clustering coefficient suggests circular fl transaction_features = features['transaction_features']
        if not transaction_features:
            return False
        
        round_amount_ratio = np.mean([tx['is_round_amount'] for tx in transaction_features])
        return round_amount_ratio > 0.6
    
    def _detect_off_hours_pattern(self, features: Dict[str, Any]) -> bool:
        """Detect off-hours transaction patterns."""
        transaction_features = features['transaction_features']
        if not transaction_features:
            return False
 > 0.6 and
                cluster_features['cluster_density'] > 2.0)
    
    def _detect_rapid_fire_pattern(self, features: Dict[str, Any]) -> bool:
        """Detect rapid fire transaction patterns."""
        temporal_features = features['temporal_features']
        
        # More than 5 transactions per hour
        return temporal_features['transaction_frequency'] > 5.0
    
    def _detect_round_amount_pattern(self, features: Dict[str, Any]) -> bool:
        """Detect round amount patterns."""
       t'] <= 9999)
        
        return (below_ctr_ratio > 0.8 and amounts_near_threshold >= 3)
    
    def _detect_layering_pattern(self, features: Dict[str, Any]) -> bool:
        """Detect layering patterns."""
        network_features = features['network_features']
        cluster_features = features['cluster_features']
        
        # High network density with many accounts suggests layering
        return (network_features['account_count'] >= 5 and 
                network_features['network_density'] ction_features']
        if not transaction_features:
            return False
        
        # Check for multiple transactions just below CTR threshold
        below_ctr_count = sum(1 for tx in transaction_features if tx['is_below_ctr_threshold'])
        below_ctr_ratio = below_ctr_count / len(transaction_features)
        
        # Check for amounts clustering around 9000-9999
        amounts_near_threshold = sum(1 for tx in transaction_features 
                                   if 9000 <= tx['amoun