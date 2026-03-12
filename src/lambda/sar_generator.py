"""
SAR Generator Lambda Function for Sentinel-AML
Integrates with Amazon Bedrock Claude 3 for automated SAR generation.
"""

import json
import logging
import boto3
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import os
from decimal import Decimal
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SARGenerationConfig:
    """Configuration for SAR generation."""
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    max_tokens: int = 4000
    temperature: float = 0.1  # Low temperature for consistent, factual output
    enable_pii_redaction: bool = True
    sar_retention_days: int = 2555  # 7 years
    confidence_threshold: float = 0.8
    max_generation_attempts: int = 3

@dataclass
class SuspiciousActivity:
    """Represents suspicious activity data for SAR generation."""
    cluster_id: str
    account_ids: List[str]
    transaction_ids: List[str]
    risk_score: float
    pattern_indicators: List[str]
    total_amount: float
    transaction_count: int
    time_span_hours: float
    explanation: str
    feature_importance: Dict[str, float]
    detection_timestamp: str

@dataclass
class AccountInfo:
    """Account information for SAR."""
    account_id: str
    customer_name: str
    account_type: str
    creation_date: str
    address: Optional[str] = None
    phone: Optional[str] = None
    ssn_last_four: Optional[str] = None
    risk_score: Optional[float] = None

@dataclass
class TransactionInfo:
    """Transaction information for SAR."""
    transaction_id: str
    amount: float
    timestamp: str
    transaction_type: str
    currency: str
    from_account: str
    to_account: str
    description: Optional[str] = None

@dataclass
class GeneratedSAR:
    """Generated SAR document."""
    sar_id: str
    cluster_id: str
    generation_timestamp: str
    confidence_score: float
    sar_content: str
    redacted_content: str
    metadata: Dict[str, Any]
    compliance_flags: List[str]
    review_required: bool
