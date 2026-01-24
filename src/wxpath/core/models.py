from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple


@dataclass(slots=True)
class CrawlTask:
    """A unit of work for the crawler."""
    elem: Any
    url: str
    segments: List[Tuple[str, str]]
    depth: int
    backlink: Optional[str] = None
    base_url: Optional[str] = None
    
    # Priority for the queue (lower number = higher priority)
    # Useful if you want Depth-First behavior in a shared queue
    priority: int = field(default=0)

    def __post_init__(self):
        # Automatically sync priority with depth for BFS behavior
        self.priority = self.depth

    def __lt__(self, other):
        return self.priority < other.priority

    def __iter__(self):
        return iter((self.elem, self.segments, self.depth, self.backlink))


@dataclass(slots=True)
class Intent:
    pass


@dataclass(slots=True)
class Result(Intent):
    """A container for an extracted item or error."""
    value: Any
    url: str
    depth: int
    error: Optional[Exception] = None
    backlink: Optional[str] = None


@dataclass(slots=True)
class CrawlIntent(Intent):
    url: str             # "I found this link"
    next_segments: list  # "Here is what to do next if you go there"


@dataclass(slots=True)
class ProcessIntent(Intent):
    elem: Any
    next_segments: list


@dataclass(slots=True)
class InfiniteCrawlIntent(ProcessIntent):
    pass


@dataclass(slots=True)
class ExtractIntent(ProcessIntent):
    """TODO: May be redundant with ProcessIntent?"""
    pass


@dataclass(slots=True)
class CrawlFromAttributeIntent(ProcessIntent):
    pass


@dataclass(slots=True)
class DataIntent(Intent):
    value: Any