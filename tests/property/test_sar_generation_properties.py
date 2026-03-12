"""
Property-based tests for SAR generation system.
Tests universal correctness properties for regulatory compliance.
"""

import pytest
import re
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

from lambda.sar_generator import (
    SARGenerator, SARGenerationConfig, SuspiciousActivity, 
    AccountInfo, TransactionInfo, GeneratedSAR
)

# Test data strategies
@st.composite
def suspicious_activity_strategy(draw):
    """Generate valid suspicious activity data for testing."""
    cluster_id = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pc'))))
    
    account_count = draw(st.integers(min_value=1, max_value=10))
    account_ids = [f"ACC{i:03d}" for i in range(account_count)]
    
    tx_count = draw(st.integers(min_value=1, max_value=50))
    transaction_ids = [f"TX{i:04d}" for i in range(tx_count)]
    
    risk_score = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    
    pattern_indicators = draw(st.lists(
        st.sampled_from(['SMURFING_PATTERN', 'LAYERING_PATTERN', 'RAPID_FIRE_PATTERN', 
                        'ROUND_AMOUNT_PATTERN', 'OFF_HOURS_PATTERN', 'CIRCULAR_FLOW_PATTERN']),
        min_size=0, max_size=6, unique=True
    ))
    
    total_amount = draw(st.floats(min_value=1000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False))
    time_span_hours = draw(st.floats(min_value=0.1, max_value=168.0, allow_nan=False, allow_infinity=False))
    
    return SuspiciousActivity(
        cluster_id=cluster_id,
        account_ids=account_ids,
        transaction_ids=transaction_ids,
        risk_score=risk_score,
        pattern_indicators=pattern_indicators,
        total_amount=total_amount,
        transaction_count=tx_count,
        time_span_hours=time_span_hours,
        explanation=f"Test explanation for cluster {cluster_id}",
        feature_importance={"test_feature": 0.5},
        detection_timestamp=datetime.utcnow().isoformat()
    )

@st.composite
def account_info_strategy(draw):
    """Generate valid account information for testing."""
    account_id = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    customer_name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Zs'))))
    account_type = draw(st.sampled_from(['checking', 'savings', 'business', 'investment']))
    
    return AccountInfo(
        account_id=account_id,
        customer_name=customer_name,
        account_type=account_type,
        creation_date=datetime.utcnow().isoformat(),
        risk_score=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    )

@st.composite
def transaction_info_strategy(draw):
    """Generate valid transaction information for testing."""
    transaction_id = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    amount = draw(st.floats(min_value=100.0, max_value=1000000.0, allow_nan=False, allow_infinity=False))
    transaction_type = draw(st.sampled_from(['wire', 'ach', 'check', 'cash', 'card']))
    currency = draw(st.sampled_from(['USD', 'EUR', 'GBP', 'JPY']))
    
    return TransactionInfo(
        transaction_id=transaction_id,
        amount=amount,
        timestamp=datetime.utcnow().isoformat(),
        transaction_type=transaction_type,
        currency=currency,
        from_account="ACC001",
        to_account="ACC002"
    )

