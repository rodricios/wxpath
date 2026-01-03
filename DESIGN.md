# `wxpath`: A Declarative Language for Web Graph Traversal

## Contents

- [Preface](#preface)
- [Mental Model](#mental-model)
- [Fundamentals: Constructing the Language](#fundamentals-constructing-the-language)
- [**(TL;DR)** Summary: Grammar, Constraints, Invariants ](#summary-grammar-constraints-invariants)
- [Rewrite Rules](#rewrite-rules)
- [Open for discussion](#open-for-discussion)

## Preface

### Motivation

Existing crawlers treat the web as an imperative control-flow problem. XPath treats documents as trees. `wxpath` treats the web as a graph, and lets you describe traversal and extraction declaratively.

This document will describe, from the ground up and with examples, the `wxpath` domain-specific language (DSL).

By the conclusion, we will have presented: 

1. The DSL's syntax and operators. 
2. The grammar/ruleset. 
3. The language's operational constraints and invariants. 

## Mental Model

Think of `wxpath` as applying XPath-style queries over a web graph rather than a single document tree.

- Documents are nodes
- Hyperlinks are directed edges
- `url()` expands the "frontier" (a queue of URLs to crawl)
- `///` performs repeated frontier expansion<sup>*</sup>
- XPath extracts structure from each visited node

<sup>*</sup> The term "recursive" is used informally in this document, however, I do not mean DFS-style recursion. `wxpath` uses a FIFO queue, and we expand that queue by visiting the URLs present in the _current document_.

## Fundamentals: Constructing the Language

### The `url()` operator

Let's begin with simplest operator in the `wxpath` DSL: `url('...')`.

The operator accepts a string, and returns an `lxml.html.HtmlElement` object:

```
url('https://example.org/') -> HtmlElement
```

Because the resulting object is an `lxml.html.HtmlElement`, the `wxpath` DSL can be used to retrieve inter-document nodes/attributes/values by chaining the `url` operator with an `xpath` expression. 

Example usage:

```
url('https://example.org/')<xpath> -> [Any type provided by lxml, or by elementpath]

e.g.,
# NOTE: adding spaces for clarity
url('https://example.org/') // a / @href -> ['/relative-url', 'absolute-url']

# XPath3 required
url('https://example.org/') / map { 'title': <xpath> } -> XPathMapObject
```


In Python, the above expression would look like:

```python
# Illustrative code
import requests, lxml.html

etree = lxml.html.fromstring(requests.get('https://example.org/'))
etree.xpath('//a/@href')
```

As we progress through this document, we will build up the ruleset and constraints for the `wxpath` DSL. 

So far, the ruleset is simple:

```
Expression        := Segment*
Segment           := UrlSegment | XPathSegment

UrlSegment        := url('literal-url')
XPathSegment      := <any valid XPath expression>
```

The `Expression` rule is the root of the ruleset. The `Segment` rule is a catch-all for any valid `xpath` expression or expression containing the  `url` operator. 


We also see our first constraint: 

```
Constraint C1:
An expression must begin with a UrlLitSegment.

UrlLitSegment := url('literal-url')
```

Those examples are fairly straight-forward. Now let's introduce more complexity by asking the question: 

What if we want to retrieve the HTML documents of the immediate children of the first retrieved document?

```
url('...') / url(./a/@href) -> list of HtmlElement documents whose URLs were retrieved via xpath
```

The above expression can be interpretted like so: 

```python
etree = lxml.html.fromstring(requests.get('https://example.org/'))

responses = []
for url in etree.xpath('./a/@href'): 
    # assuming absolute URLs
    responses.append(lxml.html.fromstring(requests.get(url))) 
```

You'll notice that we've overridden the `url` operator to _also_ accept an `xpath` expression.

Let's update our grammar:

```
Expression      := Segment*
Segment         := UrlSegment | XPathSegment

UrlSegment      := UrlLitSegment | UrlEvalSegment
XPathSegment    := <any valid XPath expression>

UrlLitSegment   := url('literal-url')
UrlEvalSegment  := /url(<xpath that produces list of URLs>)     

Constraint C1:
An expression must begin with a UrlLitSegment.
```

When the `wxpath` runtime engine encounters a `/url` (or `//url`) subexpression, the engine will **asynchronously** yield each `HtmlElement` node to the user, allowing the user to then apply `xpath` expressions on each yielded `HtmlElement` node (but we'll get to this later).

As previously hinted, `wxpath` allows for the double-slash `//url` syntax:

```
url('...') // url(a/@href) -> list of HtmlElement documents whose URLs were retrieved via xpath
```

The equivalent Python code:

```python
responses = []
for url in etree.xpath('//a/@href'): 
    responses.append(lxml.html.fromstring(requests.get(url))) # assuming full URLs
```

The key difference between `/url(<xpath>)` and `//url(<xpath>)` is how the runtime engine associates the `<xpath>` to its axes. Single slash `/url` will attach the `xpath` expression to the "Child Axis", and the double slash `//url` will attach the `xpath` expression to the "Descendant-or-self Axis". Once the axes is selected, the `xpath` argument will be appended (and potentially chomped) to the axes. 


Updated grammar: 

```
Expression      := Segment*
Segment         := UrlSegment | XPathSegment  

UrlSegment      := UrlLitSegment | UrlEvalSegment
XPathSegment    := <any valid XPath expression>

UrlLitSegment   := url('literal-url')
UrlEvalSegment  := /url(XPathExprToURLs) | //url(XPathExprToURLs)

XPathExprToURLs := <xpath that produces list of URLs> 
```


Now, consider the following:

```
url('...') // a / @href/url(.)
```


Our grammar does not need to be updated as it supports the above constructions via the `Expression` and `Segment` rules:

```
Expression      := Segment*
Segment         := UrlSegment | XPathSegment  
UrlSegment      := UrlLitSegment | UrlEvalSegment
```

The resolved expression: `Expression = [UrlLitSegment, XPathSegment, UrlEvalSegment]`

Due to the expensive nature of URL requests, the engine can't really afford to nor does it make sense to adopt the same node-selection-and-function-application semantics present in traditional `xpath`. 

Consider:

```
//div//*/fn:count(//a)
```

What the above expression will do is traverse the entire subtree underneath `//div`, visiting each node in said subtree, and for every visited noted, it will apply `fn:count(//a)`, which globally counts all `<a>` nodes in the HTML. What that means is, if there are 5 nodes in the tree, and 2 of them are `<a>` nodes, then result of the `xpath` `//div//*/fn:count(//a)` is: `[2, 2, 2, 2, 2]`. A similar pattern is observed when we replace the global axis (`//`) with child axis (`/`), e.g. `/div//*/fn:count(//a)` or `//div//*/fn:count(/a)` or `/div//*/fn:count(/a)` 

The same semantics will not be applied in wxpath, since adopting such semantics would imply issuing the same set of requests (as selected by the `url`'s `xpath`) at every node. 

**Invariant: url() is evaluated per document, never per XPath node.**

Therefore, the parser will raise errors if an `XPathExpr` is followed by a `UrlEvalSegment` that  contains a `XPathExprToURLs` which begins with an global or child axis selector (`/` or `//`).

The following will raise syntax errors: 

```
url('...') / div // * /url(/a/@href)   -> SyntaxError
url('...') / div // * /url(//a/@href)  -> SyntaxError
url('...') // div // * /url(/a/@href)  -> SyntaxError
url('...') // div // * /url(//a/@href) -> SyntaxError
```

**Invariant: the `<xpath>` in `url(<xpath>)` may not begin with / or // if following an `XPathSegment`.**

As stated previously, and as the key takeaway from the `/url` and `//url` concepts introduced above, the output of such `wxpath` expressions will yield `HtmlElement` nodes (or a list of HtmlElement nodes if collected). 

What if you want to apply an `xpath` expression to each of those yielded `HtmlElement` nodes? You can!

```
url('example.org') // url( //a/@href ) // a / @href
```

The above `wxpath` expression accomplishes the following: 

1. Hop to 'example.org' (`depth=0`)
2. for each `<a @href>`
    1. hop to each url (`depth=1`)
    2. return all `<a @href>`
3. yield each result

That's all fine, but now you just have a list of lists of links. If you wanted to more structured data:

```xpath
(: split lines for readability :)
url('example.org') 
    // url( //a/@href ) 
        / map {
            'url': string(base-uri(.)),
            'links': //a/@href
        }
```

What you've just described is a crawl job up to `depth=1` (two levels) that produces a structured representation of the small part of the web that connects to example.org.

Once again, our grammar does not need to be updated. The above `wxpath` expression is described with the following resolved expression: 

`Expression = [UrlLitSegment, UrlEvalSegment, XPathSegment]`

---

### Recursive Crawl

Now, let's introduce the `///` syntax/operator. `///` denotes a recursive crawl. 

As stated in a note above, the term "recursive" is used informally here, however, I do not mean DFS-style recursion. I use "recursive" in the sense that the engine will re-enqueue the selected links _from the current document_ to the crawl queue, and eventually hop to them, eventually repeating the process for each link.

Example:

```
url('https://example.org/') /// url(//a/@href)
```

The above `wxpath` expression will execute the following: 

1. Hop to 'example.org' (`depth=0`)
2. Enqueue all `<a @href>` present in the document to the crawl queue
3. Pop from the crawl queue and hop to the url
4. `yield` all current document's `<a @href>` to the user
5. GO TO STEP 2


What this roughly looks like in Python code: 


```python
# Illustrative pseudocode (not intended to be run)
seen = set()

def crawl(etree, xpath_expr):
    responses = []
    for url in etree.xpath(xpath_expr): 
        if url in seen:
            continue
        seen.add(url)
        # assuming absolute URLs
        responses.append(lxml.html.fromstring(requests.get(url).content)) 

    return responses + [crawl(r, xpath_expr) for r in responses]

etree = lxml.html.fromstring(requests.get('https://example.org/').content)

responses = crawl(etree, '//a/@href')
```

The above code will likely not run, for a number of reasons, but I hope you get the point: it performs a recursive, unbounded crawl. Without some kind of upper bound, and assuming a closed web, and assuming that all inputs to `requests.get` are correct, and assuming no other errors arise, and a number of other ideal factors, it will not stop until all urls in the web are visited. 

While the above code captures the recursive crawling abilities of the `///url(//a/@href)` expression, what isn't captured is the fact that `wxpath` is **asynchronous**, it handles errors, it bounds the crawl (by depth), and it yields the result of each requested response as they **arrive**, allowing you to chain more `wxpath` expressions. 

Updated grammar ruleset: 

```
Expression        := Segment*
Segment           := UrlSegment | XPathSegment  

UrlSegment        := UrlLitSegment | UrlEvalSegment | UrlRecurseSegment
XPathSegment      := <any valid XPath expression>

UrlLitSegment     := url('literal-url')
UrlEvalSegment    := /url(XPathExprToURLs) | //url(XPathExprToURLs)
UrlRecurseSegment := ///url(XPathExprToURLs)

XPathExprToURLs   := <xpath that produces list of URLs> 
```


In `wxpath`, as already mentioned, `///` will trigger a recursive crawl, yielding each response (`HtmlElement` node) as they arrive. However, if you want to apply an `xpath` expression to each yielded `HtmlElement` node, the `wxpath` runtime engine allows for that too:

```
(: split lines for readability :)
url('example.org') 
    /// url( //a/@href ) 
        / map {
            'url': string(base-uri(.)),
            'links': //a/@href
        }
```

The grammar ruleset stays the same, however, due to the inherently expensive and "explosive" implications of recursively crawling the web, `wxpath` contains another constraint:

```
Constraint C2:

At most one recursive UrlSegment (UrlRecurseSegment) may appear in an Expression.
```


## Summary: Grammar, Constraints, Invariants

`wxpath` is a declarative DSL that is specified using a small grammar of composable `segments`. Functionally, `wxpath` comes with its own runtime engine that handles the evaluation of `wxpath` expressions, asynchronous requests, and operator execution.

Key takeaways: 

| Syntax    | Meaning | 
| --------- | ------- | 
| `<xpath>` | Traditional XPath used for extraction; can affect crawl direction  |
| `url('...' \| <xpath>)`   | Expands crawl frontier |
| `/url(<xpath>)`   | Generate crawl intents from current document, once | 
| `//url(<xpath>)`  | Same as /url(x) but with descendant axis for XPath |
| `///url(<xpath>)` | Generate crawl intents and re-enqueues recursively |


The ruleset: 

```
Expression        := Segment*
Segment           := UrlSegment | XPathSegment  

UrlSegment        := UrlLitSegment | UrlEvalSegment | UrlRecurseSegment

XPathSegment      := <any valid XPath expression>

UrlLitSegment     := url('literal-url')
UrlEvalSegment    := /url(XPathExprToURLs) | //url(XPathExprToURLs)
UrlRecurseSegment := ///url(XPathExprToURLs)

XPathExprToURLs   := <xpath that produces list of URLs> 
```

The constraints and invariants:

```
Constraints:
C1: An expression must begin with a UrlLitSegment.
C2: At most one recursive UrlSegment (UrlRecurseSegment) may appear in an Expression.

Invariants: 
I1: url() is evaluated per document, never per XPath node
I2: UrlEvalSegments cannot appear at the start of an Expression
I3: UrlEvalSegments's XPathExprToURLs may not begin with / or // if following an XPath segment
```


### Rewrite Rules

This section is is here to describe the nuances related to the chomping and joining of XPath expressions. XPath chomps and joins, and `wxpath` does too.

The following are equivalent expressions to the expression `url('...') / url(a/@href)`:
```
url('...') / url(a/@href)   ==
url('...') / url(./a/@href) 
```

The following are equivalent expressions to the expression `url('...')//url(a/@href)`:

```
url('...') //url( a/@href )   ==
url('...') //url( ./a/@href ) ==
url('...') //url( //a/@href ) ==
url('...')  /url( //a/@href )
```

The expression `url('...') // a / @href /url(.)` is equivalent to: 

```xpath
url('...') // a / @href /url(.)  == 
url('...') // a / @href //url(.) ==   <!-- NOTE: this might change -->
url('...') /url( //a/@href )  
```


The following are equivalent expressions containg the `//url` expression:

```
url('...') // div / url( a/@href )      == 
url('...') // div / url(./a/@href)      ==
url('...') // div / a / @href / url(.)  ==
url('...') // url(//div/a/@href)

url('...') // div // url(a/@href)       == 
url('...') // div // url(./a/@href)     ==
url('...') // div // a / @href / url(.) ==
url('...') // url(//div//a/@href)
```

---


Some rewrite rules containing the `///url` expression:

```
url('...') /// url(//a/@href)        ==
url('...') /// url(.//a/@href)       ==
url('...') /// a / @href / url(.)

url('...') /// url(a/@href)          ==
url('...') /// url(/a/@href)         ==
url('...') /// url(./a/@href)        ==
url('...') /// ./ a / @href / url(.)
```

Alternative rules (and open to opinions):


```
url('...') /// url(//a/@href)     ==
url('...') /// url(.//a/@href)    ==
url('...') /// / a / @href / url(.)

url('...') /// url(a/@href)       ==
url('...') /// url(/a/@href)      ==
url('...') /// url(./a/@href)     ==
url('...') /// a / @href / url(.)
```

Another variation: 

```
url('...') /// url(//a/@href)     ==
url('...') /// url(.//a/@href)    ==
url('...') // a / @href /// url(.)

url('...') /// url(a/@href)       ==
url('...') /// url(/a/@href)      ==
url('...') /// url(./a/@href)     ==
url('...') / a / @href /// url(.)
```


## Open for discussion

Below are some of the language difficulties I encountered while writing `wxpath`:

### 1. The `url('...')[XPathExpr][URLWithXPath]` grammar rule

Introducing the `url('...')[XPathExpr][URLWithXPath]` rule (i.e. `url('...') // div / url( a/@href )`) was a difficulty because it required me to consider corner cases/exceptions related to joining xpaths (and to explicitly state those xpath-joining rules here and in code). 

### 2. Recursive crawl-and-extract from the get-go. 

The `wxpath` expression:

```
url('example.org') 
    /// url( //a/@href ) 
        / map {
            'url': string(base-uri(.)),
            'links': //a/@href
        }
```

... does not yield a 'map' object for the seed URL 'example.org' because the final, postfixed `xpath` (`/map{'url':...}`) expression is attached to the `///url(//a/@href)` expression. 

As of `wxpath` 0.2.0, we can have recursive crawls that begin from the seed URL **and** extract data from the seed url with the following expression:

```
url('example.org', follow=//a/@href)
    / map {
        'url': string(base-uri(.)),
        'links': //a/@href
    }
```

One alternative syntax (not currently present in the language) arises from simply dropping the `follow=` keyword argument parameter, and making the `follow` argument positional: 

```
url('example.org', //a/@href)
    / map {
        'url': string(base-uri(.)),
        'links': //a/@href
    }
```


Another alternative: 


```
//a/@href///url('example.org') or
///a/@href/url('example.org')
```

or perhaps:

```
( url('example.org') /// a / @href )
    / map {
        'url': string(base-uri(.)),
        'links': //a/@href
    }
```

The last captures the intended expression quite well. If implemented, it would exist purely as syntactic sugar, and probably a simple regex could capture it. 
