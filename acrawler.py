import argparse
import asyncio
import collections
import math
import sys
import urllib
from dataclasses import dataclass
from html.parser import HTMLParser

import aiohttp
import aioredis
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
            tag, attrs = self.queue.popleft()
            yield Tag(tag, None, dict(attrs))


async def fetch(session, url, chunk_size=8192):
    """Given `session`, yields string chunks from the `url`"""
    async with session.get(url) as response:
        while True:
            chunk = await response.content.read(chunk_size)
            if not chunk:
                break
            else:
                # HTMLParser wants str, not bytes, so coerce accordingly.
                yield chunk.decode("utf-8")  # default encoding for aiohttp client


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


# Futures are not chainable (in the bind/flat map sense) - perhaps they should
# be like JS Promises; but some quick helper code works here just fine.
def make_future_result(value):
    future = asyncio.Future()
    future.set_result(value)
    return future


# FIXME Refactor the schedulers so they share a base class, in part to share common
# code

class SimpleScheduler:
    def __init__(self):
        self.frontier = asyncio.Queue()
        self._seen = set()

    def setup(self):
        return make_future_result(None)

    def close(self):
        return make_future_result(None)

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def add_to_frontier(self, url):
        if url not in self._seen:
            await self.frontier.put(url)

    async def join(self):
        await self.frontier.join()

    async def get(self):
        while True:
            url = await self.frontier.get()
            if url not in self._seen:
                self._seen.add(url)
                return url

    def qsize(self):
        return make_future_result(self.frontier.qsize())

    def count(self):
        # Strictly speaking, len(seen) is not the number of pages.
        # Once we implement redirect unification, need to consider that
        # separately.
        return make_future_result(len(self._seen))

    def seen(self):
        return make_future_result(self._seen)

    def drain(self):
        """Drain the frontier"""
        while True:
            try:
                self.frontier.get_nowait()
                self.frontier.task_done()
            except asyncio.queues.QueueEmpty:
                return make_future_result(None)
            
    def task_done(self):
        self.frontier.task_done()


# FIXME add TTL, including on seen for real stuff;
# see https://stackoverflow.com/questions/17060672/ttl-for-a-set-member

# FIXME factor out constants like "seen", etc keys - easy to get this mixed up

class RedisScheduler:
    def __init__(self, connstr="redis://localhost"):
        self.connstr = connstr

    async def setup(self):
        self.redis = await aioredis.create_redis_pool(self.connstr)
        tr = self.redis.multi_exec()
        tr.sinterstore("seen", "zero-out-with-nonexistent-set")
        tr.ltrim("frontier", 1, 0)
        await tr.execute()

        # Avoid data races by combining ops into a script for all-or-nothing
        # semantics
        self.get_url_script_sha1 = await self.redis.script_load("""
            local frontier_key = KEYS[1]
            local seen_key = KEYS[2]
            local url = redis.call('RPOP', frontier_key)
            if url then
              if redis.call('SISMEMBER', seen_key, url) == 0 then
                redis.call('SADD', seen_key, url)
                return url
              else
                return nil
              end
            else
              return nil
            end
            """)

    async def close(self):
        self.redis.close()
        await self.redis.wait_closed()

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def add_to_frontier(self, url):
        await self.redis.lpush("frontier", url.encode("utf-8"))

    async def join(self):
        # Poll for the frontier to be empty.
        #
        # NOTE: There's probably a better way to do this! 
        #
        # The slightly more complicated solution would be to do keyspace
        # notification on the frontier, then subscribe to that channel using
        # a blocking approach. Let's do that.
        while True:
            count_urls = await self.redis.llen("frontier")
            if count_urls == 0:
                return
            await asyncio.sleep(1.0)

    async def get(self):
        while True:
            encoded_url = await self.redis.evalsha(
                self.get_url_script_sha1, keys=["frontier", "seen"])
            if encoded_url:
                return encoded_url.decode("utf-8")

    async def qsize(self):
        return await self.redis.llen("frontier")

    async def count(self):
        # NOTE: strictly speaking, len(seen) is not the number of pages. Once
        # we implement redirect unification, need to consider that separately
        count_pages = await self.redis.scard("seen")
        return count_pages

    async def seen(self):
        return {url.decode("utf-8") for url in await self.redis.smembers("seen")}

    async def drain(self):
        """Drain the frontier"""
        await self.redis.ltrim("frontier", 1, 0)
        
    def task_done(self):
          # FIXME use this entry point as part of to-be-implemented worker task
          # queue (with RPOPLPUSH) so we don't lose track of work items
        pass


