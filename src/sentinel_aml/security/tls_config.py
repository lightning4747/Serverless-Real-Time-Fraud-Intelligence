"""TLS 1.3 configuration for secure data in transit."""

import ssl
from functools import lru_cache
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from sentinel_aml.core.config import get_settings
from sentinel_aml.core.logging import get_logger

logger = get_logger(__name__)


class TLSConfig:
    """TLS 1.3 configuration for secure communications."""
    
    def __init__(self):
        """Initialize TLS configuration."""
        self.settings = get_settings()
        
    def create_ssl_context(self, 
                          min_version: int = ssl.TLSVersion.TLSv1_3,
                          max_version: int = ssl.TLSVersion.TLSv1_3) -> ssl.SSLContext:
        """Create secure SSL context with TLS 1.3."""
        context = ssl.create_default_context()
        
        # Enforce TLS 1.3
        context.minimum_version = min_version
        context.maximum_version = max_version
        
        # Security settings
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        
        # Disable weak ciphers and protocols
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        
        logger.info(f"Created SSL context with TLS {min_version.name} to {max_version.name}")
        return context
    
    def create_secure_session(self) -> requests.Session:
        """Create requests session with TLS 1.3 configuration."""
        session = requests.Session()
        
        # Create custom adapter with TLS 1.3
        adapter = SecureTLSAdapter()
        session.mount('https://', adapter)
        
        # Set security headers
        session.headers.update({
            'User-Agent': f'Sentinel-AML/{self.settings.app_version}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
        return session


class SecureTLSAdapter(HTTPAdapter):
    """Custom HTTP adapter enforcing TLS 1.3."""
    
    def init_poolmanager(self, *args, **kwargs):
        """Initialize pool manager with secure TLS context."""
        context = create_urllib3_context()
        
        # Enforce TLS 1.3
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)


@lru_cache()
def get_tls_config() -> TLSConfig:
    """Get cached TLS configuration instance."""
    return TLSConfig()


def create_secure_session() -> requests.Session:
    """Convenience function to create secure session."""
    config = get_tls_config()
    return config.create_secure_session()