"""
Configuration management for wxpath Neo4j extension.

This module handles configuration loading from environment variables,
configuration files, and provides default settings for the graph database
integration.
"""

import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional


@dataclass
class Neo4jConfig:
    """Configuration for Neo4j database connection."""
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "wxpath123"
    database: Optional[str] = None
    max_connection_lifetime: int = 1800  # 30 minutes
    max_connection_pool_size: int = 50
    connection_acquisition_timeout: int = 60
    
    @classmethod
    def from_env(cls) -> 'Neo4jConfig':
        """Create configuration from environment variables."""
        return cls(
            uri=os.getenv('NEO4J_URI', cls.uri),
            username=os.getenv('NEO4J_USERNAME', cls.username),
            password=os.getenv('NEO4J_PASSWORD', cls.password),
            database=os.getenv('NEO4J_DATABASE'),
            max_connection_lifetime=int(os.getenv('NEO4J_MAX_CONNECTION_LIFETIME', cls.max_connection_lifetime)),
            max_connection_pool_size=int(os.getenv('NEO4J_MAX_CONNECTION_POOL_SIZE', cls.max_connection_pool_size)),
            connection_acquisition_timeout=int(os.getenv('NEO4J_CONNECTION_ACQUISITION_TIMEOUT', cls.connection_acquisition_timeout))
        )


@dataclass
class PipelineConfig:
    """Configuration for the graph pipeline."""
    enabled: bool = True
    batch_size: int = 100
    auto_start_session: bool = True
    store_content_hash: bool = True
    extract_page_text: bool = True
    extract_metadata: bool = True
    max_text_length: int = 10000
    ignore_duplicate_pages: bool = True
    
    @classmethod
    def from_env(cls) -> 'PipelineConfig':
        """Create configuration from environment variables."""
        return cls(
            enabled=os.getenv('WXPATH_PIPELINE_ENABLED', 'true').lower() == 'true',
            batch_size=int(os.getenv('WXPATH_PIPELINE_BATCH_SIZE', cls.batch_size)),
            auto_start_session=os.getenv('WXPATH_PIPELINE_AUTO_START_SESSION', 'true').lower() == 'true',
            store_content_hash=os.getenv('WXPATH_PIPELINE_STORE_CONTENT_HASH', 'true').lower() == 'true',
            extract_page_text=os.getenv('WXPATH_PIPELINE_EXTRACT_PAGE_TEXT', 'true').lower() == 'true',
            extract_metadata=os.getenv('WXPATH_PIPELINE_EXTRACT_METADATA', 'true').lower() == 'true',
            max_text_length=int(os.getenv('WXPATH_PIPELINE_MAX_TEXT_LENGTH', cls.max_text_length)),
            ignore_duplicate_pages=os.getenv('WXPATH_PIPELINE_IGNORE_DUPLICATE_PAGES', 'true').lower() == 'true'
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
class WxPathConfig:
    """Main configuration container for wxpath Neo4j extension."""
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    @classmethod
    def from_env(cls) -> 'WxPathConfig':
        """Create configuration from environment variables."""
        return cls(
            neo4j=Neo4jConfig.from_env(),
            pipeline=PipelineConfig.from_env(),
            logging=LoggingConfig.from_env()
        )
    
    @classmethod
    def from_file(cls, config_path: str) -> 'WxPathConfig':
        """Create configuration from a file."""
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        if config_file.suffix.lower() == '.json':
            import json
            with open(config_file, 'r') as f:
                data = json.load(f)
        elif config_file.suffix.lower() in ['.yml', '.yaml']:
            try:
                import yaml
                with open(config_file, 'r') as f:
                    data = yaml.safe_load(f)
            except ImportError:
                raise ImportError("PyYAML is required to load YAML configuration files")
        else:
            raise ValueError(f"Unsupported configuration file format: {config_file.suffix}")
        
        return cls(**data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'neo4j': {
                'uri': self.neo4j.uri,
                'username': self.neo4j.username,
                'password': '***',  # Hide password
                'database': self.neo4j.database,
                'max_connection_lifetime': self.neo4j.max_connection_lifetime,
                'max_connection_pool_size': self.neo4j.max_connection_pool_size,
                'connection_acquisition_timeout': self.neo4j.connection_acquisition_timeout
            },
            'pipeline': {
                'enabled': self.pipeline.enabled,
                'batch_size': self.pipeline.batch_size,
                'auto_start_session': self.pipeline.auto_start_session,
                'store_content_hash': self.pipeline.store_content_hash,
                'extract_page_text': self.pipeline.extract_page_text,
                'extract_metadata': self.pipeline.extract_metadata,
                'max_text_length': self.pipeline.max_text_length,
                'ignore_duplicate_pages': self.pipeline.ignore_duplicate_pages
            },
            'logging': {
                'level': self.logging.level,
                'format': self.logging.format,
                'file_path': self.logging.file_path,
                'max_file_size': self.logging.max_file_size,
                'backup_count': self.logging.backup_count
            }
        }


def get_config() -> WxPathConfig:
    """Get configuration, first from environment, then from default config file."""
    # Try to load from environment first
    config = WxPathConfig.from_env()
    
    # Check for config file in common locations
    config_paths = [
        'wxpath_config.json',
        'wxpath_config.yml',
        'wxpath_config.yaml',
        os.path.expanduser('~/.wxpath/config.json'),
        os.path.expanduser('~/.wxpath/config.yml'),
        '/etc/wxpath/config.json',
        '/etc/wxpath/config.yml'
    ]
    
    for config_path in config_paths:
        if os.path.exists(config_path):
            try:
                file_config = WxPathConfig.from_file(config_path)
                # Merge file config with env config (env takes precedence)
                return merge_configs(file_config, config)
            except Exception as e:
                print(f"Warning: Could not load config from {config_path}: {e}")
                continue
    
    return config


def merge_configs(base_config: WxPathConfig, override_config: WxPathConfig) -> WxPathConfig:
    """Merge two configurations, with override_config taking precedence."""
    # This is a simple merge - in a real implementation, you might want
    # more sophisticated merging logic
    return override_config


def setup_logging(config: LoggingConfig):
    """Setup logging based on configuration."""
    import logging
    import logging.handlers
    
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
_global_config: Optional[WxPathConfig] = None


def initialize_config(config: Optional[WxPathConfig] = None) -> WxPathConfig:
    """Initialize global configuration."""
    global _global_config
    _global_config = config or get_config()
    
    # Setup logging
    setup_logging(_global_config.logging)
    
    return _global_config


def get_global_config() -> WxPathConfig:
    """Get the global configuration instance."""
    global _global_config
    if _global_config is None:
        _global_config = initialize_config()
    return _global_config


# Configuration validation
def validate_config(config: WxPathConfig) -> List[str]:
    """Validate configuration and return list of errors."""
    errors = []
    
    # Validate Neo4j config
    if not config.neo4j.uri:
        errors.append("Neo4j URI is required")
    if not config.neo4j.username:
        errors.append("Neo4j username is required")
    if not config.neo4j.password:
        errors.append("Neo4j password is required")
    
    # Validate pipeline config
    if config.pipeline.batch_size <= 0:
        errors.append("Pipeline batch size must be positive")
    if config.pipeline.max_text_length <= 0:
        errors.append("Pipeline max text length must be positive")
    
    # Validate logging config
    valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    if config.logging.level.upper() not in valid_log_levels:
        errors.append(f"Invalid log level: {config.logging.level}")
    
    return errors