class Crawler:
    """Crawls URLs using async tasks and an in-memory frontier queue"""
    
    def __init__(self, scheduler, collector, storage, max_pages=5, num_workers=3):
        self.scheduler = scheduler
        self.collector = collector
        self.storage = storage

        self.sites = set()
        self.max_pages = max_pages
        self.num_workers = num_workers

    async def crawl(self, root_urls):
        """Create and run worker tasks to process the `frontier` concurrently"""
        await self.scheduler.setup()
        for url in root_urls:
            parsed_url = urllib.parse.urlsplit(url)
            self.sites.add(parsed_url.netloc)
            await self.scheduler.add_to_frontier(url)

        # This method's implementation is modestly modified from the boilerplate
        # in https://docs.python.org/3/library/asyncio-queue.html#examples
        tasks = []
        for i in range(self.num_workers):
            task = asyncio.create_task(self.worker(f'worker-{i}'))
            tasks.append(task)

        # Wait until the frontier queue is fully processed.
        await self.scheduler.join()
        
        # Cancel our worker tasks.
        for task in tasks:
            task.cancel()
        
        # Wait until all worker tasks are cancelled.
        await asyncio.gather(*tasks, return_exceptions=True)

    async def worker(self, name):
        # TODO: when crawling APIs/password protected sites, this should be done
        # per site - presumably this can be memoized
        async with self.collector() as session:
            while True:
                count_pages = await self.scheduler.count()
                if count_pages >= self.max_pages:
                    break
                url = await self.scheduler.get()
                async for tag in self.crawl_next(session, url):
                    self.storage([tag])
                self.scheduler.task_done()
        
        # Retrieved the maximum number of pages, and we do not want to cause a
        # DOS attack
        await self.scheduler.drain()

    async def crawl_next(self, session, url):
        """Crawls the next url from the `frontier`, processing tags for the sitemap"""
        tag_parser = TagParser({"a", "img"})

        # TODO: support 301, error handling in general here
        async for chunk in fetch(session, url):
            for tag in self.process_sitemap_tags(url, tag_parser, chunk):
                yield tag
                # Filter entries placed on the exploration frontier such
                # that they are all prefixed by one of the root sites
                if tag.name == "a":
                    parsed_tag_url = urllib.parse.urlsplit(tag.url)
                    if parsed_tag_url.netloc in self.sites:
                        await self.scheduler.add_to_frontier(tag.url)

    def process_sitemap_tags(self, url, tag_parser, chunk):
        """Yields sitemap tags and added to `frontier` if under `roots`"""
        # TODO: This method should be refactored so it is a separate pluggable
        # factory, much like session_maker and serializer. This work will
        # require revisiting the tag_parser/chunk calling convention from
        # crawl_next.
        for tag in tag_parser.consume(chunk):
            if tag.name == "a" and "href" in tag.attrs:
                tag.url = resolve_url(url, tag.attrs["href"])

            elif tag.name == "img" and "src" in tag.attrs:
                tag.url = resolve_url(url, tag.attrs["src"])

            if tag.url is not None:
                # If there's now a url defined, then it is part of the sitemap
                yield tag


def parse_args(argv):
    """Parse command line arguments and return an argparse `Namespace`"""
    parser = argparse.ArgumentParser(
        description="Output sitemap by crawling specified root URLs.")
    parser.add_argument(
        "roots", metavar="URL", nargs="+",
        help="List of URL roots to crawl")
    parser.add_argument(
        "--redis", metavar="CONNSTR",
        help="Use Redis with specified connection string (ex: redis://localhost)")
    parser.add_argument(
        "--num-workers", type=int, default=3,
        help="Number of workers to concurrently crawl pages")
    parser.add_argument(
        "--max-pages", type=int, default=25,
        help="Maximum number of pages to crawl")
    parser.add_argument(
        "--all", action="store_true",
        help="Retrieve all pages under the specified roots")
    parser.add_argument(
        "--out", type=argparse.FileType('w'),
        default=sys.stdout,
        help="Output file, defaults to stdout")

    args = parser.parse_args(argv)
    if args.all:
        args.max_pages = math.inf
    return args


async def main(argv):
    """Runs a crawler under an event loop"""
    args = parse_args(argv)
    yaml = YAML()
    yaml.register_class(Tag)

    def serializer(objs):
        # NOTE: outputing a list takes advantage of YAML's
        # serialization for lists, which is both concatable and
        # tailable
        yaml.dump(objs, sys.stdout)

    if args.redis:
        scheduler = RedisScheduler(args.redis)
    else:
        scheduler = SimpleScheduler()
    async with scheduler as open_scheduler:
        crawler = Crawler(
            open_scheduler, aiohttp.ClientSession, serializer,
            args.max_pages, args.num_workers)
        await crawler.crawl(args.roots)
                

if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main(sys.argv[1:]))
