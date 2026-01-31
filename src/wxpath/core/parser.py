import re
from dataclasses import dataclass
from itertools import pairwise
from typing import Iterable, Iterator, TypeAlias

try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        pass


TOKEN_SPEC = [
    ("NUMBER",   r"\d+\.\d+"),
    ("INTEGER",  r"\d+"),
    ("STRING",   r"'([^'\\]|\\.)*'|\"([^\"\\]|\\.)*\""), # TODO: Rename to URL Literal
    ("WXPATH",   r"/{0,3}\s*url"),  # Must come before NAME to match 'url' as WXPATH
    # ("///URL",   r"/{3}\s*url"),
    # ("//URL",    r"/{2}\s*url"),
    # ("/URL",      r"/{1}\s*url"),
    ("URL",      r"\s*url"),  # Must come before NAME to match 'url' as WXPATH
    # ("NAME",     r"[a-zA-Z_][a-zA-Z0-9_]*"),
    ("FOLLOW",   r",?\s{,}follow="),
    ("DEPTH",    r",?\s{,}depth="),
    ("OP",       r"\|\||<=|>=|!=|=|<|>|\+|-|\*|/|!"),  # Added || for string concat
    ("LPAREN",   r"\("),
    ("RPAREN",   r"\)"),
    ("LBRACE",   r"\{"),
    ("RBRACE",   r"\}"),
    ("COLON",    r":"),
    ("COMMA",    r","),
    ("WS",       r"\s+"),
    ("DOT",      r"\."),
    ("OTHER",    r"."),  # Catch-all for xpath operators: /, @, [, ], etc.
]

TOKEN_RE = re.compile("|".join(
    f"(?P<{name}>{pattern})"
    for name, pattern in TOKEN_SPEC
))


@dataclass
class Token:
    type: str
    value: str
    start: int = 0  # position in source string
    end: int = 0


def tokenize(src: str):
    for m in TOKEN_RE.finditer(src):
        kind = m.lastgroup
        # # NOTE: in order to preserve native XPath expressions that contain whitespace,
        # # for example, "and not(...)", we can't skip whitespace
        # if kind == "WS":
        #     continue
        yield Token(kind, m.group(), m.start(), m.end())
    yield Token("EOF", "", len(src), len(src))


@dataclass
class Number:
    value: float

@dataclass
class Integer:
    value: int

@dataclass
class Depth(Integer):
    pass

@dataclass
class String:
    value: str


@dataclass
class Name:
    value: str

@dataclass
class Xpath:
    value: str

@dataclass
class Wxpath:
    value: str

@dataclass
class Call:
    func: str
    args: list

@dataclass
class Url(Call):
    pass

@dataclass
class UrlLiteral(Url):
    pass

@dataclass
class UrlQuery(Url):
    pass

UrlSelect = UrlQuery

@dataclass
class UrlCrawl(Url):
    pass

UrlFollow = UrlCrawl

@dataclass
class Binary:
    left: object
    op: str
    right: object

Segment: TypeAlias = Url | Xpath

class Segments(list):
    def __repr__(self):
        return f"Segments({super().__repr__()})"
    
    def __str__(self):
        return f"Segments({super().__str__()})"

@dataclass
class Other:
    value: str


@dataclass
class ContextItem(Xpath):
    """Represents the XPath context item expression: ."""
    value: str = "."


PRECEDENCE = {
    "||": 5,   # String concatenation (lowest precedence)
    "=": 10,
    "!=": 10,
    "<": 10,
    "<=": 10,
    ">": 10,
    ">=": 10,
    "+": 20,
    "-": 20,
    "*": 30,
    "/": 30,
    "!": 40,   # Simple map operator (highest precedence)
}


