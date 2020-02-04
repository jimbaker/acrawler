import argparse
import asyncio
import collections
import sys
import urllib
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
    url: str
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
            tagname, attrs = self.queue.popleft()
            yield Tag(tagname, None, dict(attrs))


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


def resolve_url(root, url):
    """Return  url` rewritten to use absolute scheme/netloc from root.
    
    Fragments are discarded, but queries are retained.

    A single trailing slash is equivalent to an empty path; otherwise it is
    treated as distinct; see https://searchfacts.com/url-trailing-slash/
    
    NOTE that we need to separately consider redirects (301), including with
    respect to http/https schemes and trailing slash.
    """
    parsed_root = urllib.parse.urlsplit(root)
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        parsed.scheme if parsed.scheme else parsed_root.scheme,
        parsed.netloc if parsed.netloc else parsed_root.netloc,
        parsed.path if parsed.path != "/" else "",
        parsed.query,
        ""
    ))


class Crawler:

    def __init__(self, root_urls, max_pages=5, output=sys.stdout):
        self.root_urls = root_urls
        self.max_pages = max_pages
        self.output = output
        self.frontier = collections.deque(root_urls)
        self.count_pages = 0
        self.seen = set()

    async def crawl(self):
        yaml = YAML()
        yaml.register_class(Tag)  # TODO: consider nondefault serialization

        while self.frontier and self.count_pages < self.max_pages:
            async for tag in self.crawl_next():
                # NOTE: outputing a list takes advantage of YAML's
                # serialization for lists, which is both concatable and
                # tailable
                yaml.dump([tag], self.output)
            self.count_pages += 1

    async def crawl_next(self):
        """Crawls the next url from the `frontier`, writing to stdout a sitemap"""

        # TODO: support other policies in addition to breadth-first traversal of
        # the frontier
        url = self.frontier.popleft()
        if url in self.seen:
            return
        self.seen.add(url)

        tag_parser = TagParser({"a", "img"})

        # TODO: session init can be shared across crawling a given site
        async with aiohttp.ClientSession() as session:
            async for chunk in fetch(session, url):
                # TODO: add anchor tags to frontier if not seen, etc;
                # also refactor this code a bit
                for tag in tag_parser.consume(chunk):
                    if tag.name == "a" and "href" in tag.attrs:
                        tag.url = resolve_url(url, tag.attrs["href"])
                        self.frontier.append(tag.url)
                        yield tag


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Output sitemap by crawling specified root URLs.")
    parser.add_argument("roots", metavar="URL", nargs="+",
        help="List of URL roots to crawl")
    parser.add_argument("--max", type=int, default=5,
        help="Maximum number of pages to crawl")
    # FIXME: add other output location than sys.stdout
    return parser.parse_args(argv)


async def main(argv):
    args = parse_args(argv)
    crawler = Crawler(args.roots, args.max, sys.stdout)
    await crawler.crawl()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main(sys.argv[1:]))
