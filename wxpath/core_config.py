"""
Core configuration management for wxpath.

This module handles basic configuration for the core wxpath functionality,
including HTTP settings, logging, and crawling parameters.
"""

import os
import logging
import logging.handlers
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional


@dataclass
class HttpConfig:
    """Configuration for HTTP requests."""
    timeout: int = 10
    max_retries: int = 3
    user_agent: str = "wxpath/1.0"
    follow_redirects: bool = True
    max_redirects: int = 5
    
    @classmethod
    def from_env(cls) -> 'HttpConfig':
        """Create configuration from environment variables."""
        return cls(
            timeout=int(os.getenv('WXPATH_HTTP_TIMEOUT', cls.timeout)),
            max_retries=int(os.getenv('WXPATH_HTTP_MAX_RETRIES', cls.max_retries)),
            user_agent=os.getenv('WXPATH_HTTP_USER_AGENT', cls.user_agent),
            follow_redirects=os.getenv('WXPATH_HTTP_FOLLOW_REDIRECTS', 'true').lower() == 'true',
            max_redirects=int(os.getenv('WXPATH_HTTP_MAX_REDIRECTS', cls.max_redirects))
        )


@dataclass
class CrawlConfig:
    """Configuration for crawling behavior."""
    max_depth: int = 2
    delay_between_requests: float = 0.1
    max_concurrent_requests: int = 10
    respect_robots_txt: bool = True
    
    @classmethod
    def from_env(cls) -> 'CrawlConfig':
        """Create configuration from environment variables."""
        return cls(
            max_depth=int(os.getenv('WXPATH_CRAWL_MAX_DEPTH', cls.max_depth)),
            delay_between_requests=float(os.getenv('WXPATH_CRAWL_DELAY', cls.delay_between_requests)),
            max_concurrent_requests=int(os.getenv('WXPATH_CRAWL_MAX_CONCURRENT', cls.max_concurrent_requests)),
            respect_robots_txt=os.getenv('WXPATH_CRAWL_RESPECT_ROBOTS', 'true').lower() == 'true'
        )


@dataclass
class LoggingConfig:
    """Configuration for logging."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = None
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    
    @classmethod
    def from_env(cls) -> 'LoggingConfig':
        """Create configuration from environment variables."""
        return cls(
            level=os.getenv('WXPATH_LOG_LEVEL', cls.level),
            format=os.getenv('WXPATH_LOG_FORMAT', cls.format),
            file_path=os.getenv('WXPATH_LOG_FILE'),
            max_file_size=int(os.getenv('WXPATH_LOG_MAX_FILE_SIZE', cls.max_file_size)),
            backup_count=int(os.getenv('WXPATH_LOG_BACKUP_COUNT', cls.backup_count))
        )


@dataclass
class CoreConfig:
    """Main configuration container for core wxpath functionality."""
    http: HttpConfig = field(default_factory=HttpConfig)
    crawl: CrawlConfig = field(default_factory=CrawlConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    @classmethod
    def from_env(cls) -> 'CoreConfig':
        """Create configuration from environment variables."""
        return cls(
            http=HttpConfig.from_env(),
            crawl=CrawlConfig.from_env(),
            logging=LoggingConfig.from_env()
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'http': {
                'timeout': self.http.timeout,
                'max_retries': self.http.max_retries,
                'user_agent': self.http.user_agent,
                'follow_redirects': self.http.follow_redirects,
                'max_redirects': self.http.max_redirects
            },
            'crawl': {
                'max_depth': self.crawl.max_depth,
                'delay_between_requests': self.crawl.delay_between_requests,
                'max_concurrent_requests': self.crawl.max_concurrent_requests,
                'respect_robots_txt': self.crawl.respect_robots_txt
            },
            'logging': {
                'level': self.logging.level,
                'format': self.logging.format,
                'file_path': self.logging.file_path,
                'max_file_size': self.logging.max_file_size,
                'backup_count': self.logging.backup_count
            }
        }


def setup_logging(config: LoggingConfig):
    """Setup logging based on configuration."""
    # Create logger
    logger = logging.getLogger('wxpath')
    logger.setLevel(getattr(logging, config.level.upper()))
    
    # Create formatter
    formatter = logging.Formatter(config.format)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if config.file_path:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=config.file_path,
            maxBytes=config.max_file_size,
            backupCount=config.backup_count
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


# Global configuration instance
_global_core_config: Optional[CoreConfig] = None


def get_core_config() -> CoreConfig:
    """Get the global core configuration instance."""
    global _global_core_config
    if _global_core_config is None:
        _global_core_config = CoreConfig.from_env()
        setup_logging(_global_core_config.logging)
    return _global_core_config


def validate_core_config(config: CoreConfig) -> List[str]:
    """Validate core configuration and return list of errors."""
    errors = []
    
    # Validate HTTP config
    if config.http.timeout <= 0:
        errors.append("HTTP timeout must be positive")
    if config.http.max_retries < 0:
        errors.append("HTTP max_retries cannot be negative")
    
    # Validate crawl config
    if config.crawl.max_depth < 0:
        errors.append("Crawl max_depth cannot be negative")
    if config.crawl.delay_between_requests < 0:
        errors.append("Crawl delay_between_requests cannot be negative")
    if config.crawl.max_concurrent_requests <= 0:
        errors.append("Crawl max_concurrent_requests must be positive")
    
    # Validate logging config
    valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    if config.logging.level.upper() not in valid_log_levels:
        errors.append(f"Invalid log level: {config.logging.level}")
    
    return errors