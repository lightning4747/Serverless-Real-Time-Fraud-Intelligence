#!/usr/bin/env python3
"""Simple test for schema functionality."""

import sys
sys.path.insert(0, 'src')

from sentinel_aml.data.schema import GraphSchema

def test_schema():
    """Test basic schema functionality."""
    
    print("Testing GraphSchema...")
    
    # Test getting vertex schema
    account_schema = GraphSchema.get_vertex_schema('Account')
    assert account_schema is not None
    assert 'required_properties' in account_schema
    assert 'account_id' in account_schema['required_properties']
    print("✓ Account vertex schema loaded")
    
    transaction_schema = GraphSchema.get_vertex_schema('Transaction')
    assert transaction_schema is not None
    assert 'transaction_id' in transaction_schema['required_properties']
    print("✓ Transaction vertex schema loaded")
    
    # Test getting edge schema
    sent_to_schema = GraphSchema.get_edge_schema('SENT_TO')
    assert sent_to_schema is not None
    assert sent_to_schema['from_vertex'] == 'Account'
    assert sent_to_schema['to_vertex'] == 'Account'
    print("✓ SENT_TO edge schema loaded")
    
    # Test validation
    valid_account_props = {
        'account_id': 'ACC123456789',
        'customer_name_hash': 'hashed_name',
        'account_type': 'checking',
        'risk_score': 0.5,
        'creation_date': '2024-01-01T00:00:00Z',
        'currency': 'USD',
        'is_active': True
    }
    
    errors = GraphSchema.validate_vertex_properties('Account', valid_account_props)
    assert len(errors) == 0
    print("✓ Valid account properties validation passed")
    
    # Test invalid properties
    invalid_account_props = {
        'account_id': 'ACC123456789',
        'risk_score': 1.5,  # Invalid: > 1.0
    }
    
    errors = GraphSchema.validate_vertex_properties('Account', invalid_account_props)
    assert len(errors) > 0
    print("✓ Invalid account properties validation failed as expected")
    
    # Test schema documentation
    doc = GraphSchema.get_schema_documentation()
    assert 'vertices' in doc
    assert 'edges' in doc
    assert len(doc['vertices']) == 2
    assert len(doc['edges']) == 3
    print(f"✓ Schema documentation: {len(doc['vertices'])} vertices, {len(doc['edges'])} edges")
    
    # Test Gremlin queries
    queries = GraphSchema.get_gremlin_schema_creation_queries()
    assert len(queries) > 0
    assert any('Account' in q for q in queries)
    print(f"✓ Generated {len(queries)} Gremlin creation queries")
    
    validation_queries = GraphSchema.get_schema_validation_queries()
    assert len(validation_queries) > 0
    print(f"✓ Generated {len(validation_queries)} validation queries")
    
    print("\n" + "="*50)
    print("ALL SCHEMA TESTS PASSED!")
    print("="*50)

if __name__ == "__main__":
    test_schema()