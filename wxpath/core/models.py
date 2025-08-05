from typing import NamedTuple


class WxStr(str):
    def __new__(cls, value, base_url=None, depth=-1):
        obj = super().__new__(cls, value)
        obj.base_url = base_url
        obj.depth = depth
        return obj

    def __repr__(self):
        return f"WxStr({super().__repr__()}, base_url={self.base_url!r}, depth={self.depth})"


class Task:
    def __init__(self, elem, segments, depth, backlink=None):
        self.elem = elem
        self.segments = segments
        self.depth = depth
        self.backlink = backlink
    
    def __repr__(self):
        return f"Task(elem={self.elem}, segments={self.segments}, depth={self.depth}, backlink={self.backlink})"
    
    def __iter__(self):
        return iter((self.elem, self.segments, self.depth, self.backlink))


class Segment(NamedTuple):
    op: str
    value: str