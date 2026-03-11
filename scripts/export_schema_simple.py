#!/usr/bin/env python3
"""
Simple Neptune graph schema export for Sentinel-AML.
This version doesn't import the full module to avoid dependency issues.
"""

import json
from pathlib import Path
from datetime import datetime


def create_schema_documentation():
    """Create schema documentation without importing modules."""
    
    # Vertex schemas
    vertex_schemas = {
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
    
    # Edge schemas
    edge_schemas = {
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
    
    return {
        'vertices': vertex_schemas,
        'edges': edge_schemas,
        'description': 'AML graph schema for transaction relationship analysis',
        'version': '1.0.0',
        'compliance': {
            'requirements': ['2.1', '2.2', '2.3', '2.5'],
            'description': 'Implements Account and Transaction nodes with SENT_TO relationships'
        }
    }


def create_gremlin_queries():
    """Create Gremlin schema creation queries."""
    
    queries = [
        "// Neptune Graph Schema Creation for Sentinel-AML",
        "// Note: Neptune uses different syntax for schema management",
        "",
        "// Account vertex schema",
        "// Required properties: account_id, customer_name_hash, account_type, risk_score, creation_date, currency, is_active",
        "// Optional properties: customer_id, country_code, is_pep, kyc_status, balance, last_activity_date",
        "// account_id: string",
        "// customer_name_hash: string",
        "// account_type: string",
        "// risk_score: double",
        "// creation_date: string",
        "// currency: string",
        "// is_active: boolean",
        "// customer_id: string",
        "// country_code: string",
        "// is_pep: boolean",
        "// kyc_status: string",
        "// balance: double",
        "// last_activity_date: string",
        "",
        "// Transaction vertex schema",
        "// Required properties: transaction_id, amount, timestamp, transaction_type, currency, is_cash, is_international",
        "// Optional properties: description, reference_number, channel, country_code, city, risk_flags",
        "// transaction_id: string",
        "// amount: double",
        "// timestamp: string",
        "// transaction_type: string",
        "// currency: string",
        "// is_cash: boolean",
        "// is_international: boolean",
        "// description: string",
        "// reference_number: string",
        "// channel: string",
        "// country_code: string",
        "// city: string",
        "// risk_flags: string",
        "",
        "// SENT_TO edge schema",
        "// Description: Direct transaction relationship between accounts",
        "// From: Account -> To: Account",
        "// Required properties: transaction_id, amount, timestamp, transaction_type, edge_id, created_at",
        "",
        "// INITIATED edge schema",
        "// Description: Account initiated a transaction",
        "// From: Account -> To: Transaction",
        "// Required properties: timestamp",
        "",
        "// RECEIVED edge schema",
        "// Description: Account received a transaction",
        "// From: Account -> To: Transaction",
        "// Required properties: timestamp",
        "",
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
    ]
    
    return queries


def create_validation_queries():
    """Create schema validation queries."""
    
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


def main():
    """Export schema definitions to files."""
    
    # Create output directory
    output_dir = Path("docs/schema")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create schema documentation
    schema_doc = create_schema_documentation()
    gremlin_queries = create_gremlin_queries()
    validation_queries = create_validation_queries()
    
    # Export complete schema documentation
    schema_file = output_dir / "neptune_schema.json"
    export_data = {
        'schema': schema_doc,
        'gremlin_creation_queries': gremlin_queries,
        'validation_queries': validation_queries,
        'export_timestamp': datetime.now().isoformat()
    }
    
    with open(schema_file, 'w') as f:
        json.dump(export_data, f, indent=2)
    print(f"✓ Schema documentation exported to {schema_file}")
    
    # Export Gremlin creation queries
    gremlin_file = output_dir / "schema_creation.gremlin"
    with open(gremlin_file, 'w') as f:
        f.write('\n'.join(gremlin_queries))
    print(f"✓ Gremlin creation queries exported to {gremlin_file}")
    
    # Export validation queries
    validation_file = output_dir / "schema_validation.gremlin"
    with open(validation_file, 'w') as f:
        f.write('\n'.join(validation_queries))
    print(f"✓ Schema validation queries exported to {validation_file}")
    
    # Print schema summary
    print("\n" + "="*60)
    print("NEPTUNE GRAPH SCHEMA SUMMARY")
    print("="*60)
    
    print(f"\nDescription: {schema_doc['description']}")
    print(f"Version: {schema_doc['version']}")
    print(f"Requirements: {', '.join(schema_doc['compliance']['requirements'])}")
    
    print(f"\nVertex Types ({len(schema_doc['vertices'])}):")
    for vertex_type, schema in schema_doc['vertices'].items():
        required_props = len(schema.get('required_properties', []))
        optional_props = len(schema.get('optional_properties', []))
        print(f"  • {vertex_type}: {required_props} required, {optional_props} optional properties")
    
    print(f"\nEdge Types ({len(schema_doc['edges'])}):")
    for edge_type, schema in schema_doc['edges'].items():
        from_vertex = schema.get('from_vertex', 'Any')
        to_vertex = schema.get('to_vertex', 'Any')
        print(f"  • {edge_type}: {from_vertex} → {to_vertex}")
        print(f"    {schema.get('description', 'No description')}")
    
    print(f"\nFiles generated in {output_dir}:")
    print(f"  • neptune_schema.json - Complete schema documentation")
    print(f"  • schema_creation.gremlin - Gremlin creation queries")
    print(f"  • schema_validation.gremlin - Validation queries")
    
    print("\n" + "="*60)
    print("Schema export completed successfully!")
    print("="*60)


if __name__ == "__main__":
    main()