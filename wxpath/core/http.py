import requests
import logging
import time
from typing import Dict, Optional
from lxml import etree
from urllib.parse import urljoin
from requests.exceptions import RequestException, Timeout, ConnectionError, HTTPError

logger = logging.getLogger(__name__)

# Default configuration for HTTP requests
DEFAULT_HEADERS = {
    'User-Agent': 'wxpath/1.0 (https://github.com/wxpath/wxpath)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

DEFAULT_TIMEOUT = 10
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 2


def fetch_html(url: str, 
               timeout: Optional[int] = None,
               headers: Optional[Dict[str, str]] = None,
               max_retries: Optional[int] = None,
               verify_ssl: bool = True) -> bytes:
    """
    Fetch HTML content from a URL with comprehensive error handling and retry logic.
    
    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds (default: 10)
        headers: Custom headers to send with the request
        max_retries: Maximum number of retry attempts (default: 3)
        verify_ssl: Whether to verify SSL certificates (default: True)
        
    Returns:
        Raw HTML content as bytes
        
    Raises:
        ValueError: For invalid URLs or parameters
        requests.exceptions.RequestException: For HTTP-related errors
        TimeoutError: When requests consistently timeout
        ConnectionError: When connection cannot be established
    """
    if not url or not isinstance(url, str):
        raise ValueError(f"Invalid URL provided: {url}")
    
    if not url.startswith(('http://', 'https://')):
        raise ValueError(f"URL must start with http:// or https://: {url}")
    
    # Set defaults
    timeout = timeout or DEFAULT_TIMEOUT
    max_retries = max_retries if max_retries is not None else MAX_RETRIES
    request_headers = DEFAULT_HEADERS.copy()
    if headers:
        request_headers.update(headers)
    
    logger.debug("Fetching URL: %s (timeout: %d, retries: %d)", url, timeout, max_retries)
    
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                # Exponential backoff for retries
                backoff_time = RETRY_BACKOFF_FACTOR ** (attempt - 1)
                logger.debug("Retrying URL %s after %d seconds (attempt %d/%d)", 
                           url, backoff_time, attempt + 1, max_retries + 1)
                time.sleep(backoff_time)
            
            response = requests.get(
                url,
                timeout=timeout,
                headers=request_headers,
                verify=verify_ssl,
                allow_redirects=True,
                stream=False
            )
            
            # Check for HTTP errors
            response.raise_for_status()
            
            # Validate content
            if not response.content:
                logger.warning("Empty response received from URL: %s", url)
            
            logger.debug("Successfully fetched URL: %s (status: %d, size: %d bytes)", 
                        url, response.status_code, len(response.content))
            
            return response.content
            
        except Timeout as e:
            last_exception = e
            logger.warning("Timeout fetching URL %s (attempt %d/%d): %s", 
                         url, attempt + 1, max_retries + 1, e)
            if attempt == max_retries:
                raise TimeoutError(f"Request to {url} timed out after {max_retries + 1} attempts") from e
                
        except ConnectionError as e:
            last_exception = e
            logger.warning("Connection error fetching URL %s (attempt %d/%d): %s", 
                         url, attempt + 1, max_retries + 1, e)
            if attempt == max_retries:
                raise ConnectionError(f"Could not connect to {url} after {max_retries + 1} attempts") from e
                
        except HTTPError as e:
            # Don't retry on 4xx client errors (except 429 Too Many Requests)
            if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                logger.error("HTTP client error for URL %s: %d %s", 
                           url, e.response.status_code, e.response.reason)
                raise
            
            last_exception = e
            logger.warning("HTTP error fetching URL %s (attempt %d/%d): %d %s", 
                         url, attempt + 1, max_retries + 1, 
                         e.response.status_code, e.response.reason)
            if attempt == max_retries:
                raise
                
        except RequestException as e:
            last_exception = e
            logger.warning("Request error fetching URL %s (attempt %d/%d): %s", 
                         url, attempt + 1, max_retries + 1, e)
            if attempt == max_retries:
                raise
    
    # This should never be reached, but just in case
    if last_exception:
        raise last_exception


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