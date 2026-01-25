"""
Rolling Window RAG Example

This examples demonstrates how to use a rolling window of news articles as context.

More importantly, it demonstrates complex string cleanup, metadata extraction, and other
real-world challenges of building a RAG application.

This script assumes you have gemma3 installed and your machine is capable of running a 32k
token model.
"""
import asyncio
import datetime
import threading
from collections import deque
from operator import itemgetter
from typing import List

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from wxpath import wxpath_async

# If you have the cache dependency installed, you can enable it:
# wxpath.settings.CACHE_SETTINGS.enabled = True

# ------------------------------------------------------------------
# 1. The Rolling Buffer (The "Context Window")
# ------------------------------------------------------------------
class RollingNewsBuffer(BaseRetriever):
    capacity: int = 100
    
    # Define as PrivateAttrs so Pydantic ignores them for validation
    _buffer: deque
    _seen_urls: set 
    _lock: threading.Lock 

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._buffer = deque(maxlen=self.capacity)
        self._seen_urls = set()
        self._lock = threading.Lock()
    
    def add_document(self, doc: Document):
        """Thread-safe add with url cleanup on eviction."""
        with self._lock:
            # Check if we are about to evict an item (buffer full)
            if len(self._buffer) == self._buffer.maxlen:
                # We must manually find what is being removed to clean up seen_urls
                # Note: deque[0] is the one about to be popped when appending
                oldest_doc = self._buffer[0] 
                oldest_url = oldest_doc.metadata.get("url")
                if oldest_url in self._seen_urls:
                    self._seen_urls.remove(oldest_url)

            self._buffer.append(doc)
            self._seen_urls.add(doc.metadata["url"])

    def is_seen(self, url: str) -> bool:
        """Thread-safe check."""
        with self._lock:
            return url in self._seen_urls

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun = None
    ) -> List[Document]:
        """
        Thread-safe read.
        """
        with self._lock:
            # Create a snapshot list while locked to prevent iteration crash
            snapshot = list(self._buffer)
            
        print(f"📰 Context Retrieval: Returning {len(snapshot)} docs for query: {query}")
        return snapshot
    
# ------------------------------------------------------------------
# 2. The Background Crawler (The Producer)
# ------------------------------------------------------------------
async def continuous_crawl(buffer: RollingNewsBuffer):
    """
    Constantly crawls Newsweek and feeds the buffer.
    """
    print("🕷️  Crawler started...")
    
    # Example Expression: deep crawl of newsweek
    expression = """
    url('https://www.newsweek.com/')
      ///url(
          //a/@href[starts-with(., '/') or starts-with(., './') or contains(., 'newsweek.com')]
      )
      /map{
          'title': //h1/text()[1] ! string(.),
          'text': string-join(//article//p/text()),
          'url': string(base-uri(.)),
          'pubDate': //meta[@name='article:modified_time']/@content[1] ! string(.)
      }
    """

    # Infinite loop to restart crawl if it finishes, or run continuously
    while True:
        try:
            # We use the async generator to stream results as they are found
            async for item in wxpath_async(expression, max_depth=1):
                item = item._map
                url = item.get('url')
                # Check seen status safely before doing processing work
                if not url or buffer.is_seen(url):
                    continue

                # Convert wxpath dict to LangChain Document
                text_content = item.get('text', '')
                # Basic cleaning (optional)
                if isinstance(text_content, list):
                    text_content = " ".join(text_content)
                
                if not text_content: 
                    continue

                title = item.get('title')
                if not title:
                    title = ''

                if isinstance(title, list):
                    title = " ".join(title)

                pub_date = item.get('pubDate')
                if not pub_date:
                    pub_date = str(datetime.date.today())

                text_content = ("Title: " + title + 
                                "\nPublished: " + pub_date + "\n" + 
                                text_content)
    
                doc = Document(
                    page_content=text_content,
                    metadata={"title": item.get('title'), 
                              "url": item.get('url'), 
                              "pubDate": item.get('pubDate')}
                )
                
                # PUSH TO BUFFER (Oldest gets evicted automatically if full)
                buffer.add_document(doc)
                print(f"📰 Added: {title[:30]}... (Buffer size: {len(buffer._buffer)})")
                print(f"\tArticle text: {doc.page_content[:100]}...")
                print()
            # Rate limit slightly to be polite
            await asyncio.sleep(60) 
            
        except Exception as e:
            print(f"⚠️ Crawler error: {e}. Restarting in 10s...")
            await asyncio.sleep(10)


def debug_print_prompt(prompt_value):
    print("\n" + "="*40)
    print("📢 FULL PROMPT SENT TO LLM:")
    print("="*40)
    print(prompt_value.to_string()) # This prints the exact text
    print("="*40 + "\n")
    return prompt_value

if __name__ == "__main__":
    # Initialize the Rolling Buffer
    retriever = RollingNewsBuffer(capacity=100)

    # Start Crawler in a background thread so it doesn't block the Chat
    def start_background_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(continuous_crawl(retriever))

    crawler_loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_background_loop, args=(crawler_loop,), daemon=True)
    t.start()

    import time

    from langchain_core.prompts import ChatPromptTemplate
    from langchain_ollama import ChatOllama

    # Setup standard RAG chain
    llm = ChatOllama(model="gemma3", num_ctx=32768)
    prompt = ChatPromptTemplate.from_template(
        "Answer based ONLY on the following news:\n\n{context}\n\nQuestion: {question}\n\n"
        "DO NOT include generic Newsweek-administrative articles like 'Corrections', "
        "'Company Info', 'Subscribe', Opinions', 'Press Releases', 'Editorials', etc. in your "
        "analysis or answers. Answer the question using the non-Newsweek-related news provided. "
        "You will be penalized for including old or undated news in your answer. If asked for "
        "overviews or summaries, split news items into paragraphs and provide a summary of each "
        "news item."
    )
    
    def format_docs(docs):
        slice_of_news = "\n\n".join([d.page_content[:1000] for d in docs]) # Truncate for demo
        print(f"📰 Latest news char length: {len(slice_of_news)}")
        return slice_of_news

    chain = (
        {
            # FIX: Use itemgetter so retriever gets a string, not a dict
            "context": itemgetter("question") | retriever | format_docs, 
            "question": itemgetter("question")
        }
        | prompt
        | debug_print_prompt
        | llm
    )

    # Simulate querying constantly while buffer fills in background
    print("⏳ Waiting for crawler to gather some data...")
    time.sleep(10) 
    
    while True:
        query = input("Press Enter to ask about current news (or Ctrl+C to quit)...")
        print(f"\nQuery: {query}\nThinking... 🤔")
        response = chain.invoke({"question": query})
        print(response.content)