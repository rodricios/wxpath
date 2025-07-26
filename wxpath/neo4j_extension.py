"""
Neo4j graph database extension for wxpath.

This module provides pipeline functionality to store crawled web data
as a graph in Neo4j, preserving relationships between pages, elements,
and crawl sessions.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Generator
from contextlib import contextmanager

from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import Neo4jError
from lxml import html

from .graph_models import (
    PageNode, ElementNode, CrawlSessionNode, CrawlResult,
    LinksToRelationship, ContainsRelationship, PartOfRelationship,
    GraphTransaction, CrawlStatistics,
    create_page_node, create_element_node, create_crawl_session_node
)
from .models import WxStr, Task


logger = logging.getLogger(__name__)


class Neo4jConnection:
    """Manages Neo4j database connections and transactions."""
    
    def __init__(self, uri: str, username: str, password: str):
        self.uri = uri
        self.username = username
        self.password = password
        self._driver: Optional[Driver] = None
    
    def connect(self) -> Driver:
        """Establish connection to Neo4j database."""
        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.username, self.password),
                    max_connection_lifetime=30 * 60,  # 30 minutes
                    max_connection_pool_size=50,
                    connection_acquisition_timeout=60
                )
                # Test connection
                with self._driver.session() as session:
                    session.run("RETURN 1")
                logger.info(f"Connected to Neo4j at {self.uri}")
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                raise
        return self._driver
    
    def close(self):
        """Close the Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")
    
    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Context manager for Neo4j sessions."""
        driver = self.connect()
        with driver.session() as session:
            yield session


class GraphPipeline:
    """Main pipeline for processing wxpath crawl results into Neo4j graph."""
    
    def __init__(self, connection: Neo4jConnection, batch_size: int = 100):
        self.connection = connection
        self.batch_size = batch_size
        self.current_session_id: Optional[str] = None
        self.current_transaction: Optional[GraphTransaction] = None
        self._statistics: Dict[str, CrawlStatistics] = {}
        
    def initialize_database(self):
        """Create necessary indexes and constraints in Neo4j."""
        constraints_and_indexes = [
            # Constraints
            "CREATE CONSTRAINT page_url_unique IF NOT EXISTS FOR (p:Page) REQUIRE p.url IS UNIQUE",
            "CREATE CONSTRAINT session_id_unique IF NOT EXISTS FOR (s:CrawlSession) REQUIRE s.session_id IS UNIQUE",
            
            # Indexes
            "CREATE INDEX page_depth_idx IF NOT EXISTS FOR (p:Page) ON (p.depth)",
            "CREATE INDEX page_timestamp_idx IF NOT EXISTS FOR (p:Page) ON (p.fetch_timestamp)",
            "CREATE INDEX element_xpath_idx IF NOT EXISTS FOR (e:Element) ON (e.xpath)",
            "CREATE INDEX session_start_time_idx IF NOT EXISTS FOR (s:CrawlSession) ON (s.start_time)",
        ]
        
        with self.connection.session() as session:
            for query in constraints_and_indexes:
                try:
                    session.run(query)
                    logger.debug(f"Executed: {query}")
                except Neo4jError as e:
                    logger.warning(f"Failed to execute {query}: {e}")
    
    def start_crawl_session(self, wxpath_expression: str, max_depth: int, 
                          configuration: Optional[Dict[str, Any]] = None) -> str:
        """Start a new crawl session."""
        session_id = str(uuid.uuid4())
        self.current_session_id = session_id
        
        session_node = create_crawl_session_node(
            session_id=session_id,
            wxpath_expression=wxpath_expression,
            max_depth=max_depth,
            configuration=configuration or {}
        )
        
        # Create session node in database
        with self.connection.session() as db_session:
            query = """
            CREATE (s:CrawlSession {
                session_id: $session_id,
                start_time: $start_time,
                wxpath_expression: $wxpath_expression,
                max_depth: $max_depth,
                total_pages: 0,
                total_elements: 0,
                success_count: 0,
                error_count: 0,
                configuration: $configuration
            })
            RETURN s
            """
            try:
                result = db_session.run(query, 
                    session_id=session_id,
                    start_time=session_node.start_time.isoformat(),
                    wxpath_expression=wxpath_expression,
                    max_depth=max_depth,
                    configuration=json.dumps(session_node.configuration)
                )
                created_session = result.single()
                logger.debug(f"Created CrawlSession node: {created_session}")
            except Exception as e:
                logger.error(f"Failed to create CrawlSession: {e}")
                raise
        
        # Initialize statistics
        self._statistics[session_id] = CrawlStatistics(
            session_id=session_id,
            total_pages_crawled=0,
            total_elements_extracted=0,
            total_links_discovered=0,
            unique_domains=0,
            crawl_duration_seconds=0.0,
            pages_per_depth={}
        )
        
        logger.info(f"Started crawl session {session_id}")
        return session_id
    
    def end_crawl_session(self, session_id: Optional[str] = None) -> CrawlStatistics:
        """End a crawl session and return statistics."""
        session_id = session_id or self.current_session_id
        if not session_id:
            raise ValueError("No active session to end")
        
        # Update session end time and statistics
        stats = self._statistics.get(session_id)
        if stats:
            end_time = datetime.utcnow()
            with self.connection.session() as db_session:
                query = """
                MATCH (s:CrawlSession {session_id: $session_id})
                SET s.end_time = $end_time,
                    s.total_pages = $total_pages,
                    s.total_elements = $total_elements,
                    s.success_count = $success_count,
                    s.error_count = $error_count
                RETURN s
                """
                db_session.run(query,
                    session_id=session_id,
                    end_time=end_time.isoformat(),
                    total_pages=stats.total_pages_crawled,
                    total_elements=stats.total_elements_extracted,
                    success_count=stats.total_pages_crawled,
                    error_count=len(stats.errors)
                )
        
        if session_id == self.current_session_id:
            self.current_session_id = None
        
        logger.info(f"Ended crawl session {session_id}")
        return stats or CrawlStatistics(session_id=session_id, **{})
    
    def process_page_result(self, elem: html.HtmlElement, task: Task,
                          session_id: Optional[str] = None) -> CrawlResult:
        """Process a crawled page and convert to graph representation."""
        session_id = session_id or self.current_session_id
        if not session_id:
            raise ValueError("No active session")
        
        # Extract page information
        url = getattr(elem, 'base_url', task.backlink or 'unknown')
        backlink = task.backlink
        depth = task.depth
        
        # Create content hash
        content_hash = self._generate_content_hash(elem)
        
        # Extract page title
        title_elements = elem.xpath('//title/text()')
        title = title_elements[0].strip() if title_elements else None
        
        # Create page node
        page_node = create_page_node(
            url=url,
            depth=depth,
            title=title,
            content_hash=content_hash,
            base_url=getattr(elem, 'base_url', None),
            backlink=backlink
        )
        
        # Extract elements (links, text, etc.)
        elements = self._extract_elements_from_page(elem)
        
        # Create relationships
        relationships = []
        
        # Add part of session relationship
        relationships.append(PartOfRelationship(
            order_in_session=self._statistics[session_id].total_pages_crawled
        ))
        
        # Add contains relationships for elements
        for i, element in enumerate(elements):
            relationships.append(ContainsRelationship(
                xpath_location=element.xpath,
                extraction_order=i
            ))
        
        # Add links to relationships
        link_elements = self._extract_links(elem)
        for link in link_elements:
            relationships.append(LinksToRelationship(
                href=link['href'],
                link_text=link.get('text'),
                discovered_at_depth=depth,
                anchor_xpath=link.get('xpath')
            ))
        
        # Update statistics
        stats = self._statistics[session_id]
        stats.total_pages_crawled += 1
        stats.total_elements_extracted += len(elements)
        stats.total_links_discovered += len(link_elements)
        stats.pages_per_depth[depth] = stats.pages_per_depth.get(depth, 0) + 1
        
        return CrawlResult(
            page=page_node,
            elements=elements,
            relationships=relationships,
            session_id=session_id,
            crawl_depth=depth
        )
    
    def store_crawl_result(self, result: CrawlResult):
        """Store a crawl result in the Neo4j database."""
        with self.connection.session() as session:
            # Create page node
            page_query = """
            MERGE (p:Page {url: $url})
            SET p.title = $title,
                p.fetch_timestamp = $fetch_timestamp,
                p.depth = $depth,
                p.content_hash = $content_hash,
                p.base_url = $base_url,
                p.backlink = $backlink,
                p.created_at = $created_at
            RETURN p
            """
            session.run(page_query, 
                url=result.page.url,
                title=result.page.title,
                fetch_timestamp=result.page.fetch_timestamp.isoformat(),
                depth=result.page.depth,
                content_hash=result.page.content_hash,
                base_url=result.page.base_url,
                backlink=result.page.backlink,
                created_at=result.page.created_at.isoformat()
            )
            
            # Create elements and relationships
            for element in result.elements:
                element_query = """
                CREATE (e:Element {
                    xpath: $xpath,
                    text_content: $text_content,
                    tag: $tag,
                    attributes: $attributes,
                    extraction_order: $extraction_order,
                    element_type: $element_type,
                    created_at: $created_at
                })
                WITH e
                MATCH (p:Page {url: $page_url})
                CREATE (p)-[:CONTAINS {
                    xpath_location: $xpath,
                    extraction_order: $extraction_order
                }]->(e)
                """
                session.run(element_query,
                    xpath=element.xpath,
                    text_content=element.text_content,
                    tag=element.tag,
                    attributes=element.attributes,
                    extraction_order=element.extraction_order,
                    element_type=element.element_type,
                    created_at=element.created_at.isoformat(),
                    page_url=result.page.url
                )
            
            # Create session relationships
            session_rel_query = """
            MATCH (p:Page {url: $page_url})
            MATCH (s:CrawlSession {session_id: $session_id})
            CREATE (p)-[:PART_OF {
                order_in_session: $order_in_session
            }]->(s)
            """
            session.run(session_rel_query,
                page_url=result.page.url,
                session_id=result.session_id,
                order_in_session=self._statistics[result.session_id].total_pages_crawled - 1
            )
    
    def _generate_content_hash(self, elem: html.HtmlElement) -> str:
        """Generate a hash of the page content."""
        content = html.tostring(elem, encoding='unicode')
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _extract_elements_from_page(self, elem: html.HtmlElement) -> List[ElementNode]:
        """Extract meaningful elements from a page."""
        elements = []
        
        # Extract all links
        links = elem.xpath('//a[@href]')
        for i, link in enumerate(links):
            href = link.get('href')
            text = link.text_content().strip() if link.text_content() else None
            elements.append(create_element_node(
                xpath=elem.getpath(link) if hasattr(elem, 'getpath') else f'//a[{i+1}]',
                text_content=text,
                tag='a',
                attributes={'href': href},
                extraction_order=i,
                element_type='link'
            ))
        
        # Extract headings
        headings = elem.xpath('//h1 | //h2 | //h3 | //h4 | //h5 | //h6')
        for i, heading in enumerate(headings):
            text = heading.text_content().strip() if heading.text_content() else None
            if text:
                elements.append(create_element_node(
                    xpath=elem.getpath(heading) if hasattr(elem, 'getpath') else f'//{heading.tag}[{i+1}]',
                    text_content=text,
                    tag=heading.tag,
                    extraction_order=len(elements),
                    element_type='heading'
                ))
        
        return elements
    
    def _extract_links(self, elem: html.HtmlElement) -> List[Dict[str, str]]:
        """Extract link information from a page."""
        links = []
        link_elements = elem.xpath('//a[@href]')
        
        for i, link in enumerate(link_elements):
            href = link.get('href')
            text = link.text_content().strip() if link.text_content() else None
            xpath = elem.getpath(link) if hasattr(elem, 'getpath') else f'//a[{i+1}]'
            
            links.append({
                'href': href,
                'text': text,
                'xpath': xpath
            })
        
        return links
    
    # Event-based methods for graph integration
    def on_page_fetched(self, url: str, elem: html.HtmlElement, depth: int, 
                       parent_url: Optional[str] = None, session_id: Optional[str] = None):
        """Handle page fetched event - create page node and relationships."""
        session_id = session_id or self.current_session_id
        if not session_id:
            logger.warning(f"No active session for page fetch: {url}")
            return
        
        logger.debug(f"Processing page fetch: {url}, session_id: {session_id}, current_session: {self.current_session_id}")
        
        # Create page node
        title_elements = elem.xpath('//title/text()') if elem is not None else []
        title = title_elements[0].strip() if title_elements else None
        content_hash = self._generate_content_hash(elem) if elem is not None else None
        
        page_node = create_page_node(
            url=url,
            depth=depth,
            title=title,
            content_hash=content_hash,
            base_url=getattr(elem, 'base_url', None) if elem else None,
            backlink=parent_url
        )
        
        # Store page in database
        with self.connection.session() as db_session:
            page_query = """
            MERGE (p:Page {url: $url})
            SET p.title = $title,
                p.fetch_timestamp = $fetch_timestamp,
                p.depth = $depth,
                p.content_hash = $content_hash,
                p.base_url = $base_url,
                p.backlink = $backlink,
                p.created_at = $created_at
            RETURN p
            """
            db_session.run(page_query, 
                url=page_node.url,
                title=page_node.title,
                fetch_timestamp=page_node.fetch_timestamp.isoformat(),
                depth=page_node.depth,
                content_hash=page_node.content_hash,
                base_url=page_node.base_url,
                backlink=page_node.backlink,
                created_at=page_node.created_at.isoformat()
            )
            
            # Create PART_OF relationship to session
            session_rel_query = """
            MATCH (p:Page {url: $page_url})
            MATCH (s:CrawlSession {session_id: $session_id})
            MERGE (p)-[:PART_OF {
                order_in_session: $order_in_session,
                created_at: $created_at
            }]->(s)
            """
            stats = self._statistics.get(session_id)
            order_in_session = stats.total_pages_crawled if stats else 0
            
            try:
                db_session.run(session_rel_query,
                    page_url=url,
                    session_id=session_id,
                    order_in_session=order_in_session,
                    created_at=datetime.utcnow().isoformat()
                )
                logger.debug(f"Created PART_OF relationship: {url} -> session {session_id}")
            except Exception as e:
                logger.error(f"Failed to create PART_OF relationship for {url}: {e}")
                # Check if session exists
                check_session = db_session.run("MATCH (s:CrawlSession {session_id: $session_id}) RETURN count(s) as count", session_id=session_id)
                session_exists = check_session.single()['count']
                logger.error(f"Session {session_id} exists: {session_exists > 0}")
            
            # Create LINKS_TO relationship if this page was discovered from a parent
            if parent_url:
                links_to_query = """
                MATCH (parent:Page {url: $parent_url})
                MATCH (child:Page {url: $child_url})
                MERGE (parent)-[:LINKS_TO {
                    href: $href,
                    discovered_at_depth: $discovered_at_depth,
                    created_at: $created_at
                }]->(child)
                """
                db_session.run(links_to_query,
                    parent_url=parent_url,
                    child_url=url,
                    href=url,
                    discovered_at_depth=depth - 1,
                    created_at=datetime.utcnow().isoformat()
                )
        
        # Update statistics
        if stats:
            stats.total_pages_crawled += 1
            stats.pages_per_depth[depth] = stats.pages_per_depth.get(depth, 0) + 1
            
        logger.debug(f"Processed page fetch event: {url} (depth={depth}, parent={parent_url})")
    
    def on_url_discovered(self, source_url: str, target_url: str, link_text: Optional[str] = None, 
                         xpath: Optional[str] = None, session_id: Optional[str] = None):
        """Handle URL discovered event - create LINKS_TO relationship."""
        session_id = session_id or self.current_session_id
        if not session_id:
            logger.warning(f"No active session for URL discovery: {source_url} -> {target_url}")
            return
            
        with self.connection.session() as db_session:
            # Ensure both pages exist (create target as placeholder if needed)
            ensure_pages_query = """
            MERGE (source:Page {url: $source_url})
            MERGE (target:Page {url: $target_url})
            """
            db_session.run(ensure_pages_query, source_url=source_url, target_url=target_url)
            
            # Create or update LINKS_TO relationship
            links_to_query = """
            MATCH (source:Page {url: $source_url})
            MATCH (target:Page {url: $target_url})
            MERGE (source)-[r:LINKS_TO {href: $target_url}]->(target)
            SET r.link_text = $link_text,
                r.anchor_xpath = $xpath,
                r.created_at = $created_at
            """
            db_session.run(links_to_query,
                source_url=source_url,
                target_url=target_url,
                link_text=link_text,
                xpath=xpath,
                created_at=datetime.utcnow().isoformat()
            )
        
        # Update statistics
        stats = self._statistics.get(session_id)
        if stats:
            stats.total_links_discovered += 1
            
        logger.debug(f"Processed URL discovery event: {source_url} -> {target_url}")
    
    def on_element_extracted(self, page_url: str, element: html.HtmlElement, 
                           xpath: str, session_id: Optional[str] = None):
        """Handle element extracted event - create element node and CONTAINS relationship."""
        session_id = session_id or self.current_session_id
        if not session_id:
            logger.warning(f"No active session for element extraction: {page_url}")
            return
            
        # Create element node
        text_content = element.text_content().strip() if hasattr(element, 'text_content') and element.text_content() else None
        tag = getattr(element, 'tag', None)
        attributes = dict(element.attrib) if hasattr(element, 'attrib') else {}
        
        element_node = create_element_node(
            xpath=xpath,
            text_content=text_content,
            tag=tag,
            attributes=attributes,
            extraction_order=0,  # Will be updated based on session stats
            element_type='extracted'
        )
        
        with self.connection.session() as db_session:
            # Create element and CONTAINS relationship
            element_query = """
            CREATE (e:Element {
                xpath: $xpath,
                text_content: $text_content,
                tag: $tag,
                attributes: $attributes,
                extraction_order: $extraction_order,
                element_type: $element_type,
                created_at: $created_at
            })
            WITH e
            MATCH (p:Page {url: $page_url})
            CREATE (p)-[:CONTAINS {
                xpath_location: $xpath,
                extraction_order: $extraction_order,
                created_at: $created_at
            }]->(e)
            """
            stats = self._statistics.get(session_id)
            extraction_order = stats.total_elements_extracted if stats else 0
            
            db_session.run(element_query,
                xpath=element_node.xpath,
                text_content=element_node.text_content,
                tag=element_node.tag,
                attributes=json.dumps(element_node.attributes),
                extraction_order=extraction_order,
                element_type=element_node.element_type,
                created_at=element_node.created_at.isoformat(),
                page_url=page_url
            )
        
        # Update statistics
        if stats:
            stats.total_elements_extracted += 1
            
        logger.debug(f"Processed element extraction event: {page_url} xpath={xpath}")


def create_graph_pipeline(uri: str, username: str, password: str, 
                         batch_size: int = 100) -> GraphPipeline:
    """Factory function to create a configured GraphPipeline."""
    connection = Neo4jConnection(uri, username, password)
    pipeline = GraphPipeline(connection, batch_size)
    pipeline.initialize_database()
    return pipeline


# Global pipeline instance (optional, for convenience)
_global_pipeline: Optional[GraphPipeline] = None


def initialize_global_pipeline(uri: str, username: str, password: str) -> GraphPipeline:
    """Initialize the global pipeline instance."""
    global _global_pipeline
    _global_pipeline = create_graph_pipeline(uri, username, password)
    return _global_pipeline


def get_global_pipeline() -> Optional[GraphPipeline]:
    """Get the global pipeline instance."""
    return _global_pipeline