
# Examples

The following examples demonstrate various web crawling and data extraction tasks using wxpath.

## EXAMPLE 1 - Simple, single page crawl and link extraction 

Starting from Expression language's wiki, extract all links (hrefs) from the main section. The `url(...)` operator is used to execute a web request to the specified URL and return the HTML content.

```python
import wxpath

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')//main//a/@href"
items = wxpath.wxpath_async_blocking(path_expr)
```


## EXAMPLE 2 - Two-level crawl and link extraction

Starting from Expression language's wiki, crawl all child links  starting with '/wiki/', and extract each child's links (hrefs). The `url(...)` operator is pipe'd arguments from the evaluated XPath.

```python
import wxpath

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')//url(//@href[starts-with(., '/wiki/')])//a/@href"
items = wxpath.wxpath_async_blocking(path_expr)
```


## EXAMPLE 3 - Deep crawl with BFS tree depth limit

Starting from Expression language's wiki, follow all child links (and child's child's links iteratively). The `///` syntax is used to indicate a crawl. Returns lxml.html.HtmlElement objects. `max_depth` is used to limit the BFS tree (crawl depth).

```python
import wxpath

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///url(//main//a/@href)"
# Modify (inclusive) max_depth to limit the BFS tree (crawl depth).
items = wxpath.wxpath_async_blocking(path_expr, max_depth=1)
```

## EXAMPLE 4 - Deep crawl with field extraction

Perform a deep crawl from Expression language's wiki's child links and childs' child links (recursively) and then, for each child link crawled, extracts objects with the named fields as a dict.

```python
import wxpath

path_expr = """
    url('https://en.wikipedia.org/wiki/Expression_language')
     //url(//main//a/@href)
     /map {
        'title':(//span[contains(@class, "mw-page-title-main")]/text())[1], 
        'short_description':(//div[contains(@class, "shortdescription")]/text())[1],
        'url'://link[@rel='canonical']/@href[1],
        'backlink':wx:backlink(.),
        'depth':wx:depth(.)
    }
"""
```

Under the hood of `wxpath`, we generate `segments` list, revealing the runtime engine's operations executed to accomplish the crawl.

```python
from wxpath.core import parser

for segment in parser.parse(path_expr):
    print(segment)

UrlLiteral(func='url', args=[String(value='https://en.wikipedia.org/wiki/Expression_language')])
UrlQuery(func='//url', args=[Xpath(value='//main//a/@href')])
Xpath(value='/map{\'title\':(//span[contains(@class,"mw-page-title-main")]/text())[1],\'short_description\':(//div[contains(@class,"shortdescription")]/text())[1],\'url\'://link[@rel=\'canonical\']/@href[1],\'backlink\':wx:backlink(.),\'depth\':wx:depth(.)}')
```

## EXAMPLE 5 = Seeding from XPath function expression + mapping operator (`!`)

Due to the engine supporting XPath 3.1, you can use the `!` operator to seed from XPath functions. This example demonstrates creating 10 Amazon book search result page URLs, mapping each URL to the url(.) operator, and for each page, extracting the title, price, and link of each book listed.
 

```python
import wxpath

base_url = "https://www.amazon.com/s?k=books&i=stripbooks&page="

path_expr = f"""
    (1 to 10) ! ('{base_url}' || .) !
    url(.)
        //span[@data-component-type='s-search-results']//*[@role='listitem']
            /map {{
                'title': (.//h2/span/text())[1],
                'price': (.//span[@class='a-price']/span[@class='a-offscreen']/text())[1],
                'link': (.//a[@aria-describedby='price-link']/@href)[1]
            }}
"""

items = list(wxpath.wxpath_async_blocking_iter(path_expr, max_depth=1))
```


## EXAMPLE 6 - Scraping quotes.toscrape.com with pagination

**wxpath** provides the `follow` parameter, which allows you to specify a follow path for pagination.
The `follow` parameter works almost identically to the `///url(//a[@class='next']/@href)` syntax, but it initializes the scraping at the seed URL.


```python
import wxpath

path_expr = """
url('https://quotes.toscrape.com/tag/humor/', follow=//li[@class='next']/a/@href)
  //div[@class='quote']
    /map{
      'author': (./span/small/text())[1],
      'text': (./span[@class='text']/text())[1]
      }
"""

items = list(wxpath.wxpath_async_blocking_iter(path_expr, max_depth=3))
```


## EXAMPLE 6B - Scraping quotes.toscrape.com with pagination and author extraction

```python
import wxpath

path_expr = """
url('https://quotes.toscrape.com', depth=5, follow=//li[@class='next']/a/@href)
  //url(//a[contains(@href, '/author/')]/@href)
    /map {
      'url': string(base-uri(.)),
      'name': //h3[@class='author-title']/text(),
      'born': //span[@class='author-born-date']/text(),
      'bio': //div[@class='author-description']/text() ! normalize-space(.) ! string(.),
    }
"""

items = list(wxpath.wxpath_async_blocking_iter(path_expr, max_depth=5))
```

## Example 7 - Scrape HackerNews comments

```python
import wxpath

path_expr = """
url('https://news.ycombinator.com')///url(//a[text()='comments']/@href | //a[@class='morelink']/@href)//div[@class='comment']//text()
"""

items = list(wxpath.wxpath_async_blocking_iter(path_expr, max_depth=10))
```

## Example 7B - Scrape HackerNews comments as JSONL

```python
import wxpath

path_expr = """
url('https://news.ycombinator.com')///url(//a[text()='comments']/@href | //a[@class='morelink']/@href)//tr[@class='athing']/map { 
    'text': .//div[@class='comment']//text(),
    'user': .//a[@class='hnuser']/@href,
    'parent_post': .//span[@class='onstory']/a/@href
    }
"""

items = list(wxpath.wxpath_async_blocking_iter(path_expr, max_depth=10))
```


## EXAMPLE 8 - Find Department Chair

```python
import wxpath

path_expr = """
url('https://csm.fresnostate.edu/about/directory/index.html', depth=1)
  //url(//tbody/tr[contains(.//td[2]/text(), 'Prof')]/td[1]/a/@href)
    //div[@id='main-content']//text()[contains(., 'Department') ]
      / map {
          'title': (//h1/text())[1],
          'url': string(base-uri(.))
      }
"""

items = list(wxpath.wxpath_async_blocking_iter(path_expr, max_depth=1))
```


## EXAMPLE 9 - University of Notre Dame Faculty

```python
import wxpath

path_expr = """
url('https://engineering.nd.edu/faculty/', follow=//div[@class='nav-links']//a[contains(@class, 'next')]/@href, depth=2)
  //url(//article[@id="all-people-and-profiles"]//div[@class='directory']//h2//a/@href)
    / map {
        'name': (//h1[@class='page-title']/text())[1] ! string(.),
        'url': string(base-uri(.)),
        'title': (//h2[@class='title-department']/text())[1] ! string(.),
        'email': (//a[contains(@href, 'mailto:')]/@href)[1] ! string(.)
    }
"""

items = list(wxpath.wxpath_async_blocking_iter(path_expr, max_depth=2))
```