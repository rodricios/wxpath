
# Examples

The following examples demonstrate various web crawling and data extraction tasks using wxpath.

## EXAMPLE 1 - Simple, single page crawl and link extraction 

Starting from Expression language's wiki, extract all links (hrefs) from the main section. The `url(...)` operator is used to execute a web request to the specified URL and return the HTML content.

```python
import wxpath

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')//main//a/@href"
items = wxpath.wxpath_async_blocking(path_expr)
```


## EXAMPLE 2 - Two-deep crawl and link extraction

Starting from Expression language's wiki, crawl all child links  starting with '/wiki/', and extract each child's links (hrefs). The `url(...)` operator is pipe'd arguments from the evaluated XPath.

```python
import wxpath

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')//url(//@href[starts-with(., '/wiki/')])//a/@href"
items = wxpath.wxpath_async_blocking(path_expr)
```


## EXAMPLE 3 - Infinite crawl with BFS tree depth limit

Starting from Expression language's wiki, infinitely crawl all child links (and child's child's links recursively). The `///` syntax is used to indicate an infinite crawl. Returns lxml.html.HtmlElement objects.

```python
import wxpath

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///url(//main//a/@href)"
# Modify (inclusive) max_depth to limit the BFS tree (crawl depth).
items = wxpath.wxpath_async_blocking(path_expr, max_depth=1)
```

## EXAMPLE 4 - Infinite crawl with field extraction

Infinitely crawls Expression language's wiki's child links and childs' child links (recursively) and then, for each child link crawled, extracts objects with the named fields as a dict.

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

# Under the hood of wxpath.core.wxpath, we generate `segments` list, 
# revealing the operations executed to accomplish the crawl.
# >> segments = wxpath.core.parser.parse_wxpath_expr(path_expr); 
# >> segments
# [Segment(op='url', value='https://en.wikipedia.org/wiki/Expression_language'),
#  Segment(op='url_inf', value='///url(//main//a/@href)'),
#  Segment(op='xpath', value='/map {        \'title\':(//span[contains(@class, "mw-page-title-main")]/text())[1],         \'short_description\':(//div[contains(@class, "shortdescription")]/text())[1],        \'url\'://link[@rel=\'canonical\']/@href[1]    }')]
```

## EXAMPLE 5 = Seeding from XPath function expression + mapping operator (`!`)

Functionally create 10 Amazon book search result page URLs, map each URL to the url(.) operator, and for each page, extract the title, price, and link of each book listed.
 

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

**wxpath** also provides the `follow` parameter, which allows you to specify a follow path for pagination.
This will be depth-capped according to the `max_depth` parameter.

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