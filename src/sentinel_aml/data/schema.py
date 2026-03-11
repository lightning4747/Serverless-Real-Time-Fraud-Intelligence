"""Neptune graph schema definitions for AML data."""

from typing import Dict, List, Any
from datetime import datetime
from sentinel_aml.core.logging import get_logger

logger = get_logger(__name__)


class GraphSchema:
    """Neptune graph schema manager for AML system."""
    
    # Vertex labels and their properties
    VERTEX_SCHEMAS = {
        'Account': {
            'required_properties': [
                'account_id',
                'customer_name_hash',
                'account_type',
                'risk_score',
                'creation_date',
                'currency',
                'is_active'
            ],
            'optional_properties': [
                'customer_id',
                'country_code',
                'is_pep',
                'kyc_status',
                'balance',
                'last_activity_date'
            ],
            'indexes': ['account_id', 'customer_id', 'risk_score'],
            'constraints': {
                'account_id': 'unique',
                'risk_score': 'range(0.0, 1.0)',
                'account_type': 'enum(checking, savings, business, investment, credit, loan)'
            },
            'property_types': {
                'account_id': 'string',
                'customer_name_hash': 'string',
                'account_type': 'string',
                'risk_score': 'double',
                'creation_date': 'string',
                'currency': 'string',
                'is_active': 'boolean',
                'customer_id': 'string',
                'country_code': 'string',
                'is_pep': 'boolean',
                'kyc_status': 'string',
                'balance': 'double',
                'last_activity_date': 'string'
            }
        },
        'Transaction': {
            'required_properties': [
                'transaction_id',
                'amount',
                'timestamp',
                'transaction_type',
                'currency',
                'is_cash',
                'is_international'
            ],
            'optional_properties': [
                'description',
                'reference_number',
                'channel',
                'country_code',
                'city',
                'risk_flags'
            ],
            'indexes': ['transaction_id', 'timestamp', 'amount'],
            'constraints': {
                'transaction_id': 'unique',
                'amount': 'positive',
                'transaction_type': 'enum(deposit, withdrawal, transfer, payment, wire, ach, check, card)'
            },
            'property_types': {
                'transaction_id': 'string',
                'amount': 'double',
                'timestamp': 'string',
                'transaction_type': 'string',
                'currency': 'string',
                'is_cash': 'boolean',
                'is_international': 'boolean',
                'description': 'string',
                'reference_number': 'string',
                'channel': 'string',
                'country_code': 'string',
                'city': 'string',
                'risk_flags': 'string'
            }
        }
    }
    
    # Edge labels and their properties
    EDGE_SCHEMAS = {
        'SENT_TO': {
            'description': 'Direct transaction relationship between accounts',
            'from_vertex': 'Account',
            'to_vertex': 'Account',
            'required_properties': [
                'transaction_id',
                'amount',
                'timestamp',
                'transaction_type',
                'edge_id',
                'created_at'
            ],
            'constraints': {
                'amount': 'positive',
                'transaction_id': 'references(Transaction.transaction_id)'
            },
            'property_types': {
                'transaction_id': 'string',
                'amount': 'double',
                'timestamp': 'string',
                'transaction_type': 'string',
                'edge_id': 'string',
                'created_at': 'string'
            }
        },
        'INITIATED': {
            'description': 'Account initiated a transaction',
            'from_vertex': 'Account',
            'to_vertex': 'Transaction',
            'required_properties': ['timestamp'],
            'constraints': {},
            'property_types': {
                'timestamp': 'string'
            }
        },
        'RECEIVED': {
            'description': 'Account received a transaction',
            'from_vertex': 'Account',
            'to_vertex': 'Transaction',
            'required_properties': ['timestamp'],
            'constraints': {},
            'property_types': {
                'timestamp': 'string'
            }
        }
    }
    
    @classmethod
    def get_vertex_schema(cls, label: str) -> Dict[str, Any]:
        """Get schema definition for a vertex label."""
        return cls.VERTEX_SCHEMAS.get(label, {})
    
    @classmethod
    def get_edge_schema(cls, label: str) -> Dict[str, Any]:
        """Get schema definition for an edge label."""
        return cls.EDGE_SCHEMAS.get(label, {})
    
    @classmethod
    def validate_vertex_properties(cls, label: str, properties: Dict[str, Any]) -> List[str]:
        """Validate vertex properties against schema."""
        schema = cls.get_vertex_schema(label)
        if not schema:
            return [f"Unknown vertex label: {label}"]
        
        errors = []
        required_props = schema.get('required_properties', [])
        
        # Check required properties
        for prop in required_props:
            if prop not in properties:
                errors.append(f"Missing required property: {prop}")
        
        # Check constraints
        constraints = schema.get('constraints', {})
        for prop, constraint in constraints.items():
            if prop in properties:
                value = properties[prop]
                
                if constraint == 'unique':
                    # Uniqueness will be enforced at database level
                    continue
                elif constraint.startswith('range('):
                    # Parse range constraint: range(0.0, 1.0)
                    range_str = constraint[6:-1]  # Remove 'range(' and ')'
                    min_val, max_val = map(float, range_str.split(', '))
                    if not (min_val <= float(value) <= max_val):
                        errors.append(f"Property {prop} must be between {min_val} and {max_val}")
                elif constraint.startswith('enum('):
                    # Parse enum constraint: enum(value1, value2, value3)
                    enum_str = constraint[5:-1]  # Remove 'enum(' and ')'
                    valid_values = [v.strip() for v in enum_str.split(', ')]
                    if str(value) not in valid_values:
                        errors.append(f"Property {prop} must be one of: {valid_values}")
                elif constraint == 'positive':
                    if float(value) <= 0:
                        errors.append(f"Property {prop} must be positive")
        
        return errors
    
    @classmethod
    def validate_edge_properties(cls, label: str, properties: Dict[str, Any]) -> List[str]:
        """Validate edge properties against schema."""
        schema = cls.get_edge_schema(label)
        if not schema:
            return [f"Unknown edge label: {label}"]
        
        errors = []
        required_props = schema.get('required_properties', [])
        
        # Check required properties
        for prop in required_props:
            if prop not in properties:
                errors.append(f"Missing required property: {prop}")
        
        # Check constraints
        constraints = schema.get('constraints', {})
        for prop, constraint in constraints.items():
            if prop in properties:
                value = properties[prop]
                
                if constraint == 'positive':
                    if float(value) <= 0:
                        errors.append(f"Property {prop} must be positive")
                elif constraint.startswith('references('):
                    # Reference constraints will be enforced at application level
                    continue
        
        return errors
    
    @classmethod
    def validate_referential_integrity(cls, edge_label: str, from_vertex_props: Dict[str, Any], 
                                     to_vertex_props: Dict[str, Any]) -> List[str]:
        """Validate referential integrity between vertices and edges."""
        errors = []
        edge_schema = cls.get_edge_schema(edge_label)
        
        if not edge_schema:
            return [f"Unknown edge label: {edge_label}"]
        
        # Check vertex type compatibility
        expected_from = edge_schema.get('from_vertex')
        expected_to = edge_schema.get('to_vertex')
        
        if expected_from and from_vertex_props.get('label') != expected_from:
            errors.append(f"Edge {edge_label} requires from_vertex to be {expected_from}")
        
        if expected_to and to_vertex_props.get('label') != expected_to:
            errors.append(f"Edge {edge_label} requires to_vertex to be {expected_to}")
        
        return errors
    
    @classmethod
    def get_gremlin_schema_creation_queries(cls) -> List[str]:
        """Generate Gremlin queries to create schema indexes and constraints."""
        queries = []
        
        # Add schema creation header
        queries.append("// Neptune Graph Schema Creation for Sentinel-AML")
        queries.append("// Note: Neptune uses different syntax for schema management")
        queries.append("")
        
        # Vertex schema documentation
        for label, schema in cls.VERTEX_SCHEMAS.items():
            queries.append(f"// {label} vertex schema")
            queries.append(f"// Required properties: {', '.join(schema.get('required_properties', []))}")
            queries.append(f"// Optional properties: {', '.join(schema.get('optional_properties', []))}")
            
            # Property type definitions (for documentation)
            property_types = schema.get('property_types', {})
            for prop, prop_type in property_types.items():
                queries.append(f"// {prop}: {prop_type}")
            
            queries.append("")
        
        # Edge schema documentation
        for label, schema in cls.EDGE_SCHEMAS.items():
            queries.append(f"// {label} edge schema")
            queries.append(f"// Description: {schema.get('description', '')}")
            queries.append(f"// From: {schema.get('from_vertex', 'Any')} -> To: {schema.get('to_vertex', 'Any')}")
            queries.append(f"// Required properties: {', '.join(schema.get('required_properties', []))}")
            queries.append("")
        
        # Sample vertex creation queries
        queries.extend([
            "// Sample Account vertex creation:",
            "g.addV('Account')",
            "  .property('account_id', 'ACC123456789')",
            "  .property('customer_name_hash', 'hashed_customer_name')",
            "  .property('account_type', 'checking')",
            "  .property('risk_score', 0.2)",
            "  .property('creation_date', '2024-01-01T00:00:00Z')",
            "  .property('currency', 'USD')",
            "  .property('is_active', true)",
            "",
            "// Sample Transaction vertex creation:",
            "g.addV('Transaction')",
            "  .property('transaction_id', 'TXN123456789')",
            "  .property('amount', 1500.00)",
            "  .property('timestamp', '2024-01-01T12:00:00Z')",
            "  .property('transaction_type', 'transfer')",
            "  .property('currency', 'USD')",
            "  .property('is_cash', false)",
            "  .property('is_international', false)",
            "",
            "// Sample SENT_TO edge creation:",
            "g.V().has('Account', 'account_id', 'ACC123456789').as('from')",
            "  .V().has('Account', 'account_id', 'ACC987654321').as('to')",
            "  .addE('SENT_TO').from('from').to('to')",
            "  .property('transaction_id', 'TXN123456789')",
            "  .property('amount', 1500.00)",
            "  .property('timestamp', '2024-01-01T12:00:00Z')",
            "  .property('transaction_type', 'transfer')",
            "  .property('edge_id', 'EDGE123456789')",
            "  .property('created_at', '2024-01-01T12:00:00Z')"
        ])
        
        return queries
    
    @classmethod
    def get_schema_validation_queries(cls) -> List[str]:
        """Generate Gremlin queries for schema validation."""
        return [
            "// Schema validation queries",
            "",
            "// Count vertices by label",
            "g.V().groupCount().by(label)",
            "",
            "// Count edges by label", 
            "g.E().groupCount().by(label)",
            "",
            "// Validate Account properties",
            "g.V().hasLabel('Account').has('account_id').count()",
            "g.V().hasLabel('Account').has('risk_score').count()",
            "",
            "// Validate Transaction properties",
            "g.V().hasLabel('Transaction').has('transaction_id').count()",
            "g.V().hasLabel('Transaction').has('amount').count()",
            "",
            "// Validate SENT_TO edge integrity",
            "g.E().hasLabel('SENT_TO').has('transaction_id').count()",
            "g.E().hasLabel('SENT_TO').has('amount').count()",
            "",
            "// Check referential integrity",
            "g.V().hasLabel('Account').out('SENT_TO').hasLabel('Account').count()",
            "g.V().hasLabel('Account').out('INITIATED').hasLabel('Transaction').count()",
            "g.V().hasLabel('Account').out('RECEIVED').hasLabel('Transaction').count()"
        ]
    
    @classmethod
    def get_schema_documentation(cls) -> Dict[str, Any]:
        """Get complete schema documentation."""
        return {
            'vertices': cls.VERTEX_SCHEMAS,
            'edges': cls.EDGE_SCHEMAS,
            'description': 'AML graph schema for transaction relationship analysis',
            'version': '1.0.0',
            'compliance': {
                'requirements': ['2.1', '2.2', '2.3', '2.5'],
                'description': 'Implements Account and Transaction nodes with SENT_TO relationships'
            }
        }
    
    @classmethod
    def export_schema_to_file(cls, filepath: str) -> None:
        """Export schema definitions to a file."""
        import json
        
        schema_doc = cls.get_schema_documentation()
        gremlin_queries = cls.get_gremlin_schema_creation_queries()
        validation_queries = cls.get_schema_validation_queries()
        
        export_data = {
            'schema': schema_doc,
            'gremlin_creation_queries': gremlin_queries,
            'validation_queries': validation_queries,
            'export_timestamp': datetime.now().isoformat()
        }
        
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        logger.info("Schema exported to file", filepath=filepath)
    
    @classmethod
    def log_schema_info(cls) -> None:
        """Log schema information for debugging."""
        logger.info("Graph schema loaded", 
                   vertex_types=list(cls.VERTEX_SCHEMAS.keys()),
                   edge_types=list(cls.EDGE_SCHEMAS.keys()))


# Initialize schema logging
GraphSchema.log_schema_info()