"""Alert management API handler for Sentinel-AML."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from decimal import Decimal

from sentinel_aml.data.models import Alert, AlertStatus, RiskLevel
from sentinel_aml.data.neptune_client import NeptuneClient
from sentinel_aml.core.utils import setup_logging

# Setup logging
logger = setup_logging(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for alert management API endpoints.
    
    Handles:
    - GET /alerts - Retrieve alerts with filtering and pagination
    - GET /alerts/{id} - Retrieve specific alert by ID
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    import asyncio
    
    try:
        # Extract request information
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        query_params = event.get('queryStringParameters') or {}
        path_params = event.get('pathParameters') or {}
        
        logger.info(f"Processing {http_method} request to {path}")
        
        # Route to appropriate handler
        if http_method == 'GET':
            if path_params and 'id' in path_params:
                return asyncio.run(get_alert_by_id(path_params['id']))
            else:
                return asyncio.run(get_alerts(query_params))
        else:
            return create_error_response(405, "Method not allowed")
            
    except Exception as e:
        logger.error(f"Error processing alert request: {str(e)}", exc_info=True)
        return create_error_response(500, "Internal server error")


async def get_alerts(query_params: Dict[str, str]) -> Dict[str, Any]:
    """
    Retrieve alerts with enhanced filtering, pagination, and search capabilities.
    
    Query parameters:
    - status: Filter by alert status (open, investigating, closed, etc.)
    - risk_level: Filter by risk level (low, medium, high, critical)
    - limit: Number of results to return (default: 50, max: 100)
    - offset: Number of results to skip (default: 0)
    - sort: Sort field (created_at, risk_score, updated_at, title)
    - order: Sort order (asc, desc, default: desc)
    - account_id: Filter by specific account ID
    - date_from: Filter alerts created after this date (ISO format)
    - date_to: Filter alerts created before this date (ISO format)
    - search: Search in title and description (case-insensitive)
    - risk_score_min: Minimum risk score filter (0.0-1.0)
    - risk_score_max: Maximum risk score filter (0.0-1.0)
    
    **Requirements: 6.2, 6.3, 6.4, 6.6**
    """
    try:
        # Parse and validate query parameters with enhanced validation
        status_filter = query_params.get('status')
        risk_level_filter = query_params.get('risk_level')
        account_id_filter = query_params.get('account_id')
        date_from = query_params.get('date_from')
        date_to = query_params.get('date_to')
        search_term = query_params.get('search', '').strip()
        
        # Pagination parameters
        limit = min(int(query_params.get('limit', 50)), 100)
        offset = max(int(query_params.get('offset', 0)), 0)
        
        # Sorting parameters
        sort_field = query_params.get('sort', 'created_at')
        sort_order = query_params.get('order', 'desc').lower()
        
        # Risk score filters
        risk_score_min = query_params.get('risk_score_min')
        risk_score_max = query_params.get('risk_score_max')
        
        # Validate enum values
        if status_filter and status_filter not in [s.value for s in AlertStatus]:
            return create_error_response(400, f"Invalid status: {status_filter}. Valid values: {[s.value for s in AlertStatus]}")
        
        if risk_level_filter and risk_level_filter not in [r.value for r in RiskLevel]:
            return create_error_response(400, f"Invalid risk_level: {risk_level_filter}. Valid values: {[r.value for r in RiskLevel]}")
        
        # Validate sort field
        valid_sort_fields = ['created_at', 'updated_at', 'risk_score', 'title']
        if sort_field not in valid_sort_fields:
            return create_error_response(400, f"Invalid sort field: {sort_field}. Valid values: {valid_sort_fields}")
        
        # Validate sort order
        if sort_order not in ['asc', 'desc']:
            return create_error_response(400, f"Invalid sort order: {sort_order}. Valid values: ['asc', 'desc']")
        
        # Validate date parameters
        if date_from:
            try:
                datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            except ValueError:
                return create_error_response(400, "Invalid date_from format. Use ISO format (YYYY-MM-DDTHH:MM:SSZ)")
        
        if date_to:
            try:
                datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            except ValueError:
                return create_error_response(400, "Invalid date_to format. Use ISO format (YYYY-MM-DDTHH:MM:SSZ)")
        
        # Validate risk score filters
        if risk_score_min is not None:
            try:
                risk_score_min = float(risk_score_min)
                if not 0.0 <= risk_score_min <= 1.0:
                    return create_error_response(400, "risk_score_min must be between 0.0 and 1.0")
            except ValueError:
                return create_error_response(400, "Invalid risk_score_min format. Must be a number between 0.0 and 1.0")
        
        if risk_score_max is not None:
            try:
                risk_score_max = float(risk_score_max)
                if not 0.0 <= risk_score_max <= 1.0:
                    return create_error_response(400, "risk_score_max must be between 0.0 and 1.0")
            except ValueError:
                return create_error_response(400, "Invalid risk_score_max format. Must be a number between 0.0 and 1.0")
        
        # Validate account ID format if provided
        if account_id_filter and not account_id_filter.replace('-', '').replace('_', '').isalnum():
            return create_error_response(400, "Invalid account_id format")
        
        # Connect to Neptune and query alerts
        neptune_client = NeptuneClient()
        await neptune_client.connect()
        
        try:
            # Build enhanced Gremlin query for alerts
            query = "g.V().hasLabel('Alert')"
            
            # Add filters
            if status_filter:
                query += f".has('status', '{status_filter}')"
            if risk_level_filter:
                query += f".has('risk_level', '{risk_level_filter}')"
            if account_id_filter:
                query += f".has('account_ids', containing('{account_id_filter}'))"
            if date_from:
                query += f".has('created_at', gte('{date_from}'))"
            if date_to:
                query += f".has('created_at', lte('{date_to}'))"
            if risk_score_min is not None:
                query += f".has('risk_score', gte({risk_score_min}))"
            if risk_score_max is not None:
                query += f".has('risk_score', lte({risk_score_max}))"
            
            # Add text search filter
            if search_term:
                # Escape special characters for Gremlin
                escaped_search = search_term.replace("'", "\\'").replace('"', '\\"')
                query += f".or(__.has('title', containing('{escaped_search}')), __.has('description', containing('{escaped_search}')))"
            
            # Store base query for count
            count_query = query + ".count()"
            
            # Add sorting and pagination
            if sort_order == 'desc':
                query += f".order().by('{sort_field}', desc)"
            else:
                query += f".order().by('{sort_field}', asc)"
            
            query += f".range({offset}, {offset + limit})"
            query += ".valueMap(true)"
            
            conn = await neptune_client.get_connection()
            
            # Execute main query
            result = await conn.submit(query)
            alerts_data = await result.all()
            
            # Convert to Alert models
            alerts = []
            for alert_data in alerts_data:
                try:
                    # Convert Neptune result to Alert model
                    alert_dict = convert_neptune_result_to_dict(alert_data)
                    alert = Alert(**alert_dict)
                    alerts.append(alert.model_dump())
                except Exception as e:
                    logger.warning(f"Failed to parse alert: {e}")
                    continue
            
            # Get total count for pagination
            count_result = await conn.submit(count_query)
            total_count = await count_result.next()
            
            # Calculate pagination metadata
            has_more = offset + limit < total_count
            total_pages = (total_count + limit - 1) // limit if limit > 0 else 1
            current_page = (offset // limit) + 1 if limit > 0 else 1
            
            return create_success_response({
                'alerts': alerts,
                'pagination': {
                    'total': total_count,
                    'limit': limit,
                    'offset': offset,
                    'has_more': has_more,
                    'total_pages': total_pages,
                    'current_page': current_page
                },
                'filters_applied': {
                    'status': status_filter,
                    'risk_level': risk_level_filter,
                    'account_id': account_id_filter,
                    'date_from': date_from,
                    'date_to': date_to,
                    'search': search_term if search_term else None,
                    'risk_score_min': risk_score_min,
                    'risk_score_max': risk_score_max
                },
                'sorting': {
                    'field': sort_field,
                    'order': sort_order
                }
            })
            
        finally:
            await neptune_client.disconnect()
            
    except ValueError as e:
        logger.error(f"Invalid query parameters: {e}")
        return create_error_response(400, str(e))
    except Exception as e:
        logger.error(f"Error retrieving alerts: {e}", exc_info=True)
        return create_error_response(500, "Failed to retrieve alerts")


async def get_alert_by_id(alert_id: str) -> Dict[str, Any]:
    """
    Retrieve a specific alert by ID.
    
    Args:
        alert_id: Alert ID to retrieve
        
    Returns:
        API Gateway response with alert data
    """
    try:
        if not alert_id:
            return create_error_response(400, "Alert ID is required")
        
        # Connect to Neptune
        neptune_client = NeptuneClient()
        await neptune_client.connect()
        
        try:
            # Query for specific alert
            query = f"g.V().hasLabel('Alert').has('alert_id', '{alert_id}').valueMap(true)"
            
            conn = await neptune_client.get_connection()
            result = await conn.submit(query)
            alert_data = await result.next()
            
            if not alert_data:
                return create_error_response(404, "Alert not found")
            
            # Convert to Alert model
            alert_dict = convert_neptune_result_to_dict(alert_data)
            alert = Alert(**alert_dict)
            
            return create_success_response({'alert': alert.model_dump()})
            
        finally:
            await neptune_client.disconnect()
            
    except Exception as e:
        logger.error(f"Error retrieving alert {alert_id}: {e}", exc_info=True)
        return create_error_response(500, "Failed to retrieve alert")


def convert_neptune_result_to_dict(neptune_data: Dict) -> Dict[str, Any]:
    """
    Convert Neptune query result to dictionary format for Pydantic models.
    
    Args:
        neptune_data: Raw Neptune query result
        
    Returns:
        Dictionary suitable for Pydantic model creation
    """
    result = {}
    
    for key, value in neptune_data.items():
        if key.startswith('~'):  # Skip Neptune internal fields
            continue
            
        # Handle list values (Neptune returns single values as lists)
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        elif isinstance(value, list) and len(value) == 0:
            value = None
            
        # Convert datetime strings back to datetime objects
        if key.endswith('_at') or key.endswith('_date'):
            if isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except ValueError:
                    pass  # Keep as string if parsing fails
        
        # Convert numeric strings to appropriate types
        if key in ['risk_score', 'ai_confidence'] and isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                pass
                
        result[key] = value
    
    return result


def create_success_response(data: Dict[str, Any], status_code: int = 200) -> Dict[str, Any]:
    """Create a successful API response with proper HTTP status codes."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY'
        },
        'body': json.dumps(data, default=str)
    }