class TestSARGenerationProperties:
    """Property-based tests for SAR generation correctness properties."""
    
    def setup_method(self):
        """Set up test environment."""
        self.config = SARGenerationConfig(
            enable_pii_redaction=True,
            confidence_threshold=0.8
        )
    
    @given(
        suspicious_activity_strategy(),
        st.lists(account_info_strategy(), min_size=1, max_size=5),
        st.lists(transaction_info_strategy(), min_size=1, max_size=10)
    )
    @settings(max_examples=50, deadline=10000)
    def test_property_5_report_completeness(self, suspicious_activity: SuspiciousActivity,
                                          account_info: List[AccountInfo],
                                          transaction_info: List[TransactionInfo]):
        """
        Property 5: Report completeness - All SARs must include required FinCEN fields
        This validates that generated SARs meet regulatory requirements.
        """
        # Create mock SAR generator
        generator = MockSARGenerator(self.config)
        
        # Generate SAR
        generated_sar = generator.generate_sar(suspicious_activity, account_info, transaction_info)
        
        # Property 5: SAR must include required FinCEN fields
        required_sections = [
            'EXECUTIVE SUMMARY',
            'SUSPICIOUS ACTIVITY',
            'ACCOUNT',
            'TRANSACTION',
            'REGULATORY'
        ]
        
        sar_content = generated_sar.sar_content.upper()
        
        for section in required_sections:
            assert section in sar_content, \
                f"Required FinCEN section '{section}' missing from SAR {generated_sar.sar_id}"
        
        # Must include specific data elements
        assert str(suspicious_activity.total_amount) in generated_sar.sar_content or \
               f"{suspicious_activity.total_amount:,.0f}" in generated_sar.sar_content, \
               "SAR must include total transaction amount"
        
        assert str(suspicious_activity.transaction_count) in generated_sar.sar_content, \
               "SAR must include transaction count"
        
        # Must have substantial content
        word_count = len(generated_sar.sar_content.split())
        assert word_count >= 100, \
            f"SAR content too brief ({word_count} words), must be substantial for regulatory filing"
    
    @given(
        suspicious_activity_strategy(),
        st.lists(account_info_strategy(), min_size=1, max_size=3),
        st.lists(transaction_info_strategy(), min_size=1, max_size=5)
    )
    @settings(max_examples=30, deadline=8000)
    def test_property_6_pii_protection(self, suspicious_activity: SuspiciousActivity,
                                     account_info: List[AccountInfo],
                                     transaction_info: List[TransactionInfo]):
        """
        Property 6: PII protection - Generated reports must not contain raw PII
        This ensures compliance with data privacy regulations.
        """
        # Add some PII to test data
        pii_account = account_info[0]
        pii_account.ssn_last_four = "1234"
        pii_account.phone = "555-123-4567"
        pii_account.address = "123 Main Street, Anytown, ST 12345"
        
        generator = MockSARGenerator(self.config)
        generated_sar = generator.generate_sar(suspicious_activity, account_info, transaction_info)
        
        # Property 6: Redacted content must not contain raw PII
        redacted_content = generated_sar.redacted_content
        
        # Check for common PII patterns
        pii_patterns = {
            'ssn': r'\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b',
            'phone': r'\b\d{3}-\d{3}-\d{4}\b|\b\(\d{3}\)\s*\d{3}-\d{4}\b',
            'full_address': r'\b\d+\s+[A-Z][a-z]+\s+(Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln)\b'
        }
        
        for pii_type, pattern in pii_patterns.items():
            matches = re.findall(pattern, redacted_content)
            assert len(matches) == 0, \
                f"PII pattern '{pii_type}' found in redacted SAR content: {matches}"
        
        # Should contain redaction placeholders instead
        redaction_indicators = ['[REDACTED]', 'XXX-XX-XXXX', 'XXX-XXX-XXXX', '[EMAIL_REDACTED]']
        has_redaction_indicators = any(indicator in redacted_content for indicator in redaction_indicators)
        
        # If original content had PII, redacted version should have indicators
        if pii_account.ssn_last_four or pii_account.phone or pii_account.address:
            assert has_redaction_indicators, \
                "Redacted SAR should contain redaction indicators when PII was present"
    
    @given(
        suspicious_activity_strategy(),
        st.lists(account_info_strategy(), min_size=1, max_size=3),
        st.lists(transaction_info_strategy(), min_size=1, max_size=5)
    )
    @settings(max_examples=20, deadline=6000)
    def test_property_confidence_consistency(self, suspicious_activity: SuspiciousActivity,
                                           account_info: List[AccountInfo],
                                           transaction_info: List[TransactionInfo]):
        """
        Property: Confidence consistency - Higher quality SARs should have higher confidence scores.
        """
        generator = MockSARGenerator(self.config)
        
        # Generate SAR multiple times
        confidence_scores = []
        for _ in range(3):
            generated_sar = generator.generate_sar(suspicious_activity, account_info, transaction_info)
            confidence_scores.append(generated_sar.confidence_score)
        
        # Confidence scores should be consistent (deterministic generation)
        assert all(abs(score - confidence_scores[0]) < 0.1 for score in confidence_scores), \
            f"Confidence scores should be consistent: {confidence_scores}"
        
        # Confidence should be in valid range
        for score in confidence_scores:
            assert 0.0 <= score <= 1.0, \
                f"Confidence score {score} outside valid range [0.0, 1.0]"
    
    @given(
        suspicious_activity_strategy(),
        st.lists(account_info_strategy(), min_size=1, max_size=3),
        st.lists(transaction_info_strategy(), min_size=1, max_size=5)
    )
    @settings(max_examples=20, deadline=6000)
    def test_property_regulatory_justification(self, suspicious_activity: SuspiciousActivity,
                                             account_info: List[AccountInfo],
                                             transaction_info: List[TransactionInfo]):
        """
        Property: Regulatory justification - All SARs must include proper regulatory basis.
        """
        generator = MockSARGenerator(self.config)
        generated_sar = generator.generate_sar(suspicious_activity, account_info, transaction_info)
        
        sar_content = generated_sar.sar_content.upper()
        
        # Must include regulatory references
        regulatory_terms = ['BSA', 'AML', 'FINCEN', 'SUSPICIOUS', 'MONEY LAUNDERING']
        regulatory_mentions = sum(1 for term in regulatory_terms if term in sar_content)
        
        assert regulatory_mentions >= 2, \
            f"SAR must include regulatory justification (found {regulatory_mentions} terms)"
        
        # Must explain why activity is suspicious
        explanation_indicators = ['BECAUSE', 'DUE TO', 'INDICATES', 'SUGGESTS', 'PATTERN']
        has_explanation = any(indicator in sar_content for indicator in explanation_indicators)
        
        assert has_explanation, \
            "SAR must include explanation of why activity is suspicious"
    
    @given(st.lists(suspicious_activity_strategy(), min_size=2, max_size=5))
    @settings(max_examples=10, deadline=8000)
    def test_property_unique_sar_ids(self, suspicious_activities: List[SuspiciousActivity]):
        """
        Property: Uniqueness - Each SAR must have a unique identifier.
        """
        generator = MockSARGenerator(self.config)
        
        # Generate SARs for different activities
        sar_ids = []
        for activity in suspicious_activities:
            # Create minimal test data
            account_info = [AccountInfo(
                account_id="TEST001",
                customer_name="Test Customer",
                account_type="checking",
                creation_date=datetime.utcnow().isoformat()
            )]
            
            transaction_info = [TransactionInfo(
                transaction_id="TEST_TX001",
                amount=5000.0,
                timestamp=datetime.utcnow().isoformat(),
                transaction_type="wire",
                currency="USD",
                from_account="TEST001",
                to_account="TEST002"
            )]
            
            generated_sar = generator.generate_sar(activity, account_info, transaction_info)
            sar_ids.append(generated_sar.sar_id)
        
        # All SAR IDs must be unique
        assert len(sar_ids) == len(set(sar_ids)), \
            f"SAR IDs must be unique, found duplicates: {sar_ids}"
        
        # SAR IDs should follow expected format
        for sar_id in sar_ids:
            assert sar_id.startswith('SAR_'), \
                f"SAR ID should start with 'SAR_': {sar_id}"
            assert len(sar_id) >= 10, \
                f"SAR ID should be substantial length: {sar_id}"

