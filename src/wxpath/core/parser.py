"""
This module contains mainly two kinds of functions: 

1. functions for parsing wxpath expressions.
2. functions for extracting information from wxpath expressions or subexpressions.

"""
import re
from dataclasses import dataclass, fields
from typing import NamedTuple, Optional, TypeAlias

try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        pass


@dataclass(frozen=True, slots=True)
class ValueBase:
    _value: str


@dataclass(frozen=True, slots=True)
class UrlValue(ValueBase):
    target: str
    follow: str | None = None


@dataclass(frozen=True, slots=True)
class XpathValue(ValueBase):
    expr: str


@dataclass(frozen=True, slots=True)
class UrlInfAndXpathValue(ValueBase):
    target: str
    expr: str


Value: TypeAlias = UrlValue | XpathValue | UrlInfAndXpathValue


class Segment(NamedTuple):
    op: str
    value: Value


class OPS(StrEnum):
    URL_STR_LIT       = "url_str_lit"
    URL_EVAL          = "url_eval"
    URL_INF           = "url_inf"
    URL_INF_AND_XPATH = "url_inf_and_xpath"
    XPATH             = "xpath"
    XPATH_FN_MAP_FRAG = "xpath_fn_map_frag" # XPath function ending with map operator '!'
    INF_XPATH         = "inf_xpath" # Experimental
    OBJECT            = "object" # Deprecated
    URL_FROM_ATTR     = "url_from_attr" # Deprecated
    URL_OPR_AND_ARG   = "url_opr_and_arg" # Deprecated


def _scan_path_expr(path_expr: str) -> list[str]:
    """
    Provided a wxpath expression, produce a list of all xpath and url() partitions
    
    :param path_expr: Description
    """
    # remove newlines
    path_expr = path_expr.replace('\n', '')
    partitions = []  # type: list[str]
    i = 0
    n = len(path_expr)
    while i < n:
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

    return partitions


def parse_wxpath_expr(path_expr):
    partitions = _scan_path_expr(path_expr)

    # Lex and parse
    segments = []  # type: list[Segment]
    for s in partitions:
        s = s.strip()
        if not s:
            continue
        if s.startswith('url("') or s.startswith("url('"):
            segments.append(
                Segment(
                    OPS.URL_STR_LIT, 
                    UrlValue(s, *parse_url_value(_extract_arg_from_url_op(s))),
                )
            )
        elif s.startswith('///url('):
            segments.append(
                Segment(
                    OPS.URL_INF, 
                    # XpathValue(extract_url_op_arg(s))
                    XpathValue(_value=s, expr=_extract_arg_from_url_xpath_op(s))
                    )
                )
        elif s.startswith('/url("') or s.startswith('//url("'):
            raise ValueError("url() segment cannot have string literal "
                             f"argument and preceding navigation slashes (/|//): {s}")
        elif s.startswith("/url('") or s.startswith("//url('"):
            raise ValueError("url() segment cannot have string literal "
                             f"argument and preceding navigation slashes (/|//): {s}")
        elif s.startswith('/url(') or s.startswith("//url("):
            segments.append(Segment(OPS.URL_EVAL, XpathValue(s, _extract_arg_from_url_xpath_op(s))))
        elif s.startswith('url('):
            segments.append(Segment(OPS.URL_EVAL, XpathValue(s, _extract_arg_from_url_xpath_op(s))))
        elif s.startswith('///'):
            raise ValueError(f"xpath segment cannot have preceding triple slashes : {s}")
            # segments.append(Segment(OPS.INF_XPATH, XpathValue(s, "//" + s[3:])))
        elif s.endswith('!'):
            segments.append(Segment(OPS.XPATH_FN_MAP_FRAG, XpathValue(s, s[:-1])))
        else:
            segments.append(Segment(OPS.XPATH, XpathValue(s, s)))
    
    ## EXPERIMENTAL
    ## Disabled for now
    ## Collapes inf_xpath segment and the succeeding url_eval segment into a single url_inf segment
    # for i in range(len(segments) - 1, 0, -1):
    #     if segments[i - 1][0] == OPS.INF_XPATH and segments[i][0] == OPS.URL_EVAL:
    #         inf_xpath_value = segments[i - 1][1]
    #         url_eval_value = segments[i][1]
    #         url_eval_traveral_fragment = url_eval_value._value.split('url')[0]
    #         segments[i - 1] = Segment(
    #             OPS.URL_INF,
    #             XpathValue(
    #                 _value='', 
    #                 expr=(f'{inf_xpath_value.expr}'
    #                       f'{url_eval_traveral_fragment}'
    #                       f'{url_eval_value.expr}')
    #             )
    #         )
    #         segments.pop(i)
    
    #### RAISE ERRORS FROM INVALID SEGMENTS ####
    # Raises if multiple ///url() are present
    if len([op for op, val in segments if op == OPS.URL_INF]) > 1:
        raise ValueError("Only one ///url() is allowed")
    
    # Raises if multiple url() with string literals are present
    if len([op for op, _ in segments if op == OPS.URL_STR_LIT]) > 1:
        raise ValueError("Only one url() with string literal argument is allowed")
    
    # Raises when expr starts with //url(@<attr>)
    if segments and segments[0][0] == OPS.URL_EVAL:
        raise ValueError("Path expr cannot start with [//]url(<xpath>)")
    
    # Raises if expr ends with INF_XPATH
    if segments and segments[-1][0] == OPS.INF_XPATH:
        raise ValueError("Path expr cannot end with ///<xpath>")
    
    # Raises if expr ends with XPATH_FN_MAP_FRAG
    if segments and segments[-1][0] == OPS.XPATH_FN_MAP_FRAG:
        raise ValueError("Path expr cannot end with !")
    return segments


