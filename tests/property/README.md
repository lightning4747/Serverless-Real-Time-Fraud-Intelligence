# Property-Based Tests for Graph Schema

This directory contains property-based tests that validate universal correctness properties of the Neptune graph schema used in the Sentinel-AML system.

## Property 1: Schema Consistency

**Statement**: All transactions must connect valid accounts

**Requirements Validated**: 2.1, 2.5

**Description**: This property ensures that the graph maintains referential integrity at all times. Every transaction edge (SENT_TO relationship) must reference accounts that exist in the graph, and all entities must conform to the defined schema constraints.

## Test Coverage

### Core Schema Validation Tests

1. **Account Schema Validation** (`test_property_account_schema_validation`)
   - Validates all account properties conform to schema constraints
   - Ensures risk scores are within valid range (0.0-1.0)
   - Verifies account types are valid enum values
   - Checks required properties are present

2. **Transaction Schema Validation** (`test_property_transaction_schema_validation`)
   - Validates all transaction properties conform to schema constraints
   - Ensures transaction amounts are positive
   - Verifies transaction types are valid enum values
   - Checks required properties are present

3. **Transaction Edge Referential Integrity** (`test_property_transaction_edge_referential_integrity`)
   - Ensures all SENT_TO edges reference valid accounts
   - Validates edge properties match transaction properties
   - Checks edge amounts and timestamps are consistent

### Uniqueness Constraint Tests

4. **Account Uniqueness** (`test_property_account_uniqueness`)
   - Ensures all accounts have unique account IDs
   - Validates each account individually against schema

5. **Transaction Uniqueness** (`test_property_transaction_uniqueness`)
   - Ensures all transactions have unique transaction IDs
   - Validates each transaction individually against schema

### Stateful Consistency Tests

6. **Graph Consistency Over Time** (`GraphConsistencyStateMachine`)
   - Uses stateful property testing to validate consistency as entities are added
   - Maintains invariants about referential integrity
   - Ensures accounts and transactions maintain valid properties over time

### Neptune Client Integration Tests

7. **Neptune Client Schema Enforcement** (`TestNeptuneClientSchemaEnforcement`)
   - Validates that Neptune client enforces schema constraints
   - Tests referential integrity enforcement at the client level
   - Ensures proper validation before database operations

### Constraint Violation Tests

8. **Schema Constraint Violations** (`TestSchemaConstraintViolations`)
   - Tests that invalid data is properly rejected
   - Validates error handling for constraint violations
   - Ensures proper error messages for debugging

## Running the Tests

### Using pytest directly:
```bash
pytest tests/property/test_graph_schema_properties.py -v -m property
```

### Using the test runner:
```bash
python tests/property/run_property_tests.py
```

### Running with hypothesis statistics:
```bash
pytest tests/property/test_graph_schema_properties.py -v -m property --hypothesis-show-statistics
```

## Test Framework

These tests use the [Hypothesis](https://hypothesis.readthedocs.io/) property-based testing framework, which:

- Generates thousands of random test cases automatically
- Finds edge cases that manual testing might miss
- Provides minimal failing examples when properties are violated
- Uses stateful testing to validate system behavior over time

## Property Test Benefits

Property-based tests provide stronger guarantees than example-based unit tests because they:

1. **Test Universal Properties**: Validate that properties hold for ALL possible inputs, not just specific examples
2. **Find Edge Cases**: Automatically discover inputs that violate properties
3. **Provide Better Coverage**: Generate diverse test cases that humans might not think of
4. **Validate Invariants**: Ensure system properties are maintained over time and state changes
5. **Complement Unit Tests**: Work alongside traditional tests to provide comprehensive validation

## Integration with Requirements

These property tests directly validate the following requirements from the specification:

- **Requirement 2.1**: Graph schema management with proper Account and Transaction nodes
- **Requirement 2.5**: Referential integrity between accounts and transactions
- **Schema Consistency**: Universal property that all graph operations maintain valid relationships

## Continuous Integration

These tests should be run as part of the CI/CD pipeline to ensure:

- Schema changes don't break existing constraints
- New code maintains referential integrity
- Database operations properly validate data
- System maintains consistency under all conditions