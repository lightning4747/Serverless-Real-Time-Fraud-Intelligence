# Unit Tests for Sentinel-AML Data Models

This directory contains comprehensive unit tests for the Sentinel-AML data models and utility functions.

## Test Coverage

### Core Data Models (`test_models.py`)
- **Account Model**: Validation, serialization, edge cases
- **Transaction Model**: Amount validation, currency handling, precision
- **TransactionEdge Model**: Relationship consistency
- **RiskScore Model**: Score bounds, confidence validation
- **Alert Model**: Risk level consistency, status transitions
- **SuspiciousActivityReport Model**: Amount validation, AI confidence bounds
- **Enum Classes**: All enum values and validation

### Edge Cases (`test_model_edge_cases.py`)
- **Validation Edge Cases**: Boundary conditions, invalid inputs
- **Serialization Edge Cases**: Complex nested data, precision handling
- **Business Logic Edge Cases**: Date ranges, consistency checks
- **Performance Edge Cases**: Large data sets, bulk operations

### Utility Functions (`test_utils.py`)
- **Account ID Validation**: Format checking, length validation
- **Transaction Amount Validation**: Precision, bounds, type conversion
- **Currency Code Validation**: ISO codes, case normalization
- **Risk Assessment Functions**: Velocity scoring, pattern detection
- **Data Security Functions**: PII hashing, data masking
- **ID Generation Functions**: Unique ID creation

## Requirements Validation

### Requirement 1.1: Transaction Schema Validation (100ms)
- ✅ Transaction amount validation with proper error handling
- ✅ Currency code validation and normalization
- ✅ Field type validation and conversion
- ✅ Performance-optimized validation functions

### Requirement 1.3: Descriptive Error Messages
- ✅ Clear validation error messages for invalid data
- ✅ Specific error types for different validation failures
- ✅ User-friendly error descriptions

### Requirement 2.1: Account Node Properties
- ✅ Account ID format validation (8-20 alphanumeric characters)
- ✅ Customer name validation and handling
- ✅ Account type enumeration validation
- ✅ Risk score bounds validation (0.0-1.0)
- ✅ Creation date automatic generation

## Test Categories

### Validation Tests
- Field format validation (account IDs, currency codes)
- Numeric bounds validation (risk scores, amounts)
- Required field validation
- Type conversion and normalization

### Serialization Tests
- JSON serialization/deserialization
- Decimal precision handling
- Datetime format consistency
- Complex nested data structures

### Edge Case Tests
- Boundary value testing
- Unicode character handling
- Large data set performance
- Error condition handling

### Business Logic Tests
- AML domain-specific validation
- Financial data constraints
- Regulatory compliance checks
- Data consistency rules

## Running Tests

```bash
# Run all model tests
python -m pytest tests/unit/test_models.py -v

# Run edge case tests
python -m pytest tests/unit/test_model_edge_cases.py -v

# Run utility function tests
python -m pytest tests/unit/test_utils.py -v

# Run all unit tests
python -m pytest tests/unit/ -v

# Run with coverage
python -m pytest tests/unit/ --cov=src/sentinel_aml --cov-report=html
```

## Test Data

Test fixtures are defined in `tests/conftest.py`:
- `sample_account`: Valid account for testing
- `sample_transaction`: Valid transaction for testing
- `sample_transaction_edge`: Valid transaction edge for testing
- `sample_risk_score`: Valid risk score for testing
- `sample_alert`: Valid alert for testing
- `sample_sar`: Valid SAR for testing

## Key Test Scenarios

### Financial Data Validation
- Amount precision (2 decimal places)
- Currency code normalization (ISO 4217)
- Negative amount rejection
- Maximum amount limits

### AML-Specific Validation
- Account ID format compliance
- Risk score bounds (0.0-1.0)
- High-risk jurisdiction detection
- Suspicious pattern identification

### Data Security
- PII hashing consistency
- Data masking for logging
- Sensitive field sanitization
- Audit trail generation

### Performance Considerations
- Large dataset handling
- Bulk model creation
- Complex nested serialization
- Memory-efficient validation

## Compliance Notes

These tests ensure compliance with:
- **BSA Requirements**: Proper transaction validation and reporting
- **AML Regulations**: Risk scoring and pattern detection
- **Data Privacy**: PII protection and masking
- **Audit Requirements**: Complete validation logging

All tests follow the project's AML domain knowledge and AWS integration guidelines.