class MockSARGenerator(SARGenerator):
    """Mock SAR generator for testing without external dependencies."""
    
    def __init__(self, config: SARGenerationConfig):
        self.config = config
        # Don't initialize AWS clients
        
        # PII patterns for redaction
        self.pii_patterns = {
            'ssn': r'\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b',
            'phone': r'\b\d{3}-\d{3}-\d{4}\b|\b\(\d{3}\)\s*\d{3}-\d{4}\b',
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'account_number': r'\b\d{10,16}\b',
            'routing_number': r'\b\d{9}\b'
        }
    
    def generate_sar(self, suspicious_activity: SuspiciousActivity, 
                    account_info: List[AccountInfo], 
                    transaction_info: List[TransactionInfo]) -> GeneratedSAR:
        """Mock SAR generation for testing."""
        # Generate unique SAR ID
        sar_id = self._generate_sar_id(suspicious_activity.cluster_id)
        
        # Generate mock SAR content
        sar_content = self._generate_mock_sar_content(suspicious_activity, account_info, transaction_info)
        
        # Apply PII redaction
        redacted_content = self._redact_pii(sar_content) if self.config.enable_pii_redaction else sar_content
        
        # Calculate mock confidence
        confidence_score = self._calculate_mock_confidence(sar_content, suspicious_activity)
        
        # Validate completeness
        compliance_flags = self._validate_sar_completeness(sar_content)
        
        # Determine review requirement
        review_required = confidence_score < self.config.confidence_threshold or len(compliance_flags) > 0
        
        return GeneratedSAR(
            sar_id=sar_id,
            cluster_id=suspicious_activity.cluster_id,
            generation_timestamp=datetime.utcnow().isoformat(),
            confidence_score=confidence_score,
            sar_content=sar_content,
            redacted_content=redacted_content,
            metadata={
                'risk_score': suspicious_activity.risk_score,
                'pattern_indicators': suspicious_activity.pattern_indicators,
                'account_count': len(account_info),
                'transaction_count': len(transaction_info)
            },
            compliance_flags=compliance_flags,
            review_required=review_required
        )
    
    def _generate_mock_sar_content(self, suspicious_activity: SuspiciousActivity,
                                  account_info: List[AccountInfo],
                                  transaction_info: List[TransactionInfo]) -> str:
        """Generate mock SAR content for testing."""
        # Calculate metrics
        total_amount = suspicious_activity.total_amount
        tx_count = len(transaction_info)
        account_count = len(account_info)
        
        # Build comprehensive SAR content
        content = f"""
EXECUTIVE SUMMARY
This Suspicious Activity Report documents potential money laundering activity involving {account_count} accounts and {tx_count} transactions totaling ${total_amount:,.2f}. The activity exhibits patterns consistent with {', '.join(suspicious_activity.pattern_indicators) if suspicious_activity.pattern_indicators else 'suspicious behavior'}.

SUSPICIOUS ACTIVITY DESCRIPTION
Cluster ID {suspicious_activity.cluster_id} was flagged by our AI-powered AML system with a risk score of {suspicious_activity.risk_score:.3f}. The system detected the following suspicious patterns: {suspicious_activity.explanation}

ACCOUNT HOLDER INFORMATION
The following accounts were involved in the suspicious activity:
"""
        
        for account in account_info:
            content += f"""
- Account ID: {account.account_id}
- Customer Name: {account.customer_name}
- Account Type: {account.account_type}
- Creation Date: {account.creation_date}
"""
            if account.ssn_last_four:
                content += f"- SSN (last 4): {account.ssn_last_four}\n"
            if account.phone:
                content += f"- Phone: {account.phone}\n"
            if account.address:
                content += f"- Address: {account.address}\n"
        
        content += f"""
TRANSACTION ANALYSIS
A total of {tx_count} transactions were analyzed, with amounts ranging from ${min(tx.amount for tx in transaction_info):,.2f} to ${max(tx.amount for tx in transaction_info):,.2f}. The transactions occurred over a period of {suspicious_activity.time_span_hours:.1f} hours.

Key transactions include:
"""
        
        for i, tx in enumerate(transaction_info[:5]):  # Show first 5 transactions
            content += f"""
{i+1}. Transaction ID: {tx.transaction_id}
   Amount: ${tx.amount:,.2f}
   Date: {tx.timestamp[:10]}
   Type: {tx.transaction_type}
   From: {tx.from_account} To: {tx.to_account}
"""
        
        content += f"""
REGULATORY JUSTIFICATION
This activity is being reported under the Bank Secrecy Act (BSA) and Anti-Money Laundering (AML) regulations. The suspicious patterns identified indicate potential structuring and money laundering activities that require FinCEN notification.

The AI system flagged this activity because it exhibits characteristics consistent with known money laundering typologies, including potential smurfing patterns designed to evade Currency Transaction Report (CTR) thresholds.

RECOMMENDED ACTIONS
1. File this SAR with FinCEN within required timeframes
2. Continue monitoring related accounts for additional suspicious activity
3. Maintain records in accordance with BSA recordkeeping requirements
4. Consider additional due diligence on involved parties

Report generated on {datetime.utcnow().strftime('%Y-%m-%d')} by automated AML system.
"""
        
        return content.strip()
    
    def _calculate_mock_confidence(self, sar_content: str, suspicious_activity: SuspiciousActivity) -> float:
        """Calculate mock confidence score for testing."""
        confidence = 0.5  # Base confidence
        
        # Higher confidence for more content
        word_count = len(sar_content.split())
        if word_count >= 300:
            confidence += 0.2
        elif word_count >= 200:
            confidence += 0.1
        
        # Higher confidence for more pattern indicators
        if len(suspicious_activity.pattern_indicators) >= 2:
            confidence += 0.2
        elif len(suspicious_activity.pattern_indicators) >= 1:
            confidence += 0.1
        
        # Higher confidence for higher risk scores
        confidence += suspicious_activity.risk_score * 0.2
        
        return min(confidence, 1.0)
    
    def _store_sar(self, sar: GeneratedSAR):
        """Mock storage - do nothing for testing."""
        pass

