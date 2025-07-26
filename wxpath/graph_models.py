"""
Graph data models for Neo4j integration with wxpath.

This module defines Pydantic models for representing crawled web data
in a graph structure suitable for Neo4j storage.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, HttpUrl
from enum import Enum


class NodeType(str, Enum):
    """Enumeration of node types in the graph."""
    PAGE = "Page"
    ELEMENT = "Element"
    CRAWL_SESSION = "CrawlSession"


class RelationshipType(str, Enum):
    """Enumeration of relationship types in the graph."""
    LINKS_TO = "LINKS_TO"
    CONTAINS = "CONTAINS"
    PART_OF = "PART_OF"
    EXTRACTED_FROM = "EXTRACTED_FROM"


class BaseGraphNode(BaseModel):
    """Base class for all graph nodes."""
    node_type: NodeType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    properties: Dict[str, Any] = Field(default_factory=dict)


class PageNode(BaseGraphNode):
    """Represents a web page in the graph."""
    node_type: NodeType = NodeType.PAGE
    url: str
    title: Optional[str] = None
    fetch_timestamp: datetime = Field(default_factory=datetime.utcnow)
    depth: int
    content_hash: Optional[str] = None
    status_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    content_length: Optional[int] = None
    base_url: Optional[str] = None
    backlink: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ElementNode(BaseGraphNode):
    """Represents an extracted HTML element in the graph."""
    node_type: NodeType = NodeType.ELEMENT
    xpath: str
    text_content: Optional[str] = None
    tag: Optional[str] = None
    attributes: Dict[str, str] = Field(default_factory=dict)
    extraction_order: Optional[int] = None
    element_type: Optional[str] = None  # e.g., 'link', 'text', 'image'


class CrawlSessionNode(BaseGraphNode):
    """Represents a crawling session in the graph."""
    node_type: NodeType = NodeType.CRAWL_SESSION
    session_id: str
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    wxpath_expression: str
    max_depth: int
    total_pages: int = 0
    total_elements: int = 0
    success_count: int = 0
    error_count: int = 0
    configuration: Dict[str, Any] = Field(default_factory=dict)


class BaseGraphRelationship(BaseModel):
    """Base class for all graph relationships."""
    relationship_type: RelationshipType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    properties: Dict[str, Any] = Field(default_factory=dict)


class LinksToRelationship(BaseGraphRelationship):
    """Represents a link between two pages."""
    relationship_type: RelationshipType = RelationshipType.LINKS_TO
    href: str
    link_text: Optional[str] = None
    discovered_at_depth: int
    anchor_xpath: Optional[str] = None


class ContainsRelationship(BaseGraphRelationship):
    """Represents a page containing an element."""
    relationship_type: RelationshipType = RelationshipType.CONTAINS
    xpath_location: str
    extraction_order: int


class PartOfRelationship(BaseGraphRelationship):
    """Represents an entity being part of a crawl session."""
    relationship_type: RelationshipType = RelationshipType.PART_OF
    order_in_session: Optional[int] = None


class ExtractedFromRelationship(BaseGraphRelationship):
    """Represents an element extracted from a page."""
    relationship_type: RelationshipType = RelationshipType.EXTRACTED_FROM
    source_url: str
    extraction_method: str = "wxpath"


class CrawlResult(BaseModel):
    """Container for a complete crawl result with graph data."""
    page: PageNode
    elements: List[ElementNode] = Field(default_factory=list)
    relationships: List[BaseGraphRelationship] = Field(default_factory=list)
    session_id: str
    crawl_depth: int


class GraphTransaction(BaseModel):
    """Represents a batch of graph operations to be executed as a transaction."""
    nodes: List[BaseGraphNode] = Field(default_factory=list)
    relationships: List[BaseGraphRelationship] = Field(default_factory=list)
    session_id: str
    batch_id: Optional[str] = None


class CrawlStatistics(BaseModel):
    """Statistics for a crawl session."""
    session_id: str
    total_pages_crawled: int
    total_elements_extracted: int
    total_links_discovered: int
    unique_domains: int
    crawl_duration_seconds: float
    pages_per_depth: Dict[int, int]
    errors: List[str] = Field(default_factory=list)


def create_page_node(
    url: str,
    depth: int,
    title: Optional[str] = None,
    content_hash: Optional[str] = None,
    status_code: Optional[int] = None,
    base_url: Optional[str] = None,
    backlink: Optional[str] = None,
    **kwargs
) -> PageNode:
    """Factory function to create a PageNode."""
    return PageNode(
        url=url,
        depth=depth,
        title=title,
        content_hash=content_hash,
        status_code=status_code,
        base_url=base_url,
        backlink=backlink,
        **kwargs
    )


def create_element_node(
    xpath: str,
    text_content: Optional[str] = None,
    tag: Optional[str] = None,
    attributes: Optional[Dict[str, str]] = None,
    **kwargs
) -> ElementNode:
    """Factory function to create an ElementNode."""
    return ElementNode(
        xpath=xpath,
        text_content=text_content,
        tag=tag,
        attributes=attributes or {},
        **kwargs
    )


def create_crawl_session_node(
    session_id: str,
    wxpath_expression: str,
    max_depth: int,
    **kwargs
) -> CrawlSessionNode:
    """Factory function to create a CrawlSessionNode."""
    return CrawlSessionNode(
        session_id=session_id,
        wxpath_expression=wxpath_expression,
        max_depth=max_depth,
        **kwargs
    )