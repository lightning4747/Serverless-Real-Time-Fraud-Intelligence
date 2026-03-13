"""Immutable audit storage with 7-year retention for compliance."""

import hashlib
import json
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional

import boto3
from pydantic import BaseModel, Field

from sentinel_aml.core.config import get_settings
from sentinel_aml.core.logging import get_logger
from sentinel_aml.compliance.audit_logger import AuditEvent

logger = get_logger(__name__)


class ImmutableAuditRecord(BaseModel):
    """Immutable audit record with integrity verification."""
    
    record_id: str
    timestamp: datetime
    event_data: Dict[str, Any]
    checksum: str
    previous_checksum: Optional[str] = None
    retention_until: datetime
    
    @classmethod
    def create_from_event(cls, event: AuditEvent, previous_checksum: Optional[str] = None):
        """Create immutable record from audit event."""
        settings = get_settings()
        
        # Calculate retention date (7 years)
        retention_date = datetime.now(timezone.utc) + timedelta(days=settings.audit_log_retention_days)
        
        # Serialize event data
        event_data = event.model_dump()
        event_json = json.dumps(event_data, sort_keys=True, default=str)
        
        # Calculate checksum for integrity
        checksum_input = f"{event_json}{previous_checksum or ''}"
        checksum = hashlib.sha256(checksum_input.encode()).hexdigest()
        
        return cls(
            record_id=event.event_id,
            timestamp=event.timestamp,
            event_data=event_data,
            checksum=checksum,
            previous_checksum=previous_checksum,
            retention_until=retention_date
        )


