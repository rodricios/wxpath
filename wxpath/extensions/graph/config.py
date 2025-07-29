"""
Configuration management for wxpath graph database extension.

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
class GraphConfig:
    """Main configuration container for graph database extension."""
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    
    @classmethod
    def from_env(cls) -> 'GraphConfig':
        """Create configuration from environment variables."""
        return cls(
            neo4j=Neo4jConfig.from_env(),
            pipeline=PipelineConfig.from_env()
        )
    
    @classmethod
    def from_file(cls, config_path: str) -> 'GraphConfig':
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
            }
        }


def get_graph_config() -> GraphConfig:
    """Get configuration, first from environment, then from default config file."""
    # Try to load from environment first
    config = GraphConfig.from_env()
    
    # Check for config file in common locations
    config_paths = [
        'wxpath_graph_config.json',
        'wxpath_graph_config.yml',
        'wxpath_graph_config.yaml',
        os.path.expanduser('~/.wxpath/graph_config.json'),
        os.path.expanduser('~/.wxpath/graph_config.yml'),
        '/etc/wxpath/graph_config.json',
        '/etc/wxpath/graph_config.yml'
    ]
    
    for config_path in config_paths:
        if os.path.exists(config_path):
            try:
                file_config = GraphConfig.from_file(config_path)
                # For now, just return file config (could implement merging)
                return file_config
            except Exception as e:
                print(f"Warning: Could not load graph config from {config_path}: {e}")
                continue
    
    return config


# Global configuration instance
_global_graph_config: Optional[GraphConfig] = None


def get_global_graph_config() -> GraphConfig:
    """Get the global graph configuration instance."""
    global _global_graph_config
    if _global_graph_config is None:
        _global_graph_config = get_graph_config()
    return _global_graph_config


def validate_graph_config(config: GraphConfig) -> List[str]:
    """Validate graph configuration and return list of errors."""
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
    
    return errors