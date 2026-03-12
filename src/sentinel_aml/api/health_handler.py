"""Health check API handler for Sentinel-AML."""

import json
import logging
from datetime import datetime
from typing import Any, Dict

from sentinel_aml.data.neptune_client import NeptuneClient
from sentinel_aml.core.utils import setup_logging

# Setup logging
logger = setup_logging(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for health check endpoint.
    
    Handles:
    - GET /health - System health check
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response with health status
    """
    import asyncio
    
    try:
        # Extract request information
        http_method = event.get('httpMethod', '')
        
        logger.info(f"Processing {http_method} health check request")
        
        if http_method == 'GET':
            return asyncio.run(perform_health_check())
        else:
            return create_error_response(405, "Method not allowed")
            
    except Exception as e:
        logger.error(f"Error processing health check: {str(e)}", exc_info=True)
        return create_error_response(500, "Health check failed")


async def perform_health_check() -> Dict[str, Any]:
    """
    Perform comprehensive health check of system components.
    
    Returns:
        API Gateway response with health status
    """
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0',
        'components': {}
    }
    
    overall_healthy = True
    
    # Check Neptune connectivity
    try:
        neptune_client = NeptuneClient()
        await neptune_client.connect()
        
        try:
            # Simple query to test connectivity
            conn = await neptune_client.get_connection()
            result = await conn.submit("g.V().limit(1).count()")
            await result.next()
            
            health_status['components']['neptune'] = {
                'status': 'healthy',
                'message': 'Neptune connection successful'
            }
        except Exception as e:
            health_status['components']['neptune'] = {
                'status': 'unhealthy',
                'message': f'Neptune query failed: {str(e)}'
            }
            overall_healthy = False
        finally:
            await neptune_client.disconnect()
            
    except Exception as e:
        health_status['components']['neptune'] = {
            'status': 'unhealthy',
            'message': f'Neptune connection failed: {str(e)}'
        }
        overall_healthy = False
    
    # Check Lambda function health
    try:
        # Basic Lambda health indicators
        health_status['components']['lambda'] = {
            'status': 'healthy',
            'message': 'Lambda function operational',
            'memory_limit': context.memory_limit_in_mb if 'context' in locals() else 'unknown',
            'remaining_time': context.get_remaining_time_in_millis() if 'context' in locals() else 'unknown'
        }
    except Exception as e:
        health_status['components']['lambda'] = {
            'status': 'degraded',
            'message': f'Lambda metrics unavailable: {str(e)}'
        }
    
    # Set overall status
    if not overall_healthy:
        health_status['status'] = 'unhealthy'
    
    # Return appropriate HTTP status code
    status_code = 200 if overall_healthy else 503
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
            'Access-Control-Allow-Methods': 'GET,OPTIONS'
        },
        'body': json.dumps(health_status, default=str)
    }


def create_error_response(status_code: int, message: str) -> Dict[str, Any]:
    """Create an error API response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
            'Access-Control-Allow-Methods': 'GET,OPTIONS'
        },
        'body': json.dumps({
            'error': {
                'code': status_code,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
        })
    }