#!/usr/bin/env python3
"""Export Neptune graph schema for Sentinel-AML system."""

import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sentinel_aml.data.schema import GraphSchema
from sentinel_aml.core.logging import get_logger

logger = get_logger(__name__)


def main():
    """Export schema to files."""
    try:
        # Create output directory
        output_dir = Path(__file__).parent.parent / "docs"
        output_dir.mkdir(exist_ok=True)
        
        # Export complete schema documentation
        schema_file = output_dir / "neptune_schema.json"
        GraphSchema.export_schema_to_file(str(schema_file))
        
        # Export Gremlin queries
        gremlin_file = output_dir / "gremlin_schema_queries.txt"
        queries = GraphSchema.get_gremlin_schema_creation_queries()
        
        with open(gremlin_file, 'w') as f:
            f.write('\n'.join(queries))
        
        # Export validation queries
        validation_file = output_dir / "gremlin_validation_queries.txt"
        validation_queries = GraphSchema.get_schema_validation_queries()
        
        with open(validation_file, 'w') as f:
            f.write('\n'.join(validation_queries))
        
        logger.info("Schema export completed successfully",
                   schema_file=str(schema_file),
                   gremlin_file=str(gremlin_file),
                   validation_file=str(validation_file))
        
        print(f"✅ Schema exported to:")
        print(f"   📄 {schema_file}")
        print(f"   📄 {gremlin_file}")
        print(f"   📄 {validation_file}")
        
    except Exception as e:
        logger.error("Schema export failed", error=str(e))
        print(f"❌ Schema export failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()