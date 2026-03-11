"""Unit tests for Neptune client with schema validation."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal
from datetime import datetime, timezone

from sentinel_aml.data.neptune_client import NeptuneClient
from sentinel_aml.data.models import Account, Transaction, TransactionEdge, AccountType, TransactionType
from sentinel_aml.core.exceptions import NeptuneConnectionError, NeptuneQueryError


class TestNeptuneClient:
    """Test NeptuneClient class."""
    
    @pytest.fixture
    def mock_connection(self):
        """Mock Neptune connection."""
        with patch('sentinel_aml.data.neptune_client.DriverRemoteConnection') as mock_conn:
            yield mock_conn
    
    @pytest.fixture
    def mock_traversal(self):
        """Mock Gremlin traversal."""
        with patch('sentinel_aml.data.neptune_client.traversal') as mock_trav:
            mock_g = Mock()
            mock_trav.return_value.withRemote.return_value = mock_g
            yield mock_g
    
    @pytest.fixture
    def neptune_client(self, mock_connection, mock_traversal):
        """Neptune client fixture."""
        return NeptuneClient()
    
    @pytest.fixture
    def sample_account(self):
        """Sample account for testing."""
        return Account(
            account_id="ACC123456789",
            customer_name="John Doe",
            account_type=AccountType.CHECKING,
            risk_score=0.2,
            customer_id="CUST001",
            country_code="US",
            is_pep=False,
            kyc_status="verified",
            balance=Decimal("10000.00"),
            currency="USD",
            is_active=True
        )
    
    @pytest.fixture
    def sample_transaction(self):
        """Sample transaction for testing."""
        return Transaction(
            transaction_id="TXN123456789",
            amount=Decimal("1500.00"),
            timestamp=datetime.now(timezone.utc),
            transaction_type=TransactionType.TRANSFER,
            currency="USD",
            description="Wire transfer",
            is_cash=False,
            is_international=False
        )
    
    @pytest.mark.asyncio
    async def test_validate_schema_constraints_valid_account(self, neptune_client):
        """Test schema validation with valid account properties."""
        properties = {
            'account_id': 'ACC123456789',
            'customer_name_hash': 'hashed_name',
            'account_type': 'checking',
            'risk_score': 0.5,
            'creation_date': '2024-01-01T00:00:00Z',
            'currency': 'USD',
            'is_active': True
        }
        
        # Should not raise exception
        await neptune_client.validate_schema_constraints('Account', properties)
    
    @pytest.mark.asyncio
    async def test_validate_schema_constraints_invalid_account(self, neptune_client):
        """Test schema validation with invalid account properties."""
        properties = {
            'account_id': 'ACC123456789',
            # Missing required properties
            'risk_score': 1.5,  # Invalid range
        }
        
        with pytest.raises(NeptuneQueryError) as exc_info:
            await neptune_client.validate_schema_constraints('Account', properties)
        
        assert "Schema validation failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_validate_edge_constraints_valid(self, neptune_client):
        """Test edge validation with valid properties."""
        properties = {
            'transaction_id': 'TXN123456789',
            'amount': 1500.00,
            'timestamp': '2024-01-01T12:00:00Z',
            'transaction_type': 'transfer',
            'edge_id': 'EDGE123456789',
            'created_at': '2024-01-01T12:00:00Z'
        }
        
        # Should not raise exception
        await neptune_client.validate_edge_constraints('SENT_TO', properties)
    
    @pytest.mark.asyncio
    async def test_validate_edge_constraints_invalid(self, neptune_client):
        """Test edge validation with invalid properties."""
        properties = {
            'transaction_id': 'TXN123456789',
            'amount': -100.00,  # Invalid: negative
            # Missing required properties
        }
        
        with pytest.raises(NeptuneQueryError) as exc_info:
            await neptune_client.validate_edge_constraints('SENT_TO', properties)
        
        assert "Edge schema validation failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_enforce_referential_integrity_valid(self, neptune_client, mock_traversal):
        """Test referential integrity enforcement with valid references."""
        # Mock existing entities
        mock_traversal.V.return_value.hasLabel.return_value.has.return_value.hasNext.return_value = True
        
        # Should not raise exception
        await neptune_client.enforce_referential_integrity(
            "ACC123456789", "ACC987654321", "TXN123456789"
        )
    
    @pytest.mark.asyncio
    async def test_enforce_referential_integrity_missing_account(self, neptune_client, mock_traversal):
        """Test referential integrity with missing account."""
        # Mock missing source account
        def mock_has_next(*args, **kwargs):
            call_count = getattr(mock_has_next, 'call_count', 0)
            mock_has_next.call_count = call_count + 1
            return call_count > 0  # First call (source account) returns False
        
        mock_traversal.V.return_value.hasLabel.return_value.has.return_value.hasNext = mock_has_next
        
        with pytest.raises(NeptuneQueryError) as exc_info:
            await neptune_client.enforce_referential_integrity(
                "ACC123456789", "ACC987654321", "TXN123456789"
            )
        
        assert "does not exist" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_account_with_validation(self, neptune_client, mock_traversal, sample_account):
        """Test account creation with schema validation."""
        # Mock no existing account
        mock_traversal.V.return_value.hasLabel.return_value.has.return_value.hasNext.return_value = False
        
        # Mock successful vertex creation
        mock_vertex = Mock()
        mock_vertex.id = "vertex_123"
        mock_traversal.addV.return_value.property.return_value.next.return_value = mock_vertex
        
        result = await neptune_client.create_account(sample_account)
        assert result == "vertex_123"
    
    @pytest.mark.asyncio
    async def test_create_account_duplicate(self, neptune_client, mock_traversal, sample_account):
        """Test account creation with duplicate account ID."""
        # Mock existing account
        mock_traversal.V.return_value.hasLabel.return_value.has.return_value.hasNext.return_value = True
        
        with pytest.raises(NeptuneQueryError) as exc_info:
            await neptune_client.create_account(sample_account)
        
        assert "already exists" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_transaction_with_validation(self, neptune_client, mock_traversal, sample_transaction):
        """Test transaction creation with schema validation."""
        # Mock successful vertex creation
        mock_vertex = Mock()
        mock_vertex.id = "vertex_456"
        mock_traversal.addV.return_value.property.return_value.next.return_value = mock_vertex
        
        result = await neptune_client.create_transaction(sample_transaction)
        assert result == "vertex_456"
    
    @pytest.mark.asyncio
    async def test_create_transaction_edge_with_validation(self, neptune_client, mock_traversal, sample_transaction):
        """Test transaction edge creation with validation."""
        edge = TransactionEdge(
            from_account_id="ACC123456789",
            to_account_id="ACC987654321",
            transaction_id=sample_transaction.transaction_id,
            amount=sample_transaction.amount,
            timestamp=sample_transaction.timestamp,
            transaction_type=sample_transaction.transaction_type
        )
        
        # Mock existing entities for referential integrity
        mock_traversal.V.return_value.hasLabel.return_value.has.return_value.hasNext.return_value = True
        
        # Mock vertex lookups
        mock_from_vertex = Mock()
        mock_from_vertex.id = "from_123"
        mock_to_vertex = Mock()
        mock_to_vertex.id = "to_456"
        mock_transaction_vertex = Mock()
        mock_transaction_vertex.id = "txn_789"
        
        def mock_next(*args, **kwargs):
            call_count = getattr(mock_next, 'call_count', 0)
            mock_next.call_count = call_count + 1
            if call_count == 0:
                return mock_from_vertex
            elif call_count == 1:
                return mock_to_vertex
            else:
                return mock_transaction_vertex
        
        mock_traversal.V.return_value.hasLabel.return_value.has.return_value.next = mock_next
        
        # Mock edge creation
        mock_edge = Mock()
        mock_edge.id = "edge_123"
        mock_traversal.V.return_value.addE.return_value.to.return_value.property.return_value.next.return_value = mock_edge
        
        result = await neptune_client.create_transaction_edge(edge)
        assert result == "edge_123"
    
    @pytest.mark.asyncio
    async def test_get_account(self, neptune_client, mock_traversal):
        """Test account retrieval."""
        # Mock account data
        mock_account_data = {
            'account_id': ['ACC123456789'],
            'customer_name_hash': ['hashed_name'],
            'account_type': ['checking'],
            'risk_score': [0.2]
        }
        
        mock_traversal.V.return_value.hasLabel.return_value.has.return_value.valueMap.return_value.next.return_value = mock_account_data
        
        result = await neptune_client.get_account("ACC123456789")
        assert result == mock_account_data
    
    @pytest.mark.asyncio
    async def test_get_transaction_cluster(self, neptune_client, mock_traversal):
        """Test transaction cluster retrieval."""
        mock_cluster_data = [
            {'account_id': ['ACC123456789']},
            {'transaction_id': ['TXN123456789']}
        ]
        
        mock_traversal.V.return_value.hasLabel.return_value.has.return_value.repeat.return_value.times.return_value.path.return_value.by.return_value.toList.return_value = mock_cluster_data
        
        result = await neptune_client.get_transaction_cluster("ACC123456789", depth=2)
        
        assert result['center_account'] == "ACC123456789"
        assert result['depth'] == 2
        assert result['paths'] == mock_cluster_data
    
    @pytest.mark.asyncio
    async def test_find_suspicious_patterns(self, neptune_client, mock_traversal):
        """Test suspicious pattern detection."""
        mock_suspicious_data = [
            {
                'account': {'account_id': ['ACC123456789']},
                'transactions': [
                    {'transaction_id': ['TXN001'], 'amount': [9500.0]},
                    {'transaction_id': ['TXN002'], 'amount': [9500.0]}
                ]
            }
        ]
        
        mock_traversal.V.return_value.hasLabel.return_value.where.return_value.project.return_value.by.return_value.toList.return_value = mock_suspicious_data
        
        result = await neptune_client.find_suspicious_patterns(
            time_window_hours=24,
            min_transactions=5,
            amount_threshold=10000.0
        )
        
        assert result == mock_suspicious_data
    
    @pytest.mark.asyncio
    async def test_update_risk_score(self, neptune_client, mock_traversal):
        """Test risk score update."""
        # Mock successful update
        mock_traversal.V.return_value.hasLabel.return_value.has.return_value.property.return_value.next.return_value = None
        
        # Should not raise exception
        await neptune_client.update_risk_score("ACC123456789", 0.8)
    
    @pytest.mark.asyncio
    async def test_get_health_status_healthy(self, neptune_client, mock_traversal):
        """Test health status when healthy."""
        mock_traversal.V.return_value.count.return_value.next.return_value = 1000
        mock_traversal.E.return_value.count.return_value.next.return_value = 5000
        
        result = await neptune_client.get_health_status()
        
        assert result['status'] == 'healthy'
        assert result['vertex_count'] == 1000
        assert result['edge_count'] == 5000
    
    @pytest.mark.asyncio
    async def test_get_health_status_unhealthy(self, neptune_client, mock_traversal):
        """Test health status when unhealthy."""
        mock_traversal.V.return_value.count.return_value.next.side_effect = Exception("Connection failed")
        
        result = await neptune_client.get_health_status()
        
        assert result['status'] == 'unhealthy'
        assert 'error' in result