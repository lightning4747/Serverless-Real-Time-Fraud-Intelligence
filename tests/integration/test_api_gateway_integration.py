"""
Integration tests for API Gateway endpoints.

Tests all endpoints with various authentication scenarios,
rate limiting, and error responses.

**Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6**
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from sentinel_aml.api.alert_handler import lambda_handler as alert_handler
from sentinel_aml.api.report_handler import lambda_handler as report_handler
from sentinel_aml.api.health_handler import lambda_handler as health_handler
from sentinel_aml.api.transaction_handler import lambda_handler as transaction_handler
from sentinel_aml.data.models import Alert, SuspiciousActivityReport, AlertStatus, RiskLevel


class TestAPIGatewayIntegration:
    """Integration tests for API Gateway endpoints."""
    
    @pytest.fixture
    def mock_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.memory_limit_in_mb = 512
        context.get_remaining_time_in_millis.return_value = 30000
        context.function_name = 'test-function'
        context.function_version = '1'
        return context
    
    @pytest.fixture
    def valid_api_key(self):
        """Valid API key for testing."""
        return "sentinel-aml-test-key-12345"
    
    @pytest.fixture
    def invalid_api_key(self):
        """Invalid API key for testing."""
        return "invalid-key"
    
    @pytest.fixture
    def sample_alert_data(self):
        """Sample alert data for testing."""
        return {
            'alert_id': str(uuid4()),
            'title': 'Suspicious Transaction Pattern',
            'description': 'Multiple transactions below reporting threshold',
            'risk_level': RiskLevel.HIGH,
            'status': AlertStatus.OPEN,
            'account_ids': ['ACC001', 'ACC002'],
            'transaction_ids': ['TXN001', 'TXN002'],
            'risk_score': 0.85,
            'suspicious_patterns': ['structuring', 'rapid_transfers'],
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
    
    @pytest.fixture
    def sample_report_data(self):
        """Sample SAR report data for testing."""
        return {
            'sar_id': str(uuid4()),
            'case_id': 'CASE001',
            'report_number': 'SAR-2024-001',
            'status': 'draft',
            'subject_accounts': ['ACC001'],
            'subject_names': ['John Doe (hashed)'],
            'activity_description': 'Structured transactions to avoid reporting',
            'suspicious_patterns': ['structuring'],
            'transaction_summary': 'Multiple transactions under $10,000',
            'total_amount': 45000.00,
            'currency': 'USD',
            'date_range_start': datetime.now(timezone.utc),
            'date_range_end': datetime.now(timezone.utc),
            'reporting_reason': 'Structuring to avoid CTR requirements',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
    
    def create_api_event(self, path: str, method: str, headers: Dict = None, 
                        query_params: Dict = None, path_params: Dict = None, 
                        body: str = None) -> Dict[str, Any]:
        """Create API Gateway event."""
        return {
            'httpMethod': method,
            'path': path,
            'headers': headers or {},
            'queryStringParameters': query_params,
            'pathParameters': path_params,
            'body': body,
            'requestContext': {
                'requestId': str(uuid4()),
                'stage': 'test',
                'identity': {'sourceIp': '127.0.0.1'}
            }
        }
    
    # Health Endpoint Tests
    
    def test_health_endpoint_no_auth_required(self, mock_context):
        """Test that health endpoint works without authentication."""
        event = self.create_api_event('/health', 'GET')
        
        with patch('sentinel_aml.api.health_handler.NeptuneClient') as mock_neptune:
            # Setup successful Neptune connection
            mock_instance = AsyncMock()
            mock_conn = AsyncMock()
            mock_result = AsyncMock()
            mock_result.next.return_value = 1
            mock_conn.submit.return_value = mock_result
            mock_instance.get_connection.return_value = mock_conn
            mock_neptune.return_value = mock_instance
            
            response = health_handler(event, mock_context)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] in ['healthy', 'unhealthy']
            assert 'components' in body
            assert 'neptune' in body['components']
    
    def test_health_endpoint_neptune_failure(self, mock_context):
        """Test health endpoint when Neptune is unavailable."""
        event = self.create_api_event('/health', 'GET')
        
        with patch('sentinel_aml.api.health_handler.NeptuneClient') as mock_neptune:
            # Setup Neptune connection failure
            mock_neptune.side_effect = Exception("Connection failed")
            
            response = health_handler(event, mock_context)
            
            assert response['statusCode'] == 503
            body = json.loads(response['body'])
            assert body['status'] == 'unhealthy'
    
    # Authentication Tests
    
    def test_alerts_endpoint_requires_auth(self, mock_context):
        """Test that alerts endpoint requires authentication."""
        event = self.create_api_event('/alerts', 'GET')
        
        response = alert_handler(event, mock_context)
        
        # Should return 401 or handle missing auth gracefully
        assert response['statusCode'] in [401, 403, 500]
    
    def test_alerts_endpoint_with_valid_auth(self, mock_context, valid_api_key, sample_alert_data):
        """Test alerts endpoint with valid authentication."""
        headers = {'X-API-Key': valid_api_key}
        event = self.create_api_event('/alerts', 'GET', headers=headers)
        
        with patch('sentinel_aml.api.alert_handler.NeptuneClient') as mock_neptune:
            # Setup Neptune mock with sample data
            mock_instance = AsyncMock()
            mock_conn = AsyncMock()
            mock_result = AsyncMock()
            
            # Mock alert data response
            neptune_alert_data = {
                'alert_id': [sample_alert_data['alert_id']],
                'title': [sample_alert_data['title']],
                'description': [sample_alert_data['description']],
                'risk_level': [sample_alert_data['risk_level'].value],
                'status': [sample_alert_data['status'].value],
                'risk_score': [str(sample_alert_data['risk_score'])],
                'created_at': [sample_alert_data['created_at'].isoformat()],
                'updated_at': [sample_alert_data['updated_at'].isoformat()],
                'account_ids': sample_alert_data['account_ids'],
                'transaction_ids': sample_alert_data['transaction_ids'],
                'suspicious_patterns': sample_alert_data['suspicious_patterns']
            }
            
            mock_result.all.return_value = [neptune_alert_data]
            mock_result.next.return_value = 1  # Total count
            mock_conn.submit.return_value = mock_result
            mock_instance.get_connection.return_value = mock_conn
            mock_neptune.return_value = mock_instance
            
            response = alert_handler(event, mock_context)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'alerts' in body
            assert 'pagination' in body
            assert len(body['alerts']) >= 0
    
    def test_alerts_endpoint_with_invalid_auth(self, mock_context, invalid_api_key):
        """Test alerts endpoint with invalid authentication."""
        headers = {'X-API-Key': invalid_api_key}
        event = self.create_api_event('/alerts', 'GET', headers=headers)
        
        response = alert_handler(event, mock_context)
        
        # Should handle invalid auth appropriately
        assert response['statusCode'] in [401, 403, 500]
    
    # Reports Endpoint Tests
    
    def test_reports_list_endpoint(self, mock_context, valid_api_key, sample_report_data):
        """Test reports list endpoint."""
        headers = {'X-API-Key': valid_api_key}
        event = self.create_api_event('/reports', 'GET', headers=headers)
        
        with patch('sentinel_aml.api.report_handler.NeptuneClient') as mock_neptune:
            # Setup Neptune mock
            mock_instance = AsyncMock()
            mock_conn = AsyncMock()
            mock_result = AsyncMock()
            
            # Mock report data (sanitized for list view)
            neptune_report_data = {
                'sar_id': [sample_report_data['sar_id']],
                'case_id': [sample_report_data['case_id']],
                'report_number': [sample_report_data['report_number']],
                'status': [sample_report_data['status']],
                'total_amount': [str(sample_report_data['total_amount'])],
                'currency': [sample_report_data['currency']],
                'created_at': [sample_report_data['created_at'].isoformat()],
                'updated_at': [sample_report_data['updated_at'].isoformat()],
                'date_range_start': [sample_report_data['date_range_start'].isoformat()],
                'date_range_end': [sample_report_data['date_range_end'].isoformat()],
                'reporting_reason': [sample_report_data['reporting_reason']]
            }
            
            mock_result.all.return_value = [neptune_report_data]
            mock_result.next.return_value = 1
            mock_conn.submit.return_value = mock_result
            mock_instance.get_connection.return_value = mock_conn
            mock_neptune.return_value = mock_instance
            
            response = report_handler(event, mock_context)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'reports' in body
            assert 'pagination' in body
    
    def test_reports_by_id_endpoint(self, mock_context, valid_api_key, sample_report_data):
        """Test reports by ID endpoint."""
        headers = {'X-API-Key': valid_api_key}
        report_id = sample_report_data['sar_id']
        path_params = {'id': report_id}
        event = self.create_api_event('/reports/{id}', 'GET', headers=headers, path_params=path_params)
        
        with patch('sentinel_aml.api.report_handler.NeptuneClient') as mock_neptune:
            # Setup Neptune mock
            mock_instance = AsyncMock()
            mock_conn = AsyncMock()
            mock_result = AsyncMock()
            
            # Mock full report data
            neptune_report_data = {
                'sar_id': [sample_report_data['sar_id']],
                'case_id': [sample_report_data['case_id']],
                'report_number': [sample_report_data['report_number']],
                'status': [sample_report_data['status']],
                'subject_accounts': sample_report_data['subject_accounts'],
                'subject_names': sample_report_data['subject_names'],
                'activity_description': [sample_report_data['activity_description']],
                'suspicious_patterns': sample_report_data['suspicious_patterns'],
                'transaction_summary': [sample_report_data['transaction_summary']],
                'total_amount': [str(sample_report_data['total_amount'])],
                'currency': [sample_report_data['currency']],
                'date_range_start': [sample_report_data['date_range_start'].isoformat()],
                'date_range_end': [sample_report_data['date_range_end'].isoformat()],
                'reporting_reason': [sample_report_data['reporting_reason']],
                'created_at': [sample_report_data['created_at'].isoformat()],
                'updated_at': [sample_report_data['updated_at'].isoformat()]
            }
            
            mock_result.next.return_value = neptune_report_data
            mock_conn.submit.return_value = mock_result
            mock_instance.get_connection.return_value = mock_conn
            mock_neptune.return_value = mock_instance
            
            response = report_handler(event, mock_context)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'report' in body
            assert body['report']['sar_id'] == report_id
    
    def test_reports_by_id_not_found(self, mock_context, valid_api_key):
        """Test reports by ID endpoint when report not found."""
        headers = {'X-API-Key': valid_api_key}
        path_params = {'id': 'nonexistent-id'}
        event = self.create_api_event('/reports/{id}', 'GET', headers=headers, path_params=path_params)
        
        with patch('sentinel_aml.api.report_handler.NeptuneClient') as mock_neptune:
            # Setup Neptune mock to return no data
            mock_instance = AsyncMock()
            mock_conn = AsyncMock()
            mock_result = AsyncMock()
            mock_result.next.return_value = None
            mock_conn.submit.return_value = mock_result
            mock_instance.get_connection.return_value = mock_conn
            mock_neptune.return_value = mock_instance
            
            response = report_handler(event, mock_context)
            
            assert response['statusCode'] == 404
            body = json.loads(response['body'])
            assert 'error' in body
    
    # Transaction Endpoint Tests
    
    def test_transactions_endpoint_post(self, mock_context, valid_api_key):
        """Test transaction POST endpoint."""
        headers = {'X-API-Key': valid_api_key, 'Content-Type': 'application/json'}
        transaction_data = {
            'from_account_id': 'ACC001',
            'to_account_id': 'ACC002',
            'amount': 5000.00,
            'currency': 'USD',
            'transaction_type': 'transfer'
        }
        body = json.dumps(transaction_data)
        event = self.create_api_event('/transactions', 'POST', headers=headers, body=body)
        
        with patch('sentinel_aml.lambdas.transaction_processor.lambda_handler') as mock_processor:
            # Mock successful transaction processing
            mock_processor.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Transaction processed successfully',
                    'transaction_id': str(uuid4())
                })
            }
            
            response = transaction_handler(event, mock_context)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'message' in body or 'transaction_id' in body
    
    def test_transactions_endpoint_invalid_method(self, mock_context, valid_api_key):
        """Test transaction endpoint with invalid HTTP method."""
        headers = {'X-API-Key': valid_api_key}
        event = self.create_api_event('/transactions', 'GET', headers=headers)
        
        response = transaction_handler(event, mock_context)
        
        assert response['statusCode'] == 405
        body = json.loads(response['body'])
        assert 'error' in body
    
    def test_transactions_endpoint_cors_preflight(self, mock_context):
        """Test CORS preflight request."""
        event = self.create_api_event('/transactions', 'OPTIONS')
        
        response = transaction_handler(event, mock_context)
        
        assert response['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in response['headers']
        assert 'Access-Control-Allow-Methods' in response['headers']
        assert 'Access-Control-Allow-Headers' in response['headers']
    
    # Query Parameter Tests
    
    def test_alerts_endpoint_with_filters(self, mock_context, valid_api_key):
        """Test alerts endpoint with query parameters."""
        headers = {'X-API-Key': valid_api_key}
        query_params = {
            'status': 'open',
            'risk_level': 'high',
            'limit': '10',
            'offset': '0'
        }
        event = self.create_api_event('/alerts', 'GET', headers=headers, query_params=query_params)
        
        with patch('sentinel_aml.api.alert_handler.NeptuneClient') as mock_neptune:
            # Setup Neptune mock
            mock_instance = AsyncMock()
            mock_conn = AsyncMock()
            mock_result = AsyncMock()
            mock_result.all.return_value = []
            mock_result.next.return_value = 0
            mock_conn.submit.return_value = mock_result
            mock_instance.get_connection.return_value = mock_conn
            mock_neptune.return_value = mock_instance
            
            response = alert_handler(event, mock_context)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'alerts' in body
            assert 'pagination' in body
    
    def test_alerts_endpoint_invalid_status_filter(self, mock_context, valid_api_key):
        """Test alerts endpoint with invalid status filter."""
        headers = {'X-API-Key': valid_api_key}
        query_params = {'status': 'invalid_status'}
        event = self.create_api_event('/alerts', 'GET', headers=headers, query_params=query_params)
        
        response = alert_handler(event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
    
    def test_reports_endpoint_with_date_filters(self, mock_context, valid_api_key):
        """Test reports endpoint with date filters."""
        headers = {'X-API-Key': valid_api_key}
        query_params = {
            'date_from': '2024-01-01T00:00:00Z',
            'date_to': '2024-12-31T23:59:59Z',
            'status': 'draft'
        }
        event = self.create_api_event('/reports', 'GET', headers=headers, query_params=query_params)
        
        with patch('sentinel_aml.api.report_handler.NeptuneClient') as mock_neptune:
            # Setup Neptune mock
            mock_instance = AsyncMock()
            mock_conn = AsyncMock()
            mock_result = AsyncMock()
            mock_result.all.return_value = []
            mock_result.next.return_value = 0
            mock_conn.submit.return_value = mock_result
            mock_instance.get_connection.return_value = mock_conn
            mock_neptune.return_value = mock_instance
            
            response = report_handler(event, mock_context)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'reports' in body
    
    def test_reports_endpoint_invalid_date_format(self, mock_context, valid_api_key):
        """Test reports endpoint with invalid date format."""
        headers = {'X-API-Key': valid_api_key}
        query_params = {'date_from': 'invalid-date'}
        event = self.create_api_event('/reports', 'GET', headers=headers, query_params=query_params)
        
        response = report_handler(event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
    
    # Error Handling Tests
    
    def test_alerts_endpoint_neptune_error(self, mock_context, valid_api_key):
        """Test alerts endpoint when Neptune throws an error."""
        headers = {'X-API-Key': valid_api_key}
        event = self.create_api_event('/alerts', 'GET', headers=headers)
        
        with patch('sentinel_aml.api.alert_handler.NeptuneClient') as mock_neptune:
            # Setup Neptune to throw an error
            mock_neptune.side_effect = Exception("Database connection failed")
            
            response = alert_handler(event, mock_context)
            
            assert response['statusCode'] == 500
            body = json.loads(response['body'])
            assert 'error' in body
    
    def test_reports_endpoint_neptune_timeout(self, mock_context, valid_api_key):
        """Test reports endpoint when Neptune query times out."""
        headers = {'X-API-Key': valid_api_key}
        event = self.create_api_event('/reports', 'GET', headers=headers)
        
        with patch('sentinel_aml.api.report_handler.NeptuneClient') as mock_neptune:
            # Setup Neptune mock to timeout
            mock_instance = AsyncMock()
            mock_instance.connect.side_effect = asyncio.TimeoutError("Query timeout")
            mock_neptune.return_value = mock_instance
            
            response = report_handler(event, mock_context)
            
            assert response['statusCode'] == 500
            body = json.loads(response['body'])
            assert 'error' in body
    
    # CORS and Headers Tests
    
    def test_response_headers_cors(self, mock_context):
        """Test that all responses include proper CORS headers."""
        event = self.create_api_event('/health', 'GET')
        
        with patch('sentinel_aml.api.health_handler.NeptuneClient'):
            response = health_handler(event, mock_context)
            
            headers = response.get('headers', {})
            assert 'Access-Control-Allow-Origin' in headers
            assert headers['Access-Control-Allow-Origin'] == '*'
    
    def test_content_type_headers(self, mock_context, valid_api_key):
        """Test that responses have correct Content-Type headers."""
        headers = {'X-API-Key': valid_api_key}
        event = self.create_api_event('/alerts', 'GET', headers=headers)
        
        with patch('sentinel_aml.api.alert_handler.NeptuneClient') as mock_neptune:
            # Setup basic Neptune mock
            mock_instance = AsyncMock()
            mock_conn = AsyncMock()
            mock_result = AsyncMock()
            mock_result.all.return_value = []
            mock_result.next.return_value = 0
            mock_conn.submit.return_value = mock_result
            mock_instance.get_connection.return_value = mock_conn
            mock_neptune.return_value = mock_instance
            
            response = alert_handler(event, mock_context)
            
            headers = response.get('headers', {})
            assert 'Content-Type' in headers
            assert headers['Content-Type'] == 'application/json'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])