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


async def crawl(site_url):
    """Given `site_url`, just crawls that page and writes to stdout a sitemap"""

    tag_parser = TagParser({"a", "img"})
    yaml = YAML()
    yaml.register_class(Tag)  # TODO: consider nondefault serialization
    async with aiohttp.ClientSession() as session:
        async for chunk in fetch(session, site_url):
            for tag in tag_parser.consume(chunk):
                if tag.name == "a":
                    # NOTE: outputing a list takes advantage of YAML's
                    # serialization for lists, which is both concatable and
                    # tailable
                    yaml.dump([tag], sys.stdout)
                

if __name__ == "__main__":  # pragma: no cover
    asyncio.run(crawl(sys.argv[1]))
