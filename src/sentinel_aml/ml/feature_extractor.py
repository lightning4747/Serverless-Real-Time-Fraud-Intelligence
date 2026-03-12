"""
Feature extraction for transaction graph analysis.

This module extracts features from transaction patterns for GNN-based
fraud detection, focusing on smurfing pattern identification.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from dataclasses import dataclass

from ..core.logging import get_logger
from ..data.models import Account, Transaction


@dataclass
class TransactionFeatures:
    """Features extracted from transaction patterns."""
    
    # Node features (account-level)
    account_age_days: float
    transaction_count_7d: int
    transaction_count_30d: int
    avg_transaction_amount: float
    total_volume_7d: float
    total_volume_30d: float
    unique_counterparties_7d: int
    unique_counterparties_30d: int
    
    # Temporal features
    transactions_below_threshold: int  # Below $10k (smurfing indicator)
    rapid_sequential_count: int  # Transactions within 1 hour
    weekend_transaction_ratio: float
    off_hours_transaction_ratio: float
    
    # Network features
    clustering_coefficient: float
    betweenness_centrality: float
    degree_centrality: float
    
    # Risk indicators
    circular_flow_score: float
    velocity_score: float  # Transaction frequency acceleration
    amount_pattern_score: float  # Structured amount patterns


class TransactionFeatureExtractor:
    """Extracts features from transaction graphs for GNN training."""
    
    def __init__(self, smurfing_threshold: float = 10000.0):
        """
        Initialize feature extractor.
        
        Args:
            smurfing_threshold: Amount threshold for smurfing detection (default $10k)
        """
        self.logger = get_logger(__name__)
        self.smurfing_threshold = smurfing_threshold
        
    async def extract_node_features(
        self,
        account: Account,
        transactions: List[Transaction],
        lookback_days: int = 30
    ) -> TransactionFeatures:
        """
        Extract features for a single account node.
        
        Args:
            account: Account to extract features for
            transactions: All transactions involving this account
            lookback_days: Days to look back for feature calculation
            
        Returns:
            TransactionFeatures object with extracted features
        """
        self.logger.info(
            "Extracting features for account",
            account_id=account.account_id,
            transaction_count=len(transactions)
        )
        
        # Filter transactions by time window
        cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)
        recent_transactions = [
            t for t in transactions 
            if t.timestamp >= cutoff_date
        ]
        
        # Calculate temporal features
        transactions_7d = [
            t for t in recent_transactions
            if t.timestamp >= datetime.utcnow() - timedelta(days=7)
        ]
        
        # Basic volume and count features
        account_age = (datetime.utcnow() - account.creation_date).days
        total_volume_7d = sum(t.amount for t in transactions_7d)
        total_volume_30d = sum(t.amount for t in recent_transactions)
        avg_amount = np.mean([t.amount for t in recent_transactions]) if recent_transactions else 0.0
        
        # Smurfing indicators
        below_threshold = len([
            t for t in recent_transactions 
            if t.amount < self.smurfing_threshold
        ])
        
        # Rapid sequential transactions (within 1 hour)
        rapid_sequential = self._count_rapid_sequential(recent_transactions)
        
        # Temporal pattern analysis
        weekend_ratio = self._calculate_weekend_ratio(recent_transactions)
        off_hours_ratio = self._calculate_off_hours_ratio(recent_transactions)
        
        # Counterparty analysis
        counterparties_7d = len(set(
            t.to_account_id if t.from_account_id == account.account_id 
            else t.from_account_id
            for t in transactions_7d
        ))
        
        counterparties_30d = len(set(
            t.to_account_id if t.from_account_id == account.account_id 
            else t.from_account_id
            for t in recent_transactions
        ))
        
        # Network features (placeholder - would be calculated from graph structure)
        clustering_coeff = 0.0  # Would calculate from actual graph
        betweenness_cent = 0.0  # Would calculate from actual graph  
        degree_cent = len(recent_transactions) / max(lookback_days, 1)
        
        # Risk pattern scores
        circular_score = self._calculate_circular_flow_score(recent_transactions, account.account_id)
        velocity_score = self._calculate_velocity_score(recent_transactions)
        pattern_score = self._calculate_amount_pattern_score(recent_transactions)
        
        return TransactionFeatures(
            account_age_days=float(account_age),
            transaction_count_7d=len(transactions_7d),
            transaction_count_30d=len(recent_transactions),
            avg_transaction_amount=avg_amount,
            total_volume_7d=total_volume_7d,
            total_volume_30d=total_volume_30d,
            unique_counterparties_7d=counterparties_7d,
            unique_counterparties_30d=counterparties_30d,
            transactions_below_threshold=below_threshold,
            rapid_sequential_count=rapid_sequential,
            weekend_transaction_ratio=weekend_ratio,
            off_hours_transaction_ratio=off_hours_ratio,
            clustering_coefficient=clustering_coeff,
            betweenness_centrality=betweenness_cent,
            degree_centrality=degree_cent,
            circular_flow_score=circular_score,
            velocity_score=velocity_score,
            amount_pattern_score=pattern_score
        )
    
    def _count_rapid_sequential(self, transactions: List[Transaction]) -> int:
        """Count transactions occurring within 1 hour of each other."""
        if len(transactions) < 2:
            return 0
            
        # Sort by timestamp
        sorted_txns = sorted(transactions, key=lambda t: t.timestamp)
        rapid_count = 0
        
        for i in range(1, len(sorted_txns)):
            time_diff = sorted_txns[i].timestamp - sorted_txns[i-1].timestamp
            if time_diff <= timedelta(hours=1):
                rapid_count += 1
                
        return rapid_count
    
    def _calculate_weekend_ratio(self, transactions: List[Transaction]) -> float:
        """Calculate ratio of weekend transactions."""
        if not transactions:
            return 0.0
            
        weekend_count = sum(
            1 for t in transactions 
            if t.timestamp.weekday() >= 5  # Saturday=5, Sunday=6
        )
        
        return weekend_count / len(transactions)
    
    def _calculate_off_hours_ratio(self, transactions: List[Transaction]) -> float:
        """Calculate ratio of off-hours transactions (outside 9 AM - 5 PM)."""
        if not transactions:
            return 0.0
            
        off_hours_count = sum(
            1 for t in transactions
            if t.timestamp.hour < 9 or t.timestamp.hour >= 17
        )
        
        return off_hours_count / len(transactions)
    
    def _calculate_circular_flow_score(
        self, 
        transactions: List[Transaction], 
        account_id: str
    ) -> float:
        """
        Calculate circular flow score - money that flows out and back in.
        
        This is a simplified heuristic for circular money flows.
        """
        if len(transactions) < 2:
            return 0.0
            
        # Group by counterparty
        counterparty_flows = {}
        
        for txn in transactions:
            if txn.from_account_id == account_id:
                # Outgoing transaction
                counterparty = txn.to_account_id
                if counterparty not in counterparty_flows:
                    counterparty_flows[counterparty] = {"out": 0, "in": 0}
                counterparty_flows[counterparty]["out"] += txn.amount
            else:
                # Incoming transaction
                counterparty = txn.from_account_id
                if counterparty not in counterparty_flows:
                    counterparty_flows[counterparty] = {"out": 0, "in": 0}
                counterparty_flows[counterparty]["in"] += txn.amount
        
        # Calculate circular flow score
        circular_score = 0.0
        for flows in counterparty_flows.values():
            if flows["out"] > 0 and flows["in"] > 0:
                # Both directions exist - potential circular flow
                min_flow = min(flows["out"], flows["in"])
                circular_score += min_flow
                
        # Normalize by total transaction volume
        total_volume = sum(t.amount for t in transactions)
        return circular_score / max(total_volume, 1.0)
    
    def _calculate_velocity_score(self, transactions: List[Transaction]) -> float:
        """Calculate transaction velocity acceleration score."""
        if len(transactions) < 4:
            return 0.0
            
        # Sort by timestamp
        sorted_txns = sorted(transactions, key=lambda t: t.timestamp)
        
        # Calculate transaction frequency in recent vs older periods
        mid_point = len(sorted_txns) // 2
        older_txns = sorted_txns[:mid_point]
        recent_txns = sorted_txns[mid_point:]
        
        if not older_txns or not recent_txns:
            return 0.0
            
        # Calculate time spans
        older_span = (older_txns[-1].timestamp - older_txns[0].timestamp).total_seconds()
        recent_span = (recent_txns[-1].timestamp - recent_txns[0].timestamp).total_seconds()
        
        if older_span <= 0 or recent_span <= 0:
            return 0.0
            
        # Calculate frequencies (transactions per hour)
        older_freq = len(older_txns) / (older_span / 3600)
        recent_freq = len(recent_txns) / (recent_span / 3600)
        
        # Velocity score is the acceleration ratio
        return recent_freq / max(older_freq, 0.001)
    
    def _calculate_amount_pattern_score(self, transactions: List[Transaction]) -> float:
        """Calculate structured amount pattern score."""
        if len(transactions) < 3:
            return 0.0
            
        amounts = [t.amount for t in transactions]
        
        # Check for repeated amounts (structured transactions)
        amount_counts = {}
        for amount in amounts:
            # Round to nearest dollar to catch similar amounts
            rounded = round(amount)
            amount_counts[rounded] = amount_counts.get(rounded, 0) + 1
        
        # Calculate pattern score based on repetition
        max_repetition = max(amount_counts.values())
        pattern_score = max_repetition / len(transactions)
        
        # Bonus for amounts just below common thresholds
        threshold_bonus = 0.0
        common_thresholds = [10000, 5000, 3000]  # Common reporting thresholds
        
        for amount in amounts:
            for threshold in common_thresholds:
                if threshold * 0.8 <= amount < threshold:  # Within 20% below threshold
                    threshold_bonus += 0.1
                    
        return min(pattern_score + threshold_bonus, 1.0)
    
    def features_to_array(self, features: TransactionFeatures) -> np.ndarray:
        """Convert TransactionFeatures to numpy array for ML models."""
        return np.array([
            features.account_age_days,
            features.transaction_count_7d,
            features.transaction_count_30d,
            features.avg_transaction_amount,
            features.total_volume_7d,
            features.total_volume_30d,
            features.unique_counterparties_7d,
            features.unique_counterparties_30d,
            features.transactions_below_threshold,
            features.rapid_sequential_count,
            features.weekend_transaction_ratio,
            features.off_hours_transaction_ratio,
            features.clustering_coefficient,
            features.betweenness_centrality,
            features.degree_centrality,
            features.circular_flow_score,
            features.velocity_score,
            features.amount_pattern_score
        ], dtype=np.float32)
    
    @property
    def feature_names(self) -> List[str]:
        """Get list of feature names in order."""
        return [
            "account_age_days",
            "transaction_count_7d", 
            "transaction_count_30d",
            "avg_transaction_amount",
            "total_volume_7d",
            "total_volume_30d",
            "unique_counterparties_7d",
            "unique_counterparties_30d",
            "transactions_below_threshold",
            "rapid_sequential_count",
            "weekend_transaction_ratio",
            "off_hours_transaction_ratio",
            "clustering_coefficient",
            "betweenness_centrality",
            "degree_centrality",
            "circular_flow_score",
            "velocity_score",
            "amount_pattern_score"
        ]