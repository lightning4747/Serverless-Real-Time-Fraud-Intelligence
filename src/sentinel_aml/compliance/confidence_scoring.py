"""
Confidence Scoring Module for Suspicious Pattern Detection
Provides advanced confidence scoring for AML pattern detection and SAR generation.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import numpy as np
from decimal import Decimal
import math

logger = logging.getLogger(__name__)

class PatternType(Enum):
    """Types of suspicious patterns."""
    SMURFING = "SMURFING"
    STRUCTURING = "STRUCTURING"
    LAYERING = "LAYERING"
    RAPID_FIRE = "RAPID_FIRE"
    ROUND_DOLLAR = "ROUND_DOLLAR"
    VELOCITY = "VELOCITY"
    TIME_PATTERN = "TIME_PATTERN"
    GEOGRAPHIC = "GEOGRAPHIC"

@dataclass
class PatternEvidence:
    """Evidence for a suspicious pattern."""
    pattern_type: PatternType
    strength: float  # 0.0 to 1.0
    supporting_transactions: List[str]
    statistical_significance: float
    description: str
    metadata: Dict[str, Any]

@dataclass
class ConfidenceScore:
    """Comprehensive confidence score for suspicious activity."""
    overall_confidence: float
    pattern_confidences: Dict[PatternType, float]
    evidence_quality: float
    data_completeness: float
    statistical_significance: float
    regulatory_alignment: float
    explanation: str
    contributing_factors: List[str]
    risk_factors: List[str]
class ConfidenceScorer:
    """Advanced confidence scoring engine for AML pattern detection."""
    
    def __init__(self):
        self.pattern_weights = {
            PatternType.SMURFING: 0.9,
            PatternType.STRUCTURING: 0.85,
            PatternType.LAYERING: 0.8,
            PatternType.RAPID_FIRE: 0.75,
            PatternType.ROUND_DOLLAR: 0.6,
            PatternType.VELOCITY: 0.7,
            PatternType.TIME_PATTERN: 0.65,
            PatternType.GEOGRAPHIC: 0.7
        }
        
        self.regulatory_thresholds = {
            'ctr_threshold': 10000,
            'sar_threshold': 5000,
            'structuring_threshold': 10000,
            'velocity_threshold': 50  # transactions per hour
        }
    
    def calculate_confidence(self, suspicious_activity: Dict[str, Any], 
                           transaction_data: List[Dict[str, Any]],
                           account_data: List[Dict[str, Any]]) -> ConfidenceScore:
        """Calculate comprehensive confidence score."""
        logger.info(f"Calculating confidence for cluster {suspicious_activity.get('cluster_id')}")
        
        # Extract pattern evidence
        pattern_evidence = self._extract_pattern_evidence(
            suspicious_activity, transaction_data, account_data
        )
        
        # Calculate individual pattern confidences
        pattern_confidences = {}
        for evidence in pattern_evidence:
            pattern_confidences[evidence.pattern_type] = self._calculate_pattern_confidence(evidence)
        
        # Calculate component scores
        evidence_quality = self._calculate_evidence_quality(pattern_evidence)
        data_completeness = self._calculate_data_completeness(transaction_data, account_data)
        statistical_significance = self._calculate_statistical_significance(pattern_evidence)
        regulatory_alignment = self._calculate_regulatory_alignment(suspicious_activity, transaction_data)
        
        # Calculate overall confidence using weighted combination
        overall_confidence = self._calculate_overall_confidence(
            pattern_confidences, evidence_quality, data_completeness,
            statistical_significance, regulatory_alignment
        )
        
        # Generate explanation and factors
        explanation, contributing_factors, risk_factors = self._generate_explanation(
            pattern_confidences, evidence_quality, data_completeness,
            statistical_significance, regulatory_alignment
        )
        
        return ConfidenceScore(
            overall_confidence=overall_confidence,
            pattern_confidences=pattern_confidences,
            evidence_quality=evidence_quality,
            data_completeness=data_completeness,
            statistical_significance=statistical_significance,
            regulatory_alignment=regulatory_alignment,
            explanation=explanation,
            contributing_factors=contributing_factors,
            risk_factors=risk_factors
        )
    
    def _extract_pattern_evidence(self, suspicious_activity: Dict[str, Any],
                                transaction_data: List[Dict[str, Any]],
                                account_data: List[Dict[str, Any]]) -> List[PatternEvidence]:
        """Extract evidence for each detected pattern."""
        evidence_list = []
        pattern_indicators = suspicious_activity.get('pattern_indicators', [])
        
        for pattern_name in pattern_indicators:
            try:
                pattern_type = PatternType(pattern_name)
                evidence = self._analyze_pattern_evidence(
                    pattern_type, suspicious_activity, transaction_data, account_data
                )
                if evidence:
                    evidence_list.append(evidence)
            except ValueError:
                logger.warning(f"Unknown pattern type: {pattern_name}")
        
        return evidence_list
    
    def _analyze_pattern_evidence(self, pattern_type: PatternType,
                                suspicious_activity: Dict[str, Any],
                                transaction_data: List[Dict[str, Any]],
                                account_data: List[Dict[str, Any]]) -> Optional[PatternEvidence]:
        """Analyze evidence for a specific pattern type."""
        
        if pattern_type == PatternType.SMURFING:
            return self._analyze_smurfing_evidence(suspicious_activity, transaction_data)
        elif pattern_type == PatternType.STRUCTURING:
            return self._analyze_structuring_evidence(suspicious_activity, transaction_data)
        elif pattern_type == PatternType.RAPID_FIRE:
            return self._analyze_rapid_fire_evidence(suspicious_activity, transaction_data)
        elif pattern_type == PatternType.VELOCITY:
            return self._analyze_velocity_evidence(suspicious_activity, transaction_data)
        else:
            # Generic pattern analysis
            return PatternEvidence(
                pattern_type=pattern_type,
                strength=0.5,
                supporting_transactions=[tx['transaction_id'] for tx in transaction_data[:5]],
                statistical_significance=0.5,
                description=f"Generic {pattern_type.value} pattern detected",
                metadata={}
            )
    
    def _analyze_smurfing_evidence(self, suspicious_activity: Dict[str, Any],
                                 transaction_data: List[Dict[str, Any]]) -> PatternEvidence:
        """Analyze evidence for smurfing pattern."""
        amounts = [tx['amount'] for tx in transaction_data]
        total_amount = sum(amounts)
        
        # Check for amounts just below CTR threshold
        below_threshold_count = sum(1 for amt in amounts if 9000 <= amt < 10000)
        threshold_ratio = below_threshold_count / len(amounts) if amounts else 0
        
        # Calculate strength based on threshold avoidance
        strength = min(threshold_ratio * 2, 1.0)  # Max strength if all transactions avoid threshold
        
        # Statistical significance based on probability of random occurrence
        expected_ratio = 0.1  # Expected ratio for legitimate transactions
        statistical_significance = min(abs(threshold_ratio - expected_ratio) * 5, 1.0)
        
        return PatternEvidence(
            pattern_type=PatternType.SMURFING,
            strength=strength,
            supporting_transactions=[tx['transaction_id'] for tx in transaction_data 
                                   if 9000 <= tx['amount'] < 10000],
            statistical_significance=statistical_significance,
            description=f"Smurfing pattern: {below_threshold_count}/{len(amounts)} transactions just below CTR threshold",
            metadata={
                'threshold_ratio': threshold_ratio,
                'total_amount': total_amount,
                'avg_amount': total_amount / len(amounts) if amounts else 0
            }
        )
    
    def _calculate_overall_confidence(self, pattern_confidences: Dict[PatternType, float],
                                    evidence_quality: float, data_completeness: float,
                                    statistical_significance: float, regulatory_alignment: float) -> float:
        """Calculate overall confidence using weighted combination."""
        
        # Weight the pattern confidences by their importance
        weighted_pattern_score = 0.0
        total_weight = 0.0
        
        for pattern_type, confidence in pattern_confidences.items():
            weight = self.pattern_weights.get(pattern_type, 0.5)
            weighted_pattern_score += confidence * weight
            total_weight += weight
        
        pattern_score = weighted_pattern_score / total_weight if total_weight > 0 else 0.0
        
        # Combine all components with weights
        overall_confidence = (
            pattern_score * 0.4 +
            evidence_quality * 0.2 +
            data_completeness * 0.15 +
            statistical_significance * 0.15 +
            regulatory_alignment * 0.1
        )
        
        return min(max(overall_confidence, 0.0), 1.0)
    
    def _calculate_evidence_quality(self, pattern_evidence: List[PatternEvidence]) -> float:
        """Calculate quality of evidence."""
        if not pattern_evidence:
            return 0.0
        
        total_strength = sum(evidence.strength for evidence in pattern_evidence)
        avg_strength = total_strength / len(pattern_evidence)
        
        # Bonus for multiple types of evidence
        pattern_diversity = len(set(evidence.pattern_type for evidence in pattern_evidence))
        diversity_bonus = min(pattern_diversity * 0.1, 0.3)
        
        return min(avg_strength + diversity_bonus, 1.0)
    
    def _calculate_data_completeness(self, transaction_data: List[Dict[str, Any]],
                                   account_data: List[Dict[str, Any]]) -> float:
        """Calculate completeness of available data."""
        completeness_score = 0.0
        
        # Transaction data completeness
        if transaction_data:
            required_tx_fields = ['amount', 'timestamp', 'from_account', 'to_account']
            tx_completeness = []
            
            for tx in transaction_data:
                field_count = sum(1 for field in required_tx_fields if tx.get(field))
                tx_completeness.append(field_count / len(required_tx_fields))
            
            completeness_score += sum(tx_completeness) / len(tx_completeness) * 0.6
        
        # Account data completeness
        if account_data:
            required_acc_fields = ['account_id', 'customer_name', 'account_type']
            acc_completeness = []
            
            for acc in account_data:
                field_count = sum(1 for field in required_acc_fields if acc.get(field))
                acc_completeness.append(field_count / len(required_acc_fields))
            
            completeness_score += sum(acc_completeness) / len(acc_completeness) * 0.4
        
        return min(completeness_score, 1.0)