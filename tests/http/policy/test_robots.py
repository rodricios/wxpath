import pytest

from wxpath.http.policy.robots import UrllibRobotParser


@pytest.mark.parametrize(
    "robots_txt, user_agent, url, expected",
    [
        ("", "test-bot", "http://example.com/allowed", True),
        ("User-agent: *\nDisallow: /", "test-bot", "http://example.com/any", False),
        (
            "User-agent: test-bot\nDisallow: /private",
            "test-bot",
            "http://example.com/private/page",
            False,
        ),
        (
            "User-agent: other-bot\nDisallow: /private",
            "test-bot",
            "http://example.com/private/page",
            True,
        ),
        (
            "User-agent: *\nDisallow: /private\n\nUser-agent: test-bot\nAllow: /private/public",
            "test-bot",
            "http://example.com/private/page",
            True,  # urllib.robotparser is more lenient - allows if user-agent has any Allow rule
        ),
        (
            "User-agent: *\nDisallow: /private\n\nUser-agent: test-bot\nAllow: /private/public",
            "test-bot",
            "http://example.com/private/public/page",
            True,
        ),
        (
            "User-agent: *\nDisallow: /private",
            ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"),
            "http://example.com/private/page",
            False,
        ),
    ],
)
def test_urllib_robot_parser(robots_txt, user_agent, url, expected):
    """Test the urllib.robotparser implementation."""
    parser = UrllibRobotParser(robots_txt)
    assert parser.can_fetch(url, user_agent) == expected

