import asyncio
import urllib.parse
import urllib.robotparser

import aiohttp

from wxpath.util.logging import get_logger

log = get_logger(__name__)


class RobotsTxtPolicy:
    """Caches and evaluates robots.txt rules for crawler requests."""

    def __init__(self, 
                 session: aiohttp.ClientSession, 
                 default_parser: type['RobotsParserBase'] | None = None):
        self._session = session
        self._parsers: dict[str, "RobotsParserBase"] = {}
        self._lock = asyncio.Lock()
        self._default_parser = default_parser or UrllibRobotParser

    async def can_fetch(self, url: str, user_agent: str | None) -> bool:
        """Return whether the crawler is allowed to fetch `url`."""
        host = urllib.parse.urlsplit(url).hostname
        if not host:
            return False

        # Due to multiple aiohttp workers running concurrently, we need to lock
        async with self._lock:
            if host not in self._parsers:
                self._parsers[host] = await self._fetch_robots_txt(host)

        return self._parsers[host].can_fetch(url, user_agent)

    async def _fetch_robots_txt(self, host: str) -> "RobotsParserBase":
        """Retrieve and parse the robots.txt for `host`, failing open on errors."""
        url = f"http://{host}/robots.txt"
        try:
            async with self._session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    # Pass the text as-is to the parser, let it handle the format
                    if self._default_parser == UrllibRobotParser:
                        return self._default_parser(text.splitlines())
                    else:
                        return self._default_parser(text)
                else:
                    # Empty robots.txt - allow all
                    if self._default_parser == UrllibRobotParser:
                        return self._default_parser([])
                    else:
                        return self._default_parser("")
        except Exception:
            # If robots.txt is unavailable, allow all requests (fail open)
            log.debug(f"Failed to fetch robots.txt from {host}, allowing all requests")
            if self._default_parser == UrllibRobotParser:
                return self._default_parser([])
            else:
                return self._default_parser("")


class RobotsParserBase:
    """Base type for robots.txt parsers used by the policy."""


class UrllibRobotParser(RobotsParserBase):
    """Adapter around `urllib.robotparser.RobotFileParser`."""

    def __init__(self, text):
        self._parser = urllib.robotparser.RobotFileParser()
        # urllib.robotparser.RobotFileParser.parse() expects a list of lines
        if isinstance(text, str):
            lines = text.splitlines() if text else []
        else:
            lines = text if text else []
        self._parser.parse(lines)

    def can_fetch(self, url, user_agent):
        """Return whether the URL is allowed for the given user agent."""
        return self._parser.can_fetch(user_agent, url)

