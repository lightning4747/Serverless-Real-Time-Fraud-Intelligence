"""Unit tests for configuration management."""

import pytest
from pydantic import ValidationError

from sentinel_aml.core.config import Settings, get_settings


class TestSettings:
    """Test Settings configuration class."""
    
    def test_default_settings(self):
        """Test default settings values."""
        settings = Settings()
        
        assert settings.app_name == "Sentinel-AML"
        assert settings.environment == "test"  # Set by conftest.py
        assert settings.log_level == "DEBUG"  # Set by conftest.py
        assert settings.aws_region == "us-east-1"
        assert settings.neptune_port == 8182
        assert settings.gnn_model_threshold == 0.7
    
    def test_environment_validation(self):
        """Test environment validation."""
        # Valid environment
        settings = Settings(environment="production")
        assert settings.environment == "production"
        
        # Invalid environment
        with pytest.raises(ValidationError):
            Settings(environment="invalid")
    
    def test_log_level_validation(self):
        """Test log level validation."""
        # Valid log level
        settings = Settings(log_level="DEBUG")
        assert settings.log_level == "DEBUG"
        
        # Invalid log level
        with pytest.raises(ValidationError):
            Settings(log_level="INVALID")
    
    def test_gnn_threshold_validation(self):
        """Test GNN threshold validation."""
        # Valid threshold
        settings = Settings(gnn_model_threshold=0.5)
        assert settings.gnn_model_threshold == 0.5
        
        # Invalid threshold (too low)
        with pytest.raises(ValidationError):
            Settings(gnn_model_threshold=-0.1)
        
        # Invalid threshold (too high)
        with pytest.raises(ValidationError):
            Settings(gnn_model_threshold=1.1)
    
    def test_get_settings_cached(self):
        """Test that get_settings returns cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        
        assert settings1 is settings2