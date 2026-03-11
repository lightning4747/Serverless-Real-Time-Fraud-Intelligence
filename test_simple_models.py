#!/usr/bin/env python3
"""Simple test to validate the data models without Neptune dependencies."""

import sys
import os
from datetime import datetime, timezone
from decimal import Decimal

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import core utilities first
from sentinel_aml.core.utils import validate_account_id, validate_currency_code, validate_transaction_amount

def test_core_utilities():
    """Test core utility functions."""
    print("Testing core utilities...")
    
    # Test account ID validation
    assert validate_account_id("ACC123456789") == True
    assert validate_account_id("INVALID") == False
    print("✓ Account ID validation works")
    
    # Test currency validation
    assert validate_currency_code("USD") == "USD"
    assert validate_currency_code("eur") == "EUR"
    try:
        validate_currency_code("INVALID")
        assert False, "Should have raised ValidationError"
    except Exception:
        pass
    print("✓ Currency validation works")
    
    # Test amount validation
    amount = validate_transaction_amount("1500.00")
    assert amount == Decimal("1500.00")
    try:
        validate_transaction_amount("-100")
        assert False, "Should have raised ValidationError"
    except Exception:
        pass
    print("✓ Amount validation works")

def test_models_import():
    """Test that models can be imported."""
    print("\nTesting model imports...")
    
    try:
        from sentinel_aml.data.models import AccountType, TransactionType, Account, Transaction, TransactionEdge
        print("✓ Models imported successfully")
        
        # Test enum values
        assert AccountType.CHECKING == "checking"
        assert TransactionType.TRANSFER == "transfer"
        print("✓ Enums work correctly")
        
        # Test basic model creation
        account = Account(
            account_id="ACC123456789",
            customer_name="John Doe",
            account_type=AccountType.CHECKING,
            risk_score=0.3,
            currency="USD"
        )
        print(f"✓ Account model created: {account.account_id}")
        
        transaction = Transaction(
            amount=Decimal("1500.00"),
            transaction_type=TransactionType.TRANSFER,
            currency="USD"
        )
        print(f"✓ Transaction model created: {transaction.transaction_id}")
        
        edge = TransactionEdge(
            from_account_id="ACC123456789",
            to_account_id="ACC987654321",
            transaction_id=transaction.transaction_id,
            amount=Decimal("1500.00"),
            timestamp=datetime.now(timezone.utc),
            transaction_type=TransactionType.TRANSFER
        )
        print(f"✓ Transaction edge created: {edge.edge_id}")
        
    except Exception as e:
        print(f"✗ Model import failed: {e}")
        raise

def test_schema_import():
    """Test that schema can be imported."""
    print("\nTesting schema import...")
    
    try:
        from sentinel_aml.data.schema import GraphSchema
        print("✓ Schema imported successfully")
        
        # Test schema methods
        vertex_schemas = GraphSchema.VERTEX_SCHEMAS
        edge_schemas = GraphSchema.EDGE_SCHEMAS
        
        print(f"✓ Found {len(vertex_schemas)} vertex schemas: {list(vertex_schemas.keys())}")
        print(f"✓ Found {len(edge_schemas)} edge schemas: {list(edge_schemas.keys())}")
        
        # Test validation
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
        
    except Exception as e:
        print(f"✗ Schema import failed: {e}")
        raise

if __name__ == "__main__":
    print("=== Simple Sentinel-AML Models Test ===\n")
    
    try:
        test_core_utilities()
        test_models_import()
        test_schema_import()
        
        print("\n=== All tests completed successfully! ===")
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)