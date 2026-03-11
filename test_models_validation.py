#!/usr/bin/env python3
"""Simple test to validate the data models and schema implementation."""

import sys
import os
from datetime import datetime, timezone
from decimal import Decimal

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import models directly to avoid Neptune client dependency issues
import sys
sys.path.insert(0, 'src')

# Import individual modules to avoid circular dependencies
from sentinel_aml.data.models import Account, Transaction, TransactionEdge, AccountType, TransactionType
from sentinel_aml.data.schema import GraphSchema


def test_account_model():
    """Test Account model validation."""
    print("Testing Account model...")
    
    # Valid account
    account = Account(
        account_id="ACC123456789",
        customer_name="John Doe",
        account_type=AccountType.CHECKING,
        risk_score=0.3,
        currency="USD"
    )
    
    print(f"✓ Valid account created: {account.account_id}")
    
    # Test validation
    try:
        invalid_account = Account(
            account_id="INVALID",  # Too short
            customer_name="Jane Doe",
            account_type=AccountType.SAVINGS,
            risk_score=1.5,  # Invalid range
            currency="INVALID"  # Invalid currency
        )
        print("✗ Should have failed validation")
    except Exception as e:
        print(f"✓ Validation correctly failed: {e}")


def test_transaction_model():
    """Test Transaction model validation."""
    print("\nTesting Transaction model...")
    
    # Valid transaction
    transaction = Transaction(
        amount=Decimal("1500.00"),
        transaction_type=TransactionType.TRANSFER,
        currency="USD"
    )
    
    print(f"✓ Valid transaction created: {transaction.transaction_id}")
    
    # Test validation
    try:
        invalid_transaction = Transaction(
            amount=Decimal("-100.00"),  # Negative amount
            transaction_type=TransactionType.WIRE,
            currency="INVALID"  # Invalid currency
        )
        print("✗ Should have failed validation")
    except Exception as e:
        print(f"✓ Validation correctly failed: {e}")


def test_transaction_edge_model():
    """Test TransactionEdge model."""
    print("\nTesting TransactionEdge model...")
    
    edge = TransactionEdge(
        from_account_id="ACC123456789",
        to_account_id="ACC987654321",
        transaction_id="TXN123456789",
        amount=Decimal("1500.00"),
        timestamp=datetime.now(timezone.utc),
        transaction_type=TransactionType.TRANSFER
    )
    
    print(f"✓ Valid transaction edge created: {edge.edge_id}")


def test_schema_validation():
    """Test schema validation."""
    print("\nTesting schema validation...")
    
    # Test vertex validation
    account_props = {
        'account_id': 'ACC123456789',
        'customer_name_hash': 'hashed_name',
        'account_type': 'checking',
        'risk_score': 0.3,
        'creation_date': '2024-01-01T00:00:00Z',
        'currency': 'USD',
        'is_active': True
    }
    
    errors = GraphSchema.validate_vertex_properties('Account', account_props)
    if not errors:
        print("✓ Account schema validation passed")
    else:
        print(f"✗ Account schema validation failed: {errors}")
    
    # Test edge validation
    edge_props = {
        'transaction_id': 'TXN123456789',
        'amount': 1500.00,
        'timestamp': '2024-01-01T12:00:00Z',
        'transaction_type': 'transfer',
        'edge_id': 'EDGE123456789',
        'created_at': '2024-01-01T12:00:00Z'
    }
    
    errors = GraphSchema.validate_edge_properties('SENT_TO', edge_props)
    if not errors:
        print("✓ SENT_TO edge schema validation passed")
    else:
        print(f"✗ SENT_TO edge schema validation failed: {errors}")


def test_schema_queries():
    """Test schema query generation."""
    print("\nTesting schema query generation...")
    
    queries = GraphSchema.get_gremlin_schema_creation_queries()
    print(f"✓ Generated {len(queries)} schema creation queries")
    
    validation_queries = GraphSchema.get_schema_validation_queries()
    print(f"✓ Generated {len(validation_queries)} validation queries")
    
    # Print first few queries as examples
    print("\nSample schema creation queries:")
    for i, query in enumerate(queries[:5]):
        if query.strip() and not query.startswith('//'):
            print(f"  {i+1}. {query}")


if __name__ == "__main__":
    print("=== Sentinel-AML Data Models and Schema Validation ===\n")
    
    try:
        test_account_model()
        test_transaction_model()
        test_transaction_edge_model()
        test_schema_validation()
        test_schema_queries()
        
        print("\n=== All tests completed successfully! ===")
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)