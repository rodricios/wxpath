"""
Tests for wxpath Neo4j graph database extension.

This module contains tests for the graph models, pipeline, queries,
and integration functionality.
"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from lxml import html

from wxpath.extensions.graph.models import (
    PageNode, ElementNode, CrawlSessionNode, CrawlResult,
    LinksToRelationship, ContainsRelationship, PartOfRelationship,
    create_page_node, create_element_node, create_crawl_session_node
)
from wxpath.extensions.graph.pipeline import Neo4jConnection, GraphPipeline
from wxpath.extensions.graph.queries import GraphQueries, GraphAnalyzer
from wxpath.extensions.graph.integration import GraphIntegration
from wxpath.core.models import Task
from wxpath.extensions.graph.config import Neo4jConfig, PipelineConfig, GraphConfig


class TestGraphModels:
    """Test graph data models."""
    
    def test_create_page_node(self):
        """Test PageNode creation."""
        page = create_page_node(
            url="https://example.com",
            depth=0,
            title="Example Page"
        )
        
        assert page.url == "https://example.com"
        assert page.depth == 0
        assert page.title == "Example Page"
        assert page.node_type.value == "Page"
        assert isinstance(page.created_at, datetime)
    
    def test_create_element_node(self):
        """Test ElementNode creation."""
        element = create_element_node(
            xpath="//a[@href]",
            text_content="Click here",
            tag="a",
            attributes={"href": "/link"}
        )
        
        assert element.xpath == "//a[@href]"
        assert element.text_content == "Click here"
        assert element.tag == "a"
        assert element.attributes == {"href": "/link"}
        assert element.node_type.value == "Element"
    
    def test_create_crawl_session_node(self):
        """Test CrawlSessionNode creation."""
        session_id = str(uuid.uuid4())
        session = create_crawl_session_node(
            session_id=session_id,
            wxpath_expression="url('https://example.com')//a/@href",
            max_depth=2
        )
        
        assert session.session_id == session_id
        assert session.wxpath_expression == "url('https://example.com')//a/@href"
        assert session.max_depth == 2
        assert session.node_type.value == "CrawlSession"
    
    def test_links_to_relationship(self):
        """Test LinksToRelationship creation."""
        rel = LinksToRelationship(
            href="/page2",
            link_text="Next Page",
            discovered_at_depth=1
        )
        
        assert rel.href == "/page2"
        assert rel.link_text == "Next Page"
        assert rel.discovered_at_depth == 1
        assert rel.relationship_type.value == "LINKS_TO"
    
    def test_crawl_result(self):
        """Test CrawlResult creation."""
        page = create_page_node("https://example.com", 0)
        element = create_element_node("//title", "Example")
        
        result = CrawlResult(
            page=page,
            elements=[element],
            session_id="test-session",
            crawl_depth=0
        )
        
        assert result.page.url == "https://example.com"
        assert len(result.elements) == 1
        assert result.session_id == "test-session"
        assert result.crawl_depth == 0


class TestNeo4jConnection:
    """Test Neo4j connection management."""
    
    @patch('wxpath.neo4j_extension.GraphDatabase')
    def test_connection_creation(self, mock_graph_db):
        """Test Neo4j connection creation."""
        mock_driver = Mock()
        mock_session = Mock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_graph_db.driver.return_value = mock_driver
        
        conn = Neo4jConnection("bolt://localhost:7687", "neo4j", "password")
        driver = conn.connect()
        
        assert driver == mock_driver
        mock_graph_db.driver.assert_called_once_with(
            "bolt://localhost:7687",
            auth=("neo4j", "password"),
            max_connection_lifetime=30 * 60,
            max_connection_pool_size=50,
            connection_acquisition_timeout=60
        )
    
    @patch('wxpath.neo4j_extension.GraphDatabase')
    def test_connection_session_context(self, mock_graph_db):
        """Test Neo4j session context manager."""
        mock_driver = Mock()
        mock_session = Mock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_driver.session.return_value.__exit__.return_value = None
        mock_graph_db.driver.return_value = mock_driver
        
        conn = Neo4jConnection("bolt://localhost:7687", "neo4j", "password")
        
        with conn.session() as session:
            assert session == mock_session


class TestGraphPipeline:
    """Test graph pipeline functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_connection = Mock(spec=Neo4jConnection)
        self.mock_session = Mock()
        self.mock_connection.session.return_value.__enter__.return_value = self.mock_session
        self.mock_connection.session.return_value.__exit__.return_value = None
        
        self.pipeline = GraphPipeline(self.mock_connection, batch_size=10)
    
    def test_pipeline_initialization(self):
        """Test pipeline initialization."""
        assert self.pipeline.connection == self.mock_connection
        assert self.pipeline.batch_size == 10
        assert self.pipeline.current_session_id is None
    
    def test_initialize_database(self):
        """Test database initialization with constraints and indexes."""
        self.pipeline.initialize_database()
        
        # Should have called session.run multiple times for constraints and indexes
        assert self.mock_session.run.call_count > 0
        
        # Check that constraint and index queries were executed
        calls = [call[0][0] for call in self.mock_session.run.call_args_list]
        constraint_calls = [call for call in calls if 'CONSTRAINT' in call]
        index_calls = [call for call in calls if 'INDEX' in call]
        
        assert len(constraint_calls) > 0
        assert len(index_calls) > 0
    
    def test_start_crawl_session(self):
        """Test starting a crawl session."""
        session_id = self.pipeline.start_crawl_session(
            wxpath_expression="url('https://example.com')//a/@href",
            max_depth=2
        )
        
        assert session_id is not None
        assert self.pipeline.current_session_id == session_id
        assert session_id in self.pipeline._statistics
        
        # Should have created session node in database
        self.mock_session.run.assert_called()
        
        # Check the query contains session creation
        call_args = self.mock_session.run.call_args[0][0]
        assert "CREATE (s:CrawlSession" in call_args
    
    def test_end_crawl_session(self):
        """Test ending a crawl session."""
        # Start a session first
        session_id = self.pipeline.start_crawl_session(
            wxpath_expression="url('https://example.com')//a/@href",
            max_depth=2
        )
        
        # Reset mock for end session test
        self.mock_session.run.reset_mock()
        
        # End the session
        stats = self.pipeline.end_crawl_session(session_id)
        
        assert stats is not None
        assert stats.session_id == session_id
        assert self.pipeline.current_session_id is None
        
        # Should have updated session end time in database
        self.mock_session.run.assert_called()
        call_args = self.mock_session.run.call_args[0][0]
        assert "SET s.end_time" in call_args
    
    def test_process_page_result(self):
        """Test processing a page result."""
        # Create mock HTML element
        html_content = "<html><head><title>Test Page</title></head><body><a href='/link'>Link</a></body></html>"
        elem = html.fromstring(html_content, base_url="https://example.com")
        
        # Create task
        task = Task(elem, [], 0, backlink="https://parent.com")
        
        # Start session
        session_id = self.pipeline.start_crawl_session(
            wxpath_expression="url('https://example.com')//a/@href",
            max_depth=2
        )
        
        # Process result
        result = self.pipeline.process_page_result(elem, task, session_id)
        
        assert isinstance(result, CrawlResult)
        assert result.page.url == "https://example.com"
        assert result.page.title == "Test Page"
        assert result.page.depth == 0
        assert result.session_id == session_id
        assert len(result.elements) > 0  # Should have extracted elements
    
    def test_store_crawl_result(self):
        """Test storing a crawl result in Neo4j."""
        # Create test result
        page = create_page_node("https://example.com", 0, title="Test Page")
        element = create_element_node("//a", "Link", "a", {"href": "/link"})
        
        result = CrawlResult(
            page=page,
            elements=[element],
            session_id="test-session",
            crawl_depth=0
        )
        
        # Store result
        self.pipeline.store_crawl_result(result)
        
        # Should have made multiple database calls
        assert self.mock_session.run.call_count >= 3  # Page, element, session relationship
        
        # Check that page creation query was called
        calls = [call[0][0] for call in self.mock_session.run.call_args_list]
        page_calls = [call for call in calls if 'MERGE (p:Page' in call]
        element_calls = [call for call in calls if 'CREATE (e:Element' in call]
        
        assert len(page_calls) > 0
        assert len(element_calls) > 0


