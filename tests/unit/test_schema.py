"""Unit tests for Neptune graph schema."""

import pytest
from sentinel_aml.data.schema import GraphSchema


class TestGraphSchema:
    """Test GraphSchema class."""
    
    def test_get_vertex_schema_account(self):
        """Test getting Account vertex schema."""
        schema = GraphSchema.get_vertex_schema('Account')
        
        assert schema is not None
        assert 'required_properties' in schema
        assert 'optional_properties' in schema
        assert 'property_types' in schema
        assert 'constraints' in schema
        
        # Check required properties
        required = schema['required_properties']
        assert 'account_id' in required
        assert 'customer_name_hash' in required
        assert 'account_type' in required
        assert 'risk_score' in required
        
        # Check property types
        types = schema['property_types']
        assert types['account_id'] == 'string'
        assert types['risk_score'] == 'double'
        assert types['is_active'] == 'boolean'
    
    def test_get_vertex_schema_transaction(self):
        """Test getting Transaction vertex schema."""
        schema = GraphSchema.get_vertex_schema('Transaction')
        
        assert schema is not None
        required = schema['required_properties']
        assert 'transaction_id' in required
        assert 'amount' in required
        assert 'timestamp' in required
        assert 'transaction_type' in required
        
        types = schema['property_types']
        assert types['transaction_id'] == 'string'
        assert types['amount'] == 'double'
        assert types['is_cash'] == 'boolean'
    
    def test_get_edge_schema_sent_to(self):
        """Test getting SENT_TO edge schema."""
        schema = GraphSchema.get_edge_schema('SENT_TO')
        
        assert schema is not None
        assert schema['from_vertex'] == 'Account'
        assert schema['to_vertex'] == 'Account'
        assert 'transaction_id' in schema['required_properties']
        assert 'amount' in schema['required_properties']
    
    def test_validate_vertex_properties_valid_account(self):
        """Test validating valid Account properties."""
        properties = {
            'account_id': 'ACC123456789',
            'customer_name_hash': 'hashed_name',
            'account_type': 'checking',
            'risk_score': 0.5,
            'creation_date': '2024-01-01T00:00:00Z',
            'currency': 'USD',
            'is_active': True
        }
        
        errors = GraphSchema.validate_vertex_properties('Account', properties)
        assert len(errors) == 0
    
    def test_validate_vertex_properties_missing_required(self):
        """Test validation with missing required properties."""
        properties = {
            'account_id': 'ACC123456789',
            # Missing customer_name_hash
            'account_type': 'checking',
            'risk_score': 0.5
        }
        
        errors = GraphSchema.validate_vertex_properties('Account', properties)
        assert len(errors) > 0
        assert any('customer_name_hash' in error for error in errors)
    
    def test_validate_vertex_properties_invalid_risk_score(self):
        """Test validation with invalid risk score range."""
        properties = {
            'account_id': 'ACC123456789',
            'customer_name_hash': 'hashed_name',
            'account_type': 'checking',
            'risk_score': 1.5,  # Invalid: > 1.0
            'creation_date': '2024-01-01T00:00:00Z',
            'currency': 'USD',
            'is_active': True
        }
        
        errors = GraphSchema.validate_vertex_properties('Account', properties)
        assert len(errors) > 0
        assert any('risk_score' in error and 'between' in error for error in errors)
    
    def test_validate_vertex_properties_invalid_account_type(self):
        """Test validation with invalid account type enum."""
        properties = {
            'account_id': 'ACC123456789',
            'customer_name_hash': 'hashed_name',
            'account_type': 'invalid_type',  # Invalid enum value
            'risk_score': 0.5,
            'creation_date': '2024-01-01T00:00:00Z',
            'currency': 'USD',
            'is_active': True
        }
        
        errors = GraphSchema.validate_vertex_properties('Account', properties)
        assert len(errors) > 0
        assert any('account_type' in error and 'one of' in error for error in errors)
    
    def test_validate_edge_properties_valid_sent_to(self):
        """Test validating valid SENT_TO edge properties."""
        properties = {
            'transaction_id': 'TXN123456789',
            'amount': 1500.00,
            'timestamp': '2024-01-01T12:00:00Z',
            'transaction_type': 'transfer',
            'edge_id': 'EDGE123456789',
            'created_at': '2024-01-01T12:00:00Z'
        }
        
        errors = GraphSchema.validate_edge_properties('SENT_TO', properties)
        assert len(errors) == 0
    
    def test_validate_edge_properties_negative_amount(self):
        """Test validation with negative amount."""
        properties = {
            'transaction_id': 'TXN123456789',
            'amount': -100.00,  # Invalid: negative
            'timestamp': '2024-01-01T12:00:00Z',
            'transaction_type': 'transfer',
            'edge_id': 'EDGE123456789',
            'created_at': '2024-01-01T12:00:00Z'
        }
        
        errors = GraphSchema.validate_edge_properties('SENT_TO', properties)
        assert len(errors) > 0
        assert any('amount' in error and 'positive' in error for error in errors)
    
    def test_validate_referential_integrity_valid(self):
        """Test referential integrity validation."""
        from_vertex = {'label': 'Account'}
        to_vertex = {'label': 'Account'}
        
        errors = GraphSchema.validate_referential_integrity('SENT_TO', from_vertex, to_vertex)
        assert len(errors) == 0
    
    def test_validate_referential_integrity_invalid(self):
        """Test referential integrity validation with wrong vertex types."""
        from_vertex = {'label': 'Transaction'}  # Wrong type
        to_vertex = {'label': 'Account'}
        
        errors = GraphSchema.validate_referential_integrity('SENT_TO', from_vertex, to_vertex)
        assert len(errors) > 0
        assert any('from_vertex' in error for error in errors)
    
    def test_get_schema_documentation(self):
        """Test getting complete schema documentation."""
        doc = GraphSchema.get_schema_documentation()
        
        assert 'vertices' in doc
        assert 'edges' in doc
        assert 'description' in doc
        assert 'version' in doc
        assert 'compliance' in doc
        
        assert 'Account' in doc['vertices']
        assert 'Transaction' in doc['vertices']
        assert 'SENT_TO' in doc['edges']
        
        # Check compliance requirements
        requirements = doc['compliance']['requirements']
        assert '2.1' in requirements
        assert '2.2' in requirements
        assert '2.3' in requirements
        assert '2.5' in requirements
    
    def test_get_gremlin_schema_creation_queries(self):
        """Test getting Gremlin schema creation queries."""
        queries = GraphSchema.get_gremlin_schema_creation_queries()
        
        assert isinstance(queries, list)
        assert len(queries) > 0
        
        # Check for key elements
        query_text = '\n'.join(queries)
        assert 'Account' in query_text
        assert 'Transaction' in query_text
        assert 'SENT_TO' in query_text
        assert 'addV' in query_text
        assert 'addE' in query_text
    
    def test_get_schema_validation_queries(self):
        """Test getting schema validation queries."""
        queries = GraphSchema.get_schema_validation_queries()
        
        assert isinstance(queries, list)
        assert len(queries) > 0
        
        query_text = '\n'.join(queries)
        assert 'groupCount' in query_text
        assert 'hasLabel' in query_text
        assert 'count()' in query_text
    
    def test_unknown_vertex_label(self):
        """Test validation with unknown vertex label."""
        errors = GraphSchema.validate_vertex_properties('UnknownVertex', {})
        assert len(errors) == 1
        assert 'Unknown vertex label' in errors[0]
    
    def test_unknown_edge_label(self):
        """Test validation with unknown edge label."""
        errors = GraphSchema.validate_edge_properties('UnknownEdge', {})
        assert len(errors) == 1
        assert 'Unknown edge label' in errors[0]