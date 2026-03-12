"""Transaction API handler for Sentinel-AML."""

import json
import logging
from typing import Any, Dict

from sentinel_aml.lambdas.transaction_processor import lambda_handler as process_transaction
from sentinel_aml.core.utils import setup_logging

# Setup logging
logger = setup_logging(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for transaction API endpoints.
    
    This is a wrapper around the existing transaction processor
    to maintain API Gateway compatibility.
    
    Handles:
    - POST /transactions - Submit new transaction for processing
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    try:
        # Extract request information
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        
        logger.info(f"Processing {http_method} request to {path}")
        
        # Route to appropriate handler
        if http_method == 'POST':
            # Delegate to existing transaction processor
            return process_transaction(event, context)
        elif http_method == 'OPTIONS':
            # Handle CORS preflight
            return create_cors_response()
        else:
            return create_error_response(405, "Method not allowed")
            
    except Exception as e:
        logger.error(f"Error processing transaction request: {str(e)}", exc_info=True)
        return create_error_response(500, "Internal server error")


def create_cors_response() -> Dict[str, Any]:
    """Create CORS preflight response."""
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'POST,OPTIONS',
            'Access-Control-Max-Age': '86400'
        },
        'body': ''
    }


def create_error_response(status_code: int, message: str, error_code: str = None) -> Dict[str, Any]:
    """Create an error API response with enhanced error information."""
    from datetime import datetime
    
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
        error_data['error']['details'] = 'Please check your request body and try again'
    elif status_code == 401:
        error_data['error']['type'] = 'AuthenticationError'
        error_data['error']['details'] = 'Valid API key required. Include X-Api-Key header'
    elif status_code == 405:
        error_data['error']['type'] = 'MethodNotAllowedError'
        error_data['error']['details'] = 'Only POST method is allowed for this endpoint'
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
            'Access-Control-Allow-Methods': 'POST,OPTIONS',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY'
        },
        'body': json.dumps(error_data)
    }