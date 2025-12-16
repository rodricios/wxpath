import requests
from typing import Optional
from urllib.parse import urljoin

from lxml import etree, html

from wxpath import patches
from wxpath.hooks import get_hooks, FetchContext
from wxpath.util.logging import get_logger

log = get_logger(__name__)


def _count_ops_with_url(segments):
    return len([op for op, _ in segments if op.startswith('url')])


def _ctx(url: str, backlink: str, depth: int, segments: list, seen_urls: set) -> FetchContext:
    return FetchContext(url, backlink, depth, seen_urls)


def _make_links_absolute(links, base_url):
    """
    Convert relative links to absolute links based on the base URL.

    Args:
        links (list): List of link strings.
        base_url (str): The base URL to resolve relative links against.

    Returns:
        List of absolute URLs.
    """
    if base_url is None:
        raise ValueError("base_url must not be None when making links absolute.")
    return [urljoin(base_url, link) for link in links if link]


def _get_absolute_links_from_elem_and_xpath(elem, xpath):
    base_url = getattr(elem, 'base_url', None)
    return _make_links_absolute(elem.xpath3(xpath), base_url)


def parse_html(content, base_url=None, **elem_kv_pairs) -> html.HtmlElement:
    elem = etree.HTML(content, parser=patches.html_parser_with_xpath3, base_url=base_url)
    if base_url:
        elem.getroottree().docinfo.URL = base_url  # make base-uri() work
        # Also set xml:base on the root element for XPath base-uri()
        elem.set("{http://www.w3.org/XML/1998/namespace}base", base_url)
        elem.base_url = base_url  # sets both attribute and doc-level URL
    
    for k, v in elem_kv_pairs.items():
        elem.set(k, str(v))
    return elem


def fetch_html(url):
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.content


def _load_page_as_element(
    url: str,
    backlink: Optional[str],
    depth: int, 
    seen_urls: set[str],
    curr_depth: int = -1,
    op: str = "",
) -> html.HtmlElement:
    """
    Fetches the URL, parses it into an lxml Element, sets backlink/depth,
    and runs any HTML-postprocessing handlers.
    """
    content = fetch_html(url)
    
    for hook in get_hooks():
        _content = getattr(hook, 'post_fetch', lambda _, content: content)\
                    (_ctx(url, backlink, depth, [], seen_urls), content)

        if not _content:
            return None
        content = _content
    
    # elem = html.fromstring(content, base_url=url)  # type: html.HtmlElement
    elem = parse_html(content, base_url=url)
    elem.set("backlink", backlink)
    elem.set("depth", str(depth))
    seen_urls.add(url)
    
    log.debug("fetched", extra={"url": url, "depth": depth, "backlink": backlink, "op": op})
    return elem