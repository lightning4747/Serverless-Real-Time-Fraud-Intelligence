"""Neptune database client for graph operations."""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

from gremlinpython.driver import client, serializer
from gremlinpython.driver.driver_remote_connection import DriverRemoteConnection
from gremlinpython.process.anonymous_traversal import traversal
from gremlinpython.process.graph_traversal import __
from gremlinpython.process.traversal import T, P
from tenacity import retry, stop_after_attempt, wait_exponential

from sentinel_aml.core.config import get_settings, get_neptune_connection_string
from sentinel_aml.core.exceptions import NeptuneConnectionError, NeptuneQueryError
from sentinel_aml.core.logging import AMLLoggerMixin
from sentinel_aml.data.models import Account, Transaction, TransactionEdge


class NeptuneClient(AMLLoggerMixin):
    """Neptune database client for AML graph operations."""
    
    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self._connection: Optional[DriverRemoteConnection] = None
        self._client: Optional[client.Client] = None
        self._g = None
    
    async def connect(self) -> None:
        """Establish connection to Neptune database."""
        try:
            connection_string = get_neptune_connection_string()
            
            # Create connection with retry configuration
            self._connection = DriverRemoteConnection(
                connection_string,
                'g',
                pool_size=self.settings.neptune_max_connections,
                message_serializer=serializer.GraphSONSerializersV3d0()
            )
            
            # Create traversal source
            self._g = traversal().withRemote(self._connection)
            
            # Test connection
            await self._test_connection()
            
            self.logger.info(
                "Connected to Neptune database",
                endpoint=self.settings.neptune_endpoint,
                port=self.settings.neptune_port
            )
            
        except Exception as e:
            self.logger.error("Failed to connect to Neptune", error=str(e))
            raise NeptuneConnectionError(f"Failed to connect to Neptune: {e}")
    
    async def disconnect(self) -> None:
        """Close Neptune database connection."""
        try:
            if self._connection:
                self._connection.close()
                self._connection = None
                self._g = None
            
            self.logger.info("Disconnected from Neptune database")
            
        except Exception as e:
            self.logger.error("Error disconnecting from Neptune", error=str(e))
    
    @asynccontextmanager
    async def get_connection(self):
        """Context manager for Neptune connections."""
        if not self._g:
            await self.connect()
        
        try:
            yield self._g
        finally:
            # Connection is reused, don't close here
            pass
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _test_connection(self) -> None:
        """Test Neptune connection with a simple query."""
        try:
            # Simple vertex count query to test connection
            result = self._g.V().count().next()
            self.logger.debug("Neptune connection test successful", vertex_count=result)
        except Exception as e:
            raise NeptuneConnectionError(f"Connection test failed: {e}")
    
    async def validate_schema_constraints(self, vertex_label: str, properties: Dict[str, Any]) -> None:
        """Validate vertex properties against schema constraints."""
        from sentinel_aml.data.schema import GraphSchema
        
        errors = GraphSchema.validate_vertex_properties(vertex_label, properties)
        if errors:
            raise NeptuneQueryError(f"Schema validation failed: {'; '.join(errors)}")
    
    async def validate_edge_constraints(self, edge_label: str, properties: Dict[str, Any]) -> None:
        """Validate edge properties against schema constraints."""
        from sentinel_aml.data.schema import GraphSchema
        
        errors = GraphSchema.validate_edge_properties(edge_label, properties)
        if errors:
            raise NeptuneQueryError(f"Edge schema validation failed: {'; '.join(errors)}")
    
    async def enforce_referential_integrity(self, from_account_id: str, to_account_id: str, 
                                          transaction_id: str) -> None:
        """Enforce referential integrity for SENT_TO relationships."""
        try:
            async with self.get_connection() as g:
                # Check if accounts exist
                from_exists = g.V().hasLabel('Account').has('account_id', from_account_id).hasNext()
                to_exists = g.V().hasLabel('Account').has('account_id', to_account_id).hasNext()
                transaction_exists = g.V().hasLabel('Transaction').has('transaction_id', transaction_id).hasNext()
                
                if not from_exists:
                    raise NeptuneQueryError(f"Source account {from_account_id} does not exist")
                if not to_exists:
                    raise NeptuneQueryError(f"Destination account {to_account_id} does not exist")
                if not transaction_exists:
                    raise NeptuneQueryError(f"Transaction {transaction_id} does not exist")
                
        except Exception as e:
            self.logger.error("Referential integrity check failed", error=str(e))
            raise NeptuneQueryError(f"Referential integrity check failed: {e}")

    async def create_account(self, account: Account) -> str:
        """Create an account vertex in Neptune."""
        try:
            # Validate schema constraints
            account_props = {
                'account_id': account.account_id,
                'customer_name_hash': account.customer_name,
                'account_type': account.account_type.value,
                'risk_score': account.risk_score,
                'creation_date': account.creation_date.isoformat(),
                'currency': account.currency,
                'is_active': account.is_active
            }
            await self.validate_schema_constraints('Account', account_props)
            
            async with self.get_connection() as g:
                # Check if account already exists
                existing = g.V().hasLabel('Account').has('account_id', account.account_id).hasNext()
                
                if existing:
                    raise NeptuneQueryError(f"Account {account.account_id} already exists")
                
                # Create account vertex
                vertex = (g.addV('Account')
                         .property('account_id', account.account_id)
                         .property('customer_name_hash', account.customer_name)  # Will be hashed
                         .property('account_type', account.account_type.value)
                         .property('risk_score', account.risk_score)
                         .property('creation_date', account.creation_date.isoformat())
                         .property('currency', account.currency)
                         .property('is_active', account.is_active)
                         .property('is_pep', account.is_pep)
                         .property('kyc_status', account.kyc_status))
                
                # Add optional properties
                if account.customer_id:
                    vertex = vertex.property('customer_id', account.customer_id)
                if account.country_code:
                    vertex = vertex.property('country_code', account.country_code)
                if account.balance is not None:
                    vertex = vertex.property('balance', float(account.balance))
                if account.last_activity_date:
                    vertex = vertex.property('last_activity_date', account.last_activity_date.isoformat())
                
                result = vertex.next()
                
                self.log_transaction_event(
                    event_type="account_created",
                    transaction_id="N/A",
                    account_id=account.account_id
                )
                
                return str(result.id)
                
        except Exception as e:
            self.logger.error("Failed to create account", account_id=account.account_id, error=str(e))
            raise NeptuneQueryError(f"Failed to create account: {e}")
    
    async def create_transaction(self, transaction: Transaction) -> str:
        """Create a transaction vertex in Neptune."""
        try:
            # Validate schema constraints
            transaction_props = {
                'transaction_id': transaction.transaction_id,
                'amount': float(transaction.amount),
                'timestamp': transaction.timestamp.isoformat(),
                'transaction_type': transaction.transaction_type.value,
                'currency': transaction.currency,
                'is_cash': transaction.is_cash,
                'is_international': transaction.is_international
            }
            await self.validate_schema_constraints('Transaction', transaction_props)
            
            async with self.get_connection() as g:
                # Create transaction vertex
                vertex = (g.addV('Transaction')
                         .property('transaction_id', transaction.transaction_id)
                         .property('amount', float(transaction.amount))
                         .property('timestamp', transaction.timestamp.isoformat())
                         .property('transaction_type', transaction.transaction_type.value)
                         .property('currency', transaction.currency)
                         .property('is_cash', transaction.is_cash)
                         .property('is_international', transaction.is_international))
                
                # Add optional properties
                if transaction.description:
                    vertex = vertex.property('description', transaction.description)
                if transaction.reference_number:
                    vertex = vertex.property('reference_number', transaction.reference_number)
                if transaction.channel:
                    vertex = vertex.property('channel', transaction.channel)
                if transaction.country_code:
                    vertex = vertex.property('country_code', transaction.country_code)
                if transaction.city:
                    vertex = vertex.property('city', transaction.city)
                if transaction.risk_flags:
                    vertex = vertex.property('risk_flags', ','.join(transaction.risk_flags))
                
                result = vertex.next()
                
                self.log_transaction_event(
                    event_type="transaction_created",
                    transaction_id=transaction.transaction_id,
                    amount=float(transaction.amount)
                )
                
                return str(result.id)
                
        except Exception as e:
            self.logger.error("Failed to create transaction", transaction_id=transaction.transaction_id, error=str(e))
            raise NeptuneQueryError(f"Failed to create transaction: {e}")
    
    async def create_transaction_edge(self, edge: TransactionEdge) -> str:
        """Create a SENT_TO edge between accounts through a transaction."""
        try:
            # Enforce referential integrity
            await self.enforce_referential_integrity(
                edge.from_account_id, 
                edge.to_account_id, 
                edge.transaction_id
            )
            
            # Validate edge schema constraints
            edge_props = {
                'transaction_id': edge.transaction_id,
                'amount': float(edge.amount),
                'timestamp': edge.timestamp.isoformat(),
                'transaction_type': edge.transaction_type.value,
                'edge_id': edge.edge_id,
                'created_at': edge.created_at.isoformat()
            }
            await self.validate_edge_constraints('SENT_TO', edge_props)
            
            async with self.get_connection() as g:
                # Find source and destination accounts
                from_account = g.V().hasLabel('Account').has('account_id', edge.from_account_id).next()
                to_account = g.V().hasLabel('Account').has('account_id', edge.to_account_id).next()
                transaction = g.V().hasLabel('Transaction').has('transaction_id', edge.transaction_id).next()
                
                if not from_account or not to_account or not transaction:
                    raise NeptuneQueryError("Source account, destination account, or transaction not found")
                
                # Create SENT_TO edge
                edge_result = (g.V(from_account.id)
                              .addE('SENT_TO')
                              .to(g.V(to_account.id))
                              .property('transaction_id', edge.transaction_id)
                              .property('amount', float(edge.amount))
                              .property('timestamp', edge.timestamp.isoformat())
                              .property('transaction_type', edge.transaction_type.value)
                              .property('edge_id', edge.edge_id)
                              .property('created_at', edge.created_at.isoformat())
                              .next())
                
                # Create edges from accounts to transaction
                g.V(from_account.id).addE('INITIATED').to(g.V(transaction.id)).property('timestamp', edge.timestamp.isoformat()).next()
                g.V(to_account.id).addE('RECEIVED').to(g.V(transaction.id)).property('timestamp', edge.timestamp.isoformat()).next()
                
                self.log_transaction_event(
                    event_type="transaction_edge_created",
                    transaction_id=edge.transaction_id,
                    account_id=edge.from_account_id,
                    amount=float(edge.amount)
                )
                
                return str(edge_result.id)
                
        except Exception as e:
            self.logger.error("Failed to create transaction edge", 
                            from_account=edge.from_account_id,
                            to_account=edge.to_account_id,
                            transaction_id=edge.transaction_id,
                            error=str(e))
            raise NeptuneQueryError(f"Failed to create transaction edge: {e}")
    
    async def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve account by ID."""
        try:
            async with self.get_connection() as g:
                result = (g.V()
                         .hasLabel('Account')
                         .has('account_id', account_id)
                         .valueMap(True)
                         .next())
                
                return dict(result) if result else None
                
        except Exception as e:
            self.logger.error("Failed to get account", account_id=account_id, error=str(e))
            raise NeptuneQueryError(f"Failed to get account: {e}")
    
    async def get_transaction_cluster(self, account_id: str, depth: int = 2) -> Dict[str, Any]:
        """Get transaction cluster around an account for GNN analysis."""
        try:
            async with self.get_connection() as g:
                # Get connected accounts and transactions within specified depth
                cluster = (g.V()
                          .hasLabel('Account')
                          .has('account_id', account_id)
                          .repeat(__.both('SENT_TO', 'INITIATED', 'RECEIVED').simplePath())
                          .times(depth)
                          .path()
                          .by(__.valueMap(True))
                          .toList())
                
                return {
                    'center_account': account_id,
                    'depth': depth,
                    'paths': cluster,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            self.logger.error("Failed to get transaction cluster", 
                            account_id=account_id, 
                            depth=depth, 
                            error=str(e))
            raise NeptuneQueryError(f"Failed to get transaction cluster: {e}")
    
    async def find_suspicious_patterns(self, 
                                     time_window_hours: int = 24,
                                     min_transactions: int = 5,
                                     amount_threshold: float = 10000.0) -> List[Dict[str, Any]]:
        """Find potential smurfing patterns in the graph."""
        try:
            async with self.get_connection() as g:
                # Find accounts with high transaction frequency
                current_time = datetime.now()
                time_threshold = current_time.timestamp() - (time_window_hours * 3600)
                
                suspicious_accounts = (g.V()
                                     .hasLabel('Account')
                                     .where(__.out('INITIATED')
                                           .hasLabel('Transaction')
                                           .has('timestamp', P.gte(time_threshold))
                                           .count()
                                           .is_(P.gte(min_transactions)))
                                     .project('account', 'transactions')
                                     .by(__.valueMap(True))
                                     .by(__.out('INITIATED')
                                        .hasLabel('Transaction')
                                        .has('timestamp', P.gte(time_threshold))
                                        .valueMap(True)
                                        .fold())
                                     .toList())
                
                return suspicious_accounts
                
        except Exception as e:
            self.logger.error("Failed to find suspicious patterns", error=str(e))
            raise NeptuneQueryError(f"Failed to find suspicious patterns: {e}")
    
    async def update_risk_score(self, account_id: str, risk_score: float) -> None:
        """Update account risk score."""
        try:
            async with self.get_connection() as g:
                g.V().hasLabel('Account').has('account_id', account_id).property('risk_score', risk_score).next()
                
                self.log_transaction_event(
                    event_type="risk_score_updated",
                    transaction_id="N/A",
                    account_id=account_id,
                    risk_score=risk_score
                )
                
        except Exception as e:
            self.logger.error("Failed to update risk score", 
                            account_id=account_id, 
                            risk_score=risk_score, 
                            error=str(e))
            raise NeptuneQueryError(f"Failed to update risk score: {e}")
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get Neptune cluster health status."""
        try:
            async with self.get_connection() as g:
                vertex_count = g.V().count().next()
                edge_count = g.E().count().next()
                
                return {
                    'status': 'healthy',
                    'vertex_count': vertex_count,
                    'edge_count': edge_count,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            self.logger.error("Failed to get health status", error=str(e))
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }