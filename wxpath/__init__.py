"""
wxpath - Extended XPath engine for Python with declarative web crawling.

This is the core wxpath package that provides XPath-based web crawling functionality.
For graph database integration, install with: pip install wxpath[graph]
"""

from .core import (
    wxpath,
    parse_wxpath_expr,
    evaluate_wxpath_bfs_iter,
    extract_arg_from_url_xpath_op,
    apply_to_crawler,
    wrap_strings,
    fetch_html,
    parse_html,
    make_links_absolute,
    WxElement,
    WxStr,
    Task
)

__version__ = "0.1.0"

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

# Try to provide backward compatibility warnings for graph functions
def _graph_function_warning(func_name):
    """Helper to create warning functions for moved graph functionality."""
    def wrapper(*args, **kwargs):
        import warnings
        warnings.warn(
            f"{func_name} has moved to wxpath.extensions.graph. "
            f"Please install graph dependencies with 'pip install wxpath[graph]' "
            f"and import from 'wxpath.extensions.graph import {func_name}'",
            DeprecationWarning,
            stacklevel=2
        )
        try:
            from .extensions.graph import wxpath_with_graph as _wxpath_with_graph
            from .extensions.graph import enable_graph_integration as _enable_graph_integration  
            from .extensions.graph import disable_graph_integration as _disable_graph_integration
            from .extensions.graph import with_graph_integration as _with_graph_integration
            
            func_map = {
                'wxpath_with_graph': _wxpath_with_graph,
                'enable_graph_integration': _enable_graph_integration,
                'disable_graph_integration': _disable_graph_integration,
                'with_graph_integration': _with_graph_integration
            }
            return func_map[func_name](*args, **kwargs)
        except ImportError as e:
            raise ImportError(
                f"Graph functionality requires additional dependencies. "
                f"Install with: pip install wxpath[graph]"
            ) from e
    return wrapper

# Provide backward compatibility for common graph functions
try:
    from .extensions.graph import (
        wxpath_with_graph,
        enable_graph_integration, 
        disable_graph_integration,
        with_graph_integration
    )
    # Add them to __all__ for backward compatibility
    __all__.extend([
        'wxpath_with_graph',
        'enable_graph_integration',
        'disable_graph_integration', 
        'with_graph_integration'
    ])
except ImportError:
    # Create warning stubs if graph extension not available
    wxpath_with_graph = _graph_function_warning('wxpath_with_graph')
    enable_graph_integration = _graph_function_warning('enable_graph_integration')
    disable_graph_integration = _graph_function_warning('disable_graph_integration')
    with_graph_integration = _graph_function_warning('with_graph_integration')
