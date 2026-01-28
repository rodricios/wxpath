# LangChain Integration

> **Warning:** pre-1.0.0 - APIs and contracts may change.

The `WXPathLoader` provides seamless integration between wxpath and LangChain, allowing you to use wxpath expressions as document loaders in LangChain RAG (Retrieval-Augmented Generation) pipelines.

## Location

```python
from wxpath.integrations.langchain.loader import WXPathLoader
```

## WXPathLoader

A LangChain document loader that executes wxpath expressions and converts results into LangChain `Document` objects.

```python
class WXPathLoader(BaseLoader):
    def __init__(self, expression: str, max_depth: int = 1)
```

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `expression` | str | - | wxpath expression to execute |
| `max_depth` | int | 1 | Maximum crawl depth for the wxpath query |

### Methods

#### _prep_doc

```python
def _prep_doc(self, item: (XPathMap | dict)) -> Document
```

Prepare a document from a wxpath result.

**Parameters:**
- `item`: The wxpath result (either an XPathMap or dict). Expected to be a dict or XPathMap with a `"text"` key for the document content. Any additional keys become metadata.

**Best practice** is to subclass the loader and override the _prep_doc method. For example:

```python
class MyWXPathLoader(WXPathLoader):
    def _prep_doc(self, item: (XPathMap | dict)) -> Document:
        # Custom processing here
        return super()._prep_doc(item)
```

#### lazy_load

```python
def lazy_load(self) -> Iterator[Document]
```

Lazy load documents from the wxpath query. Each item yielded by wxpath becomes a LangChain `Document`.

**Yields:** `Document` objects with:
- `page_content`: The text content extracted from the wxpath result (from the `"text"` key if present, otherwise string representation)
- `metadata`: Remaining keys from the wxpath result (e.g., `url`, `title`, etc.)

#### alazy_load

```python
async def alazy_load(self) -> AsyncIterator[Document]
```

Asynchronously lazy load documents from the wxpath query.

**Yields:** `Document` objects (same structure as `lazy_load`)

#### load

```python
def load(self) -> List[Document]
```

Load all documents from the wxpath query into memory.

**Returns:** List of `Document` objects

## Document Structure

The loader expects wxpath results to be maps (dictionaries) with a `"text"` key for the document content. Any additional keys become metadata.

Example wxpath expression structure:

```python
expression = """
url('https://example.com')
  /map{
    'text': string-join(//div[@class='content']//text()),
    'url': string(base-uri(.)),
    'title': //h1/text()
  }
"""
```

This produces `Document` objects with:
- `page_content`: The joined text from the content div
- `metadata`: `{"url": "...", "title": "..."}`

If no `"text"` key is present, the entire map is converted to a string for `page_content`.

## Examples

### Basic RAG Pipeline

A simple RAG example using wxpath to crawl documentation and create a vector store:

See: [`basic_rag.py`](https://github.com/rodricios/wxpath/blob/main/src/wxpath/integrations/langchain/examples/basic_rag.py)

This example demonstrates:
- Loading documents from Python argparse documentation
- Splitting documents into chunks
- Creating a vector store with embeddings
- Building a RAG chain for question answering

### Rolling Window RAG

An advanced example showing continuous crawling with a rolling buffer:

See: [`rolling_window_rag.py`](https://github.com/rodricios/wxpath/blob/main/src/wxpath/integrations/langchain/examples/rolling_window_rag.py)

This example demonstrates:
- Background crawling that continuously updates a document buffer
- Thread-safe document management with automatic eviction
- Real-time RAG queries against the latest crawled content
- Long-running crawler integration with LangChain

## Usage Example

```python
from wxpath.integrations.langchain.loader import WXPathLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

# Load documents using wxpath
loader = WXPathLoader(
    expression="""
    url('https://docs.python.org/3/library/')
      ///url(//a/@href[contains(., '/library/')])
      /map{
        'text': string-join(//div[@role='main']//text()),
        'source': string(base-uri(.))
      }
    """,
    max_depth=2
)

docs = loader.load()

# Split and embed
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
splits = text_splitter.split_documents(docs)

vectorstore = Chroma.from_documents(
    documents=splits,
    embedding=OllamaEmbeddings(model="nomic-embed-text")
)

# Use with retriever
retriever = vectorstore.as_retriever()
```

## Async Usage

For async workflows:

```python
import asyncio
from wxpath.integrations.langchain.loader import WXPathLoader

async def main():
    loader = WXPathLoader(
        expression="url('https://example.com')//div[@class='article']/map{'text': string(.), 'url': string(base-uri(.))}",
        max_depth=1
    )
    
    docs = []
    async for doc in loader.alazy_load():
        docs.append(doc)
        if len(docs) >= 100:
            break
    
    return docs

docs = asyncio.run(main())
```

END: Documentation generated by LLM - requires human review
