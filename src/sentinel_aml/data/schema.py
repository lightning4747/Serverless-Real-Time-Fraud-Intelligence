"""Neptune graph schema definitions for AML data."""

from typing import Dict, List, Any
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
            }
        }
    }
    
    # Edge labels and their properties
    EDGE_SCHEMAS = {
        'SENT_TO': {
            'description': 'Direct transaction relationship between accounts',
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
            }
        },
        'INITIATED': {
            'description': 'Account initiated a transaction',
            'required_properties': ['timestamp'],
            'constraints': {}
        },
        'RECEIVED': {
            'description': 'Account received a transaction',
            'required_properties': ['timestamp'],
            'constraints': {}
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
    def get_gremlin_schema_creation_queries(cls) -> List[str]:
        """Generate Gremlin queries to create schema indexes and constraints."""
        queries = []
        
        # Note: Neptune doesn't support all schema creation features
        # These are conceptual queries that would work in other Gremlin databases
        
        for label, schema in cls.VERTEX_SCHEMAS.items():
            # Create indexes for better query performance
            indexes = schema.get('indexes', [])
            for index_prop in indexes:
                # Neptune uses different syntax for index creation
                queries.append(f"// Index on {label}.{index_prop} (Neptune-specific implementation needed)")
        
        return queries
    
    @classmethod
    def get_schema_documentation(cls) -> Dict[str, Any]:
        """Get complete schema documentation."""
        return {
            'vertices': cls.VERTEX_SCHEMAS,
            'edges': cls.EDGE_SCHEMAS,
            'description': 'AML graph schema for transaction relationship analysis',
            'version': '1.0.0'
        }
    
    @classmethod
    def log_schema_info(cls) -> None:
        """Log schema information for debugging."""
        logger.info("Graph schema loaded", 
                   vertex_types=list(cls.VERTEX_SCHEMAS.keys()),
                   edge_types=list(cls.EDGE_SCHEMAS.keys()))


# Initialize schema logging
GraphSchema.log_schema_info()