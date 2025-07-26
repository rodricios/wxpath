"""
Example demonstrating wxpath with Neo4j graph database integration.

This example shows how to use wxpath to crawl websites and store
the results in a Neo4j graph database for later analysis.
"""

import os
import time
from wxpath import wxpath_with_graph, with_graph_integration
from wxpath.config import initialize_config, WxPathConfig, Neo4jConfig, PipelineConfig
from wxpath.neo4j_extension import create_graph_pipeline
from wxpath.graph_queries import create_graph_queries, create_graph_analyzer


def setup_environment():
    """Set up the environment for the example."""
    # Configure for local development
    os.environ['NEO4J_URI'] = 'bolt://localhost:7687'
    os.environ['NEO4J_USERNAME'] = 'neo4j'
    os.environ['NEO4J_PASSWORD'] = 'wxpath123'
    os.environ['WXPATH_PIPELINE_ENABLED'] = 'true'
    os.environ['WXPATH_PIPELINE_BATCH_SIZE'] = '50'
    
    # Initialize configuration
    config = initialize_config()
    print(f"Configuration loaded: Neo4j at {config.neo4j.uri}")
    return config


def basic_example():
    """Basic example of crawling with graph database storage."""
    print("\n=== Basic Graph Database Example ===")
    
    # Simple crawling with automatic graph storage
    expression = "url('https://httpbin.org/html')//a/@href"
    
    print(f"Crawling with expression: {expression}")
    results = wxpath_with_graph(
        elem=None,
        path_expr=expression,
        max_depth=1,
        enable_graph=True
    )
    
    print(f"Found {len(results)} results")
    for i, result in enumerate(results[:5]):  # Show first 5
        print(f"  {i+1}: {result}")


def context_manager_example():
    """Example using context manager for graph integration."""
    print("\n=== Context Manager Example ===")
    
    expression = "url('https://httpbin.org/links/5')//a/@href"
    
    with with_graph_integration(expression, max_depth=2) as session_id:
        print(f"Started crawl session: {session_id}")
        
        # Use regular wxpath - results will be automatically stored
        from wxpath import wxpath
        results = list(wxpath(None, expression, depth=2))
        
        print(f"Crawled {len(results)} pages/elements")
    
    print("Crawl session completed and data stored in graph database")


def advanced_analysis_example():
    """Example of analyzing crawled data using graph queries."""
    print("\n=== Advanced Analysis Example ===")
    
    # First, let's crawl some data
    expression = "url('https://httpbin.org/')//a/@href"
    
    with with_graph_integration(expression, max_depth=2) as session_id:
        print(f"Crawling with session: {session_id}")
        
        results = wxpath_with_graph(
            elem=None,
            path_expr=expression,
            max_depth=2,
            enable_graph=True
        )
        
        print(f"Crawled {len(results)} items")
        
        # Now let's analyze the data
        try:
            from wxpath.neo4j_extension import get_global_pipeline
            from wxpath.graph_queries import create_graph_queries, create_graph_analyzer
            
            pipeline = get_global_pipeline()
            if pipeline and pipeline.connection:
                with pipeline.connection.session() as db_session:
                    queries = create_graph_queries(db_session)
                    analyzer = create_graph_analyzer(db_session)
                    
                    # Get session statistics
                    print("\n--- Session Analysis ---")
                    analysis = analyzer.analyze_crawl_session(session_id)
                    print(f"Total pages: {analysis.get('statistics', {}).get('total_pages', 0)}")
                    print(f"Total elements: {analysis.get('statistics', {}).get('total_elements', 0)}")
                    print(f"Crawl efficiency: {analysis.get('crawl_efficiency', {})}")
                    
                    # Get depth distribution
                    print("\n--- Depth Distribution ---")
                    for depth_info in analysis.get('depth_distribution', []):
                        print(f"Depth {depth_info.get('depth', 0)}: {depth_info.get('pages', 0)} pages")
                    
                    # Get most linked pages
                    print("\n--- Most Linked Pages ---")
                    most_linked = queries.get_most_linked_pages(session_id, limit=3)
                    for page in most_linked.data:
                        print(f"  {page.get('url', 'N/A')} - {page.get('link_count', 0)} incoming links")
                    
        except Exception as e:
            print(f"Analysis error (likely because Neo4j is not running): {e}")