class TestGraphQueries:
    """Test graph query utilities."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_session = Mock()
        self.queries = GraphQueries(self.mock_session)
    
    def test_get_crawl_sessions(self):
        """Test getting crawl sessions."""
        # Mock query result
        mock_records = [
            Mock(data=lambda: {
                'session_id': 'session-1',
                'start_time': '2023-01-01T00:00:00',
                'expression': "url('https://example.com')//a/@href",
                'max_depth': 2,
                'total_pages': 10
            })
        ]
        self.mock_session.run.return_value = mock_records
        
        result = self.queries.get_crawl_sessions(limit=5)
        
        assert len(result.data) == 1
        assert result.data[0]['session_id'] == 'session-1'
        assert result.total_records == 1
        
        # Check query was called with correct parameters
        self.mock_session.run.assert_called_once()
        call_args = self.mock_session.run.call_args
        assert 'MATCH (s:CrawlSession)' in call_args[0][0]
        assert call_args[1]['limit'] == 5
    
    def test_get_session_pages(self):
        """Test getting pages from a session."""
        mock_records = [
            Mock(data=lambda: {
                'url': 'https://example.com/page1',
                'title': 'Page 1',
                'depth': 0
            }),
            Mock(data=lambda: {
                'url': 'https://example.com/page2',
                'title': 'Page 2',
                'depth': 1
            })
        ]
        self.mock_session.run.return_value = mock_records
        
        result = self.queries.get_session_pages('session-1')
        
        assert len(result.data) == 2
        assert result.data[0]['url'] == 'https://example.com/page1'
        assert result.data[1]['depth'] == 1
        
        # Check query parameters
        call_args = self.mock_session.run.call_args
        assert call_args[1]['session_id'] == 'session-1'
    
    def test_get_page_links(self):
        """Test getting links from a page."""
        mock_records = [
            Mock(data=lambda: {
                'target_url': 'https://example.com/linked',
                'link_text': 'Linked Page',
                'depth': 1
            })
        ]
        self.mock_session.run.return_value = mock_records
        
        result = self.queries.get_page_links('https://example.com')
        
        assert len(result.data) == 1
        assert result.data[0]['target_url'] == 'https://example.com/linked'
        
        call_args = self.mock_session.run.call_args
        assert call_args[1]['url'] == 'https://example.com'


class TestGraphAnalyzer:
    """Test graph analyzer functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_queries = Mock(spec=GraphQueries)
        self.analyzer = GraphAnalyzer(self.mock_queries)
    
    def test_analyze_crawl_session(self):
        """Test comprehensive session analysis."""
        # Mock query results
        from wxpath.graph_queries import QueryResult
        
        stats_data = [{
            'session_id': 'session-1',
            'total_pages': 10,
            'total_links': 25,
            'depth_distribution': [{'depth': 0, 'pages': 1}, {'depth': 1, 'pages': 9}]
        }]
        
        self.mock_queries.get_session_statistics.return_value = QueryResult(
            data=stats_data, query="", total_records=1
        )
        self.mock_queries.get_depth_distribution.return_value = QueryResult(
            data=[{'depth': 0, 'pages': 1}, {'depth': 1, 'pages': 9}], 
            query="", total_records=2
        )
        self.mock_queries.get_most_linked_pages.return_value = QueryResult(
            data=[], query="", total_records=0
        )
        self.mock_queries.get_orphaned_pages.return_value = QueryResult(
            data=[], query="", total_records=0
        )
        
        analysis = self.analyzer.analyze_crawl_session('session-1')
        
        assert analysis['session_id'] == 'session-1'
        assert 'statistics' in analysis
        assert 'depth_distribution' in analysis
        assert 'crawl_efficiency' in analysis
        
        # Check efficiency calculation
        efficiency = analysis['crawl_efficiency']
        assert 'link_to_page_ratio' in efficiency
        assert efficiency['link_to_page_ratio'] == 2.5  # 25 links / 10 pages