def parse_url_value(src: str) -> tuple[str, Optional[str]]:
    """
    Parse the contents of url(...).

    Examples of src:
      "'https://example.com'"
      "//a/@href"
      "'https://x', follow=//a/@href"
    """

    parts = _split_top_level_commas(src)

    if not parts:
        raise SyntaxError("url() requires at least one argument")

    # ---- positional argument (target) ----
    target_src = parts[0].strip()
    if not target_src:
        raise SyntaxError("url() target cannot be empty")

    target = _parse_url_target(target_src)

    follow = None

    # ---- keyword arguments ----
    for part in parts[1:]:
        name, value = _split_kwarg(part)

        if name == "follow":
            if follow is not None:
                raise SyntaxError("duplicate follow= in url()")
            follow = value.strip()
        else:
            raise SyntaxError(f"unknown url() argument: {name}")

    return target, follow


def extract_url_op_arg(url_op_and_arg: str) -> str:
    url_op_arg = _extract_arg_from_url_xpath_op(url_op_and_arg)
    if url_op_arg.startswith('@'):
        return ".//" + url_op_arg
    elif url_op_arg.startswith('.'):
        return url_op_arg
    elif url_op_arg.startswith('//'):
        return '.' + url_op_arg
    elif not url_op_arg.startswith('.//'):
        return './/' + url_op_arg
    else:
        return url_op_arg


def _extract_arg_from_url_xpath_op(url_subsegment):
    match = re.search(r"url\((.+)\)", url_subsegment)
    if not match:
        raise ValueError(f"Invalid url() segment: {url_subsegment}")
    return match.group(1).strip("'\"")  # Remove surrounding quotes if any


def _extract_arg_from_url_op(url_subsegment):
    match = re.search(r"url\((.+)\)", url_subsegment)
    if not match:
        raise ValueError(f"Invalid url() segment: {url_subsegment}")
    return match.group(1)  # Remove surrounding quotes if any


def _split_top_level_commas(src: str) -> list[str]:
    parts = []
    buf = []
    depth = 0
    in_string = False
    quote = None

    for ch in src:
        if in_string:
            buf.append(ch)
            if ch == quote:
                in_string = False
            continue

        if ch in ("'", '"'):
            in_string = True
            quote = ch
            buf.append(ch)
            continue

        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                raise SyntaxError("unbalanced parentheses in url()")

        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf.clear()
        else:
            buf.append(ch)

    if in_string or depth != 0:
        raise SyntaxError("unbalanced expression in url()")

    if buf:
        parts.append("".join(buf).strip())

    return parts


def _split_kwarg(src: str) -> tuple[str, str]:
    if "=" not in src:
        raise SyntaxError(f"expected keyword argument, got: {src}")

    name, value = src.split("=", 1)
    name = name.strip()
    value = value.strip()

    if not name or not value:
        raise SyntaxError(f"invalid keyword argument: {src}")

    return name, value


def _parse_url_target(src: str):
    src = src.strip()
    # string literal
    if (src.startswith("'") and src.endswith("'")) or \
       (src.startswith('"') and src.endswith('"')):
        return src[1:-1]

    return src


def _get_shallow_dict(instance: Value):
    return {field.name: getattr(instance, field.name) 
            for field in fields(instance) if field.name not in {'_value'}}

