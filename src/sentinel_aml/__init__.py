"""
Sentinel-AML: AI-Powered Anti-Money Laundering Detection Platform

An intelligent system for detecting and preventing money laundering activities
using AI agents, graph neural networks, and generative AI.
"""

__version__ = "0.1.0"
__author__ = "Sentinel AML Team"
__email__ = "team@sentinel-aml.com"

# Core imports for easy access
from sentinel_aml.core.config import Settings, get_settings
from sentinel_aml.core.logging import get_logger

__all__ = [
    "__version__",
    "__author__", 
    "__email__",
    "Settings",
    "get_settings",
    "get_logger",
]