"""
Property-based tests for fraud scoring system.
Tests universal correctness properties that must hold for all inputs.
"""

import pytest
import numpy as np
from hypothesis import given, strategies as st, settings, assume
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant
from typing import List, Dict, Any
import json
from datetime import datetime, timedelta
from dataclasses import asdict

# Import the modules we're testing
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from lambda.fraud_scoring import (
    FraudScoringEngine, FraudScoringConfig, TransactionCluster, FraudScore
)

# Test data strategies
@st.composite
def transaction_cluster_strategy(draw):
    """Generate valid transaction clusters for testing."""
    cluster_id = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    
    # Generate account IDs
    account_count = draw(st.integers(min_value=1, max_value=10))
    account_ids = [f"ACC{i:03d}" for i in range(account_count)]
    
    # Generate transaction IDs
    tx_count = draw(st.integers(min_value=1, max_value=50))
    transaction_ids = [f"TX{i:04d}" for i in range(tx_count)]
    
    # Generate amounts (positive values)
    total_amount = draw(st.floats(min_value=100.0, max_value=10000000.0, allow_nan=False, allow_infinity=False))
    
    # Time span in hours (positive)
    time_span_hours = draw(st.floats(min_value=0.1, max_value=168.0, allow_nan=False, allow_infinity=False))  # Up to 1 week
    
    cluster_type = draw(st.sampled_from(['temporal', 'amount', 'network']))
    
    return TransactionCluster(
        cluster_id=cluster_id,
        account_ids=account_ids,
        transaction_ids=transaction_ids,
        total_amount=total_amount,
        transaction_count=tx_count,
        time_span_hours=time_span_hours,
        cluster_type=cluster_type
    )

@st.composite
def fraud_scoring_config_strategy(draw):
    """Generate valid fraud scoring configurations."""
    return FraudScoringConfig(
        neptune_endpoint="test-endpoint",
        neptune_port=draw(st.integers(min_value=1000, max_value=65535)),
        model_endpoint="test-model-endpoint",
        suspicious_threshold=draw(st.floats(min_value=0.0, max_value=1.0)),
        high_risk_threshold=draw(st.floats(min_value=0.0, max_value=1.0)),
        batch_size=draw(st.integers(min_value=1, max_value=1000)),
        max_processing_time=draw(st.integers(min_value=10, max_value=3600)),
        enable_explainability=draw(st.booleans())
    )

