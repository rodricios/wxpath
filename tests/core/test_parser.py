import pytest

from wxpath.core.parser import (
    PRECEDENCE,
    Binary,
    Call,
    ContextItem,
    Name,
    Number,
    Parser,
    Segments,
    String,
    Token,
    Url,
    UrlCrawl,
    UrlLiteral,
    UrlQuery,
    Wxpath,
    Xpath,
    find_wxpath_boundary,
    parse,
    tokenize,
)

# =============================================================================
# Tokenizer Tests
# =============================================================================

class TestTokenize:
    def test_tokenize_number_integer(self):
        tokens = list(tokenize("42"))
        assert len(tokens) == 2
        assert tokens[0] == Token("NUMBER", "42", 0, 2)
        assert tokens[1].type == "EOF"

    def test_tokenize_number_float(self):
        tokens = list(tokenize("3.14"))
        assert len(tokens) == 2
        assert tokens[0] == Token("NUMBER", "3.14", 0, 4)

    def test_tokenize_string_single_quotes(self):
        tokens = list(tokenize("'hello world'"))
        assert len(tokens) == 2
        assert tokens[0] == Token("STRING", "'hello world'", 0, 13)

    def test_tokenize_string_double_quotes(self):
        tokens = list(tokenize('"hello world"'))
        assert len(tokens) == 2
        assert tokens[0] == Token("STRING", '"hello world"', 0, 13)

    def test_tokenize_string_with_escaped_quotes(self):
        tokens = list(tokenize(r"'hello\'world'"))
        assert len(tokens) == 2
        assert tokens[0].type == "STRING"

    def test_tokenize_wxpath_url(self):
        tokens = list(tokenize("url"))
        assert len(tokens) == 2
        assert tokens[0] == Token("WXPATH", "url", 0, 3)

    def test_tokenize_wxpath_with_slashes(self):
        tokens = list(tokenize("//url"))
        assert len(tokens) == 2
        assert tokens[0] == Token("WXPATH", "//url", 0, 5)

    def test_tokenize_wxpath_triple_slash(self):
        tokens = list(tokenize("///url"))
        assert len(tokens) == 2
        assert tokens[0] == Token("WXPATH", "///url", 0, 6)

    def test_tokenize_operators(self):
        ops = ["||", "<=", ">=", "!=", "=", "<", ">", "+", "-", "*", "/", "!"]
        for op in ops:
            tokens = list(tokenize(op))
            assert tokens[0].type == "OP", f"Failed for operator: {op}"
            assert tokens[0].value == op

    def test_tokenize_parens(self):
        tokens = list(tokenize("()"))
        assert tokens[0] == Token("LPAREN", "(", 0, 1)
        assert tokens[1] == Token("RPAREN", ")", 1, 2)

    def test_tokenize_comma(self):
        tokens = list(tokenize(","))
        assert tokens[0] == Token("COMMA", ",", 0, 1)

    # # NOTE: in order to preserve native XPath expressions that contain whitespace,
    # # for example, "and not(...)", we can't skip whitespace
    # def test_tokenize_skips_whitespace(self):
    #     tokens = list(tokenize("  42  "))
    #     breakpoint()
    #     assert len(tokens) == 4
    #     assert tokens[0].type == "NUMBER"

    def test_tokenize_complex_expression(self):
        tokens = list(tokenize("url('http://example.com')//a/@href"))
        types = [t.type for t in tokens[:-1]]  # exclude EOF
        assert "WXPATH" in types
        assert "STRING" in types
        assert "LPAREN" in types
        assert "RPAREN" in types


# =============================================================================
# AST Node Tests
# =============================================================================

class TestASTNodes:
    def test_number_node(self):
        node = Number(42.0)
        assert node.value == 42.0

    def test_string_node(self):
        node = String("hello")
        assert node.value == "hello"

    def test_name_node(self):
        node = Name("variable")
        assert node.value == "variable"

    def test_xpath_node(self):
        node = Xpath("//div[@class='test']")
        assert node.value == "//div[@class='test']"

    def test_wxpath_node(self):
        node = Wxpath("///url")
        assert node.value == "///url"

    def test_call_node(self):
        node = Call("func", [Number(1), String("a")])
        assert node.func == "func"
        assert len(node.args) == 2

    def test_url_inherits_from_call(self):
        node = Url("url", [String("http://example.com")])
        assert isinstance(node, Call)
        assert node.func == "url"

    def test_binary_node(self):
        node = Binary(Number(1), "+", Number(2))
        assert node.left == Number(1)
        assert node.op == "+"
        assert node.right == Number(2)

    def test_segments_is_list(self):
        seg = Segments([Xpath("//a"), Url("url", [])])
        assert isinstance(seg, list)
        assert len(seg) == 2

    def test_segments_repr(self):
        seg = Segments([Xpath("//a")])
        assert "Segments" in repr(seg)
        assert "Segments" in str(seg)

    def test_context_item_node(self):
        node = ContextItem()
        assert isinstance(node, ContextItem)


