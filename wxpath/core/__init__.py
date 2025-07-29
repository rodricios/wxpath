"""
Core wxpath functionality - pure XPath web crawling without external dependencies.
"""

from .engine import (
    wxpath,
    parse_wxpath_expr,
    evaluate_wxpath_bfs_iter,
    extract_arg_from_url_xpath_op,
    apply_to_crawler,
    wrap_strings
)
from .http import fetch_html, parse_html, make_links_absolute
from .models import WxElement, WxStr, Task
from . import patches  # Import to apply patches

__all__ = [
    'wxpath',
    'parse_wxpath_expr', 
    'evaluate_wxpath_bfs_iter',
    'extract_arg_from_url_xpath_op',
    'apply_to_crawler',
    'wrap_strings',
    'fetch_html',
    'parse_html', 
    'make_links_absolute',
    'WxElement',
    'WxStr', 
    'Task'
]