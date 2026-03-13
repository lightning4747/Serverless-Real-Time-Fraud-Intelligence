"""
Integration tests for Amazon Bedrock SAR generation.
Tests end-to-end SAR generation workflow and error handling.
"""

import pytest
import json
import boto3
from moto import mock_bedrock_runtime, mock_dynamodb, mock_s3
from datetime import datetime, timedelta
from decimal import Decimal
import os
from unittest.mock import patch, MagicMock

# Import modules under test
import sys
sys.path.append('src')
sys.path.append('src/lambda')
import sar_generator
from sar_generator import (
    SARGenerator, SARGenerationConfig, SuspiciousActivity, 
    AccountInfo, TransactionInfo, lambda_handler
)
from sentinel_aml.compliance.fincen_sar_formatter import FinCENSARFormatter
from sentinel_aml.compliance.sar_versioning import SARVersionManager

class TestBedrockIntegration:
    """Integration tests for Bedrock SAR generation."""
    
    @pytest.fixture
    def mock_aws_services(self):
        """Set up mocked AWS services."""
        with mock_bedrock_runtime(), mock_dynamodb(), mock_s3():
            # Create DynamoDB table
            dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
            table = dynamodb.create_table(
                TableName='sentinel-aml-sars',
                KeySchema=[{'AttributeName': 'sar_id', 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': 'sar_id', 'AttributeType': 'S'}],
                BillingMode='PAY_PER_REQUEST'
            )
            
            # Create S3 bucket
            s3 = boto3.client('s3', region_name='us-east-1')
            s3.create_bucket(Bucket='sentinel-aml-sars')
            
            yield {
                'dynamodb': dynamodb,
                'table': table,
                's3': s3
            }
    
    @pytest.fixture
    def sample_suspicious_activity(self):
        """Sample suspicious activity data."""
        return SuspiciousActivity(
            cluster_id="test-cluster-001",
            account_ids=["ACC001", "ACC002"],
            transaction_ids=["TX001", "TX002", "TX003"],
            risk_score=0.85,
            pattern_indicators=["SMURFING_PATTERN", "RAPID_FIRE_PATTERN"],
            total_amount=28500.0,
            transaction_count=3,
            time_span_hours=2.5,
            explanation="Multiple transactions just below CTR threshold",
            feature_importance={"small_transaction_ratio": 0.8},
            detection_timestamp=datetime.utcnow().isoformat()
        )
    
    @pytest.fixture
    def sample_accounts(self):
        """Sample account data."""
        return [
            AccountInfo(
                account_id="ACC001",
                customer_name="John D.",
                account_type="checking",
                creation_date="2023-01-15T00:00:00Z",
                risk_score=0.7
            ),
            AccountInfo(
                account_id="ACC002",
                customer_name="Jane S.",
                account_type="savings",
                creation_date="2023-02-20T00:00:00Z",
                risk_score=0.6
            )
        ]
    
    @pytest.fixture
    def sample_transactions(self):
        """Sample transaction data."""
        return [
            TransactionInfo(
                transaction_id="TX001",
                amount=9500.0,
                timestamp="2024-01-01T10:00:00Z",
                transaction_type="wire",
                currency="USD",
                from_account="ACC001",
                to_account="ACC002"
            ),
            TransactionInfo(
                transaction_id="TX002",
                amount=9800.0,
                timestamp="2024-01-01T11:30:00Z",
                transaction_type="wire",
                currency="USD",
                from_account="ACC001",
                to_account="ACC002"
            ),
            TransactionInfo(
                transaction_id="TX003",
                amount=9200.0,
                timestamp="2024-01-01T12:45:00Z",
                transaction_type="wire",
                currency="USD",
                from_account="ACC001",
                to_account="ACC002"
            )
        ]
    
    def test_successful_sar_generation(self, mock_aws_services, sample_suspicious_activity,
                                     sample_accounts, sample_transactions):
        """Test successful end-to-end SAR generation."""
        # Mock Bedrock response
        mock_bedrock_response = {
            'body': MagicMock()
        }
        mock_bedrock_response['body'].read.return_value = json.dumps({
            'content': [{
                'text': '''SUSPICIOUS ACTIVITY REPORT

EXECUTIVE SUMMARY
This report documents suspicious activity involving multiple wire transfers totaling $28,500 executed in a 2.5-hour period, exhibiting patterns consistent with structuring to avoid CTR reporting requirements.

SUSPICIOUS ACTIVITY DESCRIPTION
The subject accounts executed three wire transfers on January 1, 2024, each just below the $10,000 CTR threshold. The transactions occurred in rapid succession and appear designed to avoid regulatory reporting requirements under the Bank Secrecy Act.

ACCOUNT HOLDER INFORMATION
Primary Account: ACC001 (John D.) - Checking account opened January 15, 2023
Secondary Account: ACC002 (Jane S.) - Savings account opened February 20, 2023

TRANSACTION ANALYSIS
- TX001: $9,500 at 10:00 AM
- TX002: $9,800 at 11:30 AM  
- TX003: $9,200 at 12:45 PM
Total: $28,500 in 2.75 hours

REGULATORY JUSTIFICATION
This activity violates BSA requirements regarding structuring under 31 USC 5324. The pattern of keeping individual transactions below $10,000 while conducting multiple related transactions suggests intentional avoidance of CTR filing requirements.

RECOMMENDED ACTIONS
File SAR with FinCEN within 30 days. Consider account monitoring and potential account closure if pattern continues.'''
            }]
        }).encode('utf-8')
        
        with patch('boto3.client') as mock_boto_client:
            mock_bedrock_client = MagicMock()
            mock_bedrock_client.invoke_model.return_value = mock_bedrock_response
            mock_boto_client.return_value = mock_bedrock_client
            
            # Set environment variables
            os.environ['SAR_TABLE_NAME'] = 'sentinel-aml-sars'
            os.environ['SAR_BUCKET_NAME'] = 'sentinel-aml-sars'
            
            # Create SAR generator
            config = SARGenerationConfig(confidence_threshold=0.7)
            generator = SARGenerator(config)
            
            # Generate SAR
            result = generator.generate_sar(
                sample_suspicious_activity,
                sample_accounts,
                sample_transactions
            )
            
            # Verify results
            assert result.sar_id is not None
            assert result.cluster_id == "test-cluster-001"
            assert result.confidence_score >= 0.7
            assert "SUSPICIOUS ACTIVITY REPORT" in result.sar_content
            assert "structuring" in result.sar_content.lower()
            assert "$28,500" in result.sar_content
            assert not result.review_required  # High confidence, no compliance flags
            
            # Verify Bedrock was called
            mock_bedrock_client.invoke_model.assert_called_once()
            call_args = mock_bedrock_client.invoke_model.call_args
            assert call_args[1]['modelId'] == config.bedrock_model_id
    
    def test_low_confidence_sar_generation(self, mock_aws_services, sample_suspicious_activity,
                                         sample_accounts, sample_transactions):
        """Test SAR generation with low confidence response."""
        # Mock low-quality Bedrock response
        mock_bedrock_response = {
            'body': MagicMock()
        }
        mock_bedrock_response['body'].read.return_value = json.dumps({
            'content': [{
                'text': 'Short suspicious activity report without required details.'
            }]
        }).encode('utf-8')
        
        with patch('boto3.client') as mock_boto_client:
            mock_bedrock_client = MagicMock()
            mock_bedrock_client.invoke_model.return_value = mock_bedrock_response
            mock_boto_client.return_value = mock_bedrock_client
            
            os.environ['SAR_TABLE_NAME'] = 'sentinel-aml-sars'
            os.environ['SAR_BUCKET_NAME'] = 'sentinel-aml-sars'
            
            config = SARGenerationConfig(confidence_threshold=0.8)
            generator = SARGenerator(config)
            
            result = generator.generate_sar(
                sample_suspicious_activity,
                sample_accounts,
                sample_transactions
            )
            
            # Verify low confidence handling
            assert result.confidence_score < 0.8
            assert result.review_required  # Low confidence requires review
            assert len(result.compliance_flags) > 0  # Should have compliance issues
    
    def test_bedrock_error_handling(self, mock_aws_services, sample_suspicious_activity,
                                  sample_accounts, sample_transactions):
        """Test error handling when Bedrock fails."""
        with patch('boto3.client') as mock_boto_client:
            mock_bedrock_client = MagicMock()
            mock_bedrock_client.invoke_model.side_effect = Exception("Bedrock service error")
            mock_boto_client.return_value = mock_bedrock_client
            
            os.environ['SAR_TABLE_NAME'] = 'sentinel-aml-sars'
            os.environ['SAR_BUCKET_NAME'] = 'sentinel-aml-sars'
            
            config = SARGenerationConfig(max_generation_attempts=2)
            generator = SARGenerator(config)
            
            # Should raise exception after max attempts
            with pytest.raises(Exception) as exc_info:
                generator.generate_sar(
                    sample_suspicious_activity,
                    sample_accounts,
                    sample_transactions
                )
            
            assert "Failed to generate SAR after maximum attempts" in str(exc_info.value)
            assert mock_bedrock_client.invoke_model.call_count == 2
    
    def test_retry_logic_with_eventual_success(self, mock_aws_services, sample_suspicious_activity,
                                             sample_accounts, sample_transactions):
        """Test retry logic with eventual success."""
        # First call fails, second succeeds
        mock_responses = [
            Exception("Temporary error"),
            {
                'body': MagicMock()
            }
        ]
        
        mock_responses[1]['body'].read.return_value = json.dumps({
            'content': [{
                'text': '''SUSPICIOUS ACTIVITY REPORT
                
EXECUTIVE SUMMARY
Successful SAR generation after retry.

SUSPICIOUS ACTIVITY DESCRIPTION
Multiple transactions below CTR threshold indicating potential structuring.

ACCOUNT HOLDER INFORMATION
Account ACC001 involved in suspicious activity.

TRANSACTION ANALYSIS
Three transactions totaling $28,500.

REGULATORY JUSTIFICATION
Potential BSA violation requiring SAR filing.

RECOMMENDED ACTIONS
File SAR and monitor account.'''
            }]
        }).encode('utf-8')
        
        with patch('boto3.client') as mock_boto_client:
            mock_bedrock_client = MagicMock()
            mock_bedrock_client.invoke_model.side_effect = mock_responses
            mock_boto_client.return_value = mock_bedrock_client
            
            os.environ['SAR_TABLE_NAME'] = 'sentinel-aml-sars'
            os.environ['SAR_BUCKET_NAME'] = 'sentinel-aml-sars'
            
            config = SARGenerationConfig(max_generation_attempts=3, confidence_threshold=0.6)
            generator = SARGenerator(config)
            
            result = generator.generate_sar(
                sample_suspicious_activity,
                sample_accounts,
                sample_transactions
            )
            
            # Should succeed on second attempt
            assert result.sar_id is not None
            assert mock_bedrock_client.invoke_model.call_count == 2
            assert "Successful SAR generation after retry" in result.sar_content
    
    def test_lambda_handler_sqs_event(self, mock_aws_services):
        """Test Lambda handler with SQS event."""
        sqs_event = {
            'Records': [
                {
                    'body': json.dumps({
                        'suspicious_activity': {
                            'cluster_id': 'test-cluster-001',
                            'account_ids': ['ACC001'],
                            'transaction_ids': ['TX001'],
                            'risk_score': 0.85,
                            'pattern_indicators': ['SMURFING_PATTERN'],
                            'total_amount': 9500.0,
                            'transaction_count': 1,
                            'time_span_hours': 1.0,
                            'explanation': 'Test suspicious activity',
                            'feature_importance': {'test': 0.8},
                            'detection_timestamp': datetime.utcnow().isoformat()
                        },
                        'account_info': [
                            {
                                'account_id': 'ACC001',
                                'customer_name': 'Test User',
                                'account_type': 'checking',
                                'creation_date': '2023-01-01T00:00:00Z'
                            }
                        ],
                        'transaction_info': [
                            {
                                'transaction_id': 'TX001',
                                'amount': 9500.0,
                                'timestamp': '2024-01-01T10:00:00Z',
                                'transaction_type': 'wire',
                                'currency': 'USD',
                                'from_account': 'ACC001',
                                'to_account': 'ACC002'
                            }
                        ]
                    })
                }
            ]
        }
        
        mock_bedrock_response = {
            'body': MagicMock()
        }
        mock_bedrock_response['body'].read.return_value = json.dumps({
            'content': [{'text': 'Test SAR content with required sections'}]
        }).encode('utf-8')
        
        with patch('boto3.client') as mock_boto_client:
            mock_bedrock_client = MagicMock()
            mock_bedrock_client.invoke_model.return_value = mock_bedrock_response
            mock_boto_client.return_value = mock_bedrock_client
            
            os.environ['SAR_TABLE_NAME'] = 'sentinel-aml-sars'
            os.environ['SAR_BUCKET_NAME'] = 'sentinel-aml-sars'
            
            response = lambda_handler(sqs_event, {})
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'Generated 1 SARs' in body['message']
            assert len(body['results']) == 1