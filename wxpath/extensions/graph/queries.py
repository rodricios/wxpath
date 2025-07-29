"""
Graph query utilities for wxpath Neo4j integration.

This module provides pre-built queries and utilities for exploring
and analyzing crawled web data stored in the graph database.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

from neo4j import Session


@dataclass
class QueryResult:
    """Container for query results with metadata."""
    data: List[Dict[str, Any]]
    query: str
    execution_time_ms: Optional[float] = None
    total_records: int = 0


class GraphQueryBuilder:
    """Builder class for constructing Cypher queries."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset the query builder."""
        self._match = []
        self._where = []
        self._return = []
        self._order_by = []
        self._limit = None
        self._with = []
        
    def match(self, pattern: str) -> 'GraphQueryBuilder':
        """Add a MATCH clause."""
        self._match.append(pattern)
        return self
    
    def where(self, condition: str) -> 'GraphQueryBuilder':
        """Add a WHERE condition."""
        self._where.append(condition)
        return self
    
    def return_clause(self, items: str) -> 'GraphQueryBuilder':
        """Add a RETURN clause."""
        self._return.append(items)
        return self
    
    def order_by(self, field: str, ascending: bool = True) -> 'GraphQueryBuilder':
        """Add an ORDER BY clause."""
        direction = "ASC" if ascending else "DESC"
        self._order_by.append(f"{field} {direction}")
        return self
    
    def limit(self, count: int) -> 'GraphQueryBuilder':
        """Add a LIMIT clause."""
        self._limit = count
        return self
    
    def with_clause(self, items: str) -> 'GraphQueryBuilder':
        """Add a WITH clause."""
        self._with.append(items)
        return self
    
    def build(self) -> str:
        """Build the final Cypher query."""
        parts = []
        
        if self._match:
            parts.append("MATCH " + ", ".join(self._match))
        
        if self._where:
            parts.append("WHERE " + " AND ".join(self._where))
        
        if self._with:
            parts.append("WITH " + ", ".join(self._with))
        
        if self._return:
            parts.append("RETURN " + ", ".join(self._return))
        
        if self._order_by:
            parts.append("ORDER BY " + ", ".join(self._order_by))
        
        if self._limit:
            parts.append(f"LIMIT {self._limit}")
        
        return "\n".join(parts)