def custom_configuration_example():
    """Example of using custom configuration."""
    print("\n=== Custom Configuration Example ===")
    
    # Create custom configuration
    custom_config = WxPathConfig(
        neo4j=Neo4jConfig(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="wxpath123"
        ),
        pipeline=PipelineConfig(
            enabled=True,
            batch_size=25,
            store_content_hash=True,
            extract_page_text=True,
            max_text_length=5000
        )
    )
    
    print("Custom configuration:")
    print(f"  Batch size: {custom_config.pipeline.batch_size}")
    print(f"  Max text length: {custom_config.pipeline.max_text_length}")
    print(f"  Store content hash: {custom_config.pipeline.store_content_hash}")
    
    # Initialize with custom config
    initialize_config(custom_config)
    
    # Now use wxpath with the custom configuration
    expression = "url('https://httpbin.org/html')//title/text()"
    results = wxpath_with_graph(
        elem=None,
        path_expr=expression,
        max_depth=1,
        enable_graph=True
    )
    
    print(f"Results with custom config: {results}")


def manual_pipeline_example():
    """Example of manually managing the graph pipeline."""
    print("\n=== Manual Pipeline Management ===")
    
    try:
        # Create pipeline manually
        from wxpath.neo4j_extension import Neo4jConnection
        
        connection = Neo4jConnection(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="wxpath123"
        )
        
        pipeline = create_graph_pipeline(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="wxpath123",
            batch_size=100
        )
        
        # Start a session manually
        session_id = pipeline.start_crawl_session(
            wxpath_expression="url('https://httpbin.org/')//a/@href",
            max_depth=1,
            configuration={"manual": True, "example": "custom_settings"}
        )
        
        print(f"Started manual session: {session_id}")
        
        # Process some mock data
        from lxml import html
        from wxpath.models import Task
        
        html_content = "<html><head><title>Test</title></head><body><a href='/test'>Link</a></body></html>"
        elem = html.fromstring(html_content, base_url="https://example.com")
        task = Task(elem, [], 0, backlink="https://parent.com")
        
        # Process and store
        result = pipeline.process_page_result(elem, task, session_id)
        pipeline.store_crawl_result(result)
        
        print(f"Processed page: {result.page.url}")
        print(f"Extracted {len(result.elements)} elements")
        
        # End session
        stats = pipeline.end_crawl_session(session_id)
        print(f"Session ended. Stats: {stats}")
        
    except Exception as e:
        print(f"Manual pipeline example failed (likely Neo4j not running): {e}")


def query_examples():
    """Example of various graph queries."""
    print("\n=== Graph Query Examples ===")
    
    try:
        from wxpath.neo4j_extension import get_global_pipeline
        
        pipeline = get_global_pipeline()
        if pipeline and pipeline.connection:
            with pipeline.connection.session() as db_session:
                queries = create_graph_queries(db_session)
                
                print("--- Recent Crawl Sessions ---")
                sessions = queries.get_crawl_sessions(limit=3)
                for session in sessions.data:
                    print(f"  Session {session.get('session_id', 'N/A')[:8]}...")
                    print(f"    Expression: {session.get('expression', 'N/A')}")
                    print(f"    Pages: {session.get('total_pages', 0)}")
                
                if sessions.data:
                    session_id = sessions.data[0].get('session_id')
                    
                    print(f"\n--- Pages from Session {session_id[:8]}... ---")
                    pages = queries.get_session_pages(session_id)
                    for page in pages.data[:3]:  # Show first 3
                        print(f"  {page.get('url', 'N/A')}")
                        print(f"    Title: {page.get('title', 'N/A')}")
                        print(f"    Depth: {page.get('depth', 0)}")
        
    except Exception as e:
        print(f"Query examples failed (likely Neo4j not running): {e}")


def main():
    """Run all examples."""
    print("wxpath Neo4j Graph Database Integration Examples")
    print("=" * 50)
    
    # Setup
    config = setup_environment()
    
    # Check if Neo4j is available
    try:
        from wxpath.neo4j_extension import Neo4jConnection
        test_conn = Neo4jConnection(config.neo4j.uri, config.neo4j.username, config.neo4j.password)
        with test_conn.session():
            pass
        neo4j_available = True
        print("✓ Neo4j connection successful")
    except Exception as e:
        neo4j_available = False
        print(f"✗ Neo4j not available: {e}")
        print("\nTo run these examples:")
        print("1. Start Neo4j with Docker: docker-compose up neo4j")
        print("2. Or install Neo4j locally and start it")
        print("3. Ensure credentials match the configuration")
    
    if neo4j_available:
        print("\nRunning examples with live Neo4j connection...")
        
        # Run examples
        basic_example()
        context_manager_example()
        advanced_analysis_example()
        custom_configuration_example()
        manual_pipeline_example()
        query_examples()
        
        print("\n" + "=" * 50)
        print("All examples completed successfully!")
        print("Check Neo4j Browser at http://localhost:7474 to explore the graph data")
    else:
        print("\nSkipping examples due to Neo4j connection issues.")
        print("The code above shows how to use the graph database integration.")


if __name__ == "__main__":
    main()