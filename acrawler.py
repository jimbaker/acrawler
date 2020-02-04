import argparse
import asyncio
import collections
import sys
from dataclasses import dataclass
from html.parser import HTMLParser

import aiohttp
from ruamel.yaml import YAML


class CollectorHTMLParser(HTMLParser):
    """Subclasses `HTMLParser` to call `collector` on each matching tag in `collect_tags`"""
    def __init__(self, collect_tags, collector):
        self.collect_tags = collect_tags
        self.collector = collector
        super().__init__()

    def handle_starttag(self, tag, attrs):
        if tag in self.collect_tags:
            self.collector((tag, attrs))


@dataclass
class Tag:
    name: str
    attrs: dict
    

class TagParser:
    """For each chunk passed to `consume`, yields the corresponding tags.

    This design allows us to fan out from a chunk of HTML text that has been
    fetched to the corresponding tags, possibly none.

    Uses an inheritance by composition design on the underlying HTMLParser
    class."""
    def __init__(self, collect_tags):
        self.queue = collections.deque()
        self.html_parser = CollectorHTMLParser(collect_tags, self.queue.append)

    def consume(self, chunk):
        self.html_parser.feed(chunk)
        while self.queue:
            tag, attrs = self.queue.popleft()
            yield Tag(tag, dict(attrs))


async def fetch(session, url, chunk_size=8192):
    """Given `session`, yields string chunks from the `url`"""
    async with session.get(url) as response:
        while True:
            chunk = await response.content.read(chunk_size)
            if not chunk:
                break
            else:
                # HTMLParser wants str, not bytes, so coerce accordingly,
                # assuming UTF-8
                # FIXME: doublecheck text encoding support
                yield str(chunk)


class Crawler:

    def __init__(self, root_urls, max_pages=5, output=sys.stdout):
        self.root_urls = root_urls
        self.max_pages = max_pages
        self.output = output
        self.frontier = collections.deque(root_urls)
        self.count_pages = 0
        self.seen = {}

    async def crawl(self):
        while self.frontier and self.count_pages < self.max_pages:
            await self.crawl_next()
            self.count_pages += 1

    async def crawl_next(self):
        """Crawls the next url from the `frontier`, writing to stdout a sitemap"""

        # TODO: support other policies in addition to breadth-first traversal of
        # the frontier
        url = self.frontier.popleft()

        tag_parser = TagParser({"a", "img"})
        yaml = YAML()
        yaml.register_class(Tag)  # TODO: consider nondefault serialization

        # TODO: session init can be shared across crawling a given site
        async with aiohttp.ClientSession() as session:
            async for chunk in fetch(session, url):
                # TODO: add anchor tags to frontier if not seen, etc;
                # also refactor this code a bit
                for tag in tag_parser.consume(chunk):
                    if tag.name == "a":
                        # NOTE: outputing a list takes advantage of YAML's
                        # serialization for lists, which is both concatable and
                        # tailable
                        yaml.dump([tag], self.output)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Crawl specified URLs.")
    parser.add_argument("roots", metavar="URL", nargs="+",
                        help="List of URL roots to crawl")
    parser.add_argument("--max", type=int, default=5, help="Maximum number of pages to crawl")
    # FIXME: add other output location than sys.stdout
    return parser.parse_args(argv)


async def main(argv):
    args = parse_args(argv)
    crawler = Crawler(args.roots, args.max, sys.stdout)
    await crawler.crawl()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main(sys.argv))