class Parser:
    """Pratt-style parser that produces wxpath AST nodes."""

    def __init__(self, tokens: Iterable[Token]):
        self.tokens: Iterator[Token] = iter(tokens)
        self.token: Token = next(self.tokens)

    def advance(self) -> None:
        self.token = next(self.tokens)

    def parse(self) -> object:
        """Parse the input tokens into an AST or raise on unexpected trailing tokens."""
        output = self.expression(0)
        if self.token.type != "EOF":
            raise SyntaxError(f"unexpected token: {self.token}")

        return output

    def expression(self, min_prec: int) -> object:
        return self.parse_binary(min_prec)

    def parse_binary(self, min_prec: int) -> object:
        """Parse a binary expression chain honoring operator precedence."""
        if self.token.type == "WXPATH":
            left = self.parse_segments()
        else:
            left = self.nud()

        while self.token.type == "OP" and PRECEDENCE.get(self.token.value, -1) >= min_prec:
            op = self.token.value
            prec = PRECEDENCE[op]
            self.advance()
            if self.token.type == 'WXPATH':
                right = self.parse_segments()
            else: 
                right = self.parse_binary(prec + 1)
            left = Binary(left, op, right)

        return left
    
    @staticmethod
    def _validate_segments(func):
        """Decorator that validates segment invariants after parsing.

        Raises ValueError if the xpath in ``url(<xpath>)`` begins with ``/``
        or ``//`` when it follows an Xpath segment.

        Args:
            func: A bound method that returns a list of segments.

        Returns:
            The wrapped function that performs validation.
        """
        def _func(self) -> Segments:
            segments = func(self)
            for seg1, seg2 in pairwise(segments):
                if isinstance(seg1, Xpath) and isinstance(seg2, Url):
                    if seg2.args[0].value.startswith(("/", "//")):
                        raise ValueError(
                            f"Invalid segments: {segments}. the <xpath> in url(<xpath>)"
                            " may not begin with / or // if following an Xpath segment."
                        )
            return segments
        return _func

    @_validate_segments
    def parse_segments(self) -> Segments:
        """Parse a sequence of wxpath segments: url() calls interspersed with xpath.

        Handles patterns like::

            url('...')
            url('...')//a/@href
            url('...')//a/url(@href)//b
            //a/@href
            //a/map { 'key': value }

        Returns:
            A Segments list containing the parsed Url and Xpath nodes.
        """
        segments = []
        
        while self.token.type != "EOF":
            if self.token.type == "WXPATH":
                # Parse url() call
                call = self.nud()
                if call is not None:
                    if isinstance(call, (Segments, list)):
                        segments.extend(call)
                    else:
                        segments.append(call)
            elif self.token.type == "RPAREN":
                # End of nested context
                break
            elif self.token.type == "COMMA":
                # Argument separator - stop segment parsing
                break
            elif self.token.type == "RBRACE":
                # End of map context - stop segment parsing
                break
            else:
                # Capture xpath content until next url() or end
                xpath_content = self.capture_xpath_until_wxpath_or_end()
                if xpath_content.strip():
                    segments.append(Xpath(xpath_content.strip()))
        
        return Segments(segments)


    def nud(self) -> object | None:
        """Parse a null-denoting expression (nud).

        Null-denoting expressions include numbers, names, or expressions
        enclosed in parentheses.

        Returns:
            The parsed AST node, or None if the token is unrecognized.

        Raises:
            SyntaxError: If the token cannot form a valid expression.
        """
        tok = self.token

        if tok.type == "NUMBER":
            self.advance()
            return Number(float(tok.value))

        if tok.type == "INTEGER":
            self.advance()
            return Integer(int(tok.value))
        
        if tok.type == "STRING":
            self.advance()
            return String(tok.value[1:-1])  # strip quotes

        if tok.type == "DOT":
            self.advance()
            return ContextItem()

        if tok.type == "WXPATH":
            value = tok.value.replace(" ", "").replace("\n", "")
            self.advance()

            if self.token.type == "LPAREN":
                return self.parse_call(value)

            return Wxpath(value)

        if tok.type == "NAME":
            self.advance()

            # function call
            if self.token.type == "LPAREN":
                return self.parse_call(tok.value)

            return Name(tok.value)

        if tok.type == "LPAREN":
            self.advance()
            expr = self.expression(0)
            if self.token.type != "RPAREN":
                raise SyntaxError("expected ')'")
            self.advance()
            return expr

        # For other tokens (xpath content), return None to signal caller to handle
        return None
    

    def capture_xpath_until_wxpath_or_end(self) -> str:
        """Capture xpath tokens until a WXPATH token, EOF, RPAREN, or COMMA.

        Balances parentheses and braces so that xpath functions like
        ``contains()`` and map constructors like ``map { ... }`` are captured
        correctly.

        Returns:
            The accumulated xpath content as a string.
        """
        result = ""
        paren_depth = 0
        brace_depth = 0
        
        while self.token.type != "EOF":
            # Stop conditions (only at depth 0 for both parens and braces)
            if paren_depth == 0 and brace_depth == 0:
                if self.token.type == "WXPATH":
                    break
                if self.token.type == "RPAREN":
                    break
                if self.token.type == "COMMA":
                    break
            
            # Track paren depth for xpath functions
            if self.token.type == "LPAREN":
                paren_depth += 1
            elif self.token.type == "RPAREN":
                paren_depth -= 1
                if paren_depth < 0:
                    # This RPAREN closes an outer context
                    break
            
            # Track brace depth for map constructors
            if self.token.type == "LBRACE":
                brace_depth += 1
            elif self.token.type == "RBRACE":
                brace_depth -= 1
                if brace_depth < 0:
                    # This RBRACE closes an outer context
                    break
            
            result += self.token.value
            self.advance()
        
        return result

    def capture_url_arg_content(self) -> list[Call | Xpath | ContextItem]:
        """Capture content inside a url() call, handling nested wxpath expressions.

        Supports patterns like::

            url('...')                          -> [String]
            url('...' follow=//a/@href)         -> [String, Xpath]
            url('...' follow=//a/@href depth=2) -> [String, Xpath, Integer]
            url(//a/@href depth=2)              -> [Xpath, Integer]
            url( url('..')//a/@href )           -> [Call, Xpath]
            url( url( url('..')//a )//b )       -> [Call, Xpath]

        Returns:
            A list of parsed elements: Xpath nodes for xpath content and Call
            nodes for nested url() calls.
        """
        elements = []
        current_xpath = ""
        paren_balance = 1  # We're already inside the opening paren of url()
        brace_balance = 0  # Track braces for map constructors
        reached_follow_token = False
        reached_depth_token = False
        follow_xpath = ""
        depth_number = ""

        while paren_balance > 0 and self.token.type != "EOF":
            if self.token.type == "WXPATH":
                # Found nested wxpath: save any accumulated xpath content first
                if current_xpath.strip():
                    elements.append(Xpath(current_xpath.strip()))
                    current_xpath = ""
                
                # Parse the nested url() call using nud()
                # This recursively handles deeply nested wxpath
                nested_call = self.nud()
                if nested_call is not None:
                    elements.append(nested_call)

            elif self.token.type == "FOLLOW":
                reached_follow_token = True
                reached_depth_token = False
                self.advance()

            elif self.token.type == "DEPTH":
                reached_depth_token = True
                reached_follow_token = False
                self.advance()

            elif self.token.type == "LPAREN":
                # Opening paren that's NOT part of a url() call
                # (it's part of an xpath function like contains(), starts-with(), etc.)
                paren_balance += 1
                if not reached_follow_token:
                    current_xpath += self.token.value
                else:
                    follow_xpath += self.token.value
                self.advance()
                
            elif self.token.type == "RPAREN":
                paren_balance -= 1
                if paren_balance == 0:
                    # This is the closing paren of the outer url()
                    break
                if not reached_follow_token:
                    current_xpath += self.token.value
                else:
                    follow_xpath += self.token.value
                self.advance()

            elif self.token.type == "LBRACE":
                # Opening brace for map constructors
                brace_balance += 1
                if not reached_follow_token:
                    current_xpath += self.token.value
                else:
                    follow_xpath += self.token.value
                self.advance()

            elif self.token.type == "RBRACE":
                brace_balance -= 1
                if not reached_follow_token:
                        current_xpath += self.token.value
                else:
                    follow_xpath += self.token.value
                self.advance()
                
            else:
                # Accumulate all other tokens as xpath content
                if reached_follow_token:
                    follow_xpath += self.token.value
                elif reached_depth_token:
                    depth_number += self.token.value
                else:
                    current_xpath += self.token.value

                self.advance()
        
        if paren_balance != 0:
            raise SyntaxError("unbalanced parentheses in url()")
        
        # Save any remaining xpath content
        if current_xpath.strip():
            current_xpath = current_xpath.strip()
            if current_xpath == ".":
                elements.append(ContextItem())
            else:
                elements.append(Xpath(current_xpath))
        
        if follow_xpath.strip():
            elements.append(Xpath(follow_xpath.strip()))

        if depth_number.strip():
            elements.append(Depth(int(depth_number.strip())))

        return elements

    def parse_call(self, func_name: str) -> Call | Segments:
        """Parse a function call (including url variants) and specialize node types."""
        self.advance()  # consume '('
        args = []
        follow_arg = None

        if func_name.endswith("url"):
            if self.token.type == "STRING":
                # Simple case: url('literal string')
                args = [String(self.token.value[1:-1])]  # strip quotes
                self.advance()
                # Handle follow=...
                if self.token.type == "FOLLOW":
                    follow_arg = self.capture_url_arg_content()
                    args.extend(follow_arg)
                if self.token.type == "DEPTH":
                    depth_arg = self.capture_url_arg_content()
                    args.extend(depth_arg)
            elif self.token.type == "WXPATH":
                # Nested wxpath: url( url('...')//a/@href ) or url( /url(...) )
                # NOTE: We used to use capture_url_arg_content to handle nested wxpath and xpath
                # args = self.capture_url_arg_content()
                args = self.nud()
            else:
                # Simple xpath argument: url(//a/@href)
                # Could still contain nested wxpath, so use capture_url_arg_content
                args = self.capture_url_arg_content()

        # Handle additional comma-separated arguments (e.g., follow=...)
        if self.token.type != "RPAREN":
            while True:
                args.append(self.expression(0))
                if self.token.type == "COMMA":
                    self.advance()
                    continue
                break

        if self.token.type != "RPAREN":
            raise SyntaxError("expected ')'")
        self.advance()

        return _specify_call_types(func_name, args)

