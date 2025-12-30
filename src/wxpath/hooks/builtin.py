import atexit
import json
import os
import queue
import threading
import time

from elementpath.serialization import XPathMap, XPathNode

from wxpath.util.logging import get_logger

log = get_logger(__name__)


class SerializeXPathMapAndNodeHook:
    """
    Serialize XPathMap and XPathNode objects to plain Python types.
    This is enabled by default (once this module is imported).
    """
    def post_extract(self, value):
        if isinstance(value, (list, tuple, set)):
            return type(value)(self.post_extract(v) for v in value)
        if isinstance(value, XPathMap):
            return {k: self.post_extract(v) for k, v in value.items()}
        if isinstance(value, XPathNode):
            return self.post_extract(value.obj)
        return value


class JSONLWriter:
    """
    Efficient writer that mirrors items to an NDJSON file.
    - Non-blocking: post_extract enqueues and returns immediately.
    - Background thread flushes to disk.
    - Skips non-JSONable values (e.g., raw HtmlElement) by default.
      Customize _jsonable() to change behavior.
    """
    def __init__(self, path=None):
        self.path = path or os.getenv("WXPATH_OUT", "extractions.ndjson")
        self._q: "queue.Queue[str]" = queue.Queue(maxsize=10000)
        self._written = 0
        self._dropped = 0
        self._stop = False
        self._t = threading.Thread(target=self._writer, name="wxpath-ndjson-writer", daemon=True)
        self._t.start()
        atexit.register(self._shutdown)

    # ---- hook API ----
    def post_extract(self, value):
        js = self._jsonable(value)
        if js is not None:
            line = json.dumps(js, ensure_ascii=False, separators=(",", ":"))
            try:
                self._q.put_nowait(line)
            except queue.Full:
                self._dropped += 1
                if self._dropped in (1, 100, 1000) or self._dropped % 10000 == 0:
                    log.warning("NDJSON queue full; dropping items",
                                extra={"dropped": self._dropped, "written": self._written})
        return value  # always pass-through

    # ---- internals ----
    def _writer(self):
        # Open lazily to avoid creating files when nothing is produced.
        f = None
        try:
            last_flush = time.time()
            while not self._stop or not self._q.empty():
                try:
                    line = self._q.get(timeout=0.5)
                except queue.Empty:
                    line = None
                if line is not None:
                    if f is None:
                        f = open(self.path, "a", buffering=1, encoding="utf-8")  # line-buffered
                    f.write(line)
                    f.write("\n")
                    self._written += 1
                # periodic flush guard for OS buffers even with line buffering
                if f and (time.time() - last_flush) > 1.0:
                    f.flush()
                    last_flush = time.time()
        finally:
            if f:
                f.flush()
                f.close()
            if self._dropped:
                log.warning("NDJSON writer finished with drops",
                            extra={"dropped": self._dropped, "written": self._written})

    def _shutdown(self):
        self._stop = True
        if self._t.is_alive():
            self._t.join(timeout=2)

    def _jsonable(self, v):
        # Keep it conservative: only write JSON-friendly shapes by default.
        # You can relax this if you want to serialize HtmlElement metadata, etc.
        if v is None or isinstance(v, (bool, int, float, str, list, dict)):
            return v
        # Handle common wxpath types gently:
        # - WxStr: stringify
        if v.__class__.__name__ == "WxStr":
            return str(v)
        # - lxml HtmlElement: record minimal metadata instead of the whole DOM
        base_url = getattr(v, "base_url", None)
        tag = getattr(v, "tag", None)
        if base_url or tag:
            return {"_element": tag, "url": base_url}
        return None  # skip unknowns
    
    
NDJSONWriter = JSONLWriter