"""SAR report retrieval API handler for Sentinel-AML."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from decimal import Decimal

from sentinel_aml.data.models import SuspiciousActivityReport
from sentinel_aml.data.neptune_client import NeptuneClient
from sentinel_aml.core.utils import setup_logging

# Setup logging
logger = setup_logging(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for SAR report retrieval API endpoints.
    
    Handles:
    - GET /reports - Retrieve reports with filtering and pagination
    - GET /reports/{id} - Retrieve specific report by ID
    
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
                return asyncio.run(get_report_by_id(path_params['id']))
            else:
                return asyncio.run(get_reports(query_params))
        else:
            return create_error_response(405, "Method not allowed")
            
    except Exception as e:
        logger.error(f"Error processing report request: {str(e)}", exc_info=True)
        return create_error_response(500, "Internal server error")


async def get_reports(query_params: Dict[str, str]) -> Dict[str, Any]:
    """
    Retrieve SAR reports with enhanced filtering, pagination, and search capabilities.
    
    Query parameters:
    - status: Filter by report status (draft, submitted, filed)
    - case_id: Filter by case ID
    - date_from: Filter reports created after this date (ISO format)
    - date_to: Filter reports created before this date (ISO format)
    - limit: Number of results to return (default: 20, max: 50)
    - offset: Number of results to skip (default: 0)
    - sort: Sort field (created_at, filing_date, total_amount, updated_at)
    - order: Sort order (asc, desc, default: desc)
    - search: Search in activity description and reporting reason
    - amount_min: Minimum total amount filter
    - amount_max: Maximum total amount filter
    - currency: Filter by currency code
    - subject_account: Filter by subject account ID
    
    **Requirements: 6.2, 6.3, 6.4, 6.6**
    """
    try:
        # Parse and validate query parameters with enhanced validation
        status_filter = query_params.get('status')
        case_id_filter = query_params.get('case_id')
        date_from = query_params.get('date_from')
        date_to = query_params.get('date_to')
        search_term = query_params.get('search', '').strip()
        currency_filter = query_params.get('currency')
        subject_account_filter = query_params.get('subject_account')
        
        # Pagination parameters
        limit = min(int(query_params.get('limit', 20)), 50)
        offset = max(int(query_params.get('offset', 0)), 0)
        
        # Sorting parameters
        sort_field = query_params.get('sort', 'created_at')
        sort_order = query_params.get('order', 'desc').lower()
        
        # Amount filters
        amount_min = query_params.get('amount_min')
        amount_max = query_params.get('amount_max')
        
        # Validate status
        valid_statuses = ['draft', 'submitted', 'filed', 'rejected', 'under_review']
        if status_filter and status_filter not in valid_statuses:
            return create_error_response(400, f"Invalid status: {status_filter}. Valid values: {valid_statuses}")
        
        # Validate sort field
        valid_sort_fields = ['created_at', 'updated_at', 'filing_date', 'total_amount', 'case_id']
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
        
        # Validate amount filters
        if amount_min is not None:
            try:
                amount_min = float(amount_min)
                if amount_min < 0:
                    return create_error_response(400, "amount_min must be non-negative")
            except ValueError:
                return create_error_response(400, "Invalid amount_min format. Must be a number")
        
        if amount_max is not None:
            try:
                amount_max = float(amount_max)
                if amount_max < 0:
                    return create_error_response(400, "amount_max must be non-negative")
            except ValueError:
                return create_error_response(400, "Invalid amount_max format. Must be a number")
        
        # Validate currency format
        if currency_filter and (len(currency_filter) != 3 or not currency_filter.isalpha()):
            return create_error_response(400, "Invalid currency format. Must be 3-letter ISO code (e.g., USD)")
        
        # Connect to Neptune and query reports
        neptune_client = NeptuneClient()
        await neptune_client.connect()
        
        try:
            # Build enhanced Gremlin query for reports
            query = "g.V().hasLabel('SuspiciousActivityReport')"
            
            # Add filters
            if status_filter:
                query += f".has('status', '{status_filter}')"
            if case_id_filter:
                query += f".has('case_id', '{case_id_filter}')"
            if currency_filter:
                query += f".has('currency', '{currency_filter.upper()}')"
            if subject_account_filter:
                query += f".has('subject_accounts', containing('{subject_account_filter}'))"
            if date_from:
                query += f".has('created_at', gte('{date_from}'))"
            if date_to:
                query += f".has('created_at', lte('{date_to}'))"
            if amount_min is not None:
                query += f".has('total_amount', gte({amount_min}))"
            if amount_max is not None:
                query += f".has('total_amount', lte({amount_max}))"
            
            # Add text search filter
            if search_term:
                # Escape special characters for Gremlin
                escaped_search = search_term.replace("'", "\\'").replace('"', '\\"')
                query += f".or(__.has('activity_description', containing('{escaped_search}')), __.has('reporting_reason', containing('{escaped_search}')))"
            
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
            reports_data = await result.all()
            
            # Convert to SuspiciousActivityReport models
            reports = []
            for report_data in reports_data:
                try:
                    # Convert Neptune result to SAR model
                    report_dict = convert_neptune_result_to_dict(report_data)
                    # Remove sensitive fields for list view
                    report_dict = sanitize_report_for_list(report_dict)
                    report = SuspiciousActivityReport(**report_dict)
                    reports.append(report.model_dump())
                except Exception as e:
                    logger.warning(f"Failed to parse report: {e}")
                    continue
            
            # Get total count for pagination
            count_result = await conn.submit(count_query)
            total_count = await count_result.next()
            
            # Calculate pagination metadata
            has_more = offset + limit < total_count
            total_pages = (total_count + limit - 1) // limit if limit > 0 else 1
            current_page = (offset // limit) + 1 if limit > 0 else 1
            
            return create_success_response({
                'reports': reports,
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
                    'case_id': case_id_filter,
                    'currency': currency_filter,
                    'subject_account': subject_account_filter,
                    'date_from': date_from,
                    'date_to': date_to,
                    'search': search_term if search_term else None,
                    'amount_min': amount_min,
                    'amount_max': amount_max
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
        logger.error(f"Error retrieving reports: {e}", exc_info=True)
        return create_error_response(500, "Failed to retrieve reports")


async def get_report_by_id(report_id: str) -> Dict[str, Any]:
    """
    Retrieve a specific SAR report by ID.
    
    Args:
        report_id: SAR report ID to retrieve
        
    Returns:
        API Gateway response with full report data
    """
    try:
        if not report_id:
            return create_error_response(400, "Report ID is required")
        
        # Connect to Neptune
        neptune_client = NeptuneClient()
        await neptune_client.connect()
        
        try:
            # Query for specific report
            query = f"g.V().hasLabel('SuspiciousActivityReport').has('sar_id', '{report_id}').valueMap(true)"
            
            conn = await neptune_client.get_connection()
            result = await conn.submit(query)
            report_data = await result.next()
            
            if not report_data:
                return create_error_response(404, "Report not found")
            
            # Convert to SuspiciousActivityReport model
            report_dict = convert_neptune_result_to_dict(report_data)
            report = SuspiciousActivityReport(**report_dict)
            
            # Log access for audit trail
            logger.info(f"SAR report {report_id} accessed", extra={
                'report_id': report_id,
                'case_id': report.case_id,
                'access_timestamp': datetime.utcnow().isoformat()
            })
            
            return create_success_response({'report': report.model_dump()})
            
        finally:
            await neptune_client.disconnect()
            
    except Exception as e:
        logger.error(f"Error retrieving report {report_id}: {e}", exc_info=True)
        return create_error_response(500, "Failed to retrieve report")


def sanitize_report_for_list(report_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove sensitive fields from report for list view.
    
    Args:
        report_dict: Full report dictionary
        
    Returns:
        Sanitized report dictionary for list view
    """
    # Fields to include in list view (summary only)
    list_fields = {
        'sar_id', 'case_id', 'report_number', 'filing_date', 'status',
        'total_amount', 'currency', 'date_range_start', 'date_range_end',
        'reporting_reason', 'created_at', 'updated_at', 'ai_confidence'
    }
    
    return {k: v for k, v in report_dict.items() if k in list_fields}


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
        elif isinstance(value, list):
            # Keep as list for fields that should be lists
            if key in ['subject_accounts', 'subject_names', 'suspicious_patterns', 'regulation_violated']:
                pass  # Keep as list
            else:
                value = value[0] if value else None
            
        # Convert datetime strings back to datetime objects
        if key.endswith('_at') or key.endswith('_date') or key == 'filing_date':
            if isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except ValueError:
                    pass  # Keep as string if parsing fails
        
        # Convert numeric strings to appropriate types
        if key in ['total_amount'] and isinstance(value, str):
            try:
                value = Decimal(value)
            except (ValueError, TypeError):
                pass
        elif key in ['ai_confidence'] and isinstance(value, str):
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