"""
Lambda function for real-time fraud scoring using GNN models.

This function analyzes transaction clusters using trained GNN models
to calculate fraud risk scores and flag suspicious activities.
"""

import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
import boto3
import numpy as np
from dataclasses import dataclass, asdict

from ..core.logging import get_logger, setup_lambda_logging
from ..core.config import get_config
from ..core.exceptions import ValidationError, ProcessingError
from ..data.models import Account, Transaction, RiskScore, Alert, AlertStatus
from ..data.neptune_client import NeptuneClient
from ..ml.feature_extractor import TransactionFeatureExtractor, TransactionFeatures


@dataclass
class FraudScoringRequest:
    """Request for fraud scoring analysis."""
    
    account_ids: List[str]
    transaction_cluster_id: Optional[str] = None
    lookback_days: int = 30
    include_feature_importance: bool = True


@dataclass
class FraudScoringResult:
    """Result of fraud scoring analysis."""
    
    account_id: str
    risk_score: float  # 0.0 to 1.0
    is_suspicious: bool  # True if score > 0.7
    confidence: float
    feature_importance: Dict[str, float]
    patterns_detected: List[str]
    timestamp: datetime
    model_version: str


@dataclass
class ClusterAnalysisResult:
    """Result of transaction cluster analysis."""
    
    cluster_id: str
    account_scores: List[FraudScoringResult]
    cluster_risk_score: float
    suspicious_patterns: List[str]
    total_volume: float
    transaction_count: int
    analysis_timestamp: datetime


class GnnFraudScorer:
    """GNN-based fraud scoring engine."""
    
    def __init__(self):
        """Initialize fraud scorer."""
        self.logger = get_logger(__name__)
        self.config = get_config()
        self.neptune_client = NeptuneClient()
        self.feature_extractor = TransactionFeatureExtractor()
        
        # Neptune ML configuration
        self.endpoint_name = self.config.get('neptune_ml.inference_endpoint')
        self.model_version = self.config.get('neptune_ml.model_version', 'v1.0')
        self.suspicious_threshold = self.config.get('fraud_detection.suspicious_threshold', 0.7)
        
        # Initialize SageMaker runtime for inference
        self.sagemaker_runtime = boto3.client('sagemaker-runtime')
        
    async def score_accounts(
        self,
        account_ids: List[str],
        lookback_days: int = 30,
        include_feature_importance: bool = True
    ) -> List[FraudScoringResult]:
        """
        Calculate fraud risk scores for multiple accounts.
        
        Args:
            account_ids: List of account IDs to score
            lookback_days: Days to look back for transaction analysis
            include_feature_importance: Whether to calculate feature importance
            
        Returns:
            List of FraudScoringResult objects
        """
        self.logger.info(
            "Starting fraud scoring analysis",
            account_count=len(account_ids),
            lookback_days=lookback_days
        )
        
        results = []
        
        for account_id in account_ids:
            try:
                result = await self._score_single_account(
                    account_id=account_id,
                    lookback_days=lookback_days,
                    include_feature_importance=include_feature_importance
                )
                results.append(result)
                
            except Exception as e:
                self.logger.error(
                    "Failed to score account",
                    account_id=account_id,
                    error=str(e)
                )
                # Create error result
                error_result = FraudScoringResult(
                    account_id=account_id,
                    risk_score=0.0,
                    is_suspicious=False,
                    confidence=0.0,
                    feature_importance={},
                    patterns_detected=[f"Error: {str(e)}"],
                    timestamp=datetime.utcnow(),
                    model_version=self.model_version
                )
                results.append(error_result)
        
        self.logger.info(
            "Fraud scoring analysis completed",
            total_accounts=len(account_ids),
            successful_scores=len([r for r in results if r.risk_score > 0]),
            suspicious_accounts=len([r for r in results if r.is_suspicious])
        )
        
        return results
    
    async def _score_single_account(
        self,
        account_id: str,
        lookback_days: int,
        include_feature_importance: bool
    ) -> FraudScoringResult:
        """Score a single account for fraud risk."""
        self.logger.debug("Scoring account", account_id=account_id)
        
        # Get account and transaction data
        account = await self.neptune_client.get_account(account_id)
        if not account:
            raise ValidationError(f"Account not found: {account_id}")
        
        # Get transactions for the account
        cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)
        transactions = await self.neptune_client.get_account_transactions(
            account_id=account_id,
            start_date=cutoff_date
        )
        
        # Extract features
        features = await self.feature_extractor.extract_node_features(
            account=account,
            transactions=transactions,
            lookback_days=lookback_days
        )
        
        # Get GNN prediction
        risk_score, confidence = await self._get_gnn_prediction(features)
        
        # Calculate feature importance if requested
        feature_importance = {}
        if include_feature_importance:
            feature_importance = await self._calculate_feature_importance(features)
        
        # Detect specific patterns
        patterns_detected = await self._detect_suspicious_patterns(
            account=account,
            transactions=transactions,
            features=features
        )
        
        # Determine if suspicious
        is_suspicious = risk_score > self.suspicious_threshold
        
        return FraudScoringResult(
            account_id=account_id,
            risk_score=risk_score,
            is_suspicious=is_suspicious,
            confidence=confidence,
            feature_importance=feature_importance,
            patterns_detected=patterns_detected,
            timestamp=datetime.utcnow(),
            model_version=self.model_version
        )
    
    async def _get_gnn_prediction(
        self,
        features: TransactionFeatures
    ) -> Tuple[float, float]:
        """
        Get GNN model prediction for fraud risk.
        
        Args:
            features: Extracted transaction features
            
        Returns:
            Tuple of (risk_score, confidence)
        """
        try:
            # Convert features to model input format
            feature_array = self.feature_extractor.features_to_array(features)
            
            # Prepare input for SageMaker endpoint
            input_data = {
                'instances': 