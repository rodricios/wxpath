from urllib.parse import urljoin


def _make_links_absolute(links: list[str], base_url: str) -> list[str]:
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


def get_absolute_links_from_elem_and_xpath(elem, xpath):
    base_url = getattr(elem, 'base_url', None)
    return _make_links_absolute(elem.xpath3(xpath), base_url)