def _specify_call_types(func_name: str, args: list) -> Call | Segments:
    """
    Specify the type of a call based on the function name and arguments.
    TODO: Provide example wxpath expressions for each call type.
    
    Args:
        func_name: The name of the function.
        args: The arguments of the function.

    Returns:
        Call | Segments: The type of the call.
    """
    if func_name == "url":
        if len(args) == 1:
            if isinstance(args[0], String):
                return UrlLiteral(func_name, args)
            elif isinstance(args[0], (Xpath, ContextItem)):
                return UrlQuery(func_name, args)
            else:
                raise ValueError(f"Unknown argument type: {type(args[0])}")
        elif len(args) == 2:
            arg0, arg1 = args
            if isinstance(arg0, String) and isinstance(arg1, Xpath):
                # Example: url('...', follow=//a/@href)
                return UrlCrawl(func_name, args)
            elif isinstance(arg0, String) and isinstance(arg1, Integer):
                # Example: url('...', depth=2)
                return UrlLiteral(func_name, args)
            elif isinstance(arg0, UrlLiteral) and isinstance(arg1, Xpath):
                args.append(UrlQuery('url', [ContextItem()]))
                return Segments(args)
            elif isinstance(arg0, (Segments, list)) and isinstance(arg1, Xpath):
                segs = arg0
                segs.append(arg1)
                return Segments(segs)
            else:
                raise ValueError(f"Unknown arguments: {args}")
        elif len(args) == 3:
            arg0, arg1, arg2 = args
            if (isinstance(arg0, String) and (
                (isinstance(arg1, Xpath) and isinstance(arg2, Integer)) or
                (isinstance(arg1, Integer) and isinstance(arg2, Xpath))
            )):
                # Example: url('...', follow=//a/@href, depth=2)
                # Example: url('...', depth=2, follow=//a/@href)
                return UrlCrawl(func_name, args)
            else:
                raise ValueError(f"Unknown arguments: {args}")
        else:
            raise ValueError(f"Unknown arguments: {args}")
    elif func_name == "/url" or func_name == "//url":
        if len(args) == 1:
            if isinstance(args[0], (Xpath, ContextItem)):
                return UrlQuery(func_name, args)
            else:
                raise ValueError(f"Unknown argument type: {type(args[0])}")
        else:
            raise ValueError(f"Unknown arguments: {args}")
    elif func_name == "///url":
        if len(args) == 1:
            if isinstance(args[0], (Xpath, ContextItem)):
                return UrlCrawl(func_name, args)
            else:
                raise ValueError(f"Unknown argument type: {type(args[0])}")
        else:
            raise ValueError(f"Unknown arguments: {args}")
    else:
        return Call(func_name, args)