def create_error_response(status_code: int, message: str, error_code: str = None) -> Dict[str, Any]:
    """Create an error API response with enhanced error information."""
    error_data = {
        'error': {
            'code': error_code or f"HTTP_{status_code}",
            'message': message,
            'status': status_code,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    }
    
    # Add additional context for specific error types
    if status_code == 400:
        error_data['error']['type'] = 'ValidationError'
        error_data['error']['details'] = 'Please check your request parameters and try again'
    elif status_code == 401:
        error_data['error']['type'] = 'AuthenticationError'
        error_data['error']['details'] = 'Valid API key required. Include X-Api-Key header'
    elif status_code == 403:
        error_data['error']['type'] = 'AuthorizationError'
        error_data['error']['details'] = 'Insufficient permissions for this resource'
    elif status_code == 404:
        error_data['error']['type'] = 'NotFoundError'
        error_data['error']['details'] = 'The requested resource was not found'
    elif status_code == 429:
        error_data['error']['type'] = 'RateLimitError'
        error_data['error']['details'] = 'Rate limit exceeded. Please try again later'
    elif status_code >= 500:
        error_data['error']['type'] = 'InternalServerError'
        error_data['error']['details'] = 'An internal error occurred. Please try again later'
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY'
        },
        'body': json.dumps(error_data)
    }