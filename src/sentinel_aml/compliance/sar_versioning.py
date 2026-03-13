"""
SAR Versioning and Audit Trail Module
Manages SAR document versions, changes, and audit trails for compliance.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import boto3
from decimal import Decimal

logger = logging.getLogger(__name__)

class SARStatus(Enum):
    """SAR document status."""
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    FILED = "FILED"
    REJECTED = "REJECTED"
    AMENDED = "AMENDED"

class ChangeType(Enum):
    """Types of changes to SAR documents."""
    CREATION = "CREATION"
    CONTENT_UPDATE = "CONTENT_UPDATE"
    STATUS_CHANGE = "STATUS_CHANGE"
    APPROVAL = "APPROVAL"
    FILING = "FILING"
    AMENDMENT = "AMENDMENT"
    REJECTION = "REJECTION"

@dataclass
class SARVersion:
    """SAR document version."""
    version_id: str
    sar_id: str
    version_number: int
    content: str
    metadata: Dict[str, Any]
    status: SARStatus
    created_timestamp: str
    created_by: str
    content_hash: str
    parent_version_id: Optional[str] = None
    change_summary: Optional[str] = None

@dataclass
class SARChange:
    """SAR change record."""
    change_id: str
    sar_id: str
    version_id: str
    change_type: ChangeType
    timestamp: str
    user_id: str
    description: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class SARApproval:
    """SAR approval record."""
    approval_id: str
    sar_id: str
    version_id: str
    approver_id: str
    approval_timestamp: str
    approval_status: str  # APPROVED, REJECTED, PENDING
    comments: Optional[str] = None
    conditions: Optional[List[str]] = None

class SARVersionManager:
    """Manages SAR document versioning and audit trails."""
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.s3_client = boto3.client('s3')
        
        # DynamoDB tables
        self.versions_table = self.dynamodb.Table('sentinel-aml-sar-versions')
        self.changes_table = self.dynamodb.Table('sentinel-aml-sar-changes')
        self.approvals_table = self.dynamodb.Table('sentinel-aml-sar-approvals')
        
        # S3 bucket for version content storage
        self.versions_bucket = 'sentinel-aml-sar-versions'
    
    def create_initial_version(self, sar_id: str, content: str, metadata: Dict[str, Any], 
                             created_by: str) -> SARVersion:
        """Create the initial version of a SAR document."""
        logger.info(f"Creating initial version for SAR {sar_id}")
        
        version_id = self._generate_version_id(sar_id, 1)
        content_hash = self._calculate_content_hash(content)
        
        version = SARVersion(
            version_id=version_id,
            sar_id=sar_id,
            version_number=1,
            content=content,
            metadata=metadata,
            status=SARStatus.DRAFT,
            created_timestamp=datetime.utcnow().isoformat(),
            created_by=created_by,
            content_hash=content_hash
        )
        
        # Store version
        self._store_version(version)
        
        # Record creation change
        self._record_change(
            sar_id=sar_id,
            version_id=version_id,
            change_type=ChangeType.CREATION,
            user_id=created_by,
            description="Initial SAR creation",
            metadata={'initial_confidence': metadata.get('confidence_score')}
        )
        
        return version
    
    def create_new_version(self, sar_id: str, content: str, metadata: Dict[str, Any],
                          created_by: str, change_summary: str, 
                          parent_version_id: str) -> SARVersion:
        """Create a new version of an existing SAR document."""
        logger.info(f"Creating new version for SAR {sar_id}")
        
        # Get current version number
        current_version = self.get_latest_version(sar_id)
        new_version_number = current_version.version_number + 1
        
        version_id = self._generate_version_id(sar_id, new_version_number)
        content_hash = self._calculate_content_hash(content)
        
        # Check if content actually changed
        if content_hash == current_version.content_hash:
            logger.warning(f"No content changes detected for SAR {sar_id}")
            return current_version
        
        version = SARVersion(
            version_id=version_id,
            sar_id=sar_id,
            version_number=new_version_number,
            content=content,
            metadata=metadata,
            status=SARStatus.DRAFT,
            created_timestamp=datetime.utcnow().isoformat(),
            created_by=created_by,
            content_hash=content_hash,
            parent_version_id=parent_version_id,
            change_summary=change_summary
        )
        
        # Store version
        self._store_version(version)
        
        # Record content update change
        self._record_change(
            sar_id=sar_id,
            version_id=version_id,
            change_type=ChangeType.CONTENT_UPDATE,
            user_id=created_by,
            description=change_summary,
            old_value=current_version.content_hash,
            new_value=content_hash,
            metadata={'version_number': new_version_number}
        )
        
        return version
    
    def update_status(self, sar_id: str, version_id: str, new_status: SARStatus, 
                     user_id: str, comments: Optional[str] = None) -> bool:
        """Update the status of a SAR version."""
        logger.info(f"Updating status for SAR {sar_id} version {version_id} to {new_status.value}")
        
        try:
            # Get current version
            version = self.get_version(version_id)
            if not version:
                raise ValueError(f"Version {version_id} not found")
            
            old_status = version.status
            
            # Update status in DynamoDB
            self.versions_table.update_item(
                Key={'version_id': version_id},
                UpdateExpression='SET #status = :new_status, last_modified = :timestamp',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':new_status': new_status.value,
                    ':timestamp': datetime.utcnow().isoformat()
                }
            )
            
            # Record status change
            self._record_change(
                sar_id=sar_id,
                version_id=version_id,
                change_type=ChangeType.STATUS_CHANGE,
                user_id=user_id,
                description=f"Status changed from {old_status.value} to {new_status.value}",
                old_value=old_status.value,
                new_value=new_status.value,
                metadata={'comments': comments} if comments else None
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update status for SAR {sar_id}: {str(e)}")
            return False
    
    def approve_sar(self, sar_id: str, version_id: str, approver_id: str, 
                   approval_status: str, comments: Optional[str] = None,
                   conditions: Optional[List[str]] = None) -> SARApproval:
        """Record SAR approval or rejection."""
        logger.info(f"Recording approval for SAR {sar_id} version {version_id}")
        
        approval_id = self._generate_approval_id(sar_id, version_id)
        
        approval = SARApproval(
            approval_id=approval_id,
            sar_id=sar_id,
            version_id=version_id,
            approver_id=approver_id,
            approval_timestamp=datetime.utcnow().isoformat(),
            approval_status=approval_status,
            comments=comments,
            conditions=conditions
        )
        
        # Store approval record
        self.approvals_table.put_item(Item=asdict(approval))
        
        # Update SAR status based on approval
        if approval_status == "APPROVED":
            new_status = SARStatus.APPROVED
            change_type = ChangeType.APPROVAL
        else:
            new_status = SARStatus.REJECTED
            change_type = ChangeType.REJECTION
        
        self.update_status(sar_id, version_id, new_status, approver_id, comments)
        
        # Record approval change
        self._record_change(
            sar_id=sar_id,
            version_id=version_id,
            change_type=change_type,
            user_id=approver_id,
            description=f"SAR {approval_status.lower()} by {approver_id}",
            new_value=approval_status,
            metadata={
                'approval_id': approval_id,
                'comments': comments,
                'conditions': conditions
            }
        )
        
        return approval
    
    def get_version(self, version_id: str) -> Optional[SARVersion]:
        """Get a specific SAR version."""
        try:
            response = self.versions_table.get_item(Key={'version_id': version_id})
            if 'Item' in response:
                item = response['Item']
                
                # Get content from S3
                content = self._get_version_content(version_id)
                item['content'] = content
                
                return SARVersion(**item)
            return None
        except Exception as e:
            logger.error(f"Failed to get version {version_id}: {str(e)}")
            return None
    
    def get_latest_version(self, sar_id: str) -> Optional[SARVersion]:
        """Get the latest version of a SAR."""
        try:
            response = self.versions_table.query(
                IndexName='sar-id-version-index',
                KeyConditionExpression='sar_id = :sar_id',
                ExpressionAttributeValues={':sar_id': sar_id},
                ScanIndexForward=False,  # Descending order
                Limit=1
            )
            
            if response['Items']:
                item = response['Items'][0]
                content = self._get_version_content(item['version_id'])
                item['content'] = content
                return SARVersion(**item)
            
            return None
        except Exception as e:
            logger.error(f"Failed to get latest version for SAR {sar_id}: {str(e)}")
            return None
    
    def get_version_history(self, sar_id: str) -> List[SARVersion]:
        """Get complete version history for a SAR."""
        try:
            response = self.versions_table.query(
                IndexName='sar-id-version-index',
                KeyConditionExpression='sar_id = :sar_id',
                ExpressionAttributeValues={':sar_id': sar_id},
                ScanIndexForward=True  # Ascending order
            )
            
            versions = []
            for item in response['Items']:
                # Don't load content for history (performance)
                item['content'] = '[CONTENT_NOT_LOADED]'
                versions.append(SARVersion(**item))
            
            return versions
        except Exception as e:
            logger.error(f"Failed to get version history for SAR {sar_id}: {str(e)}")
            return []
    
    def get_change_history(self, sar_id: str) -> List[SARChange]:
        """Get complete change history for a SAR."""
        try:
            response = self.changes_table.query(
                IndexName='sar-id-timestamp-index',
                KeyConditionExpression='sar_id = :sar_id',
                ExpressionAttributeValues={':sar_id': sar_id},
                ScanIndexForward=True  # Chronological order
            )
            
            changes = []
            for item in response['Items']:
                changes.append(SARChange(**item))
            
            return changes
        except Exception as e:
            logger.error(f"Failed to get change history for SAR {sar_id}: {str(e)}")
            return []
    
    def get_approval_history(self, sar_id: str) -> List[SARApproval]:
        """Get approval history for a SAR."""
        try:
            response = self.approvals_table.query(
                IndexName='sar-id-timestamp-index',
                KeyConditionExpression='sar_id = :sar_id',
                ExpressionAttributeValues={':sar_id': sar_id},
                ScanIndexForward=True  # Chronological order
            )
            
            approvals = []
            for item in response['Items']:
                approvals.append(SARApproval(**item))
            
            return approvals
        except Exception as e:
            logger.error(f"Failed to get approval history for SAR {sar_id}: {str(e)}")
            return []
    
    def compare_versions(self, version_id_1: str, version_id_2: str) -> Dict[str, Any]:
        """Compare two SAR versions and return differences."""
        logger.info(f"Comparing versions {version_id_1} and {version_id_2}")
        
        version_1 = self.get_version(version_id_1)
        version_2 = self.get_version(version_id_2)
        
        if not version_1 or not version_2:
            raise ValueError("One or both versions not found")
        
        # Simple text comparison (could be enhanced with diff algorithms)
        content_changed = version_1.content_hash != version_2.content_hash
        metadata_changed = version_1.metadata != version_2.metadata
        status_changed = version_1.status != version_2.status
        
        return {
            'version_1': {
                'version_id': version_1.version_id,
                'version_number': version_1.version_number,
                'created_timestamp': version_1.created_timestamp,
                'status': version_1.status.value,
                'content_hash': version_1.content_hash
            },
            'version_2': {
                'version_id': version_2.version_id,
                'version_number': version_2.version_number,
                'created_timestamp': version_2.created_timestamp,
                'status': version_2.status.value,
                'content_hash': version_2.content_hash
            },
            'differences': {
                'content_changed': content_changed,
                'metadata_changed': metadata_changed,
                'status_changed': status_changed,
                'version_number_diff': version_2.version_number - version_1.version_number
            }
        }
    
    def _store_version(self, version: SARVersion):
        """Store SAR version in DynamoDB and S3."""
        # Store metadata in DynamoDB
        version_item = asdict(version)
        content = version_item.pop('content')  # Remove content for DynamoDB
        
        self.versions_table.put_item(Item=version_item)
        
        # Store content in S3
        self.s3_client.put_object(
            Bucket=self.versions_bucket,
            Key=f"versions/{version.version_id}/content.txt",
            Body=content,
            ContentType='text/plain',
            ServerSideEncryption='AES256',
            Metadata={
                'sar_id': version.sar_id,
                'version_number': str(version.version_number),
                'content_hash': version.content_hash
            }
        )
    
    def _get_version_content(self, version_id: str) -> str:
        """Get version content from S3."""
        try:
            response = self.s3_client.get_object(
                Bucket=self.versions_bucket,
                Key=f"versions/{version_id}/content.txt"
            )
            return response['Body'].read().decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to get content for version {version_id}: {str(e)}")
            return ""
    
    def _record_change(self, sar_id: str, version_id: str, change_type: ChangeType,
                      user_id: str, description: str, old_value: Optional[str] = None,
                      new_value: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """Record a change in the audit trail."""
        change_id = self._generate_change_id(sar_id, change_type)
        
        change = SARChange(
            change_id=change_id,
            sar_id=sar_id,
            version_id=version_id,
            change_type=change_type,
            timestamp=datetime.utcnow().isoformat(),
            user_id=user_id,
            description=description,
            old_value=old_value,
            new_value=new_value,
            metadata=metadata
        )
        
        self.changes_table.put_item(Item=asdict(change))
    
    def _calculate_content_hash(self, content: str) -> str:
        """Calculate SHA-256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _generate_version_id(self, sar_id: str, version_number: int) -> str:
        """Generate unique version ID."""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        return f"{sar_id}_v{version_number:03d}_{timestamp}"
    
    def _generate_change_id(self, sar_id: str, change_type: ChangeType) -> str:
        """Generate unique change ID."""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        return f"{sar_id}_{change_type.value}_{timestamp}"
    
    def _generate_approval_id(self, sar_id: str, version_id: str) -> str:
        """Generate unique approval ID."""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        return f"{sar_id}_APPROVAL_{timestamp}"