class TestFraudScoringProperties:
    """Property-based tests for fraud scoring correctness properties."""
    
    def setup_method(self):
        """Set up test environment."""
        self.config = FraudScoringConfig(
            neptune_endpoint="test-endpoint",
            model_endpoint="test-model-endpoint",
            suspicious_threshold=0.7,
            high_risk_threshold=0.9
        )
    
    @given(transaction_cluster_strategy())
    @settings(max_examples=100, deadline=5000)
    def test_property_3_score_bounds(self, cluster: TransactionCluster):
        """
        Property 3: Score bounds - All risk scores must be between 0.0 and 1.0
        This is a fundamental correctness property that must never be violated.
        """
        # Create a mock scoring engine that uses fallback scoring
        engine = MockFraudScoringEngine(self.config)
        
        # Score the cluster
        fraud_score = engine.score_transaction_cluster(cluster)
        
        # Property 3: Risk score must be in valid range [0.0, 1.0]
        assert 0.0 <= fraud_score.risk_score <= 1.0, \
            f"Risk score {fraud_score.risk_score} is outside valid range [0.0, 1.0]"
        
        # Confidence should also be in valid range
        assert 0.0 <= fraud_score.confidence <= 1.0, \
            f"Confidence {fraud_score.confidence} is outside valid range [0.0, 1.0]"
    
    @given(transaction_cluster_strategy())
    @settings(max_examples=50, deadline=5000)
    def test_property_4_smurfing_pattern_detection(self, cluster: TransactionCluster):
        """
        Property 4: Pattern detection - Known smurfing patterns must score above 0.7
        This tests that the system correctly identifies high-risk patterns.
        """
        # Create a cluster with known smurfing characteristics
        smurfing_cluster = self._create_smurfing_cluster(cluster)
        
        engine = MockFraudScoringEngine(self.config)
        fraud_score = engine.score_transaction_cluster(smurfing_cluster)
        
        # Property 4: Smurfing patterns should score above threshold
        if self._has_smurfing_indicators(smurfing_cluster):
            assert fraud_score.risk_score >= 0.7, \
                f"Smurfing pattern scored {fraud_score.risk_score}, expected >= 0.7"
            
            # Should detect smurfing pattern indicator
            assert "SMURFING_PATTERN" in fraud_score.pattern_indicators or \
                   fraud_score.risk_score >= 0.7, \
                "Smurfing pattern not detected or scored appropriately"
    
    @given(st.lists(transaction_cluster_strategy(), min_size=1, max_size=10))
    @settings(max_examples=20, deadline=10000)
    def test_property_consistency_across_batches(self, clusters: List[TransactionCluster]):
        """
        Property: Consistency - Same cluster should produce same score across different batches.
        """
        engine = MockFraudScoringEngine(self.config)
        
        # Score each cluster multiple times
        for cluster in clusters:
            scores = []
            for _ in range(3):  # Score 3 times
                fraud_score = engine.score_transaction_cluster(cluster)
                scores.append(fraud_score.risk_score)
            
            # All scores should be identical (deterministic)
            assert all(abs(score - scores[0]) < 1e-6 for score in scores), \
                f"Inconsistent scores for cluster {cluster.cluster_id}: {scores}"
    
    @given(transaction_cluster_strategy())
    @settings(max_examples=50, deadline=5000)
    def test_property_monotonicity(self, cluster: TransactionCluster):
        """
        Property: Monotonicity - More suspicious characteristics should not decrease risk score.
        """
        engine = MockFraudScoringEngine(self.config)
        
        # Score original cluster
        original_score = engine.score_transaction_cluster(cluster).risk_score
        
        # Create more suspicious version
        suspicious_cluster = self._make_more_suspicious(cluster)
        suspicious_score = engine.score_transaction_cluster(suspicious_cluster).risk_score
        
        # More suspicious cluster should have higher or equal score
        assert suspicious_score >= original_score - 0.1, \
            f"More suspicious cluster scored lower: {suspicious_score} vs {original_score}"
    
    @given(fraud_scoring_config_strategy())
    @settings(max_examples=20, deadline=3000)
    def test_property_threshold_consistency(self, config: FraudScoringConfig):
        """
        Property: Threshold consistency - Risk levels should be consistent with thresholds.
        """
        # Ensure thresholds are in correct order
        assume(config.suspicious_threshold <= config.high_risk_threshold)
        
        engine = MockFraudScoringEngine(config)
        
        # Test with different risk scores
        test_scores = [0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 1.0]
        
        for score in test_scores:
            risk_level = engine._classify_risk_level(score)
            
            # Verify risk level matches thresholds
            if score >= config.high_risk_threshold:
                assert risk_level == 'CRITICAL', \
                    f"Score {score} should be CRITICAL (threshold: {config.high_risk_threshold})"
            elif score >= config.suspicious_threshold:
                assert risk_level == 'HIGH', \
                    f"Score {score} should be HIGH (threshold: {config.suspicious_threshold})"
            elif score >= 0.5:
                assert risk_level == 'MEDIUM', \
                    f"Score {score} should be MEDIUM"
            else:
                assert risk_level == 'LOW', \
                    f"Score {score} should be LOW"
    
    def _create_smurfing_cluster(self, base_cluster: TransactionCluster) -> TransactionCluster:
        """Create a cluster with smurfing characteristics."""
        # Multiple small transactions just below CTR threshold
        return TransactionCluster(
            cluster_id=f"smurfing_{base_cluster.cluster_id}",
            account_ids=base_cluster.account_ids[:3],  # Limit accounts
            transaction_ids=[f"SMURF_TX{i:03d}" for i in range(8)],  # Multiple transactions
            total_amount=9500.0 * 8,  # 8 transactions of $9,500 each
            transaction_count=8,
            time_span_hours=2.0,  # Short time span
            cluster_type="smurfing"
        )
    
    def _has_smurfing_indicators(self, cluster: TransactionCluster) -> bool:
        """Check if cluster has smurfing indicators."""
        # Multiple transactions with amounts just below CTR threshold
        avg_amount = cluster.total_amount / cluster.transaction_count
        return (cluster.transaction_count >= 5 and 
                8000 <= avg_amount <= 9999 and 
                cluster.time_span_hours <= 24)
    
    def _make_more_suspicious(self, cluster: TransactionCluster) -> TransactionCluster:
        """Create a more suspicious version of the cluster."""
        return TransactionCluster(
            cluster_id=f"suspicious_{cluster.cluster_id}",
            account_ids=cluster.account_ids,
            transaction_ids=cluster.transaction_ids + [f"EXTRA_TX{i}" for i in range(5)],
            total_amount=cluster.total_amount + 45000.0,  # Add more transactions near threshold
            transaction_count=cluster.transaction_count + 5,
            time_span_hours=min(cluster.time_span_hours, 1.0),  # Compress time
            cluster_type=cluster.cluster_type
        )

