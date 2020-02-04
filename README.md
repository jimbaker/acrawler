# acrawler

An asyncio-based crawler.

## Branches

### Basics branch

1. Package layout - https://docs.python-guide.org/writing/structure/
2. Async testing with pytest
3. asyncio "Hello, World" starter shell - https://docs.python.org/3/library/asyncio-task.html#coroutines

Plus additions to requirements.txt, etc.

### Crawl operations

1. Use aiohttp client to fetch pages
2. Wrap stdlib html.parser.HTMLParser to parse pages
3. Change crawl function to fetch and parse a page, not just sleep, and output a
   very basic sitemap based on YAML serialization