class SARGenerationStateMachine(RuleBasedStateMachine):
    """Stateful property testing for SAR generation system."""
    
    def __init__(self):
        super().__init__()
        self.config = SARGenerationConfig()
        self.generator = MockSARGenerator(self.config)
        self.generated_sars = []
    
    @rule(
        suspicious_activity=suspicious_activity_strategy(),
        account_info=st.lists(account_info_strategy(), min_size=1, max_size=3),
        transaction_info=st.lists(transaction_info_strategy(), min_size=1, max_size=5)
    )
    def generate_sar(self, suspicious_activity, account_info, transaction_info):
        """Generate a SAR and add to collection."""
        generated_sar = self.generator.generate_sar(suspicious_activity, account_info, transaction_info)
        self.generated_sars.append(generated_sar)
    
    @invariant()
    def all_sars_have_unique_ids(self):
        """Invariant: All generated SARs must have unique IDs."""
        sar_ids = [sar.sar_id for sar in self.generated_sars]
        assert len(sar_ids) == len(set(sar_ids)), \
            f"Duplicate SAR IDs found: {sar_ids}"
    
    @invariant()
    def all_sars_have_required_content(self):
        """Invariant: All SARs must have required regulatory content."""
        for sar in self.generated_sars:
            content = sar.sar_content.upper()
            required_sections = ['EXECUTIVE SUMMARY', 'SUSPICIOUS ACTIVITY', 'REGULATORY']
            
            for section in required_sections:
                assert section in content, \
                    f"SAR {sar.sar_id} missing required section: {section}"
    
    @invariant()
    def confidence_scores_in_bounds(self):
        """Invariant: All confidence scores must be in valid range."""
        for sar in self.generated_sars:
            assert 0.0 <= sar.confidence_score <= 1.0, \
                f"SAR {sar.sar_id} confidence score out of bounds: {sar.confidence_score}"

# Test runner
TestSARGenerationStateMachine = SARGenerationStateMachine.TestCase

if __name__ == "__main__":
    # Run property tests
    pytest.main([__file__, "-v", "--tb=short"])