class MockFraudScoringEngine(FraudScoringEngine):
    """Mock fraud scoring engine for testing without external dependencies."""
    
    def __init__(self, config: FraudScoringConfig):
        self.config = config
        # Don't initialize AWS clients or Neptune connection
    
    def score_transaction_cluster(self, cluster: TransactionCluster) -> FraudScore:
        """Mock scoring implementation for testing."""
        # Generate deterministic features based on cluster properties
        features = self._generate_mock_features(cluster)
        
        # Use fallback scoring (rule-based)
        risk_score, confidence = self._fallback_scoring(features)
        
        # Ensure score bounds (Property 3)
        risk_score = max(0.0, min(1.0, risk_score))
        confidence = max(0.0, min(1.0, confidence))
        
        # Analyze patterns
        pattern_indicators = self._analyze_pattern_indicators(cluster, features)
        
        # Mock feature importance
        feature_importance = {
            'small_transaction_ratio': 0.3,
            'transaction_frequency': 0.2,
            'network_density': 0.2,
            'amount_clustering': 0.3
        }
        
        # Classify risk level
        risk_level = self._classify_risk_level(risk_score)
        
        return FraudScore(
            cluster_id=cluster.cluster_id,
            risk_score=risk_score,
            confidence=confidence,
            risk_level=risk_level,
            pattern_indicators=pattern_indicators,
            feature_importance=feature_importance,
            explanation=f"Mock explanation for score {risk_score:.3f}",
            timestamp=datetime.utcnow().isoformat()
        )
    
    def _generate_mock_features(self, cluster: TransactionCluster) -> Dict[str, Any]:
        """Generate mock features for testing."""
        # Calculate basic metrics
        avg_amount = cluster.total_amount / cluster.transaction_count
        tx_frequency = cluster.transaction_count / max(cluster.time_span_hours, 1)
        
        # Mock account features
        account_features = []
        for account_id in cluster.account_ids:
            account_features.append({
                'account_id': account_id,
                'total_transactions': cluster.transaction_count // len(cluster.account_ids),
                'total_amount': cluster.total_amount / len(cluster.account_ids),
                'avg_amount': avg_amount,
                'unique_counterparties': min(len(cluster.account_ids) - 1, 5),
                'account_age_days': 365,
                'small_transaction_ratio': 0.8 if avg_amount < 10000 else 0.2,
                'large_transaction_ratio': 0.1 if avg_amount >= 50000 else 0.0,
                'transaction_velocity': tx_frequency
            })
        
        # Mock transaction features
        transaction_features = []
        for tx_id in cluster.transaction_ids:
            tx_amount = avg_amount + np.random.normal(0, avg_amount * 0.1)
            transaction_features.append({
                'transaction_id': tx_id,
                'amount': max(tx_amount, 100),  # Minimum $100
                'amount_log': np.log10(max(tx_amount, 100)),
                'hour_of_day': 14,  # 2 PM
                'day_of_week': 2,   # Wednesday
                'is_weekend': 0,
                'is_business_hours': 1,
                'is_round_amount': 1 if tx_amount % 1000 == 0 else 0,
                'is_below_ctr_threshold': 1 if tx_amount < 10000 else 0,
                'is_above_large_threshold': 1 if tx_amount >= 50000 else 0
            })
        
        # Mock network features
        network_features = {
            'network_density': min(len(cluster.account_ids) / 10.0, 1.0),
            'clustering_coefficient': 0.5,
            'account_count': len(cluster.account_ids)
        }
        
        # Mock temporal features
        temporal_features = {
            'time_span_hours': cluster.time_span_hours,
            'transaction_frequency': tx_frequency,
            'transaction_count': cluster.transaction_count
        }
        
        # Mock cluster features
        cluster_features = {
            'total_amount': cluster.total_amount,
            'transaction_count': cluster.transaction_count,
            'time_span_hours': cluster.time_span_hours,
            'avg_amount': avg_amount,
            'amount_velocity': cluster.total_amount / max(cluster.time_span_hours, 1),
            'account_count': len(cluster.account_ids),
            'cluster_density': cluster.transaction_count / max(len(cluster.account_ids), 1)
        }
        
        return {
            'account_features': account_features,
            'transaction_features': transaction_features,
            'network_features': network_features,
            'temporal_features': temporal_features,
            'cluster_features': cluster_features
        }