class SARGenerator:
    """Main SAR generation engine using Amazon Bedrock."""
    
    def __init__(self, config: SARGenerationConfig):
        self.config = config
        self.bedrock_runtime = boto3.client('bedrock-runtime')
        self.s3_client = boto3.client('s3')
        self.dynamodb = boto3.resource('dynamodb')
        
        # Initialize SAR storage table
        self.sar_table = self.dynamodb.Table(os.environ.get('SAR_TABLE_NAME', 'sentinel-aml-sars'))
        
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
        """Generate a complete SAR document."""
        logger.info(f"Generating SAR for cluster {suspicious_activity.cluster_id}")
        
        try:
            # Generate unique SAR ID
            sar_id = self._generate_sar_id(suspicious_activity.cluster_id)
            
            # Prepare context for SAR generation
            context = self._prepare_sar_context(suspicious_activity, account_info, transaction_info)
            
            # Generate SAR content using Bedrock
            sar_content, confidence_score = self._generate_sar_content(context)
            
            # Apply PII redaction
            redacted_content = self._redact_pii(sar_content) if self.config.enable_pii_redaction else sar_content
            
            # Validate SAR completeness
            compliance_flags = self._validate_sar_completeness(sar_content)
            
            # Determine if manual review is required
            review_required = self._requires_manual_review(confidence_score, compliance_flags)
            
            # Create metadata
            metadata = {
                'generation_model': self.config.bedrock_model_id,
                'generation_timestamp': datetime.utcnow().isoformat(),
                'risk_score': suspicious_activity.risk_score,
                'pattern_indicators': suspicious_activity.pattern_indicators,
                'account_count': len(account_info),
                'transaction_count': len(transaction_info),
                'total_amount': suspicious_activity.total_amount,
                'time_span_hours': suspicious_activity.time_span_hours
            }
            
            # Create SAR object
            generated_sar = GeneratedSAR(
                sar_id=sar_id,
                cluster_id=suspicious_activity.cluster_id,
                generation_timestamp=datetime.utcnow().isoformat(),
                confidence_score=confidence_score,
                sar_content=sar_content,
                redacted_content=redacted_content,
                metadata=metadata,
                compliance_flags=compliance_flags,
                review_required=review_required
            )
            
            # Store SAR
            self._store_sar(generated_sar)
            
            logger.info(f"SAR {sar_id} generated successfully (confidence: {confidence_score:.3f})")
            return generated_sar
            
        except Exception as e:
            logger.error(f"SAR generation failed for cluster {suspicious_activity.cluster_id}: {str(e)}")
            raise
    
    def _prepare_sar_context(self, suspicious_activity: SuspiciousActivity,
                           account_info: List[AccountInfo],
                           transaction_info: List[TransactionInfo]) -> Dict[str, Any]:
        """Prepare context data for SAR generation."""
        logger.debug("Preparing SAR context")
        
        # Sort transactions by timestamp
        sorted_transactions = sorted(transaction_info, key=lambda x: x.timestamp)
        
        # Calculate additional metrics
        transaction_amounts = [tx.amount for tx in transaction_info]
        avg_amount = sum(transaction_amounts) / len(transaction_amounts) if transaction_amounts else 0
        max_amount = max(transaction_amounts) if transaction_amounts else 0
        min_amount = min(transaction_amounts) if transaction_amounts else 0
        
        # Identify unique counterparties
        all_accounts = set()
        for tx in transaction_info:
            all_accounts.add(tx.from_account)
            all_accounts.add(tx.to_account)
        
        # Calculate time patterns
        if len(sorted_transactions) > 1:
            first_tx_time = datetime.fromisoformat(sorted_transactions[0].timestamp)
            last_tx_time = datetime.fromisoformat(sorted_transactions[-1].timestamp)
            actual_time_span = (last_tx_time - first_tx_time).total_seconds() / 3600
        else:
            actual_time_span = 0
        
        context = {
            'suspicious_activity': {
                'cluster_id': suspicious_activity.cluster_id,
                'risk_score': suspicious_activity.risk_score,
                'pattern_indicators': suspicious_activity.pattern_indicators,
                'explanation': suspicious_activity.explanation,
                'detection_timestamp': suspicious_activity.detection_timestamp
            },
            'accounts': [asdict(account) for account in account_info],
            'transactions': [asdict(tx) for tx in sorted_transactions],
            'summary_metrics': {
                'total_amount': suspicious_activity.total_amount,
                'transaction_count': len(transaction_info),
                'unique_accounts': len(all_accounts),
                'avg_amount': avg_amount,
                'max_amount': max_amount,
                'min_amount': min_amount,
                'time_span_hours': actual_time_span,
                'transactions_per_hour': len(transaction_info) / max(actual_time_span, 1)
            },
            'regulatory_context': {
                'ctr_threshold': 10000,
                'sar_threshold': 5000,
                'reporting_requirements': 'BSA/AML',
                'generation_date': datetime.utcnow().strftime('%Y-%m-%d')
            }
        }
        
        return context
    
    def _generate_sar_content(self, context: Dict[str, Any]) -> Tuple[str, float]:
        """Generate SAR content using Amazon Bedrock Claude 3."""
        logger.debug("Generating SAR content with Bedrock")
        
        # Create comprehensive prompt for SAR generation
        prompt = self._create_sar_prompt(context)
        
        for attempt in range(self.config.max_generation_attempts):
            try:
                # Call Bedrock Claude 3
                response = self.bedrock_runtime.invoke_model(
                    modelId=self.config.bedrock_model_id,
                    contentType='application/json',
                    accept='application/json',
                    body=json.dumps({
                        'anthropic_version': 'bedrock-2023-05-31',
                        'max_tokens': self.config.max_tokens,
                        'temperature': self.config.temperature,
                        'messages': [
                            {
                                'role': 'user',
                                'content': prompt
                            }
                        ]
                    })
                )
                
                # Parse response
                result = json.loads(response['body'].read())
                sar_content = result['content'][0]['text']
                
                # Calculate confidence based on content quality
                confidence_score = self._calculate_content_confidence(sar_content, context)
                
                if confidence_score >= self.config.confidence_threshold:
                    return sar_content, confidence_score
                else:
                    logger.warning(f"SAR generation attempt {attempt + 1} had low confidence: {confidence_score:.3f}")
                    if attempt == self.config.max_generation_attempts - 1:
                        return sar_content, confidence_score
                
            except Exception as e:
                logger.warning(f"SAR generation attempt {attempt + 1} failed: {str(e)}")
                if attempt == self.config.max_generation_attempts - 1:
                    raise
        
        raise Exception("Failed to generate SAR after maximum attempts")
    
    def _create_sar_prompt(self, context: Dict[str, Any]) -> str:
        """Create comprehensive prompt for SAR generation."""
        suspicious_activity = context['suspicious_activity']
        accounts = context['accounts']
        transactions = context['transactions']
        metrics = context['summary_metrics']
        
        # Format account information
        account_details = []
        for account in accounts:
            details = f"Account ID: {account['account_id']}, "
            details += f"Customer: {account['customer_name']}, "
            details += f"Type: {account['account_type']}, "
            details += f"Created: {account['creation_date']}"
            if account.get('risk_score'):
                details += f", Risk Score: {account['risk_score']:.2f}"
            account_details.append(details)
        
        # Format transaction summary
        transaction_summary = []
        for i, tx in enumerate(transactions[:10]):  # Limit to first 10 for brevity
            summary = f"{i+1}. ${tx['amount']:,.2f} on {tx['timestamp'][:10]} "
            summary += f"from {tx['from_account']} to {tx['to_account']} "
            summary += f"({tx['transaction_type']})"
            transaction_summary.append(summary)
        
        if len(transactions) > 10:
            transaction_summary.append(f"... and {len(transactions) - 10} additional transactions")
        
        prompt = f"""
You are an expert AML compliance officer tasked with generating a Suspicious Activity Report (SAR) based on the following analysis.

SUSPICIOUS ACTIVITY DETECTED:
- Cluster ID: {suspicious_activity['cluster_id']}
- Risk Score: {suspicious_activity['risk_score']:.3f}/1.0
- Pattern Indicators: {', '.join(suspicious_activity['pattern_indicators'])}
- AI Explanation: {suspicious_activity['explanation']}

INVOLVED ACCOUNTS:
{chr(10).join(account_details)}

TRANSACTION SUMMARY:
- Total Amount: ${metrics['total_amount']:,.2f}
- Transaction Count: {metrics['transaction_count']}
- Time Span: {metrics['time_span_hours']:.1f} hours
- Average Amount: ${metrics['avg_amount']:,.2f}
- Transaction Frequency: {metrics['transactions_per_hour']:.1f} per hour

KEY TRANSACTIONS:
{chr(10).join(transaction_summary)}

REGULATORY CONTEXT:
- CTR Threshold: ${context['regulatory_context']['ctr_threshold']:,}
- SAR Threshold: ${context['regulatory_context']['sar_threshold']:,}
- Reporting Date: {context['regulatory_context']['generation_date']}

Generate a comprehensive SAR that includes:

1. EXECUTIVE SUMMARY (2-3 sentences)
2. SUSPICIOUS ACTIVITY DESCRIPTION (detailed narrative)
3. ACCOUNT HOLDER INFORMATION (without PII)
4. TRANSACTION ANALYSIS (patterns and red flags)
5. REGULATORY JUSTIFICATION (specific BSA/AML violations)
6. RECOMMENDED ACTIONS

Requirements:
- Use formal, professional language appropriate for regulatory filing
- Include specific dollar amounts, dates, and transaction counts
- Explain why the activity is suspicious under BSA/AML regulations
- Do not include actual SSNs, full account numbers, or personal addresses
- Focus on patterns and behaviors rather than individual identity
- Provide clear regulatory justification for the SAR filing
- Keep the report concise but comprehensive (under 2000 words)

Generate the SAR now:
"""
        
        return prompt
    
    def _calculate_content_confidence(self, sar_content: str, context: Dict[str, Any]) -> float:
        """Calculate confidence score for generated SAR content."""
        confidence = 0.0
        
        # Check for required sections
        required_sections = [
            'EXECUTIVE SUMMARY', 'SUSPICIOUS ACTIVITY', 'ACCOUNT', 
            'TRANSACTION', 'REGULATORY', 'RECOMMENDED'
        ]
        
        sections_found = 0
        for section in required_sections:
            if section.lower() in sar_content.lower():
                sections_found += 1
        
        confidence += (sections_found / len(required_sections)) * 0.3
        
        # Check for specific data inclusion
        cluster_id = context['suspicious_activity']['cluster_id']
        total_amount = context['summary_metrics']['total_amount']
        
        if cluster_id in sar_content:
            confidence += 0.1
        if f"${total_amount:,.2f}" in sar_content or f"{total_amount:,.0f}" in sar_content:
            confidence += 0.1
        
        # Check for pattern indicators
        pattern_indicators = context['suspicious_activity']['pattern_indicators']
        patterns_mentioned = 0
        for pattern in pattern_indicators:
            if pattern.lower().replace('_', ' ') in sar_content.lower():
                patterns_mentioned += 1
        
        if pattern_indicators:
            confidence += (patterns_mentioned / len(pattern_indicators)) * 0.2
        
        # Check content length (should be substantial but not excessive)
        word_count = len(sar_content.split())
        if 500 <= word_count <= 2000:
            confidence += 0.2
        elif word_count > 200:
            confidence += 0.1
        
        # Check for regulatory language
        regulatory_terms = ['BSA', 'AML', 'suspicious', 'structuring', 'layering', 'CTR', 'FinCEN']
        regulatory_mentions = sum(1 for term in regulatory_terms if term.lower() in sar_content.lower())
        confidence += min(regulatory_mentions / len(regulatory_terms), 0.1)
        
        return min(confidence, 1.0)
    
    def _redact_pii(self, content: str) -> str:
        """Redact PII from SAR content."""
        logger.debug("Applying PII redaction")
        
        redacted_content = content
        
        for pii_type, pattern in self.pii_patterns.items():
            # Replace with redacted placeholder
            if pii_type == 'ssn':
                redacted_content = re.sub(pattern, 'XXX-XX-XXXX', redacted_content)
            elif pii_type == 'phone':
                redacted_content = re.sub(pattern, 'XXX-XXX-XXXX', redacted_content)
            elif pii_type == 'email':
                redacted_content = re.sub(pattern, '[EMAIL_REDACTED]', redacted_content)
            elif pii_type == 'account_number':
                redacted_content = re.sub(pattern, '[ACCOUNT_REDACTED]', redacted_content)
            elif pii_type == 'routing_number':
                redacted_content = re.sub(pattern, '[ROUTING_REDACTED]', redacted_content)
        
        # Additional redaction for common PII patterns
        # Redact full names that might appear (keep first name + last initial)
        name_pattern = r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\s+([A-Z][a-z]+)\b'
        redacted_content = re.sub(name_pattern, r'\1 \2 [LAST_NAME_REDACTED]', redacted_content)
        
        # Redact addresses (street numbers and names)
        address_pattern = r'\b\d+\s+[A-Z][a-z]+\s+(Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln)\b'
        redacted_content = re.sub(address_pattern, '[ADDRESS_REDACTED]', redacted_content)
        
        return redacted_content
    
    def _validate_sar_completeness(self, sar_content: str) -> List[str]:
        """Validate SAR completeness and return compliance flags."""
        logger.debug("Validating SAR completeness")
        
        flags = []
        
        # Check for required FinCEN SAR elements
        required_elements = {
            'suspicious activity description': ['suspicious', 'activity', 'pattern'],
            'account information': ['account', 'customer'],
            'transaction details': ['transaction', 'amount', 'date'],
            'regulatory basis': ['BSA', 'AML', 'regulation', 'violation'],
            'narrative explanation': ['because', 'due to', 'indicates', 'suggests']
        }
        
        for element, keywords in required_elements.items():
            if not any(keyword.lower() in sar_content.lower() for keyword in keywords):
                flags.append(f"MISSING_{element.upper().replace(' ', '_')}")
        
        # Check for minimum content length
        if len(sar_content.split()) < 200:
            flags.append("INSUFFICIENT_DETAIL")
        
        # Check for excessive length
        if len(sar_content.split()) > 3000:
            flags.append("EXCESSIVE_LENGTH")
        
        # Check for potential PII exposure
        for pii_type, pattern in self.pii_patterns.items():
            if re.search(pattern, sar_content):
                flags.append(f"POTENTIAL_PII_EXPOSURE_{pii_type.upper()}")
        
        return flags
    
    def _requires_manual_review(self, confidence_score: float, compliance_flags: List[str]) -> bool:
        """Determine if SAR requires manual review."""
        # Low confidence requires review
        if confidence_score < self.config.confidence_threshold:
            return True
        
        # Any compliance flags require review
        if compliance_flags:
            return True
        
        # High-risk cases require review
        return False
    
    def _generate_sar_id(self, cluster_id: str) -> str:
        """Generate unique SAR ID."""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        hash_input = f"{cluster_id}_{timestamp}".encode('utf-8')
        hash_suffix = hashlib.md5(hash_input).hexdigest()[:8]
        return f"SAR_{timestamp}_{hash_suffix}"
    
    def _store_sar(self, sar: GeneratedSAR):
        """Store SAR in DynamoDB and S3."""
        logger.debug(f"Storing SAR {sar.sar_id}")
        
        try:
            # Store metadata in DynamoDB
            self.sar_table.put_item(
                Item={
                    'sar_id': sar.sar_id,
                    'cluster_id': sar.cluster_id,
                    'generation_timestamp': sar.generation_timestamp,
                    'confidence_score': Decimal(str(sar.confidence_score)),
                    'compliance_flags': sar.compliance_flags,
                    'review_required': sar.review_required,
                    'metadata': sar.metadata,
                    'ttl': int((datetime.utcnow() + timedelta(days=self.config.sar_retention_days)).timestamp())
                }
            )
            
            # Store full SAR content in S3
            bucket_name = os.environ.get('SAR_BUCKET_NAME', 'sentinel-aml-sars')
            
            # Store original content
            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=f"sars/{sar.sar_id}/original.txt",
                Body=sar.sar_content,
                ContentType='text/plain',
                ServerSideEncryption='AES256'
            )
            
            # Store redacted content
            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=f"sars/{sar.sar_id}/redacted.txt",
                Body=sar.redacted_content,
                ContentType='text/plain',
                ServerSideEncryption='AES256'
            )
            
            # Store metadata as JSON
            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=f"sars/{sar.sar_id}/metadata.json",
                Body=json.dumps(asdict(sar), indent=2, default=str),
                ContentType='application/json',
                ServerSideEncryption='AES256'
            )
            
            logger.info(f"SAR {sar.sar_id} stored successfully")
            
        except Exception as e:
            logger.error(f"Failed to store SAR {sar.sar_id}: {str(e)}")
            raise