class AuditStorage:
    """Immutable audit storage service with AWS integration."""
    
    def __init__(self):
        """Initialize audit storage."""
        self.settings = get_settings()
        
        # Initialize AWS clients
        self.dynamodb = boto3.resource('dynamodb', region_name=self.settings.aws_region)
        self.s3 = boto3.client('s3', region_name=self.settings.aws_region)
        
        # Table and bucket names (would be created by CDK)
        self.audit_table_name = f"sentinel-aml-audit-{self.settings.environment}"
        self.audit_bucket_name = f"sentinel-aml-audit-logs-{self.settings.environment}"
        
        # Get DynamoDB table
        try:
            self.audit_table = self.dynamodb.Table(self.audit_table_name)
        except Exception as e:
            logger.warning(f"Audit table not available: {e}")
            self.audit_table = None
        
        # Track last checksum for integrity chain
        self._last_checksum: Optional[str] = None
    
    def store_audit_record(self, event: AuditEvent) -> str:
        """Store audit record immutably."""
        try:
            # Create immutable record
            record = ImmutableAuditRecord.create_from_event(event, self._last_checksum)
            
            # Store in DynamoDB for fast queries
            if self.audit_table:
                self._store_in_dynamodb(record)
            
            # Store in S3 for long-term retention
            self._store_in_s3(record)
            
            # Update checksum chain
            self._last_checksum = record.checksum
            
            logger.debug(f"Stored audit record: {record.record_id}")
            return record.record_id
            
        except Exception as e:
            logger.error(f"Failed to store audit record: {e}")
            raise
    
    def query_audit_records(self,
                           resource_type: Optional[str] = None,
                           resource_id: Optional[str] = None,
                           user_id: Optional[str] = None,
                           start_time: Optional[datetime] = None,
                           end_time: Optional[datetime] = None,
                           limit: int = 100) -> List[AuditEvent]:
        """Query audit records with filters."""
        if not self.audit_table:
            logger.warning("Audit table not available for queries")
            return []
        
        try:
            # Build filter expression
            filter_expression = None
            expression_values = {}
            
            if resource_type:
                filter_expression = "resource_type = :resource_type"
                expression_values[':resource_type'] = resource_type
            
            if resource_id:
                if filter_expression:
                    filter_expression += " AND resource_id = :resource_id"
                else:
                    filter_expression = "resource_id = :resource_id"
                expression_values[':resource_id'] = resource_id
            
            if user_id:
                if filter_expression:
                    filter_expression += " AND user_id = :user_id"
                else:
                    filter_expression = "user_id = :user_id"
                expression_values[':user_id'] = user_id
            
            # Query parameters
            scan_kwargs = {
                'Limit': limit
            }
            
            if filter_expression:
                scan_kwargs['FilterExpression'] = filter_expression
                scan_kwargs['ExpressionAttributeValues'] = expression_values
            
            # Execute scan (in production, would use GSI for better performance)
            response = self.audit_table.scan(**scan_kwargs)
            
            # Convert to AuditEvent objects
            events = []
            for item in response.get('Items', []):
                try:
                    event_data = item['event_data']
                    event = AuditEvent(**event_data)
                    events.append(event)
                except Exception as e:
                    logger.warning(f"Failed to parse audit event: {e}")
            
            return events
            
        except Exception as e:
            logger.error(f"Failed to query audit records: {e}")
            return []
    
    def verify_audit_chain_integrity(self, start_date: Optional[datetime] = None) -> Dict[str, Any]:
        """Verify the integrity of the audit chain."""
        try:
            # Get records from S3 for verification
            records = self._get_s3_records_for_verification(start_date)
            
            integrity_report = {
                'total_records_checked': len(records),
                'integrity_violations': [],
                'chain_valid': True,
                'verification_timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            previous_checksum = None
            for record in records:
                # Verify individual record checksum
                expected_checksum = self._calculate_record_checksum(record, previous_checksum)
                
                if record.checksum != expected_checksum:
                    integrity_report['integrity_violations'].append({
                        'record_id': record.record_id,
                        'issue': 'checksum_mismatch',
                        'expected': expected_checksum,
                        'actual': record.checksum
                    })
                    integrity_report['chain_valid'] = False
                
                # Verify chain linkage
                if record.previous_checksum != previous_checksum:
                    integrity_report['integrity_violations'].append({
                        'record_id': record.record_id,
                        'issue': 'chain_break',
                        'expected_previous': previous_checksum,
                        'actual_previous': record.previous_checksum
                    })
                    integrity_report['chain_valid'] = False
                
                previous_checksum = record.checksum
            
            return integrity_report
            
        except Exception as e:
            logger.error(f"Failed to verify audit chain integrity: {e}")
            return {
                'error': str(e),
                'chain_valid': False,
                'verification_timestamp': datetime.now(timezone.utc).isoformat()
            }
    
    def generate_compliance_report(self, 
                                 start_date: datetime, 
                                 end_date: datetime) -> Dict[str, Any]:
        """Generate compliance report for regulatory requirements."""
        try:
            # Query audit records for the period
            records = self.query_audit_records(
                start_time=start_date,
                end_time=end_date,
                limit=10000  # Increase limit for reporting
            )
            
            # Analyze audit data
            report = {
                'report_metadata': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'total_events': len(records)
                },
                'event_summary': self._analyze_event_types(records),
                'pii_access_summary': self._analyze_pii_access(records),
                'security_events': self._analyze_security_events(records),
                'compliance_metrics': self._calculate_compliance_metrics(records),
                'integrity_status': self.verify_audit_chain_integrity(start_date)
            }
            
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate compliance report: {e}")
            return {'error': str(e)}
    
    def _calculate_record_checksum(self, record: ImmutableAuditRecord, previous_checksum: Optional[str]) -> str:
        """Calculate expected checksum for a record."""
        event_json = json.dumps(record.event_data, sort_keys=True, default=str)
        checksum_input = f"{event_json}{previous_checksum or ''}"
        return hashlib.sha256(checksum_input.encode()).hexdigest()
    
    def _get_s3_records_for_verification(self, start_date: Optional[datetime]) -> List[ImmutableAuditRecord]:
        """Get records from S3 for integrity verification."""
        # This would implement S3 listing and retrieval
        # For now, return empty list as placeholder
        return []
    
    def _analyze_event_types(self, records: List[AuditEvent]) -> Dict[str, int]:
        """Analyze event types in audit records."""
        event_counts = {}
        for record in records:
            event_type = record.event_type.value if hasattr(record.event_type, 'value') else str(record.event_type)
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
        return event_counts
    
    def _analyze_pii_access(self, records: List[AuditEvent]) -> Dict[str, Any]:
        """Analyze PII access patterns."""
        pii_events = [r for r in records if r.contains_pii or 'PII_ACCESS' in r.compliance_flags]
        
        return {
            'total_pii_access_events': len(pii_events),
            'unique_users_accessing_pii': len(set(r.user_id for r in pii_events if r.user_id)),
            'pii_access_by_user': self._count_by_user(pii_events)
        }
    
    def _analyze_security_events(self, records: List[AuditEvent]) -> Dict[str, Any]:
        """Analyze security-related events."""
        security_events = [r for r in records if any(
            flag in r.compliance_flags for flag in ['SECURITY_EVENT', 'ENCRYPTION_EVENT', 'ACCESS_DENIED']
        )]
        
        return {
            'total_security_events': len(security_events),
            'encryption_events': len([r for r in records if r.event_type.value in ['data_encrypted', 'data_decrypted']]),
            'access_denied_events': len([r for r in records if r.outcome == 'FAILURE'])
        }
    
    def _calculate_compliance_metrics(self, records: List[AuditEvent]) -> Dict[str, Any]:
        """Calculate compliance metrics."""
        total_events = len(records)
        successful_events = len([r for r in records if r.outcome == 'SUCCESS'])
        
        return {
            'total_audit_events': total_events,
            'success_rate': (successful_events / total_events * 100) if total_events > 0 else 0,
            'average_events_per_day': total_events / 30 if total_events > 0 else 0,  # Assuming 30-day period
            'data_classification_breakdown': self._count_by_classification(records)
        }
    
    def _count_by_user(self, records: List[AuditEvent]) -> Dict[str, int]:
        """Count events by user."""
        user_counts = {}
        for record in records:
            if record.user_id:
                user_counts[record.user_id] = user_counts.get(record.user_id, 0) + 1
        return user_counts
    
    def _count_by_classification(self, records: List[AuditEvent]) -> Dict[str, int]:
        """Count events by data classification."""
        classification_counts = {}
        for record in records:
            classification = record.data_classification
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
        return classification_counts
    
    def _store_in_dynamodb(self, record: ImmutableAuditRecord):
        """Store record in DynamoDB for fast queries."""
        item = {
            'record_id': record.record_id,
            'timestamp': record.timestamp.isoformat(),
            'event_type': record.event_data.get('event_type'),
            'user_id': record.event_data.get('user_id'),
            'resource_type': record.event_data.get('resource_type'),
            'resource_id': record.event_data.get('resource_id'),
            'action': record.event_data.get('action'),
            'outcome': record.event_data.get('outcome'),
            'checksum': record.checksum,
            'retention_until': record.retention_until.isoformat(),
            'event_data': record.event_data
        }
        
        self.audit_table.put_item(Item=item)
    
    def _store_in_s3(self, record: ImmutableAuditRecord):
        """Store record in S3 for long-term retention."""
        # Create S3 key with date partitioning
        date_partition = record.timestamp.strftime('%Y/%m/%d')
        s3_key = f"audit-logs/{date_partition}/{record.record_id}.json"
        
        # Store record as JSON
        record_json = record.model_dump_json(indent=2)
        
        self.s3.put_object(
            Bucket=self.audit_bucket_name,
            Key=s3_key,
            Body=record_json,
            ContentType='application/json',
            ServerSideEncryption='aws:kms',
            SSEKMSKeyId=self.settings.encryption_key_id,
            Metadata={
                'record_id': record.record_id,
                'event_type': record.event_data.get('event_type', ''),
                'checksum': record.checksum
            }
        )


@lru_cache()
def get_audit_storage() -> AuditStorage:
    """Get cached audit storage instance."""
    return AuditStorage()