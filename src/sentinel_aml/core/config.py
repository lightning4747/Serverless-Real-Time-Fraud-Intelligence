"""Configuration management for Sentinel-AML system."""

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application settings
    app_name: str = "Sentinel-AML"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", description="Environment (development, staging, production)")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # AWS Configuration
    aws_region: str = Field(default="us-east-1", description="AWS region")
    aws_account_id: Optional[str] = Field(default=None, description="AWS account ID")
    
    # Neptune Configuration
    neptune_endpoint: Optional[str] = Field(default=None, description="Neptune cluster endpoint")
    neptune_port: int = Field(default=8182, description="Neptune port")
    neptune_use_ssl: bool = Field(default=True, description="Use SSL for Neptune connections")
    neptune_max_connections: int = Field(default=10, description="Maximum Neptune connections")
    
    # Bedrock Configuration
    bedrock_region: str = Field(default="us-east-1", description="Bedrock region")
    bedrock_model_id: str = Field(
        default="anthropic.claude-3-sonnet-20240229-v1:0",
        description="Bedrock model ID for SAR generation"
    )
    bedrock_max_tokens: int = Field(default=4000, description="Maximum tokens for Bedrock responses")
    
    # API Configuration
    api_title: str = "Sentinel-AML API"
    api_description: str = "AI-powered Anti-Money Laundering detection platform"
    api_version: str = "1.0.0"
    api_rate_limit: int = Field(default=100, description="API rate limit per minute")
    
    # Security Configuration
    encryption_key_id: Optional[str] = Field(default=None, description="KMS key ID for encryption")
    jwt_secret_key: Optional[str] = Field(default=None, description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expiration_hours: int = Field(default=24, description="JWT expiration in hours")
    
    # ML Configuration
    gnn_model_threshold: float = Field(default=0.7, description="GNN risk score threshold for flagging")
    max_graph_nodes: int = Field(default=50000, description="Maximum nodes for GNN analysis")
    model_inference_timeout: int = Field(default=30, description="Model inference timeout in seconds")
    
    # Processing Configuration
    max_concurrent_transactions: int = Field(default=1000, description="Maximum concurrent transaction processing")
    transaction_batch_size: int = Field(default=100, description="Transaction processing batch size")
    retry_max_attempts: int = Field(default=3, description="Maximum retry attempts")
    retry_backoff_factor: float = Field(default=2.0, description="Retry backoff factor")
    
    # Compliance Configuration
    audit_log_retention_days: int = Field(default=2555, description="Audit log retention (7 years)")
    sar_generation_timeout: int = Field(default=60, description="SAR generation timeout in seconds")
    pii_masking_enabled: bool = Field(default=True, description="Enable PII masking")
    
    @validator("environment")
    def validate_environment(cls, v):
        """Validate environment setting."""
        allowed_environments = ["development", "staging", "production"]
        if v not in allowed_environments:
            raise ValueError(f"Environment must be one of {allowed_environments}")
        return v
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level setting."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of {allowed_levels}")
        return v.upper()
    
    @validator("gnn_model_threshold")
    def validate_gnn_threshold(cls, v):
        """Validate GNN model threshold is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("GNN model threshold must be between 0.0 and 1.0")
        return v
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
        # Environment variable prefixes
        env_prefix = ""
        
        # Field aliases for environment variables
        fields = {
            "neptune_endpoint": {"env": "NEPTUNE_ENDPOINT"},
            "bedrock_model_id": {"env": "BEDROCK_MODEL_ID"},
            "aws_account_id": {"env": "AWS_ACCOUNT_ID"},
            "encryption_key_id": {"env": "KMS_KEY_ID"},
            "jwt_secret_key": {"env": "JWT_SECRET_KEY"},
        }


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


def get_neptune_connection_string() -> str:
    """Get Neptune connection string."""
    settings = get_settings()
    if not settings.neptune_endpoint:
        raise ValueError("Neptune endpoint not configured")
    
    protocol = "wss" if settings.neptune_use_ssl else "ws"
    return f"{protocol}://{settings.neptune_endpoint}:{settings.neptune_port}/gremlin"


def is_production() -> bool:
    """Check if running in production environment."""
    return get_settings().environment == "production"


def is_development() -> bool:
    """Check if running in development environment."""
    return get_settings().environment == "development"