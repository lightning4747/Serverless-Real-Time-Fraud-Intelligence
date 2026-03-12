"""
GNN Model Training Pipeline for Sentinel-AML
Implements Neptune ML integration for graph neural networks with smurfing pattern detection.
"""

import json
import logging
import boto3
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from gremlin_python.driver import client
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T, P, Order

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class GNNTrainingConfig:
    """Configuration for GNN model training."""
    neptune_endpoint: str
    neptune_port: int = 8182
    model_name: str = "sentinel-aml-gnn"
    training_job_name: str = "sentinel-aml-training"
    node_classification_task: str = "account_risk_classification"
    edge_classification_task: str = "transaction_risk_classification"
    max_epochs: int = 100
    learning_rate: float = 0.001
    batch_size: int = 32
    validation_split: float = 0.2
    smurfing_threshold: float = 0.7
    feature_dimensions: int = 64

class NeptuneMLTrainingPipeline:
    """Neptune ML training pipeline for GNN-based fraud detection."""
    
    def __init__(self, config: GNNTrainingConfig):
        self.config = config
        self.neptune_client = boto3.client('neptune')
        self.sagemaker_client = boto3.client('sagemaker')
        self.s3_client = boto3.client('s3')
        
        # Initialize Gremlin connection
        self.connection = DriverRemoteConnection(
            f'wss://{config.neptune_endpoint}:{config.neptune_port}/gremlin',
            'g'
        )
        self.g = traversal().withRemote(self.connection)
        
    def extract_graph_features(self) -> Dict[str, Any]:
        """Extract features from Neptune graph for GNN training."""
        logger.info("Extracting graph features for GNN training")
        
        try:
            # Extract account features
            account_features = self._extract_account_features()
            
            # Extract transaction features
            transaction_features = self._extract_transaction_features()
            
            # Extract graph topology
            graph_topology = self._extract_graph_topology()
            
            # Create feature matrix
            feature_matrix = self._create_feature_matrix(
                account_features, 
                transaction_features
            )
            
            return {
                'account_features': account_features,
                'transaction_features': transaction_features,
                'graph_topology': graph_topology,
                'feature_matrix': feature_matrix,
                'extraction_timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Feature extraction failed: {str(e)}")
            raise
    
    def _extract_account_features(self) -> List[Dict[str, Any]]:
        """Extract account-level features for GNN training."""
        logger.info("Extracting account features")
        
        # Query account nodes with aggregated transaction statistics
        accounts = (self.g.V()
                   .hasLabel('Account')
                   .project('account_id', 'customer_name', 'account_type', 
                           'creation_date', 'transaction_count', 'total_amount',
                           'avg_amount', 'unique_counterparties', 'risk_indicators')
                   .by('account_id')
                   .by('customer_name')
                   .by('account_type')
                   .by('creation_date')
                   .by(__.outE('SENT_TO').count())
                   .by(__.outE('SENT_TO').values('amount').sum())
                   .by(__.outE('SENT_TO').values('amount').mean())
                   .by(__.outE('SENT_TO').inV().dedup().count())
                   .by(__.outE('SENT_TO').where(__.values('amount').is_(P.lt(10000)))
                       .count())
                   .toList())
        
        # Process and normalize features
        processed_accounts = []
        for account in accounts:
            # Calculate risk indicators
            small_tx_ratio = (account['risk_indicators'] / 
                            max(account['transaction_count'], 1))
            
            # Velocity features (transactions per day since creation)
            days_active = max((datetime.utcnow() - 
                             datetime.fromisoformat(account['creation_date'])).days, 1)
            tx_velocity = account['transaction_count'] / days_active
            
            processed_account = {
                'account_id': account['account_id'],
                'features': {
                    'transaction_count': account['transaction_count'],
                    'total_amount': float(account['total_amount'] or 0),
                    'avg_amount': float(account['avg_amount'] or 0),
                    'unique_counterparties': account['unique_counterparties'],
                    'small_transaction_ratio': small_tx_ratio,
                    'transaction_velocity': tx_velocity,
                    'account_age_days': days_active,
                    'account_type_encoded': self._encode_account_type(account['account_type'])
                }
            }
            processed_accounts.append(processed_account)
        
        logger.info(f"Extracted features for {len(processed_accounts)} accounts")
        return processed_accounts
    
    def _extract_transaction_features(self) -> List[Dict[str, Any]]:
        """Extract transaction-level features for GNN training."""
        logger.info("Extracting transaction features")
        
        # Query transaction edges with temporal and amount patterns
        transactions = (self.g.E()
                       .hasLabel('SENT_TO')
                       .project('transaction_id', 'amount', 'timestamp', 
                               'transaction_type', 'currency', 'from_account', 
                               'to_account', 'time_features', 'amount_features')
                       .by('transaction_id')
                       .by('amount')
                       .by('timestamp')
                       .by('transaction_type')
                       .by('currency')
                       .by(__.outV().values('account_id'))
                       .by(__.inV().values('account_id'))
                       .by(__.values('timestamp'))  # Will process for time features
                       .by(__.values('amount'))     # Will process for amount features
                       .toList())
        
        # Process transaction features
        processed_transactions = []
        for tx in transactions:
            # Time-based features
            tx_time = datetime.fromisoformat(tx['timestamp'])
            hour_of_day = tx_time.hour
            day_of_week = tx_time.weekday()
            is_weekend = day_of_week >= 5
            is_business_hours = 9 <= hour_of_day <= 17
            
            # Amount-based features
            amount = float(tx['amount'])
            is_round_amount = amount % 1000 == 0
            is_below_ctr_threshold = amount < 10000
            amount_log = np.log10(max(amount, 1))
            
            processed_tx = {
                'transaction_id': tx['transaction_id'],
                'from_account': tx['from_account'],
                'to_account': tx['to_account'],
                'features': {
                    'amount': amount,
                    'amount_log': amount_log,
                    'hour_of_day': hour_of_day,
                    'day_of_week': day_of_week,
                    'is_weekend': int(is_weekend),
                    'is_business_hours': int(is_business_hours),
                    'is_round_amount': int(is_round_amount),
                    'is_below_ctr_threshold': int(is_below_ctr_threshold),
                    'transaction_type_encoded': self._encode_transaction_type(tx['transaction_type']),
                    'currency_encoded': self._encode_currency(tx['currency'])
                }
            }
            processed_transactions.append(processed_tx)
        
        logger.info(f"Extracted features for {len(processed_transactions)} transactions")
        return processed_transactions
    
    def _extract_graph_topology(self) -> Dict[str, Any]:
        """Extract graph topology for GNN structure."""
        logger.info("Extracting graph topology")
        
        # Get all edges for adjacency matrix
        edges = (self.g.E()
                .hasLabel('SENT_TO')
                .project('from', 'to', 'weight')
                .by(__.outV().values('account_id'))
                .by(__.inV().values('account_id'))
                .by('amount')
                .toList())
        
        # Get all nodes
        nodes = (self.g.V()
                .hasLabel('Account')
                .values('account_id')
                .toList())
        
        # Create node index mapping
        node_to_idx = {node: idx for idx, node in enumerate(nodes)}
        
        # Create edge list and adjacency info
        edge_list = []
        edge_weights = []
        
        for edge in edges:
            from_idx = node_to_idx.get(edge['from'])
            to_idx = node_to_idx.get(edge['to'])
            
            if from_idx is not None and to_idx is not None:
                edge_list.append([from_idx, to_idx])
                edge_weights.append(float(edge['weight']))
        
        return {
            'nodes': nodes,
            'node_count': len(nodes),
            'edge_list': edge_list,
            'edge_weights': edge_weights,
            'edge_count': len(edge_list),
            'node_to_idx': node_to_idx
        }
    
    def _create_feature_matrix(self, account_features: List[Dict], 
                              transaction_features: List[Dict]) -> np.ndarray:
        """Create normalized feature matrix for GNN input."""
        logger.info("Creating feature matrix")
        
        # Extract account feature vectors
        account_vectors = []
        for account in account_features:
            features = account['features']
            vector = [
                features['transaction_count'],
                features['total_amount'],
                features['avg_amount'],
                features['unique_counterparties'],
                features['small_transaction_ratio'],
                features['transaction_velocity'],
                features['account_age_days'],
                features['account_type_encoded']
            ]
            account_vectors.append(vector)
        
        # Convert to numpy array and normalize
        feature_matrix = np.array(account_vectors, dtype=np.float32)
        
        # Min-max normalization
        feature_min = np.min(feature_matrix, axis=0)
        feature_max = np.max(feature_matrix, axis=0)
        feature_range = feature_max - feature_min
        feature_range[feature_range == 0] = 1  # Avoid division by zero
        
        normalized_matrix = (feature_matrix - feature_min) / feature_range
        
        logger.info(f"Created feature matrix: {normalized_matrix.shape}")
        return normalized_matrix
    
    def create_training_labels(self) -> Dict[str, List[float]]:
        """Create training labels for supervised learning."""
        logger.info("Creating training labels for smurfing detection")
        
        # Identify potential smurfing patterns
        smurfing_accounts = self._identify_smurfing_patterns()
        
        # Get all accounts
        all_accounts = (self.g.V()
                       .hasLabel('Account')
                       .values('account_id')
                       .toList())
        
        # Create binary labels (1 = suspicious, 0 = normal)
        labels = []
        for account_id in all_accounts:
            is_suspicious = account_id in smurfing_accounts
            labels.append(1.0 if is_suspicious else 0.0)
        
        return {
            'account_labels': labels,
            'suspicious_accounts': list(smurfing_accounts),
            'total_accounts': len(all_accounts),
            'suspicious_count': len(smurfing_accounts)
        }
    
    def _identify_smurfing_patterns(self) -> set:
        """Identify accounts with potential smurfing patterns."""
        logger.info("Identifying smurfing patterns")
        
        suspicious_accounts = set()
        
        # Pattern 1: Multiple transactions just below CTR threshold
        ctr_pattern_accounts = (self.g.V()
                               .hasLabel('Account')
                               .where(__.outE('SENT_TO')
                                     .has('amount', P.between(9000, 9999))
                                     .count().is_(P.gte(5)))
                               .values('account_id')
                               .toList())
        suspicious_accounts.update(ctr_pattern_accounts)
        
        # Pattern 2: Rapid sequential transactions to different accounts
        rapid_pattern_accounts = (self.g.V()
                                 .hasLabel('Account')
                                 .where(__.outE('SENT_TO')
                                       .order().by('timestamp')
                                       .limit(10)
                                       .inV()
                                       .dedup()
                                       .count().is_(P.gte(8)))
                                 .values('account_id')
                                 .toList())
        suspicious_accounts.update(rapid_pattern_accounts)
        
        # Pattern 3: Circular money flows
        circular_pattern_accounts = (self.g.V()
                                    .hasLabel('Account')
                                    .where(__.repeat(__.outE('SENT_TO').inV())
                                          .times(3)
                                          .simplePath()
                                          .where(__.path().count(local).is_(P.gte(4))))
                                    .values('account_id')
                                    .toList())
        suspicious_accounts.update(circular_pattern_accounts)
        
        logger.info(f"Identified {len(suspicious_accounts)} suspicious accounts")
        return suspicious_accounts
    
    def start_neptune_ml_training(self, features: Dict[str, Any], 
                                 labels: Dict[str, List[float]]) -> str:
        """Start Neptune ML training job."""
        logger.info("Starting Neptune ML training job")
        
        try:
            # Prepare training data
            training_data = self._prepare_training_data(features, labels)
            
            # Upload training data to S3
            s3_path = self._upload_training_data(training_data)
            
            # Create Neptune ML training job
            training_job_config = {
                'id': self.config.training_job_name,
                'dataProcessingJobId': f"{self.config.training_job_name}-processing",
                'trainModelS3Location': s3_path,
                'sagemakerIamRoleArn': self._get_sagemaker_role_arn(),
                'neptuneIamRoleArn': self._get_neptune_role_arn(),
                'baseProcessingInstanceType': 'ml.r5.xlarge',
                'trainingInstanceType': 'ml.p3.2xlarge',
                'maxHPONumberOfTrainingJobs': 10,
                'maxHPOParallelTrainingJobs': 2,
                'subnets': self._get_vpc_subnets(),
                'securityGroupIds': self._get_security_groups(),
                'volumeEncryptionKMSKey': self._get_kms_key(),
                's3OutputEncryptionKMSKey': self._get_kms_key(),
                'enableManagedSpotTraining': True,
                'customModelTrainingParameters': {
                    'sourceS3DirectoryPath': s3_path,
                    'trainingEntryPointScript': 'gnn_training_script.py',
                    'modelTransformParameters': {
                        'node_classification_task': self.config.node_classification_task,
                        'edge_classification_task': self.config.edge_classification_task
                    }
                }
            }
            
            # Start the training job
            response = self.neptune_client.start_ml_model_training_job(**training_job_config)
            
            training_job_id = response['id']
            logger.info(f"Started Neptune ML training job: {training_job_id}")
            
            return training_job_id
            
        except Exception as e:
            logger.error(f"Failed to start Neptune ML training: {str(e)}")
            raise
    
    def monitor_training_progress(self, training_job_id: str) -> Dict[str, Any]:
        """Monitor Neptune ML training job progress."""
        logger.info(f"Monitoring training job: {training_job_id}")
        
        try:
            response = self.neptune_client.get_ml_model_training_job(id=training_job_id)
            
            status = response['status']
            progress = response.get('modelTrainingJobProgress', {})
            
            return {
                'job_id': training_job_id,
                'status': status,
                'progress': progress,
                'creation_time': response.get('creationTimeInMillis'),
                'processing_time': response.get('processingTimeInMillis'),
                'model_artifacts': response.get('modelArtifacts', {})
            }
            
        except Exception as e:
            logger.error(f"Failed to get training job status: {str(e)}")
            raise
    
    def _prepare_training_data(self, features: Dict[str, Any], 
                              labels: Dict[str, List[float]]) -> Dict[str, Any]:
        """Prepare training data in Neptune ML format."""
        return {
            'graph_features': features,
            'labels': labels,
            'config': {
                'model_type': 'gnn',
                'task_type': 'node_classification',
                'target_column': 'is_suspicious',
                'feature_columns': list(features['account_features'][0]['features'].keys()),
                'graph_structure': features['graph_topology']
            }
        }
    
    def _upload_training_data(self, training_data: Dict[str, Any]) -> str:
        """Upload training data to S3."""
        bucket_name = f"sentinel-aml-training-{datetime.utcnow().strftime('%Y%m%d')}"
        key = f"training-data/{self.config.training_job_name}/data.json"
        
        # Create bucket if it doesn't exist
        try:
            self.s3_client.create_bucket(Bucket=bucket_name)
        except self.s3_client.exceptions.BucketAlreadyExists:
            pass
        
        # Upload training data
        self.s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(training_data, default=str),
            ContentType='application/json'
        )
        
        return f"s3://{bucket_name}/{key}"
    
    def _encode_account_type(self, account_type: str) -> int:
        """Encode account type as integer."""
        type_mapping = {
            'checking': 0,
            'savings': 1,
            'business': 2,
            'investment': 3,
            'other': 4
        }
        return type_mapping.get(account_type.lower(), 4)
    
    def _encode_transaction_type(self, transaction_type: str) -> int:
        """Encode transaction type as integer."""
        type_mapping = {
            'wire': 0,
            'ach': 1,
            'check': 2,
            'cash': 3,
            'card': 4,
            'other': 5
        }
        return type_mapping.get(transaction_type.lower(), 5)
    
    def _encode_currency(self, currency: str) -> int:
        """Encode currency as integer."""
        currency_mapping = {
            'usd': 0,
            'eur': 1,
            'gbp': 2,
            'jpy': 3,
            'other': 4
        }
        return currency_mapping.get(currency.lower(), 4)
    
    def _get_sagemaker_role_arn(self) -> str:
        """Get SageMaker IAM role ARN."""
        # This would be configured based on your AWS setup
        return "arn:aws:iam::123456789012:role/SentinelAMLSageMakerRole"
    
    def _get_neptune_role_arn(self) -> str:
        """Get Neptune IAM role ARN."""
        return "arn:aws:iam::123456789012:role/SentinelAMLNeptuneRole"
    
    def _get_vpc_subnets(self) -> List[str]:
        """Get VPC subnet IDs."""
        return ["subnet-12345678", "subnet-87654321"]
    
    def _get_security_groups(self) -> List[str]:
        """Get security group IDs."""
        return ["sg-12345678"]
    
    def _get_kms_key(self) -> str:
        """Get KMS key ARN for encryption."""
        return "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"
    
    def close(self):
        """Close Neptune connection."""
        if hasattr(self, 'connection'):
            self.connection.close()

