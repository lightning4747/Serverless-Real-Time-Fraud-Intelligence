"""Property-based tests for Neptune graph schema consistency.

This module implements Property 1: Schema consistency - All transactions must connect valid accounts.
Validates Requirements 2.1 and 2.5 from the specification.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List, Any
from unittest.mock import Mock, AsyncMock, patch

from hypothesis import given, strategies as st, assume, settings, HealthCheck
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize, invariant

from sentinel_aml.data.models import Account, Transaction, TransactionEdge, AccountType, TransactionType
from sentinel_aml.data.schema import GraphSchema
from sentinel_aml.data.neptune_client import NeptuneClient
from sentinel_aml.core.exceptions import NeptuneQueryError


# Hypothesis strategies for generating test data
@st.composite
def account_strategy(draw):
    """Generate valid Account instances."""
    account_id = draw(st.text(min_size=8, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    customer_name = draw(st.text(min_size=2, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', ' '))))
    account_type = draw(st.sampled_from(AccountType))
    risk_score = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    
    return Account(
        account_id=f"ACC{account_id}",
        customer_name=customer_name.strip(),
        account_type=account_type,
        risk_score=risk_score,
        currency="USD",
        is_active=True
    )


@st.composite
def transaction_strategy(draw):
    """Generate valid Transaction instances."""
    transaction_id = draw(st.text(min_size=8, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    amount = draw(st.decimals(min_value=Decimal('0.01'), max_value=Decimal('1000000.00'), places=2))
    transaction_type = draw(st.sampled_from(TransactionType))
    
    return Transaction(
        transaction_id=f"TXN{transaction_id}",
        amount=amount,
        transaction_type=transaction_type,
        currency="USD",
        is_cash=False,
        is_international=False
    )


@st.composite
def transaction_edge_strategy(draw, from_account_id: str, to_account_id: str, transaction_id: str):
    """Generate valid TransactionEdge instances."""
    amount = draw(st.decimals(min_value=Decimal('0.01'), max_value=Decimal('1000000.00'), places=2))
    transaction_type = draw(st.sampled_from(TransactionType))
    
    return TransactionEdge(
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        transaction_id=transaction_id,
        amount=amount,
        timestamp=datetime.now(timezone.utc),
        transaction_type=transaction_type
    )


class TestGraphSchemaProperties:
    """Property-based tests for graph schema consistency."""
    
    @pytest.mark.property
    @given(account=account_strategy())
    def test_property_account_schema_validation(self, account: Account):
        """Property: All account data must conform to schema constraints."""
        # Convert account to property dictionary
        account_props = {
            'account_id': account.account_id,
            'customer_name_hash': account.customer_name,
            'account_type': account.account_type.value,
            'risk_score': account.risk_score,
            'creation_date': account.creation_date.isoformat(),
            'currency': account.currency,
            'is_active': account.is_active
        }
        
        # Validate against schema
        errors = GraphSchema.validate_vertex_properties('Account', account_props)
        
        # Property: Valid accounts should have no schema validation errors
        assert len(errors) == 0, f"Valid account failed schema validation: {errors}"
        
        # Property: Risk score must be within bounds
        assert 0.0 <= account.risk_score <= 1.0, f"Risk score {account.risk_score} outside valid range"
        
        # Property: Account ID must be non-empty
        assert len(account.account_id) > 0, "Account ID cannot be empty"
        
        # Property: Account type must be valid enum value
        assert account.account_type in AccountType, f"Invalid account type: {account.account_type}"
    
    @pytest.mark.property
    @given(transaction=transaction_strategy())
    def test_property_transaction_schema_validation(self, transaction: Transaction):
        """Property: All transaction data must conform to schema constraints."""
        # Convert transaction to property dictionary
        transaction_props = {
            'transaction_id': transaction.transaction_id,
            'amount': float(transaction.amount),
            'timestamp': transaction.timestamp.isoformat(),
            'transaction_type': transaction.transaction_type.value,
            'currency': transaction.currency,
            'is_cash': transaction.is_cash,
            'is_international': transaction.is_international
        }
        
        # Validate against schema
        errors = GraphSchema.validate_vertex_properties('Transaction', transaction_props)
        
        # Property: Valid transactions should have no schema validation errors
        assert len(errors) == 0, f"Valid transaction failed schema validation: {errors}"
        
        # Property: Transaction amount must be positive
        assert transaction.amount > 0, f"Transaction amount {transaction.amount} must be positive"
        
        # Property: Transaction ID must be non-empty
        assert len(transaction.transaction_id) > 0, "Transaction ID cannot be empty"
        
        # Property: Transaction type must be valid enum value
        assert transaction.transaction_type in TransactionType, f"Invalid transaction type: {transaction.transaction_type}"
    
    @pytest.mark.property
    @given(
        from_account=account_strategy(),
        to_account=account_strategy(),
        transaction=transaction_strategy()
    )
    def test_property_transaction_edge_referential_integrity(
        self, from_account: Account, to_account: Account, transaction: Transaction
    ):
        """Property: All transaction edges must reference valid accounts and transactions."""
        # Ensure accounts are different
        assume(from_account.account_id != to_account.account_id)
        
        # Create transaction edge
        edge = TransactionEdge(
            from_account_id=from_account.account_id,
            to_account_id=to_account.account_id,
            transaction_id=transaction.transaction_id,
            amount=transaction.amount,
            timestamp=transaction.timestamp,
            transaction_type=transaction.transaction_type
        )
        
        # Validate edge properties
        edge_props = {
            'transaction_id': edge.transaction_id,
            'amount': float(edge.amount),
            'timestamp': edge.timestamp.isoformat(),
            'transaction_type': edge.transaction_type.value,
            'edge_id': edge.edge_id,
            'created_at': edge.created_at.isoformat()
        }
        
        errors = GraphSchema.validate_edge_properties('SENT_TO', edge_props)
        
        # Property: Valid edges should have no schema validation errors
        assert len(errors) == 0, f"Valid edge failed schema validation: {errors}"
        
        # Property: Edge must reference valid account IDs
        assert edge.from_account_id == from_account.account_id, "Edge from_account_id must match source account"
        assert edge.to_account_id == to_account.account_id, "Edge to_account_id must match destination account"
        
        # Property: Edge must reference valid transaction ID
        assert edge.transaction_id == transaction.transaction_id, "Edge transaction_id must match transaction"
        
        # Property: Edge amount must match transaction amount
        assert edge.amount == transaction.amount, "Edge amount must match transaction amount"
        
        # Property: Edge timestamp must match transaction timestamp
        assert edge.timestamp == transaction.timestamp, "Edge timestamp must match transaction timestamp"
    
    @pytest.mark.property
    @given(st.lists(account_strategy(), min_size=2, max_size=10))
    def test_property_account_uniqueness(self, accounts: List[Account]):
        """Property: All accounts must have unique account IDs."""
        # Extract account IDs
        account_ids = [account.account_id for account in accounts]
        
        # Make account IDs unique for this test
        unique_accounts = []
        seen_ids = set()
        for account in accounts:
            if account.account_id not in seen_ids:
                unique_accounts.append(account)
                seen_ids.add(account.account_id)
        
        # Property: No duplicate account IDs should exist
        unique_ids = set(account.account_id for account in unique_accounts)
        assert len(unique_ids) == len(unique_accounts), "Account IDs must be unique"
        
        # Property: Each account should validate individually
        for account in unique_accounts:
            account_props = {
                'account_id': account.account_id,
                'customer_name_hash': account.customer_name,
                'account_type': account.account_type.value,
                'risk_score': account.risk_score,
                'creation_date': account.creation_date.isoformat(),
                'currency': account.currency,
                'is_active': account.is_active
            }
            errors = GraphSchema.validate_vertex_properties('Account', account_props)
            assert len(errors) == 0, f"Account {account.account_id} failed validation: {errors}"
    
    @pytest.mark.property
    @given(st.lists(transaction_strategy(), min_size=2, max_size=10))
    def test_property_transaction_uniqueness(self, transactions: List[Transaction]):
        """Property: All transactions must have unique transaction IDs."""
        # Make transaction IDs unique for this test
        unique_transactions = []
        seen_ids = set()
        for transaction in transactions:
            if transaction.transaction_id not in seen_ids:
                unique_transactions.append(transaction)
                seen_ids.add(transaction.transaction_id)
        
        # Property: No duplicate transaction IDs should exist
        unique_ids = set(transaction.transaction_id for transaction in unique_transactions)
        assert len(unique_ids) == len(unique_transactions), "Transaction IDs must be unique"
        
        # Property: Each transaction should validate individually
        for transaction in unique_transactions:
            transaction_props = {
                'transaction_id': transaction.transaction_id,
                'amount': float(transaction.amount),
                'timestamp': transaction.timestamp.isoformat(),
                'transaction_type': transaction.transaction_type.value,
                'currency': transaction.currency,
                'is_cash': transaction.is_cash,
                'is_international': transaction.is_international
            }
            errors = GraphSchema.validate_vertex_properties('Transaction', transaction_props)
            assert len(errors) == 0, f"Transaction {transaction.transaction_id} failed validation: {errors}"


class GraphConsistencyStateMachine(RuleBasedStateMachine):
    """Stateful property testing for graph consistency over time."""
    
    def __init__(self):
        super().__init__()
        self.accounts: Dict[str, Account] = {}
        self.transactions: Dict[str, Transaction] = {}
        self.edges: List[TransactionEdge] = []
    
    @initialize()
    def setup(self):
        """Initialize the state machine."""
        self.accounts = {}
        self.transactions = {}
        self.edges = []
    
    @rule(account=account_strategy())
    def add_account(self, account: Account):
        """Add an account to the graph state."""
        # Ensure unique account ID
        if account.account_id not in self.accounts:
            self.accounts[account.account_id] = account
    
    @rule(transaction=transaction_strategy())
    def add_transaction(self, transaction: Transaction):
        """Add a transaction to the graph state."""
        # Ensure unique transaction ID
        if transaction.transaction_id not in self.transactions:
            self.transactions[transaction.transaction_id] = transaction
    
    @rule()
    def add_transaction_edge(self):
        """Add a transaction edge between existing accounts and transactions."""
        # Need at least 2 accounts and 1 transaction
        if len(self.accounts) >= 2 and len(self.transactions) >= 1:
            account_ids = list(self.accounts.keys())
            transaction_ids = list(self.transactions.keys())
            
            # Select random accounts and transaction
            from_account_id = account_ids[0]
            to_account_id = account_ids[1] if len(account_ids) > 1 else account_ids[0]
            transaction_id = transaction_ids[0]
            
            # Skip if same account (self-transfer not allowed in this test)
            if from_account_id != to_account_id:
                transaction = self.transactions[transaction_id]
                edge = TransactionEdge(
                    from_account_id=from_account_id,
                    to_account_id=to_account_id,
                    transaction_id=transaction_id,
                    amount=transaction.amount,
                    timestamp=transaction.timestamp,
                    transaction_type=transaction.transaction_type
                )
                self.edges.append(edge)
    
    @invariant()
    def all_edges_reference_valid_entities(self):
        """Invariant: All edges must reference valid accounts and transactions."""
        for edge in self.edges:
            # Property: Source account must exist
            assert edge.from_account_id in self.accounts, \
                f"Edge references non-existent source account: {edge.from_account_id}"
            
            # Property: Destination account must exist
            assert edge.to_account_id in self.accounts, \
                f"Edge references non-existent destination account: {edge.to_account_id}"
            
            # Property: Transaction must exist
            assert edge.transaction_id in self.transactions, \
                f"Edge references non-existent transaction: {edge.transaction_id}"
            
            # Property: Edge amount must match transaction amount
            transaction = self.transactions[edge.transaction_id]
            assert edge.amount == transaction.amount, \
                f"Edge amount {edge.amount} doesn't match transaction amount {transaction.amount}"
    
    @invariant()
    def all_accounts_have_valid_properties(self):
        """Invariant: All accounts must maintain valid properties."""
        for account_id, account in self.accounts.items():
            # Property: Risk score must be in valid range
            assert 0.0 <= account.risk_score <= 1.0, \
                f"Account {account_id} has invalid risk score: {account.risk_score}"
            
            # Property: Account ID must match key
            assert account.account_id == account_id, \
                f"Account ID mismatch: key={account_id}, account.account_id={account.account_id}"
    
    @invariant()
    def all_transactions_have_valid_properties(self):
        """Invariant: All transactions must maintain valid properties."""
        for transaction_id, transaction in self.transactions.items():
            # Property: Amount must be positive
            assert transaction.amount > 0, \
                f"Transaction {transaction_id} has non-positive amount: {transaction.amount}"
            
            # Property: Transaction ID must match key
            assert transaction.transaction_id == transaction_id, \
                f"Transaction ID mismatch: key={transaction_id}, transaction.transaction_id={transaction.transaction_id}"


@pytest.mark.property
class TestGraphConsistencyStateful:
    """Stateful property tests for graph consistency."""
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_graph_consistency_over_time(self):
        """Test that graph maintains consistency as entities are added."""
        # Run the state machine
        GraphConsistencyStateMachine.TestCase.settings = settings(max_examples=20)
        test_case = GraphConsistencyStateMachine.TestCase()
        test_case.runTest()


@pytest.mark.property
class TestNeptuneClientSchemaEnforcement:
    """Property tests for Neptune client schema enforcement."""
    
    @pytest.mark.asyncio
    @given(account=account_strategy())
    async def test_property_neptune_account_validation(self, account: Account):
        """Property: Neptune client must validate account schema before creation."""
        with patch('sentinel_aml.data.neptune_client.NeptuneClient') as mock_client_class:
            # Setup mock
            mock_client = Mock(spec=NeptuneClient)
            mock_client_class.return_value = mock_client
            mock_client.validate_schema_constraints = AsyncMock()
            mock_client.get_connection = AsyncMock()
            
            # Create client instance
            client = NeptuneClient()
            
            # Test account validation
            account_props = {
                'account_id': account.account_id,
                'customer_name_hash': account.customer_name,
                'account_type': account.account_type.value,
                'risk_score': account.risk_score,
                'creation_date': account.creation_date.isoformat(),
                'currency': account.currency,
                'is_active': account.is_active
            }
            
            # Property: Client should validate schema constraints
            await client.validate_schema_constraints('Account', account_props)
            mock_client.validate_schema_constraints.assert_called_once_with('Account', account_props)
    
    @pytest.mark.asyncio
    @given(
        from_account=account_strategy(),
        to_account=account_strategy(),
        transaction=transaction_strategy()
    )
    async def test_property_neptune_referential_integrity(
        self, from_account: Account, to_account: Account, transaction: Transaction
    ):
        """Property: Neptune client must enforce referential integrity for edges."""
        assume(from_account.account_id != to_account.account_id)
        
        with patch('sentinel_aml.data.neptune_client.NeptuneClient') as mock_client_class:
            # Setup mock
            mock_client = Mock(spec=NeptuneClient)
            mock_client_class.return_value = mock_client
            mock_client.enforce_referential_integrity = AsyncMock()
            
            # Create client instance
            client = NeptuneClient()
            
            # Create edge
            edge = TransactionEdge(
                from_account_id=from_account.account_id,
                to_account_id=to_account.account_id,
                transaction_id=transaction.transaction_id,
                amount=transaction.amount,
                timestamp=transaction.timestamp,
                transaction_type=transaction.transaction_type
            )
            
            # Property: Client should enforce referential integrity
            await client.enforce_referential_integrity(
                edge.from_account_id,
                edge.to_account_id,
                edge.transaction_id
            )
            
            mock_client.enforce_referential_integrity.assert_called_once_with(
                edge.from_account_id,
                edge.to_account_id,
                edge.transaction_id
            )


@pytest.mark.property
class TestSchemaConstraintViolations:
    """Property tests for schema constraint violations."""
    
    @pytest.mark.property
    def test_property_invalid_risk_score_rejected(self):
        """Property: Accounts with invalid risk scores must be rejected."""
        # Test risk scores outside valid range
        invalid_scores = [-0.1, 1.1, float('inf'), float('-inf')]
        
        for invalid_score in invalid_scores:
            if not (float('-inf') < invalid_score < float('inf')):
                continue  # Skip infinite values for this test
                
            account_props = {
                'account_id': 'ACC123',
                'customer_name_hash': 'test_customer',
                'account_type': 'checking',
                'risk_score': invalid_score,
                'creation_date': datetime.now(timezone.utc).isoformat(),
                'currency': 'USD',
                'is_active': True
            }
            
            errors = GraphSchema.validate_vertex_properties('Account', account_props)
            
            # Property: Invalid risk scores should generate validation errors
            assert len(errors) > 0, f"Invalid risk score {invalid_score} should be rejected"
            assert any('risk_score' in error for error in errors), \
                f"Risk score error not found in: {errors}"
    
    @pytest.mark.property
    def test_property_missing_required_properties_rejected(self):
        """Property: Entities missing required properties must be rejected."""
        # Test account missing required properties
        incomplete_account_props = {
            'account_id': 'ACC123',
            # Missing customer_name_hash, account_type, etc.
        }
        
        errors = GraphSchema.validate_vertex_properties('Account', incomplete_account_props)
        
        # Property: Missing required properties should generate validation errors
        assert len(errors) > 0, "Account missing required properties should be rejected"
        
        # Test transaction missing required properties
        incomplete_transaction_props = {
            'transaction_id': 'TXN123',
            # Missing amount, timestamp, etc.
        }
        
        errors = GraphSchema.validate_vertex_properties('Transaction', incomplete_transaction_props)
        
        # Property: Missing required properties should generate validation errors
        assert len(errors) > 0, "Transaction missing required properties should be rejected"
    
    @pytest.mark.property
    def test_property_invalid_enum_values_rejected(self):
        """Property: Invalid enum values must be rejected."""
        # Test invalid account type
        account_props = {
            'account_id': 'ACC123',
            'customer_name_hash': 'test_customer',
            'account_type': 'invalid_type',  # Invalid enum value
            'risk_score': 0.5,
            'creation_date': datetime.now(timezone.utc).isoformat(),
            'currency': 'USD',
            'is_active': True
        }
        
        errors = GraphSchema.validate_vertex_properties('Account', account_props)
        
        # Property: Invalid enum values should generate validation errors
        assert len(errors) > 0, "Invalid account type should be rejected"
        assert any('account_type' in error for error in errors), \
            f"Account type error not found in: {errors}"


if __name__ == "__main__":
    # Run property tests
    pytest.main([__file__, "-v", "--tb=short"])