def lambda_handler(event, context):
    """AWS Lambda handler for SAR generation."""
    logger.info("Starting SAR generation Lambda")
    
    try:
        # Parse configuration
        config = SARGenerationConfig(
            bedrock_model_id=os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0'),
            max_tokens=int(os.environ.get('MAX_TOKENS', 4000)),
            temperature=float(os.environ.get('TEMPERATURE', 0.1)),
            enable_pii_redaction=os.environ.get('ENABLE_PII_REDACTION', 'true').lower() == 'true',
            confidence_threshold=float(os.environ.get('CONFIDENCE_THRESHOLD', 0.8))
        )
        
        # Initialize SAR generator
        sar_generator = SARGenerator(config)
        
        # Parse input event
        if 'Records' in event:
            # SQS/SNS event
            results = []
            for record in event['Records']:
                event_data = json.loads(record['body'])
                
                # Extract data from event
                suspicious_activity = SuspiciousActivity(**event_data['suspicious_activity'])
                account_info = [AccountInfo(**acc) for acc in event_data['account_info']]
                transaction_info = [TransactionInfo(**tx) for tx in event_data['transaction_info']]
                
                # Generate SAR
                generated_sar = sar_generator.generate_sar(
                    suspicious_activity, account_info, transaction_info
                )
                
                results.append({
                    'sar_id': generated_sar.sar_id,
                    'confidence_score': generated_sar.confidence_score,
                    'review_required': generated_sar.review_required,
                    'compliance_flags': generated_sar.compliance_flags
                })
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'Generated {len(results)} SARs',
                    'results': results
                })
            }
        
        else:
            # Direct invocation
            suspicious_activity = SuspiciousActivity(**event['suspicious_activity'])
            account_info = [AccountInfo(**acc) for acc in event['account_info']]
            transaction_info = [TransactionInfo(**tx) for tx in event['transaction_info']]
            
            # Generate SAR
            generated_sar = sar_generator.generate_sar(
                suspicious_activity, account_info, transaction_info
            )
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'sar_id': generated_sar.sar_id,
                    'confidence_score': generated_sar.confidence_score,
                    'review_required': generated_sar.review_required,
                    'compliance_flags': generated_sar.compliance_flags,
                    'generation_timestamp': generated_sar.generation_timestamp
                })
            }
    
    except Exception as e:
        logger.error(f"SAR generation failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'message': 'SAR generation failed'
            })
        }

