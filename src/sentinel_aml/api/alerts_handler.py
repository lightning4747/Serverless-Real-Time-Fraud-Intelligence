"""
Alerts API Handler for Sentinel-AML
Handles GET /alerts and GET /alerts/{id} endpoints for suspicious activity retrieval.
"""

import json
import logging
import boto3
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from decimal import Decimal
import os
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class Alert:
    """Suspicious activity alert."""
    alert_id: str
    cluster_id: str
    account_ids: List[str]
    risk_score: float
    status: str  # OPEN, INVESTIGATING, CLOSED, FALSE_POSITIVE
    priority: str  # HIGH, MEDIUM, LOW
    pattern_types: List[str]
    total_amount: float
    transaction_count: int
    detection_timestamp: str
    last_updated: str
    assigned_analyst: Optional[str] = None
    investigation_notes: Optional[str] = None
    resolution: Optional[str] = None

class AlertsHandler:
    """Handler for alerts API endpoints."""
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.alerts_table = self.dynamodb.Table(
            os.environ.get('ALERTS_TABLE_NAME', 'sentinel-aml-alerts')
        )
        
        # Pagination defaults
        self.default_limit = 50
        self.max_limit = 500
    
    def get_alerts(self, query_params: Dict[str, str]) -> Dict[str, Any]:
        """Get list of alerts with filtering and pagination."""
        logger.info("Retrieving alerts list")
        
        try:
            # Parse query parameters
            status_filter = query_params.get('status')
            risk_level = query_params.get('risk_level')
            account_id = query_params.get('account_id')
            date_from = query_params.get('date_from')
            date_to = query_params.get('date_to')
            
            # Pagination parameters
            limit = min(int(query_params.get('limit', self.default_limit)), self.max_limit)
            offset = int(query_params.get('offset', 0))
            
            # Sorting parameters
            sort_field = query_params.get('sort', 'detection_timestamp')
            sort_order = query_params.get('order', 'desc')
            
            # Build query
            scan_kwargs = {
                'Limit': limit + offset,  # Get extra items for offset
                'Select': 'ALL_ATTRIBUTES'
            }
            
            # Add filters
            filter_expressions = []
            expression_values = {}
            
            if status_filter:
                filter_expressions.append('#status = :status')
                expression_values[':status'] = status_filter
            
            if risk_level:
                risk_threshold = self._get_risk_threshold(risk_level)
                if risk_threshold:
                    filter_expressions.append('risk_score >= :risk_threshold')
                    expression_values[':risk_threshold'] = Decimal(str(risk_threshold))
            
            if account_id:
                filter_expressions.append('contains(account_ids, :account_id)')
                expression_values[':account_id'] = account_id
            
            if date_from:
                filter_expressions.append('detection_timestamp >= :date_from')
                expression_values[':date_from'] = date_from
            
            if date_to:
                filter_expressions.append('detection_timestamp <= :date_to')
                expression_values[':date_to'] = date_to
            
            if filter_expressions:
                scan_kwargs['FilterExpression'] = ' AND '.join(filter_expressions)
                scan_kwargs['ExpressionAttributeValues'] = expression_values
                
                if status_filter:
                    scan_kwargs['ExpressionAttributeNames'] = {'#status': 'status'}
            
            # Execute scan
            response = self.alerts_table.scan(**scan_kwargs)
            items = response.get('Items', [])
            
            # Convert Decimal to float for JSON serialization
            alerts = []
            for item in items:
                alert_dict = self._convert_decimals(item)
                alerts.append(alert_dict)
            
            # Sort results
            alerts.sort(
                key=lambda x: x.get(sort_field, ''),
                reverse=(sort_order.lower() == 'desc')
            )
            
            # Apply pagination
            paginated_alerts = alerts[offset:offset + limit]
            
            # Calculate pagination metadata
            total_count = len(alerts)
            has_more = (offset + limit) < total_count
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'alerts': paginated_alerts,
                    'pagination': {
                        'total_count': total_count,
                        'limit': limit,
                        'offset': offset,
                        'has_more': has_more,
                        'next_offset': offset + limit if has_more else None
                    },
                    'filters_applied': {
                        'status': status_filter,
                        'risk_level': risk_level,
                        'account_id': account_id,
                        'date_from': date_from,
                        'date_to': date_to
                    }
                }),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Cache-Control': 'no-cache, no-store, must-revalidate'
                }
            }
            
        except ValueError as e:
            logger.error(f"Invalid query parameters: {str(e)}")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid query parameters',
                    'message': str(e)
                }),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                }
            }
        except Exception as e:
            logger.error(f"Error retrieving alerts: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': 'Failed to retrieve alerts'
                }),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                }
            }
    
    def get_alert_by_id(self, alert_id: str) -> Dict[str, Any]:
        """Get specific alert by ID."""
        logger.info(f"Retrieving alert {alert_id}")
        
        try:
            response = self.alerts_table.get_item(
                Key={'alert_id': alert_id}
            )
            
            if 'Item' not in response:
                return {
                    'statusCode': 404,
                    'body': json.dumps({
                        'error': 'Alert not found',
                        'message': f'Alert {alert_id} does not exist'
                    }),
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    }
                }
            
            alert = self._convert_decimals(response['Item'])
            
            # Add detailed investigation history if available
            investigation_history = self._get_investigation_history(alert_id)
            alert['investigation_history'] = investigation_history
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'alert': alert,
                    'retrieved_at': datetime.utcnow().isoformat()
                }),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Cache-Control': 'no-cache, no-store, must-revalidate'
                }
            }
            
        except Exception as e:
            logger.error(f"Error retrieving alert {alert_id}: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': f'Failed to retrieve alert {alert_id}'
                }),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                }
            }
    
    def _get_risk_threshold(self, risk_level: str) -> Optional[float]:
        """Convert risk level to threshold value."""
        risk_thresholds = {
            'low': 0.3,
            'medium': 0.6,
            'high': 0.8,
            'critical': 0.9
        }
        return risk_thresholds.get(risk_level.lower())
    
    def _convert_decimals(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert DynamoDB Decimal types to float for JSON serialization."""
        converted = {}
        for key, value in item.items():
            if isinstance(value, Decimal):
                converted[key] = float(value)
            elif isinstance(value, list):
                converted[key] = [
                    float(v) if isinstance(v, Decimal) else v for v in value
                ]
            elif isinstance(value, dict):
                converted[key] = self._convert_decimals(value)
            else:
                converted[key] = value
        return converted
    
    def _get_investigation_history(self, alert_id: str) -> List[Dict[str, Any]]:
        """Get investigation history for an alert."""
        try:
            # This would typically query a separate investigations table
            # For now, return empty list
            return []
        except Exception as e:
            logger.warning(f"Failed to get investigation history for {alert_id}: {str(e)}")
            return []

def lambda_handler(event, context):
    """AWS Lambda handler for alerts API."""
    logger.info("Processing alerts API request")
    
    try:
        handler = AlertsHandler()
        
        # Extract HTTP method and path
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        path_parameters = event.get('pathParameters') or {}
        query_parameters = event.get('queryStringParameters') or {}
        
        # Route to appropriate handler
        if http_method == 'GET':
            if path_parameters and 'id' in path_parameters:
                # GET /alerts/{id}
                alert_id = path_parameters['id']
                return handler.get_alert_by_id(alert_id)
            else:
                # GET /alerts
                return handler.get_alerts(query_parameters)
        else:
            return {
                'statusCode': 405,
                'body': json.dumps({
                    'error': 'Method not allowed',
                    'message': f'HTTP method {http_method} not supported'
                }),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Allow': 'GET, OPTIONS'
                }
            }
            
    except Exception as e:
        logger.error(f"Unhandled error in alerts handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'message': 'An unexpected error occurred'
            }),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }