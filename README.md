# acrawler

acrawler, an asyncio-based crawler, is yet another crawler to demonstrate how to
scalably crawl web sites. It can also be readily adapted to crawl APIs, such as
YouTube's API.

* To install: `make init`
* To run tests: `make test`
* To create a coverage report `make coverage`

NOTE: This code requires the use of Python 3.8.

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