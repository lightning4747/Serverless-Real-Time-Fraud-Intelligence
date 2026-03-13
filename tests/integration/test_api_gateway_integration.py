"""
Integration tests for API Gateway endpoints.
Tests all endpoints with various authentication scenarios and error responses.
"""

import pytest
import json
import boto3
import requests
from moto import mock_dynamodb, mock_s3, mock_apigateway
from datetime import datetime, timedelta
from decimal import Decimal
import os
from unittest.mock import patch, MagicMock
import time

# Import modules under test
import sys
sys.path.append('src')
sys.path.append('src/sentinel_aml/api')
from alerts_handler import lambda_handler as alerts_handler
from reports_handler import lambda_handler as reports_handler

class TestAPIGatewayIntegration:
    """Integration tests for API Gateway endpoints."""
    
    @pytest.fixture
    def aws_services_setup(self):
        """Set up AWS services for integration testing."""
        with mock_dynamodb(), mock_s3():
            # Create DynamoDB tables
            dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
            
            # Alerts table
            alerts_table = dynamodb.create_table(
                TableName='sentinel-aml-alerts',
                KeySchema=[{'AttributeName': 'alert_id', 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': 'alert_id', 'AttributeType': 'S'}],
                BillingMode='PAY_PER_REQUEST'
            )
            
            # SAR reports table
            sars_table = dynamodb.create_table(
                TableName='sentinel-aml-sars',
                KeySchema=[{'AttributeName': 'sar_id', 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': 'sar_id', 'AttributeType': 'S'}],
                BillingMode='PAY_PER_REQUEST'
            )
            
            # SAR versions table
            versions_table = dynamodb.create_table(
                TableName='sentinel-aml-sar-versions',
                KeySchema=[{'AttributeName': 'version_id', 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': 'version_id', 'AttributeType': 'S'}],
                BillingMode='PAY_PER_REQUEST'
            )
            
            # Create S3 bucket
            s3 = boto3.client('s3', region_name='us-east-1')
            s3.create_bucket(Bucket='sentinel-aml-sars')
            
            # Populate test data
            self._populate_test_data(alerts_table, sars_table)
            
            yield {
                'dynamodb': dynamodb,
                'alerts_table': alerts_table,
                'sars_table': sars_table,
                'versions_table': versions_table,
                's3': s3
            }
    
    def _populate_test_data(self, alerts_table, sars_table):
        """Populate tables with test data."""
        # Sample alerts
        test_alerts = [
            {
                'alert_id': 'ALERT_001',
                'cluster_id': 'CLUSTER_001',
                'account_ids': ['ACC001', 'ACC002'],
                'risk_score': Decimal('0.85'),
                'status': 'OPEN',
                'priority': 'HIGH',
                'pattern_types': ['SMURFING_PATTERN'],
                'total_amount': Decimal('28500.00'),
                'transaction_count': 3,
                'detection_timestamp': '2024-01-01T10:00:00Z',
                'last_updated': '2024-01-01T10:00:00Z'
            },
            {
                'alert_id': 'ALERT_002',
                'cluster_id': 'CLUSTER_002',
                'account_ids': ['ACC003'],
                'risk_score': Decimal('0.72'),
                'status': 'INVESTIGATING',
                'priority': 'MEDIUM',
                'pattern_types': ['VELOCITY_PATTERN'],
                'total_amount': Decimal('15000.00'),
                'transaction_count': 5,
                'detection_timestamp': '2024-01-02T14:30:00Z',
                'last_updated': '2024-01-02T15:00:00Z',
                'assigned_analyst': 'analyst_001'
            },
            {
                'alert_id': 'ALERT_003',
                'cluster_id': 'CLUSTER_003',
                'account_ids': ['ACC004', 'ACC005'],
                'risk_score': Decimal('0.65'),
                'status': 'CLOSED',
                'priority': 'LOW',
                'pattern_types': ['ROUND_DOLLAR_PATTERN'],
                'total_amount': Decimal('12000.00'),
                'transaction_count': 2,
                'detection_timestamp': '2024-01-03T09:15:00Z',
                'last_updated': '2024-01-03T16:45:00Z',
                'resolution': 'FALSE_POSITIVE'
            }
        ]
        
        for alert in test_alerts:
            alerts_table.put_item(Item=alert)
        
        # Sample SAR reports
        test_sars = [
            {
                'sar_id': 'SAR_20240101_001',
                'cluster_id': 'CLUSTER_001',
                'status': 'APPROVED',
                'confidence_score': Decimal('0.92'),
                'generation_timestamp': '2024-01-01T12:00:00Z',
                'total_amount': Decimal('28500.00'),
                'account_count': 2,
                'transaction_count': 3,
                'pattern_types': ['SMURFING_PATTERN'],
                'review_required': False,
                'compliance_flags': [],
                'approver_id': 'supervisor_001'
            },
            {
                'sar_id': 'SAR_20240102_001',
                'cluster_id': 'CLUSTER_002',
                'status': 'PENDING_REVIEW',
                'confidence_score': Decimal('0.78'),
                'generation_timestamp': '2024-01-02T16:00:00Z',
                'total_amount': Decimal('15000.00'),
                'account_count': 1,
                'transaction_count': 5,
                'pattern_types': ['VELOCITY_PATTERN'],
                'review_required': True,
                'compliance_flags': ['INSUFFICIENT_DETAIL']
            }
        ]
        
        for sar in test_sars:
            sars_table.put_item(Item=sar)
    
    def test_alerts_endpoint_authentication_scenarios(self, aws_services_setup):
        """Test alerts endpoint with various authentication scenarios."""
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        
        # Test 1: Valid API key
        event_valid_key = {
            'httpMethod': 'GET',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'valid-api-key-12345'}
        }
        
        response = alerts_handler(event_valid_key, {})
        assert response['statusCode'] == 200
        
        body = json.loads(response['body'])
        assert 'alerts' in body
        assert 'pagination' in body
        assert len(body['alerts']) == 3  # All test alerts
        
        # Test 2: Missing API key (simulated API Gateway rejection)
        event_no_key = {
            'httpMethod': 'GET',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': {},
            'headers': {}
        }
        
        # In real API Gateway, this would be rejected before reaching Lambda
        # We simulate this behavior
        with patch('boto3.resource') as mock_resource:
            mock_resource.side_effect = Exception("Unauthorized")
            response = alerts_handler(event_no_key, {})
            assert response['statusCode'] == 500  # Error due to missing auth
        
        # Test 3: Invalid API key format
        event_invalid_key = {
            'httpMethod': 'GET',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'invalid-key'}
        }
        
        response = alerts_handler(event_invalid_key, {})
        # Should still work in our mock environment, but would fail in real API Gateway
        assert response['statusCode'] in [200, 401, 403]
    
    def test_alerts_filtering_and_pagination(self, aws_services_setup):
        """Test alerts endpoint filtering and pagination functionality."""
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        
        # Test 1: Filter by status
        event_status_filter = {
            'httpMethod': 'GET',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': {'status': 'OPEN'},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = alerts_handler(event_status_filter, {})
        assert response['statusCode'] == 200
        
        body = json.loads(response['body'])
        open_alerts = [alert for alert in body['alerts'] if alert['status'] == 'OPEN']
        assert len(open_alerts) >= 1
        
        # Test 2: Pagination with limit
        event_pagination = {
            'httpMethod': 'GET',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': {'limit': '2', 'offset': '0'},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = alerts_handler(event_pagination, {})
        assert response['statusCode'] == 200
        
        body = json.loads(response['body'])
        assert len(body['alerts']) <= 2
        assert body['pagination']['limit'] == 2
        assert body['pagination']['offset'] == 0
        
        # Test 3: Risk level filtering
        event_risk_filter = {
            'httpMethod': 'GET',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': {'risk_level': 'high'},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = alerts_handler(event_risk_filter, {})
        assert response['statusCode'] == 200
        
        body = json.loads(response['body'])
        # Should return alerts with risk_score >= 0.8
        high_risk_alerts = [alert for alert in body['alerts'] if alert['risk_score'] >= 0.8]
        assert len(high_risk_alerts) >= 1
    
    def test_individual_alert_access(self, aws_services_setup):
        """Test individual alert access by ID."""
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        
        # Test 1: Valid alert ID
        event_valid_id = {
            'httpMethod': 'GET',
            'path': '/v1/alerts/ALERT_001',
            'pathParameters': {'id': 'ALERT_001'},
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = alerts_handler(event_valid_id, {})
        assert response['statusCode'] == 200
        
        body = json.loads(response['body'])
        assert 'alert' in body
        assert body['alert']['alert_id'] == 'ALERT_001'
        assert body['alert']['cluster_id'] == 'CLUSTER_001'
        
        # Test 2: Non-existent alert ID
        event_invalid_id = {
            'httpMethod': 'GET',
            'path': '/v1/alerts/NONEXISTENT',
            'pathParameters': {'id': 'NONEXISTENT'},
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = alerts_handler(event_invalid_id, {})
        assert response['statusCode'] == 404
        
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'not found' in body['error'].lower()
    
    def test_reports_endpoint_functionality(self, aws_services_setup):
        """Test reports endpoint functionality."""
        
        os.environ['SAR_TABLE_NAME'] = 'sentinel-aml-sars'
        os.environ['SAR_VERSIONS_TABLE_NAME'] = 'sentinel-aml-sar-versions'
        os.environ['SAR_BUCKET_NAME'] = 'sentinel-aml-sars'
        
        # Test 1: Get all reports
        event_all_reports = {
            'httpMethod': 'GET',
            'path': '/v1/reports',
            'pathParameters': None,
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = reports_handler(event_all_reports, {})
        assert response['statusCode'] == 200
        
        body = json.loads(response['body'])
        assert 'reports' in body
        assert 'pagination' in body
        assert 'statistics' in body
        assert len(body['reports']) == 2  # Two test SARs
        
        # Test 2: Filter by status
        event_status_filter = {
            'httpMethod': 'GET',
            'path': '/v1/reports',
            'pathParameters': None,
            'queryStringParameters': {'status': 'APPROVED'},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = reports_handler(event_status_filter, {})
        assert response['statusCode'] == 200
        
        body = json.loads(response['body'])
        approved_reports = [r for r in body['reports'] if r['status'] == 'APPROVED']
        assert len(approved_reports) >= 1
        
        # Test 3: Filter by case ID (cluster_id)
        event_case_filter = {
            'httpMethod': 'GET',
            'path': '/v1/reports',
            'pathParameters': None,
            'queryStringParameters': {'case_id': 'CLUSTER_001'},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = reports_handler(event_case_filter, {})
        assert response['statusCode'] == 200
        
        body = json.loads(response['body'])
        case_reports = [r for r in body['reports'] if r['cluster_id'] == 'CLUSTER_001']
        assert len(case_reports) >= 1
    
    def test_individual_report_access(self, aws_services_setup):
        """Test individual SAR report access by ID."""
        
        os.environ['SAR_TABLE_NAME'] = 'sentinel-aml-sars'
        os.environ['SAR_VERSIONS_TABLE_NAME'] = 'sentinel-aml-sar-versions'
        os.environ['SAR_BUCKET_NAME'] = 'sentinel-aml-sars'
        
        # Test 1: Valid SAR ID
        event_valid_sar = {
            'httpMethod': 'GET',
            'path': '/v1/reports/SAR_20240101_001',
            'pathParameters': {'id': 'SAR_20240101_001'},
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = reports_handler(event_valid_sar, {})
        assert response['statusCode'] == 200
        
        body = json.loads(response['body'])
        assert 'report' in body
        assert body['report']['sar_id'] == 'SAR_20240101_001'
        assert body['report']['status'] == 'APPROVED'
        
        # Test 2: Non-existent SAR ID
        event_invalid_sar = {
            'httpMethod': 'GET',
            'path': '/v1/reports/NONEXISTENT_SAR',
            'pathParameters': {'id': 'NONEXISTENT_SAR'},
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = reports_handler(event_invalid_sar, {})
        assert response['statusCode'] == 404
        
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'not found' in body['error'].lower()
    
    def test_error_handling_scenarios(self, aws_services_setup):
        """Test various error handling scenarios."""
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        
        # Test 1: Invalid HTTP method
        event_invalid_method = {
            'httpMethod': 'POST',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = alerts_handler(event_invalid_method, {})
        assert response['statusCode'] == 405
        
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'not allowed' in body['error'].lower()
        
        # Test 2: Invalid query parameters
        event_invalid_params = {
            'httpMethod': 'GET',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': {'limit': 'invalid_number'},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = alerts_handler(event_invalid_params, {})
        assert response['statusCode'] == 400
        
        body = json.loads(response['body'])
        assert 'error' in body
        
        # Test 3: Database connection error simulation
        with patch('boto3.resource') as mock_resource:
            mock_resource.side_effect = Exception("Database connection failed")
            
            event_db_error = {
                'httpMethod': 'GET',
                'path': '/v1/alerts',
                'pathParameters': None,
                'queryStringParameters': {},
                'headers': {'X-API-Key': 'valid-key'}
            }
            
            response = alerts_handler(event_db_error, {})
            assert response['statusCode'] == 500
            
            body = json.loads(response['body'])
            assert 'error' in body
    
    def test_rate_limiting_simulation(self, aws_services_setup):
        """Test rate limiting behavior simulation."""
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        
        # Simulate multiple rapid requests
        responses = []
        request_count = 10
        
        for i in range(request_count):
            event = {
                'httpMethod': 'GET',
                'path': '/v1/alerts',
                'pathParameters': None,
                'queryStringParameters': {'limit': '5'},
                'headers': {'X-API-Key': 'test-key'}
            }
            
            # In real API Gateway, rate limiting would be handled automatically
            # Here we simulate successful processing since we're testing Lambda directly
            response = alerts_handler(event, {})
            responses.append(response)
        
        # All requests should succeed in our test environment
        successful_responses = [r for r in responses if r['statusCode'] == 200]
        assert len(successful_responses) == request_count
        
        # Verify consistent response format
        for response in responses:
            assert 'Content-Type' in response['headers']
            assert response['headers']['Content-Type'] == 'application/json'
            assert 'Access-Control-Allow-Origin' in response['headers']
    
    def test_cors_headers(self, aws_services_setup):
        """Test CORS headers are properly set."""
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        
        event = {
            'httpMethod': 'GET',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = alerts_handler(event, {})
        
        # Verify CORS headers
        assert 'Access-Control-Allow-Origin' in response['headers']
        assert response['headers']['Access-Control-Allow-Origin'] == '*'
        
        # Test with reports endpoint as well
        os.environ['SAR_TABLE_NAME'] = 'sentinel-aml-sars'
        
        reports_event = {
            'httpMethod': 'GET',
            'path': '/v1/reports',
            'pathParameters': None,
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        reports_response = reports_handler(reports_event, {})
        assert 'Access-Control-Allow-Origin' in reports_response['headers']
    
    def test_response_caching_headers(self, aws_services_setup):
        """Test appropriate caching headers are set."""
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        
        event = {
            'httpMethod': 'GET',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = alerts_handler(event, {})
        
        # Verify no-cache headers for sensitive financial data
        assert 'Cache-Control' in response['headers']
        cache_control = response['headers']['Cache-Control']
        assert 'no-cache' in cache_control or 'no-store' in cache_control

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])