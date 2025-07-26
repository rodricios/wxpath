# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

wxpath is an extended XPath engine for Python that enables declarative web crawling. It allows XPath expressions to traverse multiple HTML pages using a custom `url(...)` operator, combining familiar XPath syntax with recursive web navigation.

## Common Commands

### Development Setup
```bash
pip install -e .
```

### Testing
```bash
pytest                    # Run all tests
pytest tests/test_core.py # Run specific test file
pytest -v                 # Verbose output
```

### Package Management
The project uses pyproject.toml for configuration. Dependencies are managed through:
- Core dependencies: requests>=2.0, lxml>=4.0
- Test dependencies: pytest>=7.0

## Architecture

### Core Components

**wxpath/core.py** - Main processing engine containing:
- `parse_wxpath_expr()` - Parses wxpath expressions into segments
- `evaluate_wxpath_bfs_iter()` - BFS iterator for evaluating wxpath expressions
- `fetch_html()`, `parse_html()` - HTTP and HTML processing utilities
- `make_links_absolute()` - URL resolution for crawling

**wxpath/models.py** - Data models:
- `WxElement` - Wrapper for HTML elements with crawling context
- `WxStr` - String wrapper that maintains base URL context
- `Task` - Represents crawling tasks in the BFS queue

**wxpath/patches.py** - HTML element representation patches

### Key Patterns

The library uses a BFS (breadth-first search) approach for web crawling with a task queue system. The `url()` operator in XPath expressions triggers HTTP requests and page transitions. Results maintain context (base URLs) through wrapper classes to enable further traversal.

### Example Usage Pattern
```python
import wxpath

# Parse wxpath expression with url() operators
segments = wxpath.core.parse_wxpath_expr(path_expr)

# Evaluate with BFS traversal and depth limiting
for result in wxpath.core.evaluate_wxpath_bfs_iter(None, segments, max_depth=2):
    # Process crawled results
    pass
```

## Neo4j Graph Database Extension

The project includes a Neo4j integration for storing and analyzing crawled web data as a graph.

### Setup and Configuration

**Docker Environment:**
```bash
# Start Neo4j database
docker-compose up neo4j

# Or run full development environment
docker-compose --profile dev up
```

**Environment Variables:**
```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
WXPATH_PIPELINE_ENABLED=true
```

### Graph Data Model

**Nodes:**
- `Page`: Web pages with URL, title, depth, content hash
- `Element`: Extracted HTML elements with XPath, text, attributes
- `CrawlSession`: Crawl sessions with expression, depth, statistics

**Relationships:**
- `LINKS_TO`: Page → Page (navigation links)
- `CONTAINS`: Page → Element (extracted content)
- `PART_OF`: Page/Element → CrawlSession (session membership)

### Usage Examples

**Basic crawling with graph storage:**
```python
from wxpath import wxpath_with_graph

# Crawl and automatically store in graph database
results = wxpath_with_graph(
    elem=None,
    path_expr="url('https://example.com')//a/@href",
    max_depth=2,
    enable_graph=True
)
```

**Session management:**
```python
from wxpath import with_graph_integration

with with_graph_integration("url('https://example.com')//a/@href", max_depth=2) as session_id:
    # Regular wxpath calls will be stored in graph
    results = wxpath.core.evaluate_wxpath_bfs_iter(None, segments, max_depth=2)
```

**Graph analysis:**
```python
from wxpath.graph_queries import create_graph_queries, create_graph_analyzer
from wxpath.neo4j_extension import get_global_pipeline

pipeline = get_global_pipeline()
with pipeline.connection.session() as db_session:
    queries = create_graph_queries(db_session)
    analyzer = create_graph_analyzer(db_session)
    
    # Get crawl sessions
    sessions = queries.get_crawl_sessions(limit=10)
    
    # Analyze a session
    analysis = analyzer.analyze_crawl_session(session_id)
```

### Key Components

- **wxpath/neo4j_extension.py**: Main pipeline for graph storage
- **wxpath/graph_models.py**: Pydantic models for graph data
- **wxpath/graph_queries.py**: Pre-built queries and analysis tools
- **wxpath/graph_integration.py**: Integration with core wxpath
- **wxpath/config.py**: Configuration management
- **examples/graph_database_example.py**: Comprehensive usage examples