import pytest

from wxpath.core.parser import OPS, _extract_arg_from_url_xpath_op, parse_wxpath_expr


def test_parse_wxpath_expr_single_url():
    expr = "url('http://example.com')"
    assert parse_wxpath_expr(expr) == [
        (OPS.URL_STR_LIT, 'http://example.com')
    ]


def test_parse_wxpath_expr_mixed_segments():
    expr = (
        "url('https://en.wikipedia.org/wiki/Expression_language')"
        "//url(@href[starts-with(., '/wiki/')])"
        "//url(@href)"
    )
    expected = [
        (OPS.URL_STR_LIT, 'https://en.wikipedia.org/wiki/Expression_language'),
        (OPS.URL_EVAL, "//url(@href[starts-with(., '/wiki/')])"),
        (OPS.URL_EVAL, "//url(@href)"),
    ]
    assert parse_wxpath_expr(expr) == expected


def test_parse_wxpath_expr_filtered_inf_url_equality_filter():
    path_expr_1 = "url('https://en.wikipedia.org/wiki/Expression_language')///main//a/url(@href)"
    # The same expression written differently:
    path_expr_2 = "url('https://en.wikipedia.org/wiki/Expression_language')///url(//main//a/@href)"
    assert parse_wxpath_expr(path_expr_1) == parse_wxpath_expr(path_expr_2)


def test_extract_arg_with_quotes():
    assert _extract_arg_from_url_xpath_op("url('abc')") == 'abc'
    assert _extract_arg_from_url_xpath_op('url("def")') == 'def'


def test_extract_arg_without_quotes():
    assert _extract_arg_from_url_xpath_op('url(xyz)') == 'xyz'


def test_extract_arg_invalid_raises():
    with pytest.raises(ValueError):
        _extract_arg_from_url_xpath_op('url()')


# Raises when there are multiple ///url() segments
def test_parse_wxpath_expr_multiple_inf_url_segments():
    expr = "url('http://example.com/')///url(@href)///url(@href)"
    with pytest.raises(ValueError) as excinfo:
        parse_wxpath_expr(expr)
    assert "Only one ///url() is allowed" in str(excinfo.value)


# Raise error if url() with fixed-length argument is preceded by navigation slashes
def test_parse_wxpath_expr_fixed_length_url_preceded_by_slashes():
    expr = "url('http://example.com/')//url('http://example2.com/')"
    with pytest.raises(ValueError) as excinfo:
        parse_wxpath_expr(expr)
    assert \
        ("url() segment cannot have string literal argument and "
        "preceding navigation slashes (/|//): //url('http://example2.com/')") \
        in str(excinfo.value)
    

# Raises when expr starts with //url_from_attr()
def test_parse_wxpath_expr_url_from_attr_without_elem():
    expr = "//url(@href)"
    with pytest.raises(ValueError) as excinfo:
        parse_wxpath_expr(expr)
    assert "Path expr cannot start with [//]url(<xpath>)" in str(excinfo.value)


def test_parse_wxpath_expr_object_segment():
    expr = "url('http://example.com')/map{ 'title':string(//h1/text()) }"
    parsed = parse_wxpath_expr(expr)
    assert parsed == [
        (OPS.URL_STR_LIT, 'http://example.com'),
        (OPS.XPATH, "/map{ 'title':string(//h1/text()) }"),
    ]
