from lxml import etree, html

from wxpath import patches
from wxpath.util.logging import get_logger

log = get_logger(__name__)


def parse_html(content, base_url=None, response=None, **elem_kv_pairs) -> html.HtmlElement:
    elem = etree.HTML(content, parser=patches.html_parser_with_xpath3, base_url=base_url)
    if base_url:
        elem.getroottree().docinfo.URL = base_url  # make base-uri() work
        # Also set xml:base on the root element for XPath base-uri()
        elem.set("{http://www.w3.org/XML/1998/namespace}base", base_url)
        elem.base_url = base_url  # sets both attribute and doc-level URL
    
    if response:
        elem.response = response
        elem.getroottree().getroot().response = response
    # NOTE: some pages may have multiple root elements, i.e.
    # len(elem.itersiblings()) > 0 AND elem.getparent() is None. 
    # This breaks elementpath. If elem has siblings, recreate the 
    # root element and only the root element.
    if len(list(elem.itersiblings())) > 0:
        elem = detach_html_root(elem, base_url)

    for k, v in elem_kv_pairs.items():
        elem.set(k, str(v))
    return elem


def detach_html_root(elem, base_url=None):
    new_root = etree.HTML(
        etree.tostring(elem, encoding="utf-8"),
        parser=patches.html_parser_with_xpath3, 
        base_url=base_url
    )

    if base_url:
        new_root.getroottree().docinfo.URL = base_url
        new_root.set("{http://www.w3.org/XML/1998/namespace}base", base_url)
        new_root.base_url = base_url

    return new_root
