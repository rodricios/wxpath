
# wxpath

**wxpath** is an extended XPath engine for Python that enables declarative web crawling by allowing XPath expressions to seamlessly follow links and traverse multiple HTML pages using a custom `url(...)` operator. It combines familiar XPath syntax with recursive web navigation for advanced data extraction workflows.

## Features

- **Extended XPath Syntax**: Use `url()` operators within XPath expressions to follow links
- **BFS Web Crawling**: Breadth-first search traversal of web pages with depth control
- **Infinite Crawling**: `///url(@href)` syntax for recursive link discovery
- **Graph Database Integration**: Optional Neo4j integration to preserve crawling relationships
- **Declarative Approach**: No boilerplate - express complex crawling logic in single expressions

## Quick Start

### Basic Usage

```python
import wxpath

# Simple page fetch and XPath
results = wxpath.wxpath(None, "url('https://example.com')//h1/text()", depth=1)

# Follow links and extract data
path_expr = "url('https://example.com')//a/url(@href)//title/text()"
segments = wxpath.core.parse_wxpath_expr(path_expr)
for result in wxpath.core.evaluate_wxpath_bfs_iter(None, segments, max_depth=2):
    print(result)
```

### Graph Database Integration

Store crawled data and relationships in Neo4j for analysis:

```python
from wxpath import wxpath_with_graph

# Crawl with automatic graph storage
results = wxpath_with_graph(
    elem=None,
    path_expr="url('https://example.com')///url(@href)",
    max_depth=2,
    enable_graph=True
)
```

## Installation

```bash
pip install -e .
```

### Neo4j Setup (Optional)

For graph database features, start Neo4j using Docker:

```bash
# Start Neo4j in background
docker-compose up neo4j -d

# View logs
docker-compose logs neo4j

# Stop when done
docker-compose down
```

Neo4j will be available at:
- **Web Interface**: http://localhost:7474
- **Bolt Connection**: bolt://localhost:7687  
- **Default Credentials**: neo4j/password

Configure environment variables in `.env`:
```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
WXPATH_PIPELINE_ENABLED=true
```

## Syntax Reference

### URL Operators

- `url('https://example.com')` - Fetch a specific URL
- `//a/url(@href)` - Follow href attributes from anchor tags  
- `///url(@href)` - Infinite crawl following all links recursively

### Examples

```python
# Basic page crawling
"url('https://news.ycombinator.com')//a[@class='storylink']/text()"

# Multi-hop link following  
"url('https://example.com')//a/url(@href)//h1/text()"

# Infinite crawling with depth limit
"url('https://example.com')///url(@href)"  # max_depth controls recursion
```

## Graph Database Features

When enabled, wxpath automatically stores:

### Node Types
- **Page**: Web pages with URL, title, content hash, fetch timestamp
- **Element**: Extracted HTML elements with XPath, text, attributes  
- **CrawlSession**: Crawl sessions with expression, depth, statistics

### Relationships
- **LINKS_TO**: Page → Page (discovered links)
- **CONTAINS**: Page → Element (extracted content)
- **PART_OF**: Page/Element → CrawlSession (session membership)

### Graph Analysis

```python
from wxpath.graph_queries import create_graph_queries, create_graph_analyzer
from wxpath.neo4j_extension import get_global_pipeline

pipeline = get_global_pipeline()
with pipeline.connection.session() as session:
    queries = create_graph_queries(session)
    analyzer = create_graph_analyzer(session)
    
    # Get crawl sessions
    sessions = queries.get_crawl_sessions(limit=10)
    
    # Analyze session data
    analysis = analyzer.analyze_crawl_session(session_id)
```

## Architecture

- **Core Engine** (`wxpath/core.py`): BFS crawling with queue-based processing
- **Graph Integration** (`wxpath/graph_integration.py`): Event-based graph storage
- **Neo4j Pipeline** (`wxpath/neo4j_extension.py`): Database operations and relationships
- **Data Models** (`wxpath/graph_models.py`): Pydantic models for graph data

## Configuration

See `CLAUDE.md` for detailed configuration options and development guidance.

## License

MIT