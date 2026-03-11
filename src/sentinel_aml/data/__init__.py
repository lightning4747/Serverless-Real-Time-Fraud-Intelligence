"""Data models and Neptune integration for Sentinel-AML."""

from sentinel_aml.data.models import (
    Account,
    Transaction,
    TransactionEdge,
    RiskScore,
    Alert,
    SuspiciousActivityReport,
)
from sentinel_aml.data.schema import GraphSchema

# Optional Neptune client import (requires gremlinpython)
try:
    from sentinel_aml.data.neptune_client import NeptuneClient
    _NEPTUNE_AVAILABLE = True
except ImportError:
    NeptuneClient = None
    _NEPTUNE_AVAILABLE = False

__all__ = [
    "Account",
    "Transaction", 
    "TransactionEdge",
    "RiskScore",
    "Alert",
    "SuspiciousActivityReport",
    "GraphSchema",
]

if _NEPTUNE_AVAILABLE:
    __all__.append("NeptuneClient")