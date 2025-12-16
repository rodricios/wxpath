
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