# =============================================================================
# Precedence Tests
# =============================================================================

class TestPrecedence:
    def test_string_concat_lowest(self):
        assert PRECEDENCE["||"] < PRECEDENCE["="]

    def test_comparison_operators(self):
        assert PRECEDENCE["="] == PRECEDENCE["!="]
        assert PRECEDENCE["<"] == PRECEDENCE["<="]
        assert PRECEDENCE[">"] == PRECEDENCE[">="]

    def test_additive_operators(self):
        assert PRECEDENCE["+"] == PRECEDENCE["-"]
        assert PRECEDENCE["+"] > PRECEDENCE["="]

    def test_multiplicative_operators(self):
        assert PRECEDENCE["*"] == PRECEDENCE["/"]
        assert PRECEDENCE["*"] > PRECEDENCE["+"]

    def test_simple_map_highest(self):
        assert PRECEDENCE["!"] > PRECEDENCE["*"]


# =============================================================================
# Parser Tests
# =============================================================================

class TestParser:
    def test_parse_number(self):
        result = parse("42")
        assert result == Xpath("42")

    def test_parse_string(self):
        result = parse("'hello'")
        assert result == Xpath("'hello'")

    def test_parse_simple_url(self):
        result = parse("url('http://example.com')")
        assert isinstance(result, Segments)
        assert len(result) == 1
        assert isinstance(result[0], Url)
        assert result[0].func == "url"
        assert result[0].args == [String("http://example.com")]

    def test_parse_url_with_xpath(self):
        result = parse("url('http://example.com')//a/@href")
        assert isinstance(result, Segments)
        assert len(result) == 2
        assert isinstance(result[0], Url)
        assert isinstance(result[1], Xpath)
        assert result[1].value == "//a/@href"

    def test_parse_chained_url_calls(self):
        result = parse("url('http://example.com')//a/url(@href)")
        assert isinstance(result, Segments)
        # Should have: Url, Xpath, Url
        url_count = sum(1 for seg in result if isinstance(seg, Url))
        assert url_count == 2

    def test_parse_url_with_xpath_argument(self):
        result = parse("url(//a/@href)")
        assert isinstance(result, Segments)
        assert len(result) == 1
        assert isinstance(result[0], Url)
        # The xpath argument should be parsed
        assert len(result[0].args) >= 1

    def test_parse_nested_url(self):
        result = parse("url(url('http://example.com')//a/@href)")
        assert isinstance(result, Segments)
        assert len(result) == 3
        assert isinstance(result[0], UrlLiteral)
        assert isinstance(result[1], Xpath)
        assert isinstance(result[2], UrlQuery)

    def test_parse_binary_with_wxpath(self):
        result = parse("//a = url('http://example.com')")
        assert isinstance(result, Binary)
        assert result.op == "="
        assert isinstance(result.left, Xpath)
        assert result.left.value == "//a"

    def test_parse_pure_xpath(self):
        result = parse("//div[@class='test']/a/@href")
        assert isinstance(result, Xpath)
        assert result.value == "//div[@class='test']/a/@href"

    def test_parse_arithmetic_binary(self):
        # This should be parsed as pure xpath since no wxpath
        result = parse("1 + 2")
        assert isinstance(result, Xpath)

    def test_parse_url_with_follow_argument(self):
        result = parse("url('http://example.com', follow=1)")
        assert isinstance(result, Segments)
        assert len(result) == 1
        url_node = result[0]
        assert isinstance(url_node, Url)
        # First arg is string, then comma handling adds None, then number
        assert url_node.args[0] == String("http://example.com")
        assert url_node.args[-1] == Xpath("1")

    def test_parse_triple_slash_url(self):
        result = parse("url('http://example.com')///url(//a/@href)")
        assert isinstance(result, Segments)
        assert len(result) == 2
        assert isinstance(result[0], UrlLiteral)
        assert result[0].func == "url"
        assert isinstance(result[1], UrlCrawl)
        assert result[1].func == "///url"

# =============================================================================
# find_wxpath_boundary Tests
# =============================================================================