def find_wxpath_boundary(tokens: list[Token]) -> tuple[int, int] | None:
    """Find the operator that connects pure xpath to wxpath.

    The boundary is the last operator at depth 0 before the first WXPATH token.

    Args:
        tokens: List of Token objects from the tokenizer.

    Returns:
        A tuple of (op_position, wxpath_position) or None if no boundary
        exists.
    """
    # Find first WXPATH token position
    wxpath_pos = None
    for i, tok in enumerate(tokens):
        if tok.type == "WXPATH":
            wxpath_pos = i
            break
    
    if wxpath_pos is None:
        return None
    
    # Walk backwards from wxpath to find connecting operator at depth 0
    paren_depth = 0
    for i in range(wxpath_pos - 1, -1, -1):
        tok = tokens[i]
        if tok.type == "RPAREN":
            paren_depth += 1
        elif tok.type == "LPAREN":
            paren_depth -= 1
        elif paren_depth == 0 and tok.type == "OP":
            return (i, wxpath_pos)
    
    return None


def parse(src):
    tokens = list(tokenize(src))
    
    boundary = find_wxpath_boundary(tokens)
    
    # If no wxpath at all, return as pure xpath
    if boundary is None:
        # Check if there's any WXPATH token
        has_wxpath = any(t.type == "WXPATH" for t in tokens)
        if not has_wxpath:
            return Xpath(src.strip())
        # Has wxpath but no boundary operator - parse normally
        parser = Parser(iter(tokens))
        return parser.parse()
    
    op_pos, wxpath_pos = boundary
    
    # Use source positions to extract xpath string (preserves whitespace)
    op_token = tokens[op_pos]
    xpath_str = src[:op_token.start].strip()
    
    # Parse wxpath part (tokens after the operator)
    wxpath_tokens = tokens[op_pos + 1:]  # includes EOF
    parser = Parser(iter(wxpath_tokens))
    wxpath_ast = parser.parse()
    
    return Binary(Xpath(xpath_str), op_token.value, wxpath_ast)
