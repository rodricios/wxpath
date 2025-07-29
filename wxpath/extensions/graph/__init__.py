"""
Graph database extension for wxpath.

This extension provides Neo4j integration for storing and analyzing crawled web data as a graph.
It requires additional dependencies: neo4j>=5.15.0, pydantic>=2.0.0

Usage:
    from wxpath.extensions.graph import wxpath_with_graph, enable_graph_integration
    
    # Enable graph integration globally
    enable_graph_integration("url('https://example.com')//a/@href", max_depth=2)
    
    # Or use graph-enabled crawling directly
    results = wxpath_with_graph(
        elem=None,
        path_expr="url('https://example.com')//a/@href", 
        max_depth=2,
        enable_graph=True
    )
"""

from .integration import (
    wxpath_with_graph,
    enable_graph_integration, 
    disable_graph_integration,
    with_graph_integration,
    evaluate_wxpath_bfs_iter_with_graph,
    graph_enabled_wxpath_bfs_iter
)
from .pipeline import GraphPipeline, Neo4jConnection, create_graph_pipeline
from .models import (
    PageNode, ElementNode, CrawlSessionNode,
    LinksToRelationship, ContainsRelationship, PartOfRelationship,
    CrawlResult, GraphTransaction, CrawlStatistics
)
from .queries import create_graph_queries, create_graph_analyzer

__all__ = [
    # Main graph integration functions
    'wxpath_with_graph',
    'enable_graph_integration', 
    'disable_graph_integration',
    'with_graph_integration',
    'evaluate_wxpath_bfs_iter_with_graph',
    'graph_enabled_wxpath_bfs_iter',
    
    # Pipeline classes
    'GraphPipeline',
    'Neo4jConnection', 
    'create_graph_pipeline',
    
    # Graph models
    'PageNode',
    'ElementNode', 
    'CrawlSessionNode',
    'LinksToRelationship',
    'ContainsRelationship',
    'PartOfRelationship',
    'CrawlResult',
    'GraphTransaction',
    'CrawlStatistics',
    
    # Query utilities
    'create_graph_queries',
    'create_graph_analyzer'
]