class TestFindWxpathBoundary:
    def test_no_wxpath_returns_none(self):
        tokens = list(tokenize("//a/@href"))
        result = find_wxpath_boundary(tokens)
        assert result is None

    def test_wxpath_without_operator_returns_none(self):
        tokens = list(tokenize("url('http://example.com')"))
        result = find_wxpath_boundary(tokens)
        assert result is None

    def test_finds_boundary_with_equals(self):
        tokens = list(tokenize("//a = url('http://example.com')"))
        result = find_wxpath_boundary(tokens)
        assert result is not None
        op_pos, wxpath_pos = result
        assert tokens[op_pos].value == "="
        assert tokens[wxpath_pos].type == "WXPATH"

    def test_finds_boundary_with_concat(self):
        tokens = list(tokenize("'prefix' || url('http://example.com')"))
        result = find_wxpath_boundary(tokens)
        assert result is not None
        op_pos, wxpath_pos = result
        assert tokens[op_pos].value == "||"

    def test_ignores_operators_in_parens(self):
        # Operators inside parentheses shouldn't be considered boundary
        tokens = list(tokenize("(//a = 1) || url('http://example.com')"))
        result = find_wxpath_boundary(tokens)
        assert result is not None
        op_pos, _ = result
        # Should find || not =
        assert tokens[op_pos].value == "||"


# =============================================================================
# Parser Error Handling Tests
# =============================================================================

class TestParserErrors:
    def test_unbalanced_parens_raises(self):
        with pytest.raises(SyntaxError):
            parse("url('http://example.com'")

    def test_unexpected_token_raises(self):
        # Create a parser that will have leftover tokens
        tokens = list(tokenize("42 ) extra"))
        parser = Parser(iter(tokens))
        with pytest.raises(SyntaxError) as excinfo:
            parser.parse()
        assert "unexpected token" in str(excinfo.value)


# =============================================================================
# Complex Expression Tests  
# =============================================================================

class TestComplexExpressions:
    def test_url_with_xpath_function(self):
        """Test url() with xpath functions like contains()"""
        result = parse("url('http://example.com')//a[contains(@href, '/wiki/')]")
        assert isinstance(result, Segments)
        xpath_part = result[1]
        assert "contains" in xpath_part.value

    def test_multiple_url_segments(self):
        """Test chaining multiple url() calls"""
        result = parse("url('http://example.com')//a/url(@href)//div/url(@src)")
        assert isinstance(result, Segments)
        url_count = sum(1 for seg in result if isinstance(seg, Url))
        assert url_count == 3

    def test_url_with_complex_xpath_predicate(self):
        """Test url() followed by xpath with complex predicates"""
        result = parse("url('http://example.com')//table[@class='data']//tr[position() > 1]/td[1]")
        assert isinstance(result, Segments)
        assert len(result) == 2

    def test_deeply_nested_url(self):
        """Test deeply nested url() calls"""
        result = parse("url(url(url('http://example.com')//a/@href)//b/@src)")
        assert isinstance(result, Segments)
        assert len(result) == 4
        assert isinstance(result[0], UrlLiteral)
        assert isinstance(result[1], Xpath)
        assert isinstance(result[2], UrlQuery)
        assert isinstance(result[3], Xpath)

    def test_range_with_simple_map_and_url_and_map_constructor(self):
        """Test complex expression with range, simple map (!), url(), and map constructor"""
        expr = """
        (1 to 10) ! ('https://example.com?page=' || .) ! 
            url(.)
                //div[@class='results']//*[@role='listitem']
                /map {
                    'title': (.//h2/text())[1],
                    'price': (.//span[@class='price']/text())[1],
                    'link': (.//a/@href)[1]}
        """
        result = parse(expr)
        # Should parse as Binary with ! operator
        assert isinstance(result, Binary)
        assert result.op == "!"
        # Left side should be xpath containing the range expression
        assert isinstance(result.left, Xpath)
        assert "to" in result.left.value
        # Right side should be Segments with url() and xpath containing map
        assert isinstance(result.right, Segments)
        # Should have url() call and xpath with map constructor
        assert len(result.right) >= 1
        # Find the xpath segment with the map constructor
        xpath_segments = [s for s in result.right if isinstance(s, Xpath)]
        assert len(xpath_segments) >= 1
        map_xpath = xpath_segments[-1].value
        assert "/map{" in map_xpath.replace(" ", "") or "/map {" in map_xpath
        assert "'title':" in map_xpath
        assert "'price':" in map_xpath
        assert "'link':" in map_xpath

    def test_tokenize_braces(self):
        """Test that braces are tokenized as LBRACE/RBRACE"""
        tokens = list(tokenize("map { }"))
        types = [t.type for t in tokens[:-1]]  # exclude EOF
        assert "LBRACE" in types
        assert "RBRACE" in types

    def test_tokenize_colon(self):
        """Test that colon is tokenized as COLON"""
        tokens = list(tokenize("'key': value"))
        types = [t.type for t in tokens[:-1]]  # exclude EOF
        assert "COLON" in types

    def test_map_constructor_in_xpath(self):
        """Test that map constructor is captured as part of xpath"""
        result = parse("url('http://example.com')//div/map { 'a': 1, 'b': 2 }")
        assert isinstance(result, Segments)
        xpath_part = result[-1]
        assert isinstance(xpath_part, Xpath)
        assert "map" in xpath_part.value
        assert "'a':" in xpath_part.value
        assert "'b':" in xpath_part.value