class GraphQueries:
    """Collection of pre-built queries for analyzing crawled data."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_crawl_sessions(self, limit: int = 10) -> QueryResult:
        """Get recent crawl sessions."""
        query = """
        MATCH (s:CrawlSession)
        RETURN s.session_id as session_id,
               s.start_time as start_time,
               s.end_time as end_time,
               s.wxpath_expression as expression,
               s.max_depth as max_depth,
               s.total_pages as total_pages,
               s.total_elements as total_elements
        ORDER BY s.start_time DESC
        LIMIT $limit
        """
        
        result = self.session.run(query, limit=limit)
        records = [record.data() for record in result]
        
        return QueryResult(
            data=records,
            query=query,
            total_records=len(records)
        )
    
    def get_session_pages(self, session_id: str, depth: Optional[int] = None) -> QueryResult:
        """Get pages from a specific crawl session."""
        where_clause = "s.session_id = $session_id"
        params = {"session_id": session_id}
        
        if depth is not None:
            where_clause += " AND p.depth = $depth"
            params["depth"] = depth
        
        query = f"""
        MATCH (p:Page)-[:PART_OF]->(s:CrawlSession)
        WHERE {where_clause}
        RETURN p.url as url,
               p.title as title,
               p.depth as depth,
               p.fetch_timestamp as fetch_timestamp,
               p.backlink as backlink
        ORDER BY p.depth, p.fetch_timestamp
        """
        
        result = self.session.run(query, **params)
        records = [record.data() for record in result]
        
        return QueryResult(
            data=records,
            query=query,
            total_records=len(records)
        )
    
    def get_page_links(self, url: str) -> QueryResult:
        """Get all outgoing links from a specific page."""
        query = """
        MATCH (source:Page {url: $url})-[r:LINKS_TO]->(target:Page)
        RETURN target.url as target_url,
               target.title as target_title,
               r.link_text as link_text,
               r.discovered_at_depth as depth,
               r.anchor_xpath as xpath
        ORDER BY r.discovered_at_depth
        """
        
        result = self.session.run(query, url=url)
        records = [record.data() for record in result]
        
        return QueryResult(
            data=records,
            query=query,
            total_records=len(records)
        )
    
    def get_page_elements(self, url: str, element_type: Optional[str] = None) -> QueryResult:
        """Get elements extracted from a specific page."""
        where_clause = "p.url = $url"
        params = {"url": url}
        
        if element_type:
            where_clause += " AND e.element_type = $element_type"
            params["element_type"] = element_type
        
        query = f"""
        MATCH (p:Page)-[:CONTAINS]->(e:Element)
        WHERE {where_clause}
        RETURN e.xpath as xpath,
               e.text_content as text_content,
               e.tag as tag,
               e.attributes as attributes,
               e.element_type as element_type,
               e.extraction_order as extraction_order
        ORDER BY e.extraction_order
        """
        
        result = self.session.run(query, **params)
        records = [record.data() for record in result]
        
        return QueryResult(
            data=records,
            query=query,
            total_records=len(records)
        )
    
    def get_link_chain(self, start_url: str, max_depth: int = 3) -> QueryResult:
        """Get a chain of links starting from a URL."""
        query = """
        MATCH path = (start:Page {url: $start_url})-[:LINKS_TO*1..$max_depth]->(end:Page)
        RETURN [node in nodes(path) | node.url] as urls,
               [rel in relationships(path) | rel.link_text] as link_texts,
               length(path) as chain_length
        ORDER BY chain_length
        LIMIT 50
        """
        
        result = self.session.run(query, start_url=start_url, max_depth=max_depth)
        records = [record.data() for record in result]
        
        return QueryResult(
            data=records,
            query=query,
            total_records=len(records)
        )
    
    def get_most_linked_pages(self, session_id: Optional[str] = None, limit: int = 10) -> QueryResult:
        """Get pages with the most incoming links."""
        if session_id:
            query = """
            MATCH (target:Page)-[:PART_OF]->(s:CrawlSession {session_id: $session_id})
            MATCH (source:Page)-[:LINKS_TO]->(target)
            WITH target, count(source) as link_count
            RETURN target.url as url,
                   target.title as title,
                   link_count
            ORDER BY link_count DESC
            LIMIT $limit
            """
            params = {"session_id": session_id, "limit": limit}
        else:
            query = """
            MATCH (source:Page)-[:LINKS_TO]->(target:Page)
            WITH target, count(source) as link_count
            RETURN target.url as url,
                   target.title as title,
                   link_count
            ORDER BY link_count DESC
            LIMIT $limit
            """
            params = {"limit": limit}
        
        result = self.session.run(query, **params)
        records = [record.data() for record in result]
        
        return QueryResult(
            data=records,
            query=query,
            total_records=len(records)
        )
    
    def get_depth_distribution(self, session_id: str) -> QueryResult:
        """Get the distribution of pages by depth for a session."""
        query = """
        MATCH (p:Page)-[:PART_OF]->(s:CrawlSession {session_id: $session_id})
        WITH p.depth as depth, count(p) as page_count
        RETURN depth, page_count
        ORDER BY depth
        """
        
        result = self.session.run(query, session_id=session_id)
        records = [record.data() for record in result]
        
        return QueryResult(
            data=records,
            query=query,
            total_records=len(records)
        )
    
    def get_orphaned_pages(self, session_id: Optional[str] = None) -> QueryResult:
        """Get pages with no incoming links (except the start page)."""
        if session_id:
            query = """
            MATCH (p:Page)-[:PART_OF]->(s:CrawlSession {session_id: $session_id})
            WHERE NOT ()-[:LINKS_TO]->(p) AND p.depth > 0
            RETURN p.url as url,
                   p.title as title,
                   p.depth as depth,
                   p.backlink as backlink
            ORDER BY p.depth
            """
            params = {"session_id": session_id}
        else:
            query = """
            MATCH (p:Page)
            WHERE NOT ()-[:LINKS_TO]->(p) AND p.depth > 0
            RETURN p.url as url,
                   p.title as title,
                   p.depth as depth,
                   p.backlink as backlink
            ORDER BY p.depth
            """
            params = {}
        
        result = self.session.run(query, **params)
        records = [record.data() for record in result]
        
        return QueryResult(
            data=records,
            query=query,
            total_records=len(records)
        )
    
    def get_session_statistics(self, session_id: str) -> QueryResult:
        """Get comprehensive statistics for a crawl session."""
        query = """
        MATCH (s:CrawlSession {session_id: $session_id})
        OPTIONAL MATCH (p:Page)-[:PART_OF]->(s)
        OPTIONAL MATCH (e:Element)<-[:CONTAINS]-(p)
        OPTIONAL MATCH (p)-[l:LINKS_TO]->()
        
        WITH s, 
             count(DISTINCT p) as total_pages,
             count(DISTINCT e) as total_elements,
             count(DISTINCT l) as total_links,
             collect(DISTINCT p.depth) as depths
        
        UNWIND depths as depth
        MATCH (dp:Page {depth: depth})-[:PART_OF]->(s)
        WITH s, total_pages, total_elements, total_links, 
             depth, count(dp) as pages_at_depth
        
        RETURN s.session_id as session_id,
               s.start_time as start_time,
               s.end_time as end_time,
               s.wxpath_expression as expression,
               total_pages,
               total_elements,
               total_links,
               collect({depth: depth, pages: pages_at_depth}) as depth_distribution
        """
        
        result = self.session.run(query, session_id=session_id)
        records = [record.data() for record in result]
        
        return QueryResult(
            data=records,
            query=query,
            total_records=len(records)
        )
    
    def find_similar_pages(self, url: str, limit: int = 5) -> QueryResult:
        """Find pages similar to the given URL based on content hash or structure."""
        query = """
        MATCH (reference:Page {url: $url})
        MATCH (similar:Page)
        WHERE similar.url <> reference.url 
          AND (similar.content_hash = reference.content_hash 
               OR similar.title = reference.title)
        RETURN similar.url as url,
               similar.title as title,
               similar.depth as depth,
               CASE 
                 WHEN similar.content_hash = reference.content_hash THEN 'identical_content'
                 WHEN similar.title = reference.title THEN 'same_title'
                 ELSE 'other'
               END as similarity_type
        LIMIT $limit
        """
        
        result = self.session.run(query, url=url, limit=limit)
        records = [record.data() for record in result]
        
        return QueryResult(
            data=records,
            query=query,
            total_records=len(records)
        )


class GraphAnalyzer:
    """Higher-level analysis tools for graph data."""
    
    def __init__(self, queries: GraphQueries):
        self.queries = queries
    
    def analyze_crawl_session(self, session_id: str) -> Dict[str, Any]:
        """Perform comprehensive analysis of a crawl session."""
        stats = self.queries.get_session_statistics(session_id)
        depth_dist = self.queries.get_depth_distribution(session_id)
        most_linked = self.queries.get_most_linked_pages(session_id, limit=5)
        orphaned = self.queries.get_orphaned_pages(session_id)
        
        analysis = {
            "session_id": session_id,
            "statistics": stats.data[0] if stats.data else {},
            "depth_distribution": depth_dist.data,
            "most_linked_pages": most_linked.data,
            "orphaned_pages": orphaned.data,
            "crawl_efficiency": self._calculate_crawl_efficiency(stats.data[0] if stats.data else {}),
        }
        
        return analysis
    
    def _calculate_crawl_efficiency(self, stats: Dict[str, Any]) -> Dict[str, float]:
        """Calculate efficiency metrics for a crawl session."""
        total_pages = stats.get('total_pages', 0)
        total_links = stats.get('total_links', 0)
        
        if total_pages == 0:
            return {"link_to_page_ratio": 0.0, "pages_per_depth": 0.0}
        
        link_to_page_ratio = total_links / total_pages if total_pages > 0 else 0.0
        
        depth_dist = stats.get('depth_distribution', [])
        avg_pages_per_depth = sum(d.get('pages', 0) for d in depth_dist) / len(depth_dist) if depth_dist else 0.0
        
        return {
            "link_to_page_ratio": link_to_page_ratio,
            "pages_per_depth": avg_pages_per_depth
        }


def create_graph_queries(session: Session) -> GraphQueries:
    """Factory function to create GraphQueries instance."""
    return GraphQueries(session)


def create_graph_analyzer(session: Session) -> GraphAnalyzer:
    """Factory function to create GraphAnalyzer instance."""
    queries = create_graph_queries(session)
    return GraphAnalyzer(queries)