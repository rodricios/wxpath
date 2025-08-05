import pytest
from wxpath import hooks
from wxpath.core import parser, helpers, sync

def _generate_fake_fetch_html(pages):
    def _fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")

    return _fake_fetch_html


HTML_A = b"""
<html lang="en"><body>
  <h1>The A Page</h1>
  <a href="http://b/">link</a>
  <a href="http://c/">link</a>
  <a href="http://d/">link</a>
</body></html>
"""

HTML_B = b"""
<html lang="en"><body>
  <h1>The B Page</h1>
</body></html>
"""

HTML_C = b"""
<html lang="en"><body>
  <h1>The C Page</h1>
</body></html>
"""

HTML_D = b"""
<html lang="en"><body>
  <h1>The D Page</h1>
</body></html>
"""


@pytest.fixture(autouse=True)
def clear_hooks():
    # Clear hooks before each test
    hooks._global_hooks.clear()
    yield
    hooks._global_hooks.clear()


# def test_pre_fetch_veto(monkeypatch):
#     """Hook returning False from pre_fetch prevents fetching."""
#     class DenyAll:
#         def pre_fetch(self, ctx):
#             return False
#     hooks.register(DenyAll())

#     monkeypatch.setattr(core, "fetch_html", _generate_fake_fetch_html({"http://a/": HTML_A}))
#     expr = "url('http://a/')//h1/text()[0]"
#     segs = parser.parse_wxpath_expr(expr)
#     results = list(sync.evaluate_wxpath_bfs_iter(None, segs, max_depth=0))
#     assert results == []  # nothing fetched because vetoed


def test_post_fetch_mutation(monkeypatch):
    """post_fetch can rewrite the HTML before parse."""
    class RewriteTitle:
        def post_fetch(self, ctx, html_bytes):
            return html_bytes.replace(b"The A Page", b"Rewritten")

    hooks.register(RewriteTitle)
    monkeypatch.setattr(helpers, "fetch_html", _generate_fake_fetch_html({"http://a/": HTML_A}))
    expr = "url('http://a/')//h1/text()"
    segs = parser.parse_wxpath_expr(expr)
    
    val = list(sync.evaluate_wxpath_bfs_iter(None, segs, max_depth=0))[0]
    assert str(val) == "Rewritten"
    
def test_post_fetch_prunes_branch(monkeypatch):
    """post_fetch returning None stops branch traversal."""
    class Prune:
        def post_fetch(self, ctx, html_bytes):
            if b"The B Page" in html_bytes:
                return None
            return html_bytes

    hooks.register(Prune)
    monkeypatch.setattr(helpers, "fetch_html", _generate_fake_fetch_html({
        "http://a/": HTML_A,
        "http://b/": HTML_B,
        "http://c/": HTML_C,
        "http://d/": HTML_D,
        }))
    expr = "url('http://a/')///url(@href)"
    segs = parser.parse_wxpath_expr(expr)
    results = list(sync.evaluate_wxpath_bfs_iter(None, segs, max_depth=1))
    assert [e.base_url for e in results] == [
        'http://c/',
        'http://d/',
        ]


def test_post_parse_prunes_branch(monkeypatch):
    """post_parse returning None stops branch traversal."""
    class Prune:
        def post_parse(self, ctx, elem):
            return None  # drop entire branch

    hooks.register(Prune)
    monkeypatch.setattr(helpers, "fetch_html", _generate_fake_fetch_html({"http://a/": HTML_A}))
    expr = "url('http://a/')///url(@href)"
    segs = parser.parse_wxpath_expr(expr)
    results = list(sync.evaluate_wxpath_bfs_iter(None, segs, max_depth=1))
    assert results == []  # nothing because branch stopped


# def test_pre_queue_veto(monkeypatch):
#     """pre_queue can block discovered links."""
#     class BlockB:
#         def pre_queue(self, ctx, url):
#             return not url.startswith("http://b/")

#     hooks.register(BlockB())
#     monkeypatch.setattr(core, "fetch_html", _generate_fake_fetch_html({"http://a/": HTML_A, "http://b/": HTML_B}))
#     expr = "url('http://a/')///url(@href)"
#     segs = parser.parse_wxpath_expr(expr)
#     # Should not fetch B because vetoed, so result list empty
#     results = list(sync.evaluate_wxpath_bfs_iter(None, segs, max_depth=1))
#     assert results == []


# def test_post_extract_transforms(monkeypatch):
#     """post_extract can transform yielded values."""
#     class Upper:
#         def post_extract(self, value, ctx):
#             if isinstance(value, str):
#                 return value.upper()
#             if isinstance(value, dict) and "title" in value:
#                 value["title"] = value["title"].upper()
#             return value

#     hooks.register(Upper())
#     monkeypatch.setattr(core, "fetch_html", _generate_fake_fetch_html({"http://a/": HTML_A}))
#     expr = "url('http://a/')/{ title://h1/text()[0] }"
#     segs = parser.parse_wxpath_expr(expr)
#     obj = list(sync.evaluate_wxpath_bfs_iter(None, segs, max_depth=0))[0]
#     assert obj["title"] == "THE A PAGE"