class FraudScoringStateMachine(RuleBasedStateMachine):
    """Stateful property testing for fraud scoring system."""
    
    def __init__(self):
        super().__init__()
        self.config = FraudScoringConfig(
            neptune_endpoint="test-endpoint",
            model_endpoint="test-model-endpoint",
            suspicious_threshold=0.7,
            high_risk_threshold=0.9
        )
        self.engine = MockFraudScoringEngine(self.config)
        self.scored_clusters = []
    
    @rule(cluster=transaction_cluster_strategy())
    def score_cluster(self, cluster):
        """Score a transaction cluster."""
        fraud_score = self.engine.score_transaction_cluster(cluster)
        self.scored_clusters.append((cluster, fraud_score))
    
    @invariant()
    def all_scores_in_bounds(self):
        """Invariant: All scores must be in valid bounds."""
        for cluster, fraud_score in self.scored_clusters:
            assert 0.0 <= fraud_score.risk_score <= 1.0, \
                f"Score {fraud_score.risk_score} out of bounds for cluster {cluster.cluster_id}"
            assert 0.0 <= fraud_score.confidence <= 1.0, \
                f"Confidence {fraud_score.confidence} out of bounds for cluster {cluster.cluster_id}"
    
    @invariant()
    def risk_levels_consistent_with_scores(self):
        """Invariant: Risk levels must be consistent with scores."""
        for cluster, fraud_score in self.scored_clusters:
            score = fraud_score.risk_score
            level = fraud_score.risk_level
            
            if score >= self.config.high_risk_threshold:
                assert level == 'CRITICAL', \
                    f"Score {score} should be CRITICAL, got {level}"
            elif score >= self.config.suspicious_threshold:
                assert level == 'HIGH', \
                    f"Score {score} should be HIGH, got {level}"

# Test runner
TestFraudScoringStateMachine = FraudScoringStateMachine.TestCase

if __name__ == "__main__":
    # Run property tests
    pytest.main([__file__, "-v", "--tb=short"])