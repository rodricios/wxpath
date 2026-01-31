from typing import Iterator

from elementpath.xpath_tokens import XPathMap
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

import wxpath


class WXPathLoader(BaseLoader):
    """A LangChain loader for wxpath queries. 
    
    For more complex examples, see the examples directory.
    Best practice would be to subclass the loader and override the _prep_doc method.
    For example:
    ```python
    class MyWXPathLoader(WXPathLoader):
        def _prep_doc(self, item: (XPathMap | dict)) -> Document:
            # Custom processing here
            return super()._prep_doc(item)
    ```
    """
    
    def __init__(self, expression: str, max_depth: int = 1):
        self.expression = expression
        self.max_depth = max_depth

    def _prep_doc(self, item: (XPathMap | dict)) -> Document:
        
        if isinstance(item, dict):
            content = item.pop("text", str(item)) # Fallback if no "text" key
        else:
            content = item._map.pop("text", str(item._map)) # Fallback if no "text" key
            item = item._map

        return Document(
            page_content=content,
            metadata=item # Remaining keys go here (url, title, etc.)
        )

    def lazy_load(self) -> Iterator[Document]:
        """
        Lazy load documents from the wxpath query.
        Each item yielded by wxpath becomes a LangChain Document.
        """
        # wxpath_async_blocking_iter allows iteration in sync environments
        results = wxpath.wxpath_async_blocking_iter(
            self.expression, 
            max_depth=self.max_depth
        )

        for item in results:
            yield self._prep_doc(item)

    async def alazy_load(self):
        async for item in wxpath.wxpath_async(
            self.expression, 
            max_depth=self.max_depth
        ):
            yield self._prep_doc(item)