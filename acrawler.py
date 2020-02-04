import argparse
import asyncio
import collections
import math
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

    def __init__(self, root_urls, max_pages=5, num_workers=3, output=sys.stdout):
        self.root_urls = root_urls
        self.sites = set()
        self.max_pages = max_pages
        self.num_workers = num_workers
        self.output = output
        self.frontier = asyncio.Queue()
        self.count_pages = 0
        self.seen = set()

        for url in root_urls:
            parsed_url = urllib.parse.urlsplit(url)
            self.sites.add(parsed_url.netloc)
            self.frontier.put_nowait(url)

    async def crawl(self):
        """Create and run worker tasks to process the `frontier` concurrently"""
        
        # This method's implementation is modestly modified from the boilerplate
        # in https://docs.python.org/3/library/asyncio-queue.html#examples
        tasks = []
        for i in range(self.num_workers):
            task = asyncio.create_task(self.worker(f'worker-{i}'))
            tasks.append(task)

        # Wait until the frontier queue is fully processed.
        await self.frontier.join()
        
        # Cancel our worker tasks.
        for task in tasks:
            task.cancel()
        
        # Wait until all worker tasks are cancelled.
        await asyncio.gather(*tasks, return_exceptions=True)

    async def worker(self, name):
        yaml = YAML()
        yaml.register_class(Tag)  # TODO: consider nondefault serialization

        while self.count_pages < self.max_pages:
            # TODO: support other policies in addition to breadth-first
            # traversal of the frontier
            url = await self.frontier.get()
            async for tag in self.crawl_next(url):
                # NOTE: outputing a list takes advantage of YAML's
                # serialization for lists, which is both concatable and
                # tailable
                yaml.dump([tag], self.output)
            self.frontier.task_done()
            self.count_pages += 1
        
        # Drain the frontier - do not want to cause a DOS attack
        while True:
            url = await self.frontier.get()
            self.frontier.task_done()

    async def crawl_next(self, url):
        """Crawls the next url from the `frontier`, writing to stdout a sitemap"""
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
                        # TODO: repeat of the above parsing work, but of course
                        # minor amount of work
                        parsed_tag_url = urllib.parse.urlsplit(tag.url)

                        # Filter entries placed on the exploration frontier such
                        # that they are all prefixed by one of the root sites
                        if parsed_tag_url.netloc in self.sites:
                            self.frontier.put_nowait(tag.url)
                    elif tag.name == "img" and "src" in tag.attrs:
                        tag.url = resolve_url(url, tag.attrs["src"])

                    if tag.url is not None:
                        # for writing to the sitemap
                        yield tag
                        



def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Output sitemap by crawling specified root URLs.")
    parser.add_argument("roots", metavar="URL", nargs="+",
        help="List of URL roots to crawl")
    parser.add_argument("--num-workers", type=int, default=3,
        help="Number of workers to concurrently crawl pages")
    parser.add_argument("--max-pages", type=int, default=25,
        help="Maximum number of pages to crawl")
    parser.add_argument("--all", action="store_true",
        help="Retrieve all pages under the specified roots")
    # TODO: add other output location than sys.stdout
    return parser.parse_args(argv)


async def main(argv):
    args = parse_args(argv)
    if args.all:
        max_pages = math.inf
    else:
        max_pages = args.max_pages

    crawler = Crawler(args.roots, max_pages, args.num_workers, sys.stdout)
    await crawler.crawl()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main(sys.argv[1:]))
