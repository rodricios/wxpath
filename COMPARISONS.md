# Comparisons with Other Tools

This document will provide comparisons between **wxpath** and other web-scraping tools.


## Scrapy

From Scrapy's official [documentation](https://docs.scrapy.org/en/latest/intro/overview.html#walk-through-of-an-example-spider), here is an example of a simple spider that scrapes quotes from a website and writes to a file.

Scrapy: 

```python
import scrapy


class QuotesSpider(scrapy.Spider):
    name = "quotes"
    start_urls = [
        "https://quotes.toscrape.com/tag/humor/",
    ]

    def parse(self, response):
        for quote in response.css("div.quote"):
            yield {
                "author": quote.xpath("span/small/text()").get(),
                "text": quote.css("span.text::text").get(),
            }

        next_page = response.css('li.next a::attr("href")').get()
        if next_page is not None:
            yield response.follow(next_page, self.parse)

```

Then from the command line, you would run:

```bash
scrapy runspider quotes_spider.py -o quotes.jsonl
```


## wxpath

**wxpath** gives you two options: write directly from a Python script or from the command line.

```python
from wxpath import wxpath_async_blocking_iter 
from wxpath.hooks import registry, builtin

path_expr = """
url('https://quotes.toscrape.com/tag/humor/', follow=//li[@class='next']/a/@href)
  //div[@class='quote']
    /map{
      'author': (./span/small/text())[1],
      'text': (./span[@class='text']/text())[1]
      }
"""

registry.register(builtin.JSONLWriter(path='quotes.jsonl'))
items = list(wxpath_async_blocking_iter(path_expr, max_depth=3))
```

or

```bash
wxpath --depth 1 "\
url('https://quotes.toscrape.com/tag/humor/', follow=//li[@class='next']/a/@href) \
  //div[@class='quote'] \
    /map{ \
      'author': (./span/small/text())[1], \
      'text': (./span[@class='text']/text())[1] \
      }" > quotes.jsonl
```
