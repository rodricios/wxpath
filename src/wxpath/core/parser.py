"""
This module contains mainly two kinds of functions: 

1. functions for parsing wxpath expressions.
2. functions for extracting information from wxpath expressions or subexpressions.

"""
import re
from typing import NamedTuple


class Segment(NamedTuple):
    op: str
    value: str


def _url_inf_filter_expr(url_op_and_arg):
    url_op_arg = _extract_arg_from_url_xpath_op(url_op_and_arg)
    if url_op_arg.startswith('@'):
        return ".//" + url_op_arg
    else:
        return url_op_arg


def _extract_arg_from_url_xpath_op(url_subsegment):
    match = re.search(r"url\((.+)\)", url_subsegment)
    if not match:
        raise ValueError(f"Invalid url() segment: {url_subsegment}")
    return match.group(1).strip("'\"")  # Remove surrounding quotes if any


def _split_top_level(s: str, sep: str = ',') -> list[str]:
    """
    Split *s* on *sep* but only at the top-level (i.e. not inside (), [] or {}).

    This is needed so we can correctly split key/value pairs inside an object
    segment even when the value itself contains commas or braces.
    """
    parts, depth, current = [], 0, []
    opening, closing = "([{", ")]}"

    for ch in s:
        if ch in opening:
            depth += 1
        elif ch in closing:
            depth -= 1

        if ch == sep and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(ch)

    parts.append(''.join(current))
    return parts


def _parse_object_mapping(segment: str) -> dict[str, str]:
    # Trim the leading '/{' or '{' and the trailing '}'.
    if segment.startswith('/{'):
        inner = segment[2:-1]
    else:
        inner = segment[1:-1]

    mapping = {}
    for part in _split_top_level(inner):
        if not part.strip():
            continue
        key, expr = part.split(':', 1)
        mapping[key.strip()] = expr.strip()
    return mapping


def parse_wxpath_expr(path_expr):
    # remove newlines
    path_expr = path_expr.replace('\n', '')
    partitions = []  # type: list[str]
    i = 0
    n = len(path_expr)
    while i < n:
        # Detect object-construction partitions:  '/{ ... }'  or  '{ ... }'
        if path_expr[i] == '{' or (path_expr[i] == '/' and i + 1 < n and path_expr[i + 1] == '{'):
            seg_start = i
            # Skip the optional leading '/'
            if path_expr[i] == '/':
                i += 1
            # We are now at the opening '{'
            brace_depth = 1
            i += 1
            while i < n and brace_depth > 0:
                if path_expr[i] == '{':
                    brace_depth += 1
                elif path_expr[i] == '}':
                    brace_depth -= 1
                i += 1
            partitions.append(path_expr[seg_start:i])  # include leading '/' if present
            continue
        # Detect ///url(, //url(, /url(, or url(
        match = re.match(r'/{0,3}url\(', path_expr[i:])
        if match:
            seg_start = i
            i += match.end()  # Move past the matched "url("
            paren_depth = 1
            while i < n and paren_depth > 0:
                if path_expr[i] == '(':
                    paren_depth += 1
                elif path_expr[i] == ')':
                    paren_depth -= 1
                i += 1
            partitions.append(path_expr[seg_start:i])
        else:
            # Grab until the next /url(
            next_url = re.search(r'/{0,3}url\(', path_expr[i:])
            next_pos = next_url.start() + i if next_url else n
            if i != next_pos:
                partitions.append(path_expr[i:next_pos])
            i = next_pos

    segments = []  # type: list[Segment]
    for s in partitions:
        s = s.strip()
        if not s:
            continue
        if s.startswith('url("') or s.startswith("url('"):
            segments.append(Segment('url', _extract_arg_from_url_xpath_op(s)))
        elif s.startswith('/url(@') or s.startswith('//url(@'):
            segments.append(Segment('url_from_attr', s))
        elif s.startswith('///url('):
            segments.append(Segment('url_inf', s))
        elif s.startswith('/url("') or s.startswith('//url("'):  # RAISE ERRORS FROM INVALID SEGMENTS
            raise ValueError(f"url() segment cannot have fixed-length argument and preceding navigation slashes (/|//): {s}")
        elif s.startswith("/url('") or s.startswith("//url('"):  # RAISE ERRORS FROM INVALID SEGMENTS
            raise ValueError(f"url() segment cannot have fixed-length argument and preceding navigation slashes (/|//): {s}")
        elif s.startswith('/url(') or s.startswith("//url("):    # RAISE ERRORS FROM INVALID SEGMENTS
            # Reaching this presumes an unsupported value
            raise ValueError(f"Unsupported url() segment: {s}")
        elif s.startswith('///'):
            segments.append(Segment('inf_xpath', "//" + s[3:]))
        # elif s.startswith('/{') or s.startswith('{'):
        #     parsed.append(('object', s))
        else:
            segments.append(Segment('xpath', s))
    
    # Collapes inf_xpath segment and the succeeding url_from_attr segment into a single url_inf segment
    for i in range(len(segments) - 1):
        if segments[i][0] == 'inf_xpath' and segments[i + 1][0] == 'url_from_attr':
            inf_xpath_value = segments[i][1]
            url_from_attr_value = _extract_arg_from_url_xpath_op(segments[i + 1][1])
            url_from_attr_traveral_fragment = segments[i + 1][1].split('url')[0]
            segments[i] = Segment(
                'url_inf', 
                f'///url({inf_xpath_value}{url_from_attr_traveral_fragment}{url_from_attr_value})'
            )
            segments.pop(i + 1)
    
    #### RAISE ERRORS FROM INVALID SEGMENTS ####
    # Raises if multiple ///url() are present
    if len([op for op, val in segments if op == 'url_inf']) > 1:
        raise ValueError("Only one ///url() is allowed")
    
    # Raises if multiple url() are present
    if len([op for op, val in segments if op == 'url']) > 1:
        raise ValueError("Only one url() is allowed")
    
    # Raises when expr starts with //url(@<attr>)
    if segments and segments[0][0] == 'url_from_attr':
        raise ValueError("Path expr cannot start with [//]url(@<attr>)")
    
    return segments
