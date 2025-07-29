"""
Integration layer between wxpath core and Neo4j graph database.

This module provides decorator and utility functions to seamlessly integrate
the Neo4j pipeline with the existing wxpath evaluation process.
"""

import functools
import logging
from typing import Optional, Iterator, Any, Dict
from contextlib import contextmanager

from .config import get_global_graph_config
from .pipeline import GraphPipeline, create_graph_pipeline, Neo4jConnection
from wxpath.core.models import Task

logger = logging.getLogger(__name__)


class GraphIntegration:
    """Manages the integration between wxpath core and Neo4j pipeline."""
    
    def __init__(self, pipeline: Optional[GraphPipeline] = None):
        self.pipeline = pipeline
        self._enabled = False
        self._current_session_id: Optional[str] = None
        
    def enable(self, wxpath_expression: str, max_depth: int, 
               configuration: Optional[Dict[str, Any]] = None) -> str:
        """Enable graph integration and start a new crawl session."""
        if not self.pipeline:
            config = get_global_graph_config()
            if not config.pipeline.enabled:
                logger.info("Graph pipeline is disabled in configuration")
                return ""
            
            try:
                connection = Neo4jConnection(
                    config.neo4j.uri,
                    config.neo4j.username,
                    config.neo4j.password
                )
                self.pipeline = GraphPipeline(connection, config.pipeline.batch_size)
                self.pipeline.initialize_database()
            except Exception as e:
                logger.error(f"Failed to initialize graph pipeline: {e}")
                return ""
        
        try:
            self._current_session_id = self.pipeline.start_crawl_session(
                wxpath_expression=wxpath_expression,
                max_depth=max_depth,
                configuration=configuration
            )
            self._enabled = True
            logger.info(f"Graph integration enabled with session {self._current_session_id}")
            return self._current_session_id
        except Exception as e:
            logger.error(f"Failed to start crawl session: {e}")
            return ""
    
    def disable(self) -> Optional[Dict[str, Any]]:
        """Disable graph integration and end the current session."""
        if not self._enabled or not self.pipeline:
            return None
        
        try:
            stats = self.pipeline.end_crawl_session(self._current_session_id)
            self._enabled = False
            self._current_session_id = None
            logger.info("Graph integration disabled")
            return stats.dict() if stats else None
        except Exception as e:
            logger.error(f"Error ending crawl session: {e}")
            return None
    
    def is_enabled(self) -> bool:
        """Check if graph integration is currently enabled."""
        return self._enabled and self.pipeline is not None
    


# Global integration instance
_global_integration: Optional[GraphIntegration] = None


def get_global_integration() -> GraphIntegration:
    """Get or create the global graph integration instance."""
    global _global_integration
    if _global_integration is None:
        _global_integration = GraphIntegration()
    return _global_integration


def enable_graph_integration(wxpath_expression: str, max_depth: int,
                           configuration: Optional[Dict[str, Any]] = None) -> str:
    """Enable graph integration globally."""
    integration = get_global_integration()
    return integration.enable(wxpath_expression, max_depth, configuration)


def disable_graph_integration() -> Optional[Dict[str, Any]]:
    """Disable graph integration globally."""
    integration = get_global_integration()
    return integration.disable()


def with_graph_integration(wxpath_expression: str, max_depth: int,
                          configuration: Optional[Dict[str, Any]] = None):
    """Context manager for graph integration."""
    @contextmanager
    def context():
        session_id = enable_graph_integration(wxpath_expression, max_depth, configuration)
        try:
            yield session_id
        finally:
            stats = disable_graph_integration()
            if stats:
                logger.info(f"Crawl session completed: {stats}")
    
    return context()


