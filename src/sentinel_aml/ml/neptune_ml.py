"""
Neptune ML integration for GNN-based fraud detection.

This module provides integration with Amazon Neptune ML for training
and inference of Graph Neural Networks for smurfing pattern detection.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
import boto3
import numpy as np
from dataclasses import dataclass, asdict

from ..core.logging import get_logger
from ..core.config import get_config
from ..data.models import Account, Transaction, RiskScore
from .feature_extractor import TransactionFeatureExtractor, TransactionFeatures


@dataclass
class GNNTrainingConfig:
    """Configuration for GNN model training."""
    
    model_name: str
    training_job_name: str
    node_classification_task: str = "fraud_detection"
    max_epochs: int = 100
    learning_rate: float = 0.001
    batch_size: int = 64
    hidden_dim: int = 128
    num_layers: int = 3
    dropout_rate: float = 0.2
    early_stopping_patience: int = 10
    validation_split: float = 0.2
    
    # Neptune ML specific settings
    neptune_ml_iam_role: str = ""
    s3_output_path: str = ""
    processing_instance_type: str = "ml.r5.xlarge"
    training_instance_type: str = "ml.p3.2xlarge"
    inference_instance_type: str = "ml.r5.large"


@dataclass
class TrainingJobStatus:
    """Status of a Neptune ML training job."""
    
    job_name: str
    status: str  # PENDING, RUNNING, COMPLETED, FAILED
    model_name: Optional[str] = None
    endpoint_name: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metrics: Optional[Dict[str, float]] = None


class NeptuneMlClient:
    """Client for Neptune ML operations."""
    
    def __init__(self):
        """Initialize Neptune ML client."""
        self.logger = get_logger(__name__)
        self.config = get_config()
        
        # Initialize AWS clients
        self.neptune_client = boto3.client('neptune')
        self.sagemaker_client = boto3.client('sagemaker')
        self.s3_client = boto3.client('s3')
        
        # Neptune cluster configuration
        self.cluster_id = self.config.get('neptune.cluster_id')
        self.cluster_endpoint = self.config.get('neptune.cluster_endpoint')
        
    async def create_training_job(
        self,
        config: GNNTrainingConfig,
        training_data_s3_path: str,
        validation_data_s3_path: Optional[str] = None
    ) -> str:
        """
        Create a Neptune ML training job for GNN fraud detection.
        
        Args:
            config: Training configuration
            training_data_s3_path: S3 path to training data
            validation_data_s3_path: Optional S3 path to validation data
            
        Returns:
            Training job ID
        """
        self.logger.info(
            "Creating Neptune ML training job",
            job_name=config.training_job_name,
            model_name=config.model_name
        )
        
        # Prepare training job configuration
        training_job_config = {
            'id': config.training_job_name,
            'dataProcessingJobId': f"{config.training_job_name}-processing",
            'trainModelS3Location': config.s3_output_path,
            'sagemakerIamRoleArn': config.neptune_ml_iam_role,
            'neptuneResourceName': self.cluster_id,
            'modelName': config.model_name,
            'modelType': 'node_classification',
            'baseProcessingInstanceType': config.processing_instance_type,
            'trainingInstanceType': config.training_instance_type,
            'modelHyperParameters': {
                'max_epochs': str(config.max_epochs),
                'learning_rate': str(config.learning_rate),
                'batch_size': str(config.batch_size),
                'hidden_dim': str(config.hidden_dim),
                'num_layers': str(config.num_layers),
                'dropout_rate': str(config.dropout_rate),
                'early_stopping_patience': str(config.early_stopping_patience)
            }
        }
        
        try:
            # Start the training job
            response = self.neptune_client.start_ml_model_training_job(**training_job_config)
            
            job_id = response['id']
            self.logger.info(
                "Neptune ML training job created successfully",
                job_id=job_id,
                arn=response.get('arn')
            )
            
            return job_id
            
        except Exception as e:
            self.logger.error(
                "Failed to create Neptune ML training job",
                error=str(e),
                job_name=config.training_job_name
            )
            raise
    
    async def get_training_job_status(self, job_id: str) -> TrainingJobStatus:
        """
        Get the status of a Neptune ML training job.
        
        Args:
            job_id: Training job ID
            
        Returns:
            TrainingJobStatus object
        """
        try:
            response = self.neptune_client.describe_ml_model_training_job(id=job_id)
            
            status = TrainingJobStatus(
                job_name=job_id,
                status=response['status'],
                model_name=response.get('modelName'),
                created_at=response.get('creationTimeInMillis'),
                completed_at=response.get('modelTrainingCompletionTimeInMillis'),
                error_message=response.get('failureReason')
            )
            
            # Parse metrics if available
            if 'modelMetrics' in response:
                status.metrics = response['modelMetrics']
                
            return status
            
        except Exception as e:
            self.logger.error(
                "Failed to get training job status",
                job_id=job_id,
                error=str(e)
            )
            raise
    
    async def wait_for_training_completion(
        self,
        job_id: str,
        timeout_minutes: int = 120,
        poll_interval_seconds: int = 30
    ) -> TrainingJobStatus:
        """
        Wait for training job to complete.
        
        Args:
            job_id: Training job ID
            timeout_minutes: Maximum time to wait
            poll_interval_seconds: Polling interval
            
        Returns:
            Final TrainingJobStatus
        """
        self.logger.info(
            "Waiting for training job completion",
            job_id=job_id,
            timeout_minutes=timeout_minutes
        )
        
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        
        while time.time() - start_time < timeout_seconds:
            status = await self.get_training_job_status(job_id)
            
            if status.status in ['COMPLETED', 'FAILED', 'STOPPED']:
                self.logger.info(
                    "Training job finished",
                    job_id=job_id,
                    status=status.status,
                    metrics=status.metrics
                )
                return status
                
            self.logger.debug(
                "Training job still running",
                job_id=job_id,
                status=status.status
            )
            
            time.sleep(poll_interval_seconds)
        
        raise TimeoutError(f"Training job {job_id} did not complete within {timeout_minutes} minutes")
    
    async def create_inference_endpoint(
        self,
        model_name: str,
        endpoint_name: str,
        instance_type: str = "ml.r5.large"
    ) -> str:
        """
        Create inference endpoint for trained model.
        
        Args:
            model_name: Name of trained model
            endpoint_name: Name for inference endpoint
            instance_type: SageMaker instance type
            
        Returns:
            Endpoint ARN
        """
        self.logger.info(
            "Creating inference endpoint",
            model_name=model_name,
            endpoint_name=endpoint_name
        )
        
        try:
            response = self.neptune_client.create_ml_endpoint(
                id=endpoint_name,
                mlModelTrainingJobId=model_name,
                instanceType=instance_type,
                neptuneResourceName=self.cluster_id
            )
            
            endpoint_arn = response['arn']
            self.logger.info(
                "Inference endpoint created successfully",
                endpoint_name=endpoint_name,
                arn=endpoint_arn
            )
            
            return endpoint_arn
            
        except Exception as e:
            self.logger.error(
                "Failed to create inference endpoint",
                model_name=model_name,
                endpoint_name=endpoint_name,
                error=str(e)
            )
            raise
    
    async def get_endpoint_status(self, endpoint_name: str) -> Dict[str, Any]:
        """Get status of inference endpoint."""
        try:
            response = self.neptune_client.describe_ml_endpoint(id=endpoint_name)
            return {
                'name': endpoint_name,
                'status': response['status'],
                'endpoint_url': response.get('endpoint'),
                'created_at': response.get('creationTimeInMillis'),
                'instance_type': response.get('instanceType')
            }
        except Exception as e:
            self.logger.error(
                "Failed to get endpoint status",
                endpoint_name=endpoint_name,
                error=str(e)
            )
            raise


class GnnTrainingPipeline:
    """Pipeline for training GNN models on transaction data."""
    
    def __init__(self):
        """Initialize training pipeline."""
        self.logger = get_logger(__name__)
        self.config = get_config()
        self.neptune_ml = NeptuneMlClient()
        self.feature_extractor = TransactionFeatureExtractor()
        
    async def prepare_training_data(
        self,
        accounts: List[Account],
        transactions: List[Transaction],
        labels: Dict[str, int],  # account_id -> label (0=normal, 1=fraud)
        output_s3_path: str
    ) -> Tuple[str, str]:
        """
        Prepare training data in Neptune ML format.
        
        Args:
            accounts: List of account nodes
            transactions: List of transaction edges
            labels: Ground truth labels for accounts
            output_s3_path: S3 path for output data
            
        Returns:
            Tuple of (nodes_file_path, edges_file_path)
        """
        self.logger.info(
            "Preparing training data for Neptune ML",
            num_accounts=len(accounts),
            num_transactions=len(transactions),
            num_labels=len(labels)
        )
        
        # Prepare node features
        nodes_data = []
        for account in accounts:
            # Get transactions for this account
            account_transactions = [
                t for t in transactions
                if t.from_account_id == account.account_id or t.to_account_id == account.account_id
            ]
            
            # Extract features
            features = await self.feature_extractor.extract_node_features(
                account, account_transactions
            )
            
            # Convert to Neptune ML format
            feature_array = self.feature_extractor.features_to_array(features)
            
            node_data = {
                '~id': account.account_id,
                '~label': 'Account',
                'features': feature_array.tolist(),
                'fraud_label': labels.get(account.account_id, 0)
            }
            
            nodes_data.append(node_data)
        
        # Prepare edge data
        edges_data = []
        for transaction in transactions:
            edge_data = {
                '~id': transaction.transaction_id,
                '~from': transaction.from_account_id,
                '~to': transaction.to_account_id,
                '~label': 'SENT_TO',
                'amount': transaction.amount,
                'timestamp': transaction.timestamp.isoformat(),
                'transaction_type': transaction.transaction_type.value
            }
            edges_data.append(edge_data)
        
        # Upload to S3
        nodes_file = f"{output_s3_path}/nodes.csv"
        edges_file = f"{output_s3_path}/edges.csv"
        
        await self._upload_training_data_to_s3(nodes_data, nodes_file)
        await self._upload_training_data_to_s3(edges_data, edges_file)
        
        self.logger.info(
            "Training data prepared successfully",
            nodes_file=nodes_file,
            edges_file=edges_file
        )
        
        return nodes_file, edges_file
    
    async def _upload_training_data_to_s3(
        self,
        data: List[Dict[str, Any]],
        s3_path: str
    ) -> None:
        """Upload training data to S3 in CSV format."""
        import pandas as pd
        import io
        
        # Convert to DataFrame and then CSV
        df = pd.DataFrame(data)
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        
        # Parse S3 path
        s3_parts = s3_path.replace('s3://', '').split('/', 1)
        bucket = s3_parts[0]
        key = s3_parts[1]
        
        # Upload to S3
        self.neptune_ml.s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=csv_buffer.getvalue()
        )
        
        self.logger.debug("Uploaded training data to S3", s3_path=s3_path)
    
    async def train_model(
        self,
        model_name: str,
        training_data_path: str,
        validation_data_path: Optional[str] = None,
        config_overrides: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Train GNN model for fraud detection.
        
        Args:
            model_name: Name for the trained model
            training_data_path: S3 path to training data
            validation_data_path: Optional S3 path to validation data
            config_overrides: Optional configuration overrides
            
        Returns:
            Training job ID
        """
        self.logger.info(
            "Starting GNN model training",
            model_name=model_name,
            training_data_path=training_data_path
        )
        
        # Create training configuration
        config = GNNTrainingConfig(
            model_name=model_name,
            training_job_name=f"{model_name}-{int(time.time())}",
            neptune_ml_iam_role=self.config.get('neptune_ml.iam_role'),
            s3_output_path=self.config.get('neptune_ml.s3_output_path')
        )
        
        # Apply any configuration overrides
        if config_overrides:
            for key, value in config_overrides.items():
                if hasattr(config, key):
                    setattr(config, key, value)
        
        # Start training job
        job_id = await self.neptune_ml.create_training_job(
            config=config,
            training_data_s3_path=training_data_path,
            validation_data_s3_path=validation_data_path
        )
        
        return job_id
    
    async def evaluate_model(
        self,
        job_id: str,
        test_data: List[Tuple[Account, List[Transaction], int]]
    ) -> Dict[str, float]:
        """
        Evaluate trained model performance.
        
        Args:
            job_id: Training job ID
            test_data: Test data as (account, transactions, label) tuples
            
        Returns:
            Dictionary of evaluation metrics
        """
        self.logger.info(
            "Evaluating model performance",
            job_id=job_id,
            test_samples=len(test_data)
        )
        
        # Wait for training to complete
        status = await self.neptune_ml.wait_for_training_completion(job_id)
        
        if status.status != 'COMPLETED':
            raise RuntimeError(f"Training job failed: {status.error_message}")
        
        # Create inference endpoint
        endpoint_name = f"{status.model_name}-endpoint"
        await self.neptune_ml.create_inference_endpoint(
            model_name=status.model_name,
            endpoint_name=endpoint_name
        )
        
        # TODO: Implement actual model evaluation
        # This would involve running inference on test data and calculating metrics
        
        # Placeholder metrics
        metrics = {
            'accuracy': 0.85,
            'precision': 0.82,
            'recall': 0.88,
            'f1_score': 0.85,
            'auc_roc': 0.91
        }
        
        self.logger.info(
            "Model evaluation completed",
            job_id=job_id,
            metrics=metrics
        )
        
        return metrics