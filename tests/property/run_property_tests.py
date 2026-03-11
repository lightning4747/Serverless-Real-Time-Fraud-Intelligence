#!/usr/bin/env python3
"""
Property Test Runner for Graph Schema Validation

This script runs the property-based tests for graph schema consistency.
It validates Property 1: Schema consistency - All transactions must connect valid accounts.

Usage:
    python tests/property/run_property_tests.py
    
Or with pytest:
    pytest tests/property/test_graph_schema_properties.py -v -m property
"""

import sys
import subprocess
from pathlib import Path

def run_property_tests():
    """Run property-based tests for graph schema."""
    
    # Get the project root directory
    project_root = Path(__file__).parent.parent.parent
    
    print("🧪 Running Property-Based Tests for Graph Schema Consistency")
    print("=" * 60)
    print()
    print("Property 1: Schema consistency - All transactions must connect valid accounts")
    print("Validates Requirements: 2.1, 2.5")
    print()
    
    # Run the property tests
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/property/test_graph_schema_properties.py",
        "-v",
        "-m", "property",
        "--tb=short",
        "--hypothesis-show-statistics"
    ]
    
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✅ All property tests passed!")
            print()
            print("Schema consistency properties validated:")
            print("  ✓ Account schema validation")
            print("  ✓ Transaction schema validation") 
            print("  ✓ Transaction edge referential integrity")
            print("  ✓ Account uniqueness constraints")
            print("  ✓ Transaction uniqueness constraints")
            print("  ✓ Stateful graph consistency over time")
            print("  ✓ Neptune client schema enforcement")
            print("  ✓ Schema constraint violation detection")
        else:
            print("❌ Some property tests failed!")
            print(f"Exit code: {result.returncode}")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Error running property tests: {e}")
        return False

def main():
    """Main entry point."""
    success = run_property_tests()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()