def graph_enabled_wxpath_bfs_iter(original_func):
    """Decorator to add graph integration to evaluate_wxpath_bfs_iter."""
    @functools.wraps(original_func)
    def wrapper(elem, segments, max_depth=1, seen_urls=None, curr_depth=0, 
                html_handlers=None, enable_graph=None, **kwargs):
        
        html_handlers = html_handlers or []
        
        # Determine if graph integration should be enabled
        if enable_graph is None:
            config = get_global_config()
            enable_graph = config.pipeline.enabled and config.pipeline.auto_start_session
        
        integration = get_global_integration()
        session_started = False
        
        # Auto-start session if enabled and not already active
        if enable_graph and not integration.is_enabled():
            # Reconstruct wxpath expression from segments (approximate)
            wxpath_expr = _reconstruct_wxpath_expression(segments)
            session_id = integration.enable(wxpath_expr, max_depth)
            session_started = bool(session_id)
        
        try:
            # Call original function with graph-aware html_handler
            if integration.is_enabled():
                # Add our graph processing handler
                graph_handler = _create_graph_handler(integration)
                html_handlers = list(html_handlers) + [graph_handler]
            
            # Call the original function
            for result in original_func(elem, segments, max_depth, seen_urls, 
                                      curr_depth, html_handlers, **kwargs):
                yield result
                
        finally:
            # End session if we started it
            if session_started:
                integration.disable()
    
    return wrapper


def _create_graph_handler(integration: GraphIntegration):
    """Create an HTML handler that processes results through the graph pipeline."""
    def graph_handler(elem):
        # The graph processing will be handled in the main iteration loop
        # This handler is mainly for any pre-processing if needed
        return elem
    
    return graph_handler


def _reconstruct_wxpath_expression(segments) -> str:
    """Reconstruct a wxpath expression from parsed segments (approximate)."""
    parts = []
    for op, value in segments:
        if op == 'url':
            parts.append(f"url('{value}')")
        elif op == 'url_from_attr':
            parts.append(value)
        elif op == 'url_inf':
            parts.append(value)
        elif op == 'xpath':
            parts.append(value)
    return ''.join(parts)


# Enhanced version of evaluate_wxpath_bfs_iter with graph integration
def evaluate_wxpath_bfs_iter_with_graph(elem, segments, max_depth=1, seen_urls=None, 
                                       curr_depth=0, html_handlers=None, 
                                       enable_graph=None, **kwargs):
    """
    Enhanced version of evaluate_wxpath_bfs_iter with graph database integration.
    
    This function wraps the original evaluate_wxpath_bfs_iter and adds graph
    database storage capabilities while maintaining full compatibility.
    """
    # Import here to avoid circular imports
    from .core import evaluate_wxpath_bfs_iter
    
    html_handlers = html_handlers or []
    
    # Determine if graph integration should be enabled
    if enable_graph is None:
        config = get_global_config()
        enable_graph = config.pipeline.enabled and config.pipeline.auto_start_session
    
    integration = get_global_integration()
    session_started = False
    
    # Auto-start session if enabled and not already active
    if enable_graph and not integration.is_enabled():
        wxpath_expr = _reconstruct_wxpath_expression(segments)
        session_id = integration.enable(wxpath_expr, max_depth)
        session_started = bool(session_id)
    
    try:
        # Call original function with graph integration passed through
        for result in evaluate_wxpath_bfs_iter(elem, segments, max_depth, 
                                             seen_urls, curr_depth, html_handlers,
                                             _graph_integration=integration if integration.is_enabled() else None):
            yield result
            
    finally:
        # End session if we started it
        if session_started:
            stats = integration.disable()
            if stats:
                logger.info(f"Graph crawl session completed with {stats.get('total_pages_crawled', 0)} pages")


# Convenience function for users
def wxpath_with_graph(elem, path_expr, max_depth=1, enable_graph=True, **kwargs):
    """
    Convenience function for wxpath evaluation with graph database integration.
    
    Args:
        elem: HTML element to start from (can be None for URL-based expressions)
        path_expr: wxpath expression string
        max_depth: Maximum crawl depth
        enable_graph: Whether to enable graph database storage
        **kwargs: Additional arguments passed to the evaluation function
    
    Returns:
        List of results from the wxpath evaluation
    """
    from .core import parse_wxpath_expr
    
    segments = parse_wxpath_expr(path_expr)
    return list(evaluate_wxpath_bfs_iter_with_graph(
        elem, segments, max_depth=max_depth, enable_graph=enable_graph, **kwargs
    ))