# acrawler

acrawler, an asyncio-based crawler, is yet another crawler to demonstrate how to
scalably crawl web sites. It can also be readily adapted to crawl APIs, such as
YouTube's API.

* To install dependencies: `make init`
* To run tests: `make test`
* To create a coverage report `make coverage`

NOTE: This code requires the use of Python 3.8 (possibly lower). I recommend
using the standard support for virtual enviroments, namely something like the
following before running the make commands above:

```
$ python3.8 -m venv env_acrawler
$ . env_acrawler/bin/activate
$ make init
```

The above sets `python` to the appropriate version. You can then run with this
command:

```
$ python acrawler.py https://example.com
```

which will produce this YAML-serialized sitemap:

```
- !Tag
  name: a
  url: https://www.iana.org/domains/example
  attrs:
    href: https://www.iana.org/domains/example
```

If you are feeling bold, you can try running the crawler with the `--all` option
-- it will crawl all pages under the specified root. *This could be a large
result set.*

# TODOs

There are a number of straightforward FIXMEs in the code. Some additions:

* More extensive testing. Currently there is about 93% coverage, but this is
  mostly due to a functional testing. A little refactoring plus some more unit
  testing would be great, but of course async code is somewhat harder to test!

* Proper support of 301 Redirections, `robots.txt`, and other crawling niceties.

* API support would be readily supportable, with some additions on setting up
  the client connection, eg for API keys.

* Support for a scalable queue system like Redis. It would be straightforward to
  map our FIFO queues onto a Redis queue, including async support. Now you would
  have the potential to rival Google in your crawling ability, or at least
  [Scrapy](https://scrapy.org/).

# Branches

This project is a demonstration on how to approach the building of a scalable web
crawler by using asyncio. Therefore I have attached the sequence of branches
needed for this implementation.

### Basics branch

1. Package layout - https://docs.python-guide.org/writing/structure/
2. Async testing with pytest
3. asyncio "Hello, World" starter shell -
   https://docs.python.org/3/library/asyncio-task.html#coroutines

Plus additions to requirements.txt, etc.

Branch: https://github.com/jimbaker/acrawler/tree/basics

### Crawl operations branch

1. Use aiohttp client to fetch pages
2. Wrap stdlib html.parser.HTMLParser to parse pages
3. Change crawl function to fetch and parse a page, not just sleep, and output a
   very basic sitemap based on YAML serialization

Branch: https://github.com/jimbaker/acrawler/tree/operations

### Crawler branch

1. Implement basic crawling logic, including a set of seen URLs and a frontier
   that is used for scheduling.
2. Basic resolution of URLs from relative to absolute

Branch: https://github.com/jimbaker/acrawler/tree/crawler

## Task branch

1. Use asyncio's support for task management and use asyncio.Queue to manage the
   frontier.
2. Support draining the queue.
3. Output image tags as well in the sitemap.
3. Various updates to the README and more control of the crawling process.

Branch: https://github.com/jimbaker/acrawler/tree/task