"""
Reports API Handler for Sentinel-AML
Handles GET /reports and GET /reports/{id} endpoints for SAR access.
"""

import json
import logging
import boto3
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from decimal import Decimal
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SARReport:
    """SAR report metadata."""
    sar_id: str
    cluster_id: str
    status: str  # DRAFT, PENDING_REVIEW, APPROVED, FILED, REJECTED
    confidence_score: float
    generation_timestamp: str
    filing_timestamp: Optional[str]
    total_amount: float
    account_count: int
    transaction_count: int
    pattern_types: List[str]
    review_required: bool
    compliance_flags: List[str]
    approver_id: Optional[str] = None
    filing_reference: Optional[str] = None

class ReportsHandler:
    """Handler for reports API endpoints."""
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.s3_client = boto3.client('s3')
        
        # DynamoDB tables
        self.sars_table = self.dynamodb.Table(
            os.environ.get('SAR_TABLE_NAME', 'sentinel-aml-sars')
        )
        self.versions_table = self.dynamodb.Table(
            os.environ.get('SAR_VERSIONS_TABLE_NAME', 'sentinel-aml-sar-versions')
        )
        
        # S3 bucket for SAR content
        self.sar_bucket = os.environ.get('SAR_BUCKET_NAME', 'sentinel-aml-sars')
        
        # Pagination defaults
        self.default_limit = 25
        self.max_limit = 100
    
    def get_reports(self, query_params: Dict[str, str]) -> Dict[str, Any]:
        """Get list of SAR reports with filtering and pagination."""
        logger.info("Retrieving SAR reports list")
        
        try:
            # Parse query parameters
            status_filter = query_params.get('status')
            case_id = query_params.get('case_id')  # cluster_id
            date_from = query_params.get('date_from')
            date_to = query_params.get('date_to')
            
            # Pagination parameters
            limit = min(int(query_params.get('limit', self.default_limit)), self.max_limit)
            offset = int(query_params.get('offset', 0))
            
            # Sorting parameters
            sort_field = query_params.get('sort', 'generation_timestamp')
            sort_order = query_params.get('order', 'desc')
            
            # Build query
            scan_kwargs = {
                'Limit': limit + offset,
                'Select': 'ALL_ATTRIBUTES'
            }
            
            # Add filters
            filter_expressions = []
            expression_values = {}
            expression_names = {}
            
            if status_filter:
                filter_expressions.append('#status = :status')
                expression_values[':status'] = status_filter
                expression_names['#status'] = 'status'
            
            if case_id:
                filter_expressions.append('cluster_id = :cluster_id')
                expression_values[':cluster_id'] = case_id
            
            if date_from:
                filter_expressions.append('generation_timestamp >= :date_from')
                expression_values[':date_from'] = date_from
            
            if date_to:
                filter_expressions.append('generation_timestamp <= :date_to')
                expression_values[':date_to'] = date_to
            
            if filter_expressions:
                scan_kwargs['FilterExpression'] = ' AND '.join(filter_expressions)
                scan_kwargs['ExpressionAttributeValues'] = expression_values
                
                if expression_names:
                    scan_kwargs['ExpressionAttributeNames'] = expression_names
            
            # Execute scan
            response = self.sars_table.scan(**scan_kwargs)
            items = response.get('Items', [])
            
            # Convert and enrich data
            reports = []
            for item in items:
                report_dict = self._convert_decimals(item)
                
                # Add summary information
                report_dict['summary'] = {
                    'has_compliance_issues': len(report_dict.get('compliance_flags', [])) > 0,
                    'requires_review': report_dict.get('review_required', False),
                    'is_filed': report_dict.get('status') == 'FILED',
                    'confidence_level': self._get_confidence_level(report_dict.get('confidence_score', 0))
                }
                
                reports.append(report_dict)
            
            # Sort results
            reports.sort(
                key=lambda x: x.get(sort_field, ''),
                reverse=(sort_order.lower() == 'desc')
            )
            
            # Apply pagination
            paginated_reports = reports[offset:offset + limit]
            
            # Calculate statistics
            stats = self._calculate_report_statistics(reports)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'reports': paginated_reports,
                    'pagination': {
                        'total_count': len(reports),
                        'limit': limit,
                        'offset': offset,
                        'has_more': (offset + limit) < len(reports),
                        'next_offset': offset + limit if (offset + limit) < len(reports) else None
                    },
                    'statistics': stats,
                    'filters_applied': {
                        'status': status_filter,
                        'case_id': case_id,
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
            logger.error(f"Error retrieving reports: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': 'Failed to retrieve reports'
                }),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                }
            }
    
    def get_report_by_id(self, sar_id: str, include_content: bool = False) -> Dict[str, Any]:
        """Get specific SAR report by ID."""
        logger.info(f"Retrieving SAR report {sar_id}")
        
        try:
            # Get SAR metadata
            response = self.sars_table.get_item(
                Key={'sar_id': sar_id}
            )
            
            if 'Item' not in response:
                return {
                    'statusCode': 404,
                    'body': json.dumps({
                        'error': 'Report not found',
                        'message': f'SAR report {sar_id} does not exist'
                    }),
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    }
                }
            
            report = self._convert_decimals(response['Item'])
            
            # Add version history
            version_history = self._get_version_history(sar_id)
            report['version_history'] = version_history
            
            # Add approval history
            approval_history = self._get_approval_history(sar_id)
            report['approval_history'] = approval_history
            
            # Optionally include content
            if include_content:
                content = self._get_sar_content(sar_id)
                if content:
                    report['content'] = content
            
            # Add compliance analysis
            report['compliance_analysis'] = self._analyze_compliance_status(report)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'report': report,
                    'retrieved_at': datetime.utcnow().isoformat()
                }),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Cache-Control': 'no-cache, no-store, must-revalidate'
                }
            }
            
        except Exception as e:
            logger.error(f"Error retrieving report {sar_id}: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': f'Failed to retrieve report {sar_id}'
                }),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                }
            }
    
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
    
    def _get_confidence_level(self, confidence_score: float) -> str:
        """Convert confidence score to level."""
        if confidence_score >= 0.9:
            return 'VERY_HIGH'
        elif confidence_score >= 0.8:
            return 'HIGH'
        elif confidence_score >= 0.6:
            return 'MEDIUM'
        elif confidence_score >= 0.4:
            return 'LOW'
        else:
            return 'VERY_LOW'
    
    def _calculate_report_statistics(self, reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate statistics for the reports."""
        if not reports:
            return {
                'total_reports': 0,
                'by_status': {},
                'avg_confidence': 0.0,
                'total_amount': 0.0
            }
        
        # Count by status
        status_counts = {}
        for report in reports:
            status = report.get('status', 'UNKNOWN')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Calculate averages
        confidence_scores = [r.get('confidence_score', 0) for r in reports]
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        total_amount = sum(r.get('total_amount', 0) for r in reports)
        
        return {
            'total_reports': len(reports),
            'by_status': status_counts,
            'avg_confidence': round(avg_confidence, 3),
            'total_amount': round(total_amount, 2)
        }
    
    def _get_version_history(self, sar_id: str) -> List[Dict[str, Any]]:
        """Get version history for a SAR."""
        try:
            # Query versions table (simplified for now)
            return []
        except Exception as e:
            logger.warning(f"Failed to get version history for {sar_id}: {str(e)}")
            return []
    
    def _get_approval_history(self, sar_id: str) -> List[Dict[str, Any]]:
        """Get approval history for a SAR."""
        try:
            # Query approvals table (simplified for now)
            return []
        except Exception as e:
            logger.warning(f"Failed to get approval history for {sar_id}: {str(e)}")
            return []
    
    def _get_sar_content(self, sar_id: str) -> Optional[str]:
        """Get SAR content from S3."""
        try:
            response = self.s3_client.get_object(
                Bucket=self.sar_bucket,
                Key=f"sars/{sar_id}/redacted.txt"
            )
            return response['Body'].read().decode('utf-8')
        except Exception as e:
            logger.warning(f"Failed to get SAR content for {sar_id}: {str(e)}")
            return None
    
    def _analyze_compliance_status(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze compliance status of a report."""
        compliance_flags = report.get('compliance_flags', [])
        review_required = report.get('review_required', False)
        confidence_score = report.get('confidence_score', 0)
        
        return {
            'has_issues': len(compliance_flags) > 0,
            'issue_count': len(compliance_flags),
            'requires_review': review_required,
            'confidence_level': self._get_confidence_level(confidence_score),
            'ready_for_filing': (
                len(compliance_flags) == 0 and 
                not review_required and 
                confidence_score >= 0.8 and
                report.get('status') == 'APPROVED'
            )
        }

def lambda_handler(event, context):
    """AWS Lambda handler for reports API."""
    logger.info("Processing reports API request")
    
    try:
        handler = ReportsHandler()
        
        # Extract HTTP method and path
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        path_parameters = event.get('pathParameters') or {}
        query_parameters = event.get('queryStringParameters') or {}
        
        # Route to appropriate handler
        if http_method == 'GET':
            if path_parameters and 'id' in path_parameters:
                # GET /reports/{id}
                sar_id = path_parameters['id']
                include_content = query_parameters.get('include_content', '').lower() == 'true'
                return handler.get_report_by_id(sar_id, include_content)
            else:
                # GET /reports
                return handler.get_reports(query_parameters)
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
        logger.error(f"Unhandled error in reports handler: {str(e)}")
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