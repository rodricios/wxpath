# Core Module

> **Warning:** pre-1.0.0 - APIs and contracts may change.

The `wxpath.core` module contains the expression parser, execution engine, and data models.

## Submodules

| Module | Description |
|--------|-------------|
| [engine](engine.md) | Main execution engine (`WXPathEngine`) |
| TODO: parser | Pratt-style expression parser |
| TODO: models | Data models and intent types |
| [ops](ops.md) | Operation handlers and registry |

## Quick Import

```python
from wxpath.core.runtime import WXPathEngine
from wxpath.core import parser
from wxpath.core.models import CrawlTask, CrawlIntent, DataIntent
from wxpath.core.ops import get_operator
```

## Architecture

```
Expression String
            │
            ▼ 
        ┌────────┐
        │ Parser │  → AST (Segments)
        └────────┘
            │
            ▼
        ┌────────┐                  ┌─────────┐
        │ Engine │  → CrawlTasks →  │ Crawler │ 
    ┌── │        │  ← HTML Body  ←  │         │
    │   └────────┘                  └─────────┘
    │      │  ▲  
    │      ▼  | Intents
    │   ┌─────────┐
    │   │   Ops   │  → Executes segment operations
    │   └─────────┘
    │       
    │   ╭─────────╮
    └─▶ │ Results │  
        ╰─────────╯
```

The parser converts expressions to an AST. The engine processes the AST with a BFS-like crawl queue. Operations handle each segment type and emit intents. Intents drive the next processing step (crawl, extract, or yield data).