if __name__ == "__main__":
    # For local testing
    test_suspicious_activity = SuspiciousActivity(
        cluster_id="test-cluster-001",
        account_ids=["ACC001", "ACC002"],
        transaction_ids=["TX001", "TX002", "TX003"],
        risk_score=0.85,
        pattern_indicators=["SMURFING_PATTERN", "RAPID_FIRE_PATTERN"],
        total_amount=28500.0,
        transaction_count=3,
        time_span_hours=2.5,
        explanation="Multiple transactions just below CTR threshold in short time period",
        feature_importance={"small_transaction_ratio": 0.8, "transaction_frequency": 0.6},
        detection_timestamp=datetime.utcnow().isoformat()
    )
    
    test_accounts = [
        AccountInfo(
            account_id="ACC001",
            customer_name="John D.",
            account_type="checking",
            creation_date="2023-01-15T00:00:00Z",
            risk_score=0.7
        )
    ]
    
    test_transactions = [
        TransactionInfo(
            transaction_id="TX001",
            amount=9500.0,
            timestamp="2024-01-01T10:00:00Z",
            transaction_type="wire",
            currency="USD",
            from_account="ACC001",
            to_account="ACC002"
        )
    ]
    
    config = SARGenerationConfig()
    generator = SARGenerator(config)
    
    try:
        result = generator.generate_sar(test_suspicious_activity, test_accounts, test_transactions)
        print(f"Generated SAR: {result.sar_id}")
        print(f"Confidence: {result.confidence_score:.3f}")
        print(f"Review Required: {result.review_required}")
    except Exception as e:
        print(f"Test failed: {e}")