class TestGraphIntegration:
    """Test graph integration functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_pipeline = Mock(spec=GraphPipeline)
        self.integration = GraphIntegration(self.mock_pipeline)
    
    def test_enable_integration(self):
        """Test enabling graph integration."""
        self.mock_pipeline.start_crawl_session.return_value = "session-123"
        
        session_id = self.integration.enable(
            wxpath_expression="url('https://example.com')//a/@href",
            max_depth=2
        )
        
        assert session_id == "session-123"
        assert self.integration.is_enabled()
        assert self.integration._current_session_id == "session-123"
        
        self.mock_pipeline.start_crawl_session.assert_called_once_with(
            wxpath_expression="url('https://example.com')//a/@href",
            max_depth=2,
            configuration=None
        )
    
    def test_disable_integration(self):
        """Test disabling graph integration."""
        # Enable first
        self.mock_pipeline.start_crawl_session.return_value = "session-123"
        self.integration.enable("url('https://example.com')//a/@href", 2)
        
        # Mock end session
        mock_stats = Mock()
        mock_stats.dict.return_value = {'total_pages_crawled': 5}
        self.mock_pipeline.end_crawl_session.return_value = mock_stats
        
        # Disable
        stats = self.integration.disable()
        
        assert stats is not None
        assert stats['total_pages_crawled'] == 5
        assert not self.integration.is_enabled()
        assert self.integration._current_session_id is None
        
        self.mock_pipeline.end_crawl_session.assert_called_once()
    
    def test_process_result(self):
        """Test processing a crawl result."""
        # Enable integration
        self.mock_pipeline.start_crawl_session.return_value = "session-123"
        self.integration.enable("url('https://example.com')//a/@href", 2)
        
        # Create mock element and task
        elem = Mock()
        task = Mock(spec=Task)
        
        # Mock pipeline methods
        mock_result = Mock(spec=CrawlResult)
        self.mock_pipeline.process_page_result.return_value = mock_result
        
        # Process result
        success = self.integration.process_result(elem, task)
        
        assert success is True
        self.mock_pipeline.process_page_result.assert_called_once_with(
            elem, task, "session-123"
        )
        self.mock_pipeline.store_crawl_result.assert_called_once_with(mock_result)


class TestConfiguration:
    """Test configuration management."""
    
    def test_neo4j_config_from_env(self):
        """Test Neo4j configuration from environment."""
        with patch.dict('os.environ', {
            'NEO4J_URI': 'bolt://test:7687',
            'NEO4J_USERNAME': 'testuser',
            'NEO4J_PASSWORD': 'testpass'
        }):
            config = Neo4jConfig.from_env()
            
            assert config.uri == 'bolt://test:7687'
            assert config.username == 'testuser'
            assert config.password == 'testpass'
    
    def test_pipeline_config_from_env(self):
        """Test pipeline configuration from environment."""
        with patch.dict('os.environ', {
            'WXPATH_PIPELINE_ENABLED': 'false',
            'WXPATH_PIPELINE_BATCH_SIZE': '50'
        }):
            config = PipelineConfig.from_env()
            
            assert config.enabled is False
            assert config.batch_size == 50
    
    def test_full_config_from_env(self):
        """Test full configuration from environment."""
        config = WxPathConfig.from_env()
        
        assert isinstance(config.neo4j, Neo4jConfig)
        assert isinstance(config.pipeline, PipelineConfig)
        assert isinstance(config.logging, LoggingConfig)
    
    def test_config_to_dict(self):
        """Test configuration serialization."""
        config = WxPathConfig()
        config_dict = config.to_dict()
        
        assert 'neo4j' in config_dict
        assert 'pipeline' in config_dict
        assert 'logging' in config_dict
        
        # Password should be hidden
        assert config_dict['neo4j']['password'] == '***'


if __name__ == '__main__':
    pytest.main([__file__])