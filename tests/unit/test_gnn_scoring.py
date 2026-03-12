"""
Unit tests for GNN scoring logic.
Tests individual components and edge cases.
"""

import pytest
import numpy as np
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from dataclasses import asdict

# Import modules under test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from lambda.fraud_scoring import (
    FraudScoringEngine, FraudScoringConfig, TransactionCluster, FraudScore
)

class TestFraudScoringEngine:
    """Unit tests for FraudScoringEngine class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = FraudScoringConfig(
            neptune_endpoint="test-endpoint",
            model_endpoint="test-model-endpoint",
            suspicious_threshold=0.7,
            high_risk_threshold=0.9
        )
        
        self.sample_cluster = TransactionCluster(
            cluster_id="test-cluster-001",
            account_ids=["ACC001", "ACC002", "ACC003"],
            transaction_ids=["TX001", "TX002", "TX003"],
            total_amount=25000.0,
            transaction_count=3,
            time_span_hours=4.5,
            cluster_type="temporal"
        )
    
    @patch('boto3.client')
    def test_engine_initialization(self, mock_boto_client):
        """Test fraud scoring engine initialization."""
        engine = FraudScoringEngine(self.config)
        
        assert engine.config == self.config
        assert mock_boto_client.call_count >= 3  # neptune, sagemaker-runtime, bedrock-runtime
    
    def test_classify_risk_level(self):
        """Test risk level classification logic."""
        engine = FraudScoringEngine(self.config)
        
        # Test different score ranges
        assert engine._classify_risk_level(0.95) == 'CRITICAL'
        assert engine._classify_risk_level(0.9) == 'CRITICAL'
        assert engine._classify_risk_level(0.85) == 'HIGH'
        assert engine._classify_risk_level(0.7) == 'HIGH'
        assert engine._classify_risk_level(0.65) == 'MEDIUM'
        assert engine._classify_risk_level(0.5) == 'MEDIUM'
        assert engine._classify_risk_level(0.3) == 'LOW'
        assert engine._classify_risk_level(0.0) == 'LOW'
    
    def test_classify_risk_level_edge_cases(self):
        """Test risk level classification edge cases."""
        engine = FraudScoringEngine(self.config)
        
        # Test boundary values
        assert engine._classify_risk_level(0.89999) == 'HIGH'
        assert engine._classify_risk_level(0.90001) == 'CRITICAL'
        assert engine._classify_risk_level(0.69999) == 'MEDIUM'
        assert engine._classify_risk_level(0.70001) == 'HIGH'
    
    def test_detect_smurfing_pattern_positive(self):
        """Test smurfing pattern detection - positive case."""
        engine = FraudScoringEngine(self.config)
        
        # Create features indicating smurfing
        features = {
            'transaction_features': [
                {'amount': 9500, 'is_below_ctr_threshold': 1, 'is_round_amount': 1},
                {'amount': 9800, 'is_below_ctr_threshold': 1, 'is_round_amount': 0},
                {'amount': 9200, 'is_below_ctr_threshold': 1, 'is_round_amount': 0},
                {'amount': 9900, 'is_below_ctr_threshold': 1, 'is_round_amount': 0}
            ]
        }
        
        result = engine._detect_smurfing_pattern(features)
        assert result == True
    
    def test_detect_smurfing_pattern_negative(self):
        """Test smurfing pattern detection - negative case."""
        engine = FraudScoringEngine(self.config)
        
        # Create features not indicating smurfing
        features = {
            'transaction_features': [
                {'amount': 15000, 'is_below_ctr_threshold': 0, 'is_round_amount': 0},
                {'amount': 25000, 'is_below_ctr_threshold': 0, 'is_round_amount': 0}
            ]
        }
        
        result = engine._detect_smurfing_pattern(features)
        assert result == False
    
    def test_detect_smurfing_pattern_empty_features(self):
        """Test smurfing pattern detection with empty features."""
        engine = FraudScoringEngine(self.config)
        
        features = {'transaction_features': []}
        result = engine._detect_smurfing_pattern(features)
        assert result == False
    
    def test_detect_layering_pattern_positive(self):
        """Test layering pattern detection - positive case."""
        engine = FraudScoringEngine(self.config)
        
        features = {
            'network_features': {
                'account_count': 6,
                'network_density': 0.7
            },
            'cluster_features': {
                'cluster_density': 2.5
            }
        }
        
        result = engine._detect_layering_pattern(features)
        assert result == True
    
    def test_detect_layering_pattern_negative(self):
        """Test layering pattern detection - negative case."""
        engine = FraudScoringEngine(self.config)
        
        features = {
            'network_features': {
                'account_count': 2,
                'network_density': 0.3
            },
            'cluster_features': {
                'cluster_density': 1.0
            }
        }
        
        result = engine._detect_layering_pattern(features)
        assert result == False
    
    def test_detect_rapid_fire_pattern(self):
        """Test rapid fire pattern detection."""
        engine = FraudScoringEngine(self.config)
        
        # High frequency should trigger pattern
        features = {'temporal_features': {'transaction_frequency': 8.0}}
        assert engine._detect_rapid_fire_pattern(features) == True
        
        # Low frequency should not trigger pattern
        features = {'temporal_features': {'transaction_frequency': 2.0}}
        assert engine._detect_rapid_fire_pattern(features) == False
    
    def test_detect_round_amount_pattern(self):
        """Test round amount pattern detection."""
        engine = FraudScoringEngine(self.config)
        
        # High ratio of round amounts
        features = {
            'transaction_features': [
                {'is_round_amount': 1},
                {'is_round_amount': 1},
                {'is_round_amount': 0}
            ]
        }
        assert engine._detect_round_amount_pattern(features) == True
        
        # Low ratio of round amounts
        features = {
            'transaction_features': [
                {'is_round_amount': 0},
                {'is_round_amount': 0},
                {'is_round_amount': 0}
            ]
        }
        assert engine._detect_round_amount_pattern(features) == False
    
    def test_detect_off_hours_pattern(self):
        """Test off-hours pattern detection."""
        engine = FraudScoringEngine(self.config)
        
        # High off-hours activity
        features = {
            'transaction_features': [
                {'is_business_hours': 0, 'is_weekend': 0},
                {'is_business_hours': 0, 'is_weekend': 1},
                {'is_business_hours': 1, 'is_weekend': 0}
            ]
        }
        assert engine._detect_off_hours_pattern(features) == True
        
        # Normal business hours activity
        features = {
            'transaction_features': [
                {'is_business_hours': 1, 'is_weekend': 0},
                {'is_business_hours': 1, 'is_weekend': 0},
                {'is_business_hours': 1, 'is_weekend': 0}
            ]
        }
        assert engine._detect_off_hours_pattern(features) == False
    
    def test_detect_circular_flow_pattern(self):
        """Test circular flow pattern detection."""
        engine = FraudScoringEngine(self.config)
        
        # High clustering coefficient with multiple accounts
        features = {
            'network_features': {
                'clustering_coefficient': 0.9,
                'account_count': 4
            }
        }
        assert engine._detect_circular_flow_pattern(features) == True
        
        # Low clustering coefficient
        features = {
            'network_features': {
                'clustering_coefficient': 0.3,
                'account_count': 4
            }
        }
        assert engine._detect_circular_flow_pattern(features) == False
        
        # High clustering but too few accounts
        features = {
            'network_features': {
                'clustering_coefficient': 0.9,
                'account_count': 2
            }
        }
        assert engine._detect_circular_flow_pattern(features) == False
    
    def test_fallback_scoring_high_risk(self):
        """Test fallback scoring for high-risk scenarios."""
        engine = FraudScoringEngine(self.config)
        
        # Create high-risk features
        features = {
            'account_features': [
                {'small_transaction_ratio': 0.9},
                {'small_transaction_ratio': 0.8}
            ],
            'temporal_features': {'transaction_frequency': 15.0},
            'network_features': {'network_density': 0.8},
            'transaction_features': [
                {'is_round_amount': 1},
                {'is_round_amount': 1}
            ]
        }
        
        score, confidence = engine._fallback_scoring(features)
        
        assert 0.8 <= score <= 1.0  # Should be high risk
        assert confidence == 0.3    # Fallback confidence
    
    def test_fallback_scoring_low_risk(self):
        """Test fallback scoring for low-risk scenarios."""
        engine = FraudScoringEngine(self.config)
        
        # Create low-risk features
        features = {
            'account_features': [
                {'small_transaction_ratio': 0.1}
            ],
            'temporal_features': {'transaction_frequency': 1.0},
            'network_features': {'network_density': 0.2},
            'transaction_features': [
                {'is_round_amount': 0}
            ]
        }
        
        score, confidence = engine._fallback_scoring(features)
        
        assert 0.0 <= score <= 0.3  # Should be low risk
        assert confidence == 0.3    # Fallback confidence
    
    def test_calculate_feature_importance(self):
        """Test feature importance calculation."""
        engine = FraudScoringEngine(self.config)
        
        features = {
            'account_features': [
                {'small_transaction_ratio': 0.8, 'transaction_velocity': 5.0}
            ],
            'network_features': {
                'network_density': 0.6,
                'clustering_coefficient': 0.7
            },
            'temporal_features': {
                'transaction_frequency': 3.0
            }
        }
        
        risk_score = 0.8
        importance = engine._calculate_feature_importance(features, risk_score)
        
        # Check that all expected features are present
        assert 'small_transaction_ratio' in importance
        assert 'transaction_velocity' in importance
        assert 'network_density' in importance
        assert 'clustering_coefficient' in importance
        assert 'transaction_frequency' in importance
        
        # Check that importance values are reasonable
        for feature, value in importance.items():
            assert 0.0 <= value <= 1.0
    
    def test_prepare_model_input(self):
        """Test model input preparation."""
        engine = FraudScoringEngine(self.config)
        
        features = {
            'account_features': [
                {
                    'total_transactions': 10,
                    'total_amount': 50000,
                    'small_transaction_ratio': 0.6,
                    'transaction_velocity': 2.0
                }
            ],
            'transaction_features': [
                {
                    'amount': 5000,
                    'is_weekend': 0,
                    'is_round_amount': 1,
                    'is_below_ctr_threshold': 1
                }
            ],
            'network_features': {
                'network_density': 0.5,
                'clustering_coefficient': 0.4,
                'account_count': 3
            },
            'temporal_features': {
                'time_span_hours': 6.0,
                'transaction_frequency': 2.5,
                'transaction_count': 15
            },
            'cluster_features': {
                'total_amount': 75000,
                'avg_amount': 5000,
                'amount_velocity': 12500,
                'cluster_density': 5.0
            }
        }
        
        model_input = engine._prepare_model_input(features)
        
        # Check structure
        assert 'instances' in model_input
        assert 'configuration' in model_input
        assert len(model_input['instances']) == 1
        
        # Check feature vector length (should be 18 features total)
        feature_vector = model_input['instances'][0]
        assert len(feature_vector) == 18
        
        # Check that all values are numeric
        for value in feature_vector:
            assert isinstance(value, (int, float))
            assert not np.isnan(value)
            assert not np.isinf(value)
    
    def test_prepare_model_input_empty_features(self):
        """Test model input preparation with empty features."""
        engine = FraudScoringEngine(self.config)
        
        features = {
            'account_features': [],
            'transaction_features': [],
            'network_features': {
                'network_density': 0.0,
                'clustering_coefficient': 0.0,
                'account_count': 0
            },
            'temporal_features': {
                'time_span_hours': 0.0,
                'transaction_frequency': 0.0,
                'transaction_count': 0
            },
            'cluster_features': {
                'total_amount': 0.0,
                'avg_amount': 0.0,
                'amount_velocity': 0.0,
                'cluster_density': 0.0
            }
        }
        
        model_input = engine._prepare_model_input(features)
        
        # Should handle empty features gracefully
        assert 'instances' in model_input
        feature_vector = model_input['instances'][0]
        assert len(feature_vector) == 18
        
        # First 8 features should be 0.0 (empty account/transaction features)
        for i in range(8):
            assert feature_vector[i] == 0.0

class TestTransactionCluster:
    """Unit tests for TransactionCluster data class."""
    
    def test_transaction_cluster_creation(self):
        """Test transaction cluster creation."""
        cluster = TransactionCluster(
            cluster_id="test-001",
            account_ids=["ACC1", "ACC2"],
            transaction_ids=["TX1", "TX2", "TX3"],
            total_amount=15000.0,
            transaction_count=3,
            time_span_hours=2.5,
            cluster_type="amount"
        )
        
        assert cluster.cluster_id == "test-001"
        assert len(cluster.account_ids) == 2
        assert len(cluster.transaction_ids) == 3
        assert cluster.total_amount == 15000.0
        assert cluster.transaction_count == 3
        assert cluster.time_span_hours == 2.5
        assert cluster.cluster_type == "amount"
    
    def test_transaction_cluster_serialization(self):
        """Test transaction cluster serialization."""
        cluster = TransactionCluster(
            cluster_id="test-002",
            account_ids=["ACC1"],
            transaction_ids=["TX1"],
            total_amount=5000.0,
            transaction_count=1,
            time_span_hours=1.0,
            cluster_type="network"
        )
        
        # Test conversion to dict
        cluster_dict = asdict(cluster)
        assert isinstance(cluster_dict, dict)
        assert cluster_dict['cluster_id'] == "test-002"
        
        # Test JSON serialization
        json_str = json.dumps(cluster_dict)
        assert isinstance(json_str, str)
        
        # Test deserialization
        loaded_dict = json.loads(json_str)
        loaded_cluster = TransactionCluster(**loaded_dict)
        assert loaded_cluster.cluster_id == cluster.cluster_id

class TestFraudScore:
    """Unit tests for FraudScore data class."""
    
    def test_fraud_score_creation(self):
        """Test fraud score creation."""
        score = FraudScore(
            cluster_id="test-cluster",
            risk_score=0.85,
            confidence=0.92,
            risk_level="HIGH",
            pattern_indicators=["SMURFING_PATTERN", "RAPID_FIRE_PATTERN"],
            feature_importance={"feature1": 0.6, "feature2": 0.4},
            explanation="High risk due to smurfing patterns",
            timestamp="2024-01-01T12:00:00Z"
        )
        
        assert score.cluster_id == "test-cluster"
        assert score.risk_score == 0.85
        assert score.confidence == 0.92
        assert score.risk_level == "HIGH"
        assert len(score.pattern_indicators) == 2
        assert "SMURFING_PATTERN" in score.pattern_indicators
        assert len(score.feature_importance) == 2
        assert score.explanation == "High risk due to smurfing patterns"
    
    def test_fraud_score_serialization(self):
        """Test fraud score serialization."""
        score = FraudScore(
            cluster_id="test",
            risk_score=0.5,
            confidence=0.8,
            risk_level="MEDIUM",
            pattern_indicators=[],
            feature_importance={},
            explanation="",
            timestamp=datetime.utcnow().isoformat()
        )
        
        # Test conversion to dict
        score_dict = asdict(score)
        assert isinstance(score_dict, dict)
        
        # Test JSON serialization
        json_str = json.dumps(score_dict)
        assert isinstance(json_str, str)

class TestFraudScoringConfig:
    """Unit tests for FraudScoringConfig."""
    
    def test_config_defaults(self):
        """Test configuration defaults."""
        config = FraudScoringConfig(neptune_endpoint="test")
        
        assert config.neptune_endpoint == "test"
        assert config.neptune_port == 8182
        assert config.suspicious_threshold == 0.7
        assert config.high_risk_threshold == 0.9
        assert config.batch_size == 100
        assert config.max_processing_time == 300
        assert config.enable_explainability == True
    
    def test_config_custom_values(self):
        """Test configuration with custom values."""
        config = FraudScoringConfig(
            neptune_endpoint="custom-endpoint",
            neptune_port=9999,
            suspicious_threshold=0.6,
            high_risk_threshold=0.8,
            enable_explainability=False
        )
        
        assert config.neptune_endpoint == "custom-endpoint"
        assert config.neptune_port == 9999
        assert config.suspicious_threshold == 0.6
        assert config.high_risk_threshold == 0.8
        assert config.enable_explainability == False

if __name__ == "__main__":
    pytest.main([__file__, "-v"])