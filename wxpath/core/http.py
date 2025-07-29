import requests
from lxml import etree
from urllib.parse import urljoin


def fetch_html(url):
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.content


def parse_html(content):
    return etree.HTML(content)


def make_links_absolute(links, base_url):
    """
    Convert relative links to absolute links based on the base URL.

    Args:
        links (list): List of link strings.
        base_url (str): The base URL to resolve relative links against.

    Returns:
        List of absolute URLs.
    """
    if base_url is None:
        raise ValueError("base_url must not be None when making links absolute.")
    return [urljoin(base_url, link) for link in links if link]