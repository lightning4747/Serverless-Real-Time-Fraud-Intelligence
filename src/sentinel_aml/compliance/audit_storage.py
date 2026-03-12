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