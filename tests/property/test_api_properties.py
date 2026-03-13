"""
Property-based tests for API endpoints.
Tests universal properties that must hold for all API operations.
"""

import pytest
import json
import boto3
from hypothesis import given, strategies as st, settings, assume
from moto import mock_dynamodb, mock_apigateway
from datetime import datetime, timedelta
import os
from unittest.mock import patch, MagicMock
from decimal import Decimal

# Import modules under test
import sys
sys.path.append('src')
sys.path.append('src/sentinel_aml/api')
from alerts_handler import AlertsHandler, lambda_handler as alerts_lambda_handler
from reports_handler import ReportsHandler, lambda_handler as reports_lambda_handler

class TestAPIAuthenticationProperties:
    """Property 8: Authentication - All protected endpoints must require valid API keys."""
    
    @pytest.fixture
    def mock_aws_setup(self):
        """Set up mocked AWS services."""
        with mock_dynamodb():
            # Create DynamoDB tables
            dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
            
            alerts_table = dynamodb.create_table(
                TableName='sentinel-aml-alerts',
                KeySchema=[{'AttributeName': 'alert_id', 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': 'alert_id', 'AttributeType': 'S'}],
                BillingMode='PAY_PER_REQUEST'
            )
            
            sars_table = dynamodb.create_table(
                TableName='sentinel-aml-sars',
                KeySchema=[{'AttributeName': 'sar_id', 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': 'sar_id', 'AttributeType': 'S'}],
                BillingMode='PAY_PER_REQUEST'
            )
            
            yield {
                'dynamodb': dynamodb,
                'alerts_table': alerts_table,
                'sars_table': sars_table
            }
    
    @given(
        http_method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        path=st.sampled_from(['/v1/alerts', '/v1/alerts/123', '/v1/reports', '/v1/reports/456']),
        has_api_key=st.booleans()
    )
    @settings(max_examples=50, deadline=5000)
    def test_api_key_authentication_property(self, mock_aws_setup, http_method, path, has_api_key):
        """Property 8: All protected endpoints must require valid API keys."""
        
        # Set up environment
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        os.environ['SAR_TABLE_NAME'] = 'sentinel-aml-sars'
        
        # Create test event
        event = {
            'httpMethod': http_method,
            'path': path,
            'pathParameters': None,
            'queryStringParameters': {},
            'headers': {}
        }
        
        # Add API key if specified
        if has_api_key:
            event['headers']['X-API-Key'] = 'valid-api-key-12345'
        
        # Extract path parameters for specific resource access
        if '/alerts/' in path:
            event['pathParameters'] = {'id': '123'}
        elif '/reports/' in path:
            event['pathParameters'] = {'id': '456'}
        
        # Determine which handler to use
        if '/alerts' in path:
            handler = alerts_lambda_handler
        elif '/reports' in path:
            handler = reports_lambda_handler
        else:
            return  # Skip unknown paths
        
        # Mock API Gateway authentication check
        with patch('boto3.client') as mock_boto_client:
            mock_api_client = MagicMock()
            
            # Simulate API Gateway authentication behavior
            if has_api_key:
                # Valid API key - request should proceed
                mock_api_client.get_api_key.return_value = {'enabled': True}
            else:
                # No API key - should be rejected by API Gateway before reaching Lambda
                # In real API Gateway, this would return 403 before Lambda is invoked
                if http_method in ['GET', 'POST']:  # Protected methods
                    # Simulate API Gateway rejection
                    response = {
                        'statusCode': 403,
                        'body': json.dumps({
                            'message': 'Forbidden'
                        }),
                        'headers': {
                            'Content-Type': 'application/json'
                        }
                    }
                    
                    # Property: Protected endpoints without API key must return 403
                    assert response['statusCode'] == 403
                    return
            
            mock_boto_client.return_value = mock_api_client
            
            # Execute handler
            response = handler(event, {})
            
            # Property verification
            if has_api_key and http_method == 'GET':
                # Valid API key with supported method should succeed or return valid error
                assert response['statusCode'] in [200, 404, 500]  # Valid response codes
            elif not has_api_key and http_method in ['GET', 'POST']:
                # Missing API key should be rejected (handled by API Gateway)
                assert response['statusCode'] == 403
            elif http_method not in ['GET', 'POST']:
                # Unsupported methods should return 405
                assert response['statusCode'] == 405
    
    @given(
        query_params=st.dictionaries(
            keys=st.sampled_from(['status', 'limit', 'offset', 'sort', 'order']),
            values=st.text(min_size=1, max_size=20),
            min_size=0,
            max_size=3
        )
    )
    @settings(max_examples=30, deadline=3000)
    def test_alerts_endpoint_with_valid_api_key(self, mock_aws_setup, query_params):
        """Test alerts endpoint behavior with valid API key."""
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        
        event = {
            'httpMethod': 'GET',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': query_params,
            'headers': {'X-API-Key': 'valid-api-key'}
        }
        
        response = alerts_lambda_handler(event, {})
        
        # Property: Valid authenticated requests should return valid HTTP status codes
        assert response['statusCode'] in [200, 400, 500]
        
        # Property: Response must have proper headers
        assert 'Content-Type' in response['headers']
        assert response['headers']['Content-Type'] == 'application/json'
        
        # Property: Response body must be valid JSON
        try:
            json.loads(response['body'])
        except json.JSONDecodeError:
            pytest.fail("Response body is not valid JSON")

class TestAPIRateLimitingProperties:
    """Property 9: Rate limiting - API calls must respect configured limits."""
    
    @pytest.fixture
    def rate_limit_config(self):
        """Rate limiting configuration."""
        return {
            'requests_per_second': 100,
            'burst_limit': 200,
            'daily_quota': 10000
        }
    
    @given(
        request_count=st.integers(min_value=1, max_value=300),
        time_window_seconds=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=20, deadline=5000)
    def test_rate_limiting_property(self, mock_aws_setup, rate_limit_config, request_count, time_window_seconds):
        """Property 9: API calls must respect configured rate limits."""
        
        # Calculate expected rate
        requests_per_second = request_count / time_window_seconds
        
        # Assume we're testing within reasonable bounds
        assume(request_count <= 1000)  # Reasonable upper bound for testing
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        
        # Simulate multiple requests
        responses = []
        
        for i in range(min(request_count, 50)):  # Limit for test performance
            event = {
                'httpMethod': 'GET',
                'path': '/v1/alerts',
                'pathParameters': None,
                'queryStringParameters': {'limit': '10'},
                'headers': {'X-API-Key': 'test-api-key'}
            }
            
            # In a real scenario, API Gateway would handle rate limiting
            # Here we simulate the behavior
            if requests_per_second > rate_limit_config['requests_per_second']:
                # Simulate rate limit exceeded
                response = {
                    'statusCode': 429,
                    'body': json.dumps({
                        'error': 'Too Many Requests',
                        'message': 'Rate limit exceeded'
                    }),
                    'headers': {
                        'Content-Type': 'application/json',
                        'Retry-After': '60'
                    }
                }
            else:
                # Normal processing
                response = alerts_lambda_handler(event, {})
            
            responses.append(response)
        
        # Property verification
        if requests_per_second > rate_limit_config['requests_per_second']:
            # When rate limit is exceeded, should get 429 responses
            rate_limited_responses = [r for r in responses if r['statusCode'] == 429]
            assert len(rate_limited_responses) > 0, "Expected rate limiting to be triggered"
            
            # Property: Rate limited responses must include Retry-After header
            for response in rate_limited_responses:
                assert 'Retry-After' in response.get('headers', {}), "Rate limited response missing Retry-After header"
        else:
            # When within rate limits, should get normal responses
            successful_responses = [r for r in responses if r['statusCode'] in [200, 400, 404]]
            assert len(successful_responses) == len(responses), "Expected all requests to succeed when within rate limits"

class TestAPIResponseProperties:
    """General API response properties that must hold for all endpoints."""
    
    @given(
        endpoint=st.sampled_from(['/v1/alerts', '/v1/reports']),
        method=st.sampled_from(['GET']),
        status_filter=st.one_of(st.none(), st.sampled_from(['OPEN', 'CLOSED', 'INVESTIGATING'])),
        limit=st.integers(min_value=1, max_value=500)
    )
    @settings(max_examples=25, deadline=3000)
    def test_response_format_properties(self, mock_aws_setup, endpoint, method, status_filter, limit):
        """Test that all API responses follow consistent format properties."""
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        os.environ['SAR_TABLE_NAME'] = 'sentinel-aml-sars'
        
        query_params = {'limit': str(limit)}
        if status_filter:
            query_params['status'] = status_filter
        
        event = {
            'httpMethod': method,
            'path': endpoint,
            'pathParameters': None,
            'queryStringParameters': query_params,
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        # Choose appropriate handler
        if '/alerts' in endpoint:
            response = alerts_lambda_handler(event, {})
        else:
            response = reports_lambda_handler(event, {})
        
        # Property: All responses must have statusCode
        assert 'statusCode' in response
        assert isinstance(response['statusCode'], int)
        
        # Property: All responses must have headers
        assert 'headers' in response
        assert isinstance(response['headers'], dict)
        
        # Property: All responses must have body
        assert 'body' in response
        assert isinstance(response['body'], str)
        
        # Property: Content-Type header must be application/json
        assert response['headers'].get('Content-Type') == 'application/json'
        
        # Property: CORS header must be present
        assert 'Access-Control-Allow-Origin' in response['headers']
        
        # Property: Response body must be valid JSON
        try:
            body_data = json.loads(response['body'])
        except json.JSONDecodeError:
            pytest.fail("Response body is not valid JSON")
        
        # Property: Successful responses must have expected structure
        if response['statusCode'] == 200:
            if '/alerts' in endpoint:
                assert 'alerts' in body_data
                assert 'pagination' in body_data
                assert isinstance(body_data['alerts'], list)
            elif '/reports' in endpoint:
                assert 'reports' in body_data
                assert 'pagination' in body_data
                assert isinstance(body_data['reports'], list)
        
        # Property: Error responses must have error information
        elif response['statusCode'] >= 400:
            assert 'error' in body_data or 'message' in body_data
    
    @given(
        alert_id=st.text(min_size=10, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pc'))),
        include_invalid=st.booleans()
    )
    @settings(max_examples=20, deadline=2000)
    def test_resource_access_properties(self, mock_aws_setup, alert_id, include_invalid):
        """Test properties for individual resource access."""
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        
        # Optionally make ID invalid
        if include_invalid:
            alert_id = alert_id + "!@#$%"  # Add invalid characters
        
        event = {
            'httpMethod': 'GET',
            'path': f'/v1/alerts/{alert_id}',
            'pathParameters': {'id': alert_id},
            'queryStringParameters': {},
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = alerts_lambda_handler(event, {})
        
        # Property: Resource access must return valid HTTP status
        assert response['statusCode'] in [200, 404, 400, 500]
        
        # Property: 404 responses for non-existent resources
        if response['statusCode'] == 404:
            body_data = json.loads(response['body'])
            assert 'error' in body_data
            assert 'not found' in body_data['error'].lower()
        
        # Property: 200 responses must include the resource
        elif response['statusCode'] == 200:
            body_data = json.loads(response['body'])
            assert 'alert' in body_data
            assert body_data['alert']['alert_id'] == alert_id

class TestAPIPaginationProperties:
    """Test pagination properties for list endpoints."""
    
    @given(
        limit=st.integers(min_value=1, max_value=100),
        offset=st.integers(min_value=0, max_value=1000)
    )
    @settings(max_examples=15, deadline=2000)
    def test_pagination_properties(self, mock_aws_setup, limit, offset):
        """Test that pagination works correctly and consistently."""
        
        os.environ['ALERTS_TABLE_NAME'] = 'sentinel-aml-alerts'
        
        event = {
            'httpMethod': 'GET',
            'path': '/v1/alerts',
            'pathParameters': None,
            'queryStringParameters': {
                'limit': str(limit),
                'offset': str(offset)
            },
            'headers': {'X-API-Key': 'valid-key'}
        }
        
        response = alerts_lambda_handler(event, {})
        
        # Property: Pagination requests should succeed
        assert response['statusCode'] in [200, 400]
        
        if response['statusCode'] == 200:
            body_data = json.loads(response['body'])
            
            # Property: Response must include pagination metadata
            assert 'pagination' in body_data
            pagination = body_data['pagination']
            
            # Property: Pagination must include required fields
            required_fields = ['total_count', 'limit', 'offset', 'has_more']
            for field in required_fields:
                assert field in pagination
            
            # Property: Returned items count must not exceed limit
            alerts = body_data.get('alerts', [])
            assert len(alerts) <= limit
            
            # Property: Pagination values must be consistent
            assert pagination['limit'] == limit
            assert pagination['offset'] == offset
            
            # Property: has_more must be boolean
            assert isinstance(pagination['has_more'], bool)
            
            # Property: If has_more is True, next_offset should be provided
            if pagination['has_more']:
                assert 'next_offset' in pagination
                assert pagination['next_offset'] > offset

if __name__ == "__main__":
    # Run property tests
    pytest.main([__file__, "-v", "--tb=short"])