def main():
    """Main training pipeline execution."""
    config = GNNTrainingConfig(
        neptune_endpoint="sentinel-aml-neptune.cluster-xyz.us-east-1.neptune.amazonaws.com",
        model_name="sentinel-aml-gnn-v1",
        training_job_name=f"sentinel-aml-training-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    )
    
    pipeline = NeptuneMLTrainingPipeline(config)
    
    try:
        # Extract features
        logger.info("Starting GNN training pipeline")
        features = pipeline.extract_graph_features()
        
        # Create labels
        labels = pipeline.create_training_labels()
        
        # Start training
        training_job_id = pipeline.start_neptune_ml_training(features, labels)
        
        # Monitor progress
        while True:
            status = pipeline.monitor_training_progress(training_job_id)
            logger.info(f"Training status: {status['status']}")
            
            if status['status'] in ['Completed', 'Failed', 'Stopped']:
                break
                
            time.sleep(60)  # Check every minute
        
        logger.info("GNN training pipeline completed")
        
    except Exception as e:
        logger.error(f"Training pipeline failed: {str(e)}")
        raise
    finally:
        pipeline.close()

if __name__ == "__main__":
    main()

# Additional utility functions for GNN training

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

class SmurfingPatternDetector:
    """Specialized detector for smurfing patterns in transaction graphs."""
    
    def __init__(self, g):
        self.g = g
    
    def detect_structured_transactions(self, time_window_hours: int = 24) -> List[Dict[str, Any]]:
        """Detect structured transactions (smurfing) within time windows."""
        logger.info(f"Detecting structured transactions in {time_window_hours}h windows")
        
        # Find accounts with multiple transactions just below reporting thresholds
        structured_patterns = []
        
        # Query for accounts with suspicious transaction patterns
        suspicious_accounts = (self.g.V()
                              .hasLabel('Account')
                              .where(__.outE('SENT_TO')
                                    .has('amount', P.between(9000, 9999))
                                    .count().is_(P.gte(3)))
                              .project('account_id', 'transactions', 'total_amount', 'pattern_score')
                              .by('account_id')
                              .by(__.outE('SENT_TO')
                                  .has('amount', P.between(9000, 9999))
                                  .valueMap())
                              .by(__.outE('SENT_TO')
                                  .has('amount', P.between(9000, 9999))
                                  .values('amount').sum())
                              .by(__.outE('SENT_TO')
                                  .has('amount', P.between(9000, 9999))
                                  .count())
                              .toList())
        
        for account_data in suspicious_accounts:
            # Calculate pattern indicators
            transactions = account_data['transactions']
            pattern_score = float(account_data['pattern_score'])
            total_amount = float(account_data['total_amount'])
            
            # Analyze temporal clustering
            temporal_score = self._analyze_temporal_clustering(transactions)
            
            # Analyze amount clustering
            amount_score = self._analyze_amount_clustering(transactions)
            
            # Calculate composite suspicion score
            composite_score = (pattern_score * 0.4 + 
                             temporal_score * 0.3 + 
                             amount_score * 0.3)
            
            pattern = {
                'account_id': account_data['account_id'],
                'pattern_type': 'structured_transactions',
                'transaction_count': int(pattern_score),
                'total_amount': total_amount,
                'temporal_score': temporal_score,
                'amount_score': amount_score,
                'composite_score': composite_score,
                'risk_level': self._classify_risk_level(composite_score),
                'transactions': transactions
            }
            
            structured_patterns.append(pattern)
        
        # Sort by composite score (highest risk first)
        structured_patterns.sort(key=lambda x: x['composite_score'], reverse=True)
        
        logger.info(f"Detected {len(structured_patterns)} structured transaction patterns")
        return structured_patterns
    
    def detect_layering_patterns(self) -> List[Dict[str, Any]]:
        """Detect layering patterns - complex chains of transactions."""
        logger.info("Detecting layering patterns")
        
        layering_patterns = []
        
        # Find transaction chains longer than 3 hops
        chains = (self.g.V()
                 .hasLabel('Account')
                 .repeat(__.outE('SENT_TO').inV().simplePath())
                 .times(4)
                 .path()
                 .by('account_id')
                 .toList())
        
        for chain in chains:
            # Analyze chain characteristics
            chain_length = len(chain)
            accounts_in_chain = list(chain)
            
            # Calculate chain metrics
            total_amount = self._calculate_chain_amount(accounts_in_chain)
            time_span = self._calculate_chain_timespan(accounts_in_chain)
            geographic_spread = self._calculate_geographic_spread(accounts_in_chain)
            
            # Calculate layering score
            layering_score = self._calculate_layering_score(
                chain_length, total_amount, time_span, geographic_spread
            )
            
            pattern = {
                'pattern_type': 'layering',
                'chain_length': chain_length,
                'accounts': accounts_in_chain,
                'total_amount': total_amount,
                'time_span_hours': time_span,
                'geographic_spread': geographic_spread,
                'layering_score': layering_score,
                'risk_level': self._classify_risk_level(layering_score)
            }
            
            layering_patterns.append(pattern)
        
        # Sort by layering score
        layering_patterns.sort(key=lambda x: x['layering_score'], reverse=True)
        
        logger.info(f"Detected {len(layering_patterns)} layering patterns")
        return layering_patterns
    
    def detect_integration_patterns(self) -> List[Dict[str, Any]]:
        """Detect integration patterns - money returning to legitimate economy."""
        logger.info("Detecting integration patterns")
        
        integration_patterns = []
        
        # Find accounts that receive from multiple sources and then make large legitimate transactions
        integration_accounts = (self.g.V()
                               .hasLabel('Account')
                               .where(__.inE('SENT_TO').count().is_(P.gte(5)))
                               .where(__.outE('SENT_TO')
                                     .has('transaction_type', 'wire')
                                     .has('amount', P.gte(50000))
                                     .count().is_(P.gte(1)))
                               .project('account_id', 'inbound_count', 'outbound_large', 'integration_score')
                               .by('account_id')
                               .by(__.inE('SENT_TO').count())
                               .by(__.outE('SENT_TO')
                                   .has('amount', P.gte(50000))
                                   .count())
                               .by(__.inE('SENT_TO').values('amount').sum())
                               .toList())
        
        for account_data in integration_accounts:
            inbound_count = int(account_data['inbound_count'])
            outbound_large = int(account_data['outbound_large'])
            total_inbound = float(account_data['integration_score'])
            
            # Calculate integration score
            integration_score = (inbound_count * 0.3 + 
                               outbound_large * 0.4 + 
                               min(total_inbound / 100000, 10) * 0.3)
            
            pattern = {
                'account_id': account_data['account_id'],
                'pattern_type': 'integration',
                'inbound_transaction_count': inbound_count,
                'large_outbound_count': outbound_large,
                'total_inbound_amount': total_inbound,
                'integration_score': integration_score,
                'risk_level': self._classify_risk_level(integration_score)
            }
            
            integration_patterns.append(pattern)
        
        # Sort by integration score
        integration_patterns.sort(key=lambda x: x['integration_score'], reverse=True)
        
        logger.info(f"Detected {len(integration_patterns)} integration patterns")
        return integration_patterns
    
    def _analyze_temporal_clustering(self, transactions: List[Dict]) -> float:
        """Analyze temporal clustering of transactions."""
        if len(transactions) < 2:
            return 0.0
        
        # Extract timestamps and calculate time differences
        timestamps = []
        for tx in transactions:
            if 'timestamp' in tx:
                timestamps.append(datetime.fromisoformat(tx['timestamp'][0]))
        
        timestamps.sort()
        
        # Calculate average time between transactions
        time_diffs = []
        for i in range(1, len(timestamps)):
            diff = (timestamps[i] - timestamps[i-1]).total_seconds() / 3600  # hours
            time_diffs.append(diff)
        
        if not time_diffs:
            return 0.0
        
        avg_time_diff = sum(time_diffs) / len(time_diffs)
        
        # Score based on how clustered the transactions are
        # Lower average time = higher clustering = higher suspicion
        if avg_time_diff < 1:  # Less than 1 hour apart on average
            return 1.0
        elif avg_time_diff < 6:  # Less than 6 hours apart
            return 0.8
        elif avg_time_diff < 24:  # Less than 24 hours apart
            return 0.6
        else:
            return 0.2
    
    def _analyze_amount_clustering(self, transactions: List[Dict]) -> float:
        """Analyze amount clustering of transactions."""
        if len(transactions) < 2:
            return 0.0
        
        amounts = []
        for tx in transactions:
            if 'amount' in tx:
                amounts.append(float(tx['amount'][0]))
        
        if not amounts:
            return 0.0
        
        # Calculate coefficient of variation
        mean_amount = sum(amounts) / len(amounts)
        variance = sum((x - mean_amount) ** 2 for x in amounts) / len(amounts)
        std_dev = variance ** 0.5
        
        if mean_amount == 0:
            return 0.0
        
        cv = std_dev / mean_amount
        
        # Lower coefficient of variation = more similar amounts = higher suspicion
        if cv < 0.1:  # Very similar amounts
            return 1.0
        elif cv < 0.3:
            return 0.7
        elif cv < 0.5:
            return 0.4
        else:
            return 0.1
    
    def _calculate_chain_amount(self, accounts: List[str]) -> float:
        """Calculate total amount flowing through a transaction chain."""
        # This would query the actual transaction amounts in the chain
        # Simplified implementation
        return 0.0
    
    def _calculate_chain_timespan(self, accounts: List[str]) -> float:
        """Calculate time span of a transaction chain in hours."""
        # This would query the actual transaction timestamps
        # Simplified implementation
        return 0.0
    
    def _calculate_geographic_spread(self, accounts: List[str]) -> int:
        """Calculate geographic spread of accounts in chain."""
        # This would analyze account locations
        # Simplified implementation
        return 1
    
    def _calculate_layering_score(self, chain_length: int, total_amount: float, 
                                 time_span: float, geographic_spread: int) -> float:
        """Calculate layering suspicion score."""
        # Weighted scoring based on layering characteristics
        length_score = min(chain_length / 10, 1.0) * 0.4
        amount_score = min(total_amount / 1000000, 1.0) * 0.3
        time_score = (1.0 / max(time_span, 1)) * 0.2
        geo_score = min(geographic_spread / 5, 1.0) * 0.1
        
        return length_score + amount_score + time_score + geo_score
    
    def _classify_risk_level(self, score: float) -> str:
        """Classify risk level based on score."""
        if score >= 0.8:
            return 'HIGH'
        elif score >= 0.6:
            return 'MEDIUM'
        elif score >= 0.4:
            return 'LOW'
        else:
            return 'MINIMAL'

class GNNFeatureEngineer:
    """Advanced feature engineering for GNN models."""
    
    def __init__(self, g):
        self.g = g
    
    def create_graph_embeddings(self, embedding_dim: int = 64) -> Dict[str, np.ndarray]:
        """Create graph embeddings using random walk and skip-gram."""
        logger.info(f"Creating graph embeddings with dimension {embedding_dim}")
        
        # This would implement node2vec or similar graph embedding algorithm
        # Simplified implementation for now
        
        nodes = (self.g.V()
                .hasLabel('Account')
                .values('account_id')
                .toList())
        
        # Generate random embeddings as placeholder
        embeddings = {}
        for node in nodes:
            embeddings[node] = np.random.normal(0, 1, embedding_dim)
        
        logger.info(f"Created embeddings for {len(embeddings)} nodes")
        return embeddings
    
    def calculate_centrality_measures(self) -> Dict[str, Dict[str, float]]:
        """Calculate various centrality measures for nodes."""
        logger.info("Calculating centrality measures")
        
        centrality_measures = {}
        
        # Get all accounts
        accounts = (self.g.V()
                   .hasLabel('Account')
                   .values('account_id')
                   .toList())
        
        for account in accounts:
            # Degree centrality
            degree = (self.g.V()
                     .has('account_id', account)
                     .bothE('SENT_TO')
                     .count()
                     .next())
            
            # Betweenness centrality (simplified)
            # In a full implementation, this would use proper betweenness calculation
            betweenness = self._calculate_betweenness_centrality(account)
            
            # PageRank (simplified)
            pagerank = self._calculate_pagerank(account)
            
            centrality_measures[account] = {
                'degree_centrality': float(degree),
                'betweenness_centrality': betweenness,
                'pagerank': pagerank
            }
        
        logger.info(f"Calculated centrality measures for {len(centrality_measures)} accounts")
        return centrality_measures
    
    def _calculate_betweenness_centrality(self, account: str) -> float:
        """Calculate betweenness centrality for an account."""
        # Simplified implementation
        # In practice, this would use proper shortest path algorithms
        return 0.5
    
    def _calculate_pagerank(self, account: str) -> float:
        """Calculate PageRank score for an account."""
        # Simplified implementation
        # In practice, this would use iterative PageRank algorithm
        return 0.5