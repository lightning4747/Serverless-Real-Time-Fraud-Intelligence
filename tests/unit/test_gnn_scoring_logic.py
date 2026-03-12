"""
Unit tests for GNN scoring logic and feature extraction.

Tests specific functionality of the fraud scoring system including
feature extraction, score calculation, and edge case handling.

**Requirements: 3.1, 3.2, 3.4**
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
import numpy as np

from src.sentinel_aml.data.models import Account, Transaction, TransactionType, AccountType
from src.sentinel_aml.lambdas.fraud_scorer import (
    GnnFraudScorer, 
    FraudScoringResult, 
    ClusterAnalysisResult,
    FraudScoringRequest
)
from src.sentinel_aml.ml.feature_extractor import (
    TransactionFeatureExtractor, 
    TransactionFeatures
)
from src.sentinel_aml.core.exceptions import ValidationError, ProcessingError


class TestTransactionFeatureExtractor:
    """Unit tests for transaction feature extraction."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.feature_extractor = TransactionFeatureExtractor(smurfing_threshold=10000.0)
        self.test_account = Account(
            account_id="test_account_001",
            customer_name="Test Customer",
            account_type=AccountType.CHECKING,
            risk_score=0.0,
            creation_date=datetime.utcnow() - timedelta(days=60)
        )
    
    def test_extract_node_features_empty_transactions(self):
        """Test feature extraction with no transactions."""
        async def run_test():
            features = await self.feature_extractor.extract_node_features(
                account=self.test_account,
                transactions=[],
                lookback_days=30
            )
            
            # Should return zero values for all features
            assert features.transaction_count_7d == 0
            assert features.transaction_count_30d == 0
            assert features.avg_transaction_amount == 0.0
            assert features.total_volume_7d == 0.0
            assert features.total_volume_30d == 0.0
            assert features.unique_counterparties_7d == 0
            assert features.unique_counterparties_30d == 0
            assert features.transactions_below_threshold == 0
            assert features.rapid_sequential_count == 0
        
        asyncio.run(run_test())
    
    def test_extract_node_features_normal_transactions(self):
        """Test feature extraction with normal transaction patterns."""
        # Create normal transactions
        transactions = []
        base_time = datetime.utcnow() - timedelta(days=5)
        
        for i in range(5):
            transaction = Transaction(
                amount=Decimal('15000.00'),  # Above smurfing threshold
                timestamp=base_time + timedelta(days=i),
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
            transactions.append(transaction)
        
        async def run_test():
            features = await self.feature_extractor.extract_node_features(
                account=self.test_account,
                transactions=transactions,
                lookback_days=30
            )
            
            # Verify basic counts
            assert features.transaction_count_7d == 5
            assert features.transaction_count_30d == 5
            assert features.avg_transaction_amount == 15000.0
            assert features.total_volume_7d == 75000.0
            assert features.total_volume_30d == 75000.0
            
            # Should have no smurfing indicators
            assert features.transactions_below_threshold == 0
            assert features.rapid_sequential_count == 0
        
        asyncio.run(run_test())
    
    def test_extract_node_features_smurfing_pattern(self):
        """Test feature extraction with smurfing transaction patterns."""
        # Create smurfing transactions (below $10k threshold)
        transactions = []
        base_time = datetime.utcnow() - timedelta(hours=2)
        
        for i in range(8):
            transaction = Transaction(
                amount=Decimal('9500.00'),  # Below smurfing threshold
                timestamp=base_time + timedelta(minutes=i * 15),  # Rapid sequence
                transaction_type=TransactionType.TRANSFER,
                currency="USD",
                risk_flags=["below_threshold", "rapid_sequence"]
            )
            transactions.append(transaction)
        
        async def run_test():
            features = await self.feature_extractor.extract_node_features(
                account=self.test_account,
                transactions=transactions,
                lookback_days=30
            )
            
            # Should detect smurfing indicators
            assert features.transactions_below_threshold == 8
            assert features.rapid_sequential_count > 0  # Should detect rapid sequences
            assert features.avg_transaction_amount == 9500.0
            assert features.total_volume_7d == 76000.0
        
        asyncio.run(run_test())
    
    def test_count_rapid_sequential_transactions(self):
        """Test rapid sequential transaction counting."""
        # Create transactions within 1 hour of each other
        transactions = []
        base_time = datetime.utcnow()
        
        # Add transactions 30 minutes apart (should be rapid)
        for i in range(4):
            transaction = Transaction(
                amount=Decimal('5000.00'),
                timestamp=base_time + timedelta(minutes=i * 30),
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
            transactions.append(transaction)
        
        rapid_count = self.feature_extractor._count_rapid_sequential(transactions)
        assert rapid_count == 3  # 3 pairs within 1 hour
    
    def test_calculate_weekend_ratio(self):
        """Test weekend transaction ratio calculation."""
        transactions = []
        
        # Create transactions on different days
        monday = datetime(2024, 1, 1)  # Monday
        saturday = datetime(2024, 1, 6)  # Saturday
        sunday = datetime(2024, 1, 7)  # Sunday
        
        # 2 weekend transactions, 1 weekday
        for day in [monday, saturday, sunday]:
            transaction = Transaction(
                amount=Decimal('1000.00'),
                timestamp=day,
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
            transactions.append(transaction)
        
        weekend_ratio = self.feature_extractor._calculate_weekend_ratio(transactions)
        assert weekend_ratio == 2/3  # 2 out of 3 transactions on weekend
    
    def test_calculate_off_hours_ratio(self):
        """Test off-hours transaction ratio calculation."""
        transactions = []
        
        # Create transactions at different hours
        base_date = datetime(2024, 1, 1)
        hours = [8, 10, 18, 22]  # 8am, 10am (business), 6pm, 10pm (off-hours)
        
        for hour in hours:
            transaction = Transaction(
                amount=Decimal('1000.00'),
                timestamp=base_date.replace(hour=hour),
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
            transactions.append(transaction)
        
        off_hours_ratio = self.feature_extractor._calculate_off_hours_ratio(transactions)
        assert off_hours_ratio == 0.5  # 2 out of 4 transactions off-hours
    
    def test_calculate_circular_flow_score(self):
        """Test circular flow detection."""
        transactions = []
        account_id = "test_account"
        
        # Create circular flow: account -> other1 -> account
        transactions.extend([
            Transaction(  # Outgoing
                amount=Decimal('5000.00'),
                timestamp=datetime.utcnow(),
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            ),
            Transaction(  # Incoming (circular)
                amount=Decimal('4800.00'),
                timestamp=datetime.utcnow() + timedelta(minutes=30),
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
        ])
        
        # Mock the transaction directions for testing
        with patch.object(transactions[0], 'from_account_id', account_id), \
             patch.object(transactions[0], 'to_account_id', 'other1'), \
             patch.object(transactions[1], 'from_account_id', 'other1'), \
             patch.object(transactions[1], 'to_account_id', account_id):
            
            circular_score = self.feature_extractor._calculate_circular_flow_score(
                transactions, account_id
            )
            
            assert circular_score > 0  # Should detect circular flow
    
    def test_calculate_velocity_score(self):
        """Test transaction velocity calculation."""
        transactions = []
        base_time = datetime.utcnow() - timedelta(hours=24)
        
        # Create transactions with increasing frequency
        # First half: 2 transactions over 12 hours
        transactions.extend([
            Transaction(
                amount=Decimal('1000.00'),
                timestamp=base_time,
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            ),
            Transaction(
                amount=Decimal('1000.00'),
                timestamp=base_time + timedelta(hours=12),
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
        ])
        
        # Second half: 4 transactions over 12 hours (higher velocity)
        for i in range(4):
            transaction = Transaction(
                amount=Decimal('1000.00'),
                timestamp=base_time + timedelta(hours=12 + i * 3),
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
            transactions.append(transaction)
        
        velocity_score = self.feature_extractor._calculate_velocity_score(transactions)
        assert velocity_score > 1.0  # Should detect acceleration
    
    def test_calculate_amount_pattern_score(self):
        """Test structured amount pattern detection."""
        transactions = []
        
        # Create transactions with repeated amounts (structured)
        repeated_amount = Decimal('9999.00')  # Just below $10k threshold
        for i in range(5):
            transaction = Transaction(
                amount=repeated_amount,
                timestamp=datetime.utcnow() - timedelta(hours=i),
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
            transactions.append(transaction)
        
        pattern_score = self.feature_extractor._calculate_amount_pattern_score(transactions)
        assert pattern_score > 0.5  # Should detect structured amounts
    
    def test_features_to_array_conversion(self):
        """Test conversion of features to numpy array."""
        features = TransactionFeatures(
            account_age_days=30.0,
            transaction_count_7d=5,
            transaction_count_30d=15,
            avg_transaction_amount=5000.0,
            total_volume_7d=25000.0,
            total_volume_30d=75000.0,
            unique_counterparties_7d=3,
            unique_counterparties_30d=8,
            transactions_below_threshold=10,
            rapid_sequential_count=2,
            weekend_transaction_ratio=0.2,
            off_hours_transaction_ratio=0.3,
            clustering_coefficient=0.1,
            betweenness_centrality=0.05,
            degree_centrality=0.15,
            circular_flow_score=0.4,
            velocity_score=1.5,
            amount_pattern_score=0.6
        )
        
        feature_array = self.feature_extractor.features_to_array(features)
        
        assert isinstance(feature_array, np.ndarray)
        assert feature_array.dtype == np.float32
        assert len(feature_array) == len(self.feature_extractor.feature_names)
        assert feature_array[0] == 30.0  # account_age_days
        assert feature_array[1] == 5  # transaction_count_7d


class TestGnnFraudScorer:
    """Unit tests for GNN fraud scorer."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.fraud_scorer = GnnFraudScorer()
        self.test_account = Account(
            account_id="test_scorer_001",
            customer_name="Test Scorer Customer",
            account_type=AccountType.CHECKING,
            risk_score=0.0,
            creation_date=datetime.utcnow() - timedelta(days=30)
        )
    
    @patch('src.sentinel_aml.lambdas.fraud_scorer.GnnFraudScorer._get_gnn_prediction')
    @patch('src.sentinel_aml.data.neptune_client.NeptuneClient.get_account')
    @patch('src.sentinel_aml.data.neptune_client.NeptuneClient.get_account_transactions')
    def test_score_single_account_success(self, mock_get_transactions, mock_get_account, mock_gnn_prediction):
        """Test successful scoring of a single account."""
        # Mock dependencies
        mock_get_account.return_value = self.test_account
        mock_get_transactions.return_value = [
            Transaction(
                amount=Decimal('5000.00'),
                timestamp=datetime.utcnow(),
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
        ]
        mock_gnn_prediction.return_value = (0.75, 0.85)  # risk_score, confidence
        
        async def run_test():
            result = await self.fraud_scorer._score_single_account(
                account_id="test_scorer_001",
                lookback_days=30,
                include_feature_importance=True
            )
            
            assert isinstance(result, FraudScoringResult)
            assert result.account_id == "test_scorer_001"
            assert result.risk_score == 0.75
            assert result.confidence == 0.85
            assert result.is_suspicious == True  # 0.75 > 0.7 threshold
            assert isinstance(result.feature_importance, dict)
            assert isinstance(result.patterns_detected, list)
        
        asyncio.run(run_test())
    
    @patch('src.sentinel_aml.data.neptune_client.NeptuneClient.get_account')
    def test_score_single_account_not_found(self, mock_get_account):
        """Test scoring when account is not found."""
        mock_get_account.return_value = None
        
        async def run_test():
            with pytest.raises(ValidationError, match="Account not found"):
                await self.fraud_scorer._score_single_account(
                    account_id="nonexistent_account",
                    lookback_days=30,
                    include_feature_importance=True
                )
        
        asyncio.run(run_test())
    
    def test_get_gnn_prediction_error_handling(self):
        """Test GNN prediction error handling."""
        # Mock SageMaker runtime to raise an exception
        with patch.object(self.fraud_scorer, 'sagemaker_runtime') as mock_sagemaker:
            mock_sagemaker.invoke_endpoint.side_effect = Exception("Endpoint error")
            
            async def run_test():
                features = TransactionFeatures(
                    account_age_days=30.0,
                    transaction_count_7d=5,
                    transaction_count_30d=15,
                    avg_transaction_amount=5000.0,
                    total_volume_7d=25000.0,
                    total_volume_30d=75000.0,
                    unique_counterparties_7d=3,
                    unique_counterparties_30d=8,
                    transactions_below_threshold=0,
                    rapid_sequential_count=0,
                    weekend_transaction_ratio=0.2,
                    off_hours_transaction_ratio=0.3,
                    clustering_coefficient=0.1,
                    betweenness_centrality=0.05,
                    degree_centrality=0.15,
                    circular_flow_score=0.0,
                    velocity_score=1.0,
                    amount_pattern_score=0.0
                )
                
                risk_score, confidence = await self.fraud_scorer._get_gnn_prediction(features)
                
                # Should return conservative values on error
                assert risk_score == 0.5
                assert confidence == 0.0
            
            asyncio.run(run_test())
    
    def test_calculate_feature_importance(self):
        """Test feature importance calculation."""
        features = TransactionFeatures(
            account_age_days=30.0,
            transaction_count_7d=5,
            transaction_count_30d=15,
            avg_transaction_amount=5000.0,
            total_volume_7d=25000.0,
            total_volume_30d=75000.0,
            unique_counterparties_7d=3,
            unique_counterparties_30d=8,
            transactions_below_threshold=8,  # High smurfing indicator
            rapid_sequential_count=3,  # High rapid sequence
            weekend_transaction_ratio=0.2,
            off_hours_transaction_ratio=0.3,
            clustering_coefficient=0.1,
            betweenness_centrality=0.05,
            degree_centrality=0.15,
            circular_flow_score=0.6,  # High circular flow
            velocity_score=2.5,  # High velocity
            amount_pattern_score=0.8  # High pattern score
        )
        
        async def run_test():
            importance = await self.fraud_scorer._calculate_feature_importance(features)
            
            assert isinstance(importance, dict)
            assert len(importance) > 0
            
            # High-risk features should have higher importance
            assert importance['transactions_below_threshold'] > 0.5
            assert importance['rapid_sequential_count'] > 0.5
            assert importance['circular_flow_score'] == 0.6
            assert importance['amount_pattern_score'] == 0.8
        
        asyncio.run(run_test())
    
    def test_detect_suspicious_patterns(self):
        """Test suspicious pattern detection."""
        # Create account and transactions with suspicious patterns
        transactions = []
        for i in range(8):
            transaction = Transaction(
                amount=Decimal('9500.00'),  # Below threshold
                timestamp=datetime.utcnow() - timedelta(minutes=i * 15),  # Rapid
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
            transactions.append(transaction)
        
        features = TransactionFeatures(
            account_age_days=30.0,
            transaction_count_7d=8,
            transaction_count_30d=8,
            avg_transaction_amount=9500.0,
            total_volume_7d=76000.0,
            total_volume_30d=76000.0,
            unique_counterparties_7d=3,
            unique_counterparties_30d=3,
            transactions_below_threshold=8,  # Smurfing
            rapid_sequential_count=4,  # Rapid sequence
            weekend_transaction_ratio=0.8,  # Weekend activity
            off_hours_transaction_ratio=0.9,  # Off-hours activity
            clustering_coefficient=0.1,
            betweenness_centrality=0.05,
            degree_centrality=0.15,
            circular_flow_score=0.4,  # Circular flows
            velocity_score=3.0,  # High velocity
            amount_pattern_score=0.7  # Structured amounts
        )
        
        async def run_test():
            patterns = await self.fraud_scorer._detect_suspicious_patterns(
                account=self.test_account,
                transactions=transactions,
                features=features
            )
            
            assert isinstance(patterns, list)
            assert len(patterns) > 0
            
            # Should detect multiple suspicious patterns
            pattern_text = ' '.join(patterns)
            assert 'Smurfing' in pattern_text
            assert 'Rapid sequential' in pattern_text
            assert 'High velocity' in pattern_text
            assert 'Structured amounts' in pattern_text
            assert 'Weekend activity' in pattern_text
            assert 'Off-hours activity' in pattern_text
        
        asyncio.run(run_test())
    
    @patch('src.sentinel_aml.lambdas.fraud_scorer.GnnFraudScorer.score_accounts')
    @patch('src.sentinel_aml.data.neptune_client.NeptuneClient.get_account_transactions')
    def test_analyze_transaction_cluster(self, mock_get_transactions, mock_score_accounts):
        """Test transaction cluster analysis."""
        # Mock account scoring results
        mock_score_accounts.return_value = [
            FraudScoringResult(
                account_id="acc1",
                risk_score=0.8,
                is_suspicious=True,
                confidence=0.9,
                feature_importance={},
                patterns_detected=["Smurfing: 5 transactions below $10k threshold"],
                timestamp=datetime.utcnow(),
                model_version="test_v1"
            ),
            FraudScoringResult(
                account_id="acc2",
                risk_score=0.6,
                is_suspicious=False,
                confidence=0.7,
                feature_importance={},
                patterns_detected=[],
                timestamp=datetime.utcnow(),
                model_version="test_v1"
            )
        ]
        
        # Mock transaction data
        mock_get_transactions.return_value = [
            Transaction(
                amount=Decimal('9500.00'),
                timestamp=datetime.utcnow(),
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
        ]
        
        async def run_test():
            result = await self.fraud_scorer.analyze_transaction_cluster(
                cluster_id="test_cluster_001",
                account_ids=["acc1", "acc2"],
                lookback_days=30
            )
            
            assert isinstance(result, ClusterAnalysisResult)
            assert result.cluster_id == "test_cluster_001"
            assert len(result.account_scores) == 2
            assert result.cluster_risk_score == 0.7  # Mean of 0.8 and 0.6
            assert len(result.suspicious_patterns) >= 0
            assert result.total_volume > 0
            assert result.transaction_count > 0
        
        asyncio.run(run_test())


class TestFraudScoringEdgeCases:
    """Test edge cases and error conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.fraud_scorer = GnnFraudScorer()
    
    def test_empty_account_list_scoring(self):
        """Test scoring with empty account list."""
        async def run_test():
            results = await self.fraud_scorer.score_accounts(
                account_ids=[],
                lookback_days=30,
                include_feature_importance=True
            )
            
            assert results == []
        
        asyncio.run(run_test())
    
    def test_invalid_lookback_days(self):
        """Test with invalid lookback days."""
        async def run_test():
            # Should handle negative or zero lookback days gracefully
            results = await self.fraud_scorer.score_accounts(
                account_ids=["test_account"],
                lookback_days=0,
                include_feature_importance=False
            )
            
            # Should still return results (may be error results)
            assert isinstance(results, list)
        
        asyncio.run(run_test())
    
    def test_very_large_transaction_amounts(self):
        """Test feature extraction with very large transaction amounts."""
        extractor = TransactionFeatureExtractor()
        
        transactions = [
            Transaction(
                amount=Decimal('999999999.99'),  # Very large amount
                timestamp=datetime.utcnow(),
                transaction_type=TransactionType.WIRE,
                currency="USD"
            )
        ]
        
        account = Account(
            account_id="large_txn_account",
            customer_name="Large Transaction Customer",
            account_type=AccountType.BUSINESS,
            risk_score=0.0,
            creation_date=datetime.utcnow() - timedelta(days=30)
        )
        
        async def run_test():
            features = await extractor.extract_node_features(
                account=account,
                transactions=transactions,
                lookback_days=30
            )
            
            # Should handle large amounts without overflow
            assert features.avg_transaction_amount == 999999999.99
            assert features.total_volume_7d == 999999999.99
            assert features.transactions_below_threshold == 0  # Above threshold
        
        asyncio.run(run_test())
    
    def test_concurrent_timestamp_transactions(self):
        """Test transactions with identical timestamps."""
        extractor = TransactionFeatureExtractor()
        
        same_time = datetime.utcnow()
        transactions = []
        
        # Create multiple transactions at exact same time
        for i in range(5):
            transaction = Transaction(
                amount=Decimal('1000.00'),
                timestamp=same_time,
                transaction_type=TransactionType.TRANSFER,
                currency="USD"
            )
            transactions.append(transaction)
        
        # Should not crash on rapid sequential calculation
        rapid_count = extractor._count_rapid_sequential(transactions)
        assert rapid_count >= 0  # Should handle gracefully


if __name__ == "__main__":
    pytest.main([__file__, "-v"])