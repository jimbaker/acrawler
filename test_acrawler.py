import asyncio
import collections
import contextlib
import functools
import math
import unittest

import acrawler
import pytest
from acrawler import Tag
from ruamel.yaml import YAML

# NOTE: https://bugs.python.org/issue38529
# "Python 3.8 improperly warns about closing properly closed streams" - fixed in 3.8.1

# Based on the page from https://example.com
example_html = """
<!doctype html>
<html>
<head>
    <title>Example Domain</title>
</head>
<body>
<div>
    <h1>Example Domain</h1>
    <p><a href="https://www.iana.org/domains/example">More information...</a></p>
</div>
</body>
</html>
"""


def make_fake_http_session(data):
    # The aiohttp client is a bit complex, so creating a fake is likewise
    # complex!

    class FakeContent:
        def __init__(self, num_chunks=13):
            chunk_length = len(data) // num_chunks
            self.chunks = collections.deque()
            for i in range(num_chunks - 1):
                self.chunks.append(
                    data[(i * chunk_length):((i + 1) * chunk_length)])
            self.chunks.append(data[((num_chunks - 1) * chunk_length):])

        def read(self, chunk_size):
            fake_result = asyncio.Future()
            try:
                chunk = self.chunks.popleft()
                fake_result.set_result(chunk)
            except IndexError:
                fake_result.set_result(None)
            return fake_result

    class FakeResponse:
        def __init__(self):
            self.content = FakeContent()

    class FakeAsyncContextManager:
        def __init__(self):
            self.response = FakeResponse()

        def __aenter__(self):
            fake_response = asyncio.Future()
            fake_response.set_result(self.response)
            return fake_response

        def __aexit__(self, exc_type, exc, tb):
            fake_exit = asyncio.Future()
            fake_exit.set_result(None)
            return fake_exit

    class FakeSession:
        def get(self, url):
            return FakeAsyncContextManager()

        def __aenter__(self):
            fake_response = asyncio.Future()
            fake_response.set_result(self)
            return fake_response

        def __aexit__(self, exc_type, exc, tb):
            fake_exit = asyncio.Future()
            fake_exit.set_result(None)
            return fake_exit

    return FakeSession()


def test_tag_parser():
    tag_parser = acrawler.TagParser({"a"})
    assert list(tag_parser.consume(example_html)) == [
        acrawler.Tag(
            "a", None, {"href": "https://www.iana.org/domains/example"})]


@pytest.mark.asyncio
async def test_fetch():
    chunks = []
    async for chunk in acrawler.fetch(
        make_fake_http_session(
            bytes(example_html, "utf-8")), "https://url-is.invalid"):
        chunks.append(chunk)
    assert "".join(chunks) == example_html


reference_loop_html = """
<body>
    <p><a href="https://reference-loop.example">Click to loop again...</a></p>
</body>
"""


# Yes, there is https://github.com/guillotinaweb/pytest-docker-fixtures, with support for Redis among others;
# TBD how well it works!
# See https://guillotina.io/ (a Plone project)

# Need to make Redis testing an optional dependency, possibly along with using Docker;
# use cmdopt fixture support for this; https://docs.pytest.org/en/latest/example/simple.html

# Note that we may want to scope to the module, instead of using function
# scope, to avoid the overhead of spinning up/down a Redis instance with
# Docker (once we implement that). But first see if that's a real cost.

@pytest.fixture(params=[acrawler.SimpleScheduler, acrawler.RedisScheduler])
async def scheduler(request, event_loop):
    my_scheduler = request.param()
    yield my_scheduler
    await my_scheduler.close()


@pytest.mark.asyncio
async def test_scheduler(scheduler):
    await scheduler.setup()

    await scheduler.add_to_frontier("https://some.example")
    assert await scheduler.qsize() == 1
    assert await scheduler.count() == 0
    assert await scheduler.get() == "https://some.example"
    scheduler.task_done()
    assert (await scheduler.qsize()) == 0
    assert (await scheduler.count()) == 1

    await scheduler.add_to_frontier("https://another.example")
    await scheduler.add_to_frontier("https://yet-another.example")
    await scheduler.add_to_frontier("https://one-more.example")
    assert (await scheduler.qsize()) == 3
    assert (await scheduler.count()) == 1
    await scheduler.drain()
    assert (await scheduler.qsize()) == 0
    assert (await scheduler.count()) == 1

    await scheduler.join()


@pytest.mark.asyncio
async def test_crawler(scheduler):
    fake_session_maker = functools.partial(
        make_fake_http_session, bytes(example_html, "utf-8"))

    tags = []
    def serializer(objects):
        tags.append(objects)

    crawler = acrawler.Crawler(
        scheduler, fake_session_maker, serializer,
        num_workers=1, max_pages=1)
    await crawler.crawl(
        ["https://url-is.invalid", "https://another-url-is.invalid"])
    assert tags == [[Tag(
        "a", "https://www.iana.org/domains/example",
        {"href": "https://www.iana.org/domains/example"})]]
    assert await crawler.scheduler.qsize() == 0
    assert await crawler.scheduler.count() == 1


@pytest.mark.asyncio
async def test_reference_loop(scheduler):
    fake_session_maker = functools.partial(
        make_fake_http_session, bytes(reference_loop_html, "utf-8"))

    tags = []
    def serializer(objects):
        tags.append(objects)

    crawler = acrawler.Crawler(
        scheduler, fake_session_maker, serializer)
    await crawler.crawl(["https://reference-loop.example"])
    assert tags == [[Tag(
        "a", "https://reference-loop.example",
        {"href": "https://reference-loop.example"})]]
    assert await crawler.scheduler.qsize() == 0
    assert await crawler.scheduler.seen() == {"https://reference-loop.example"}


misc_tags_html = """
<head>
    <script src="https://cdn.example/some-javascript.js">Ignored</script>
</head>
<body>
    <img src="image-123.jpeg"/>
    <p><a href="https://this.example/page2">Click for a page</a></p>
    <p><a href="https://another.example">Click for another page</a></p>
</body>
"""

def test_process_sitemap_tags():
    crawler = acrawler.Crawler(None, None, None)
    tag_parser = acrawler.TagParser({"a", "img"})
    tags = list(crawler.process_sitemap_tags(
        "https://this.example", tag_parser, misc_tags_html))

    assert tags == [
        acrawler.Tag("img", "https://this.example/image-123.jpeg",
                     {"src": "image-123.jpeg"}),
        acrawler.Tag("a", "https://this.example/page2",
                     {"href": "https://this.example/page2"}),
        acrawler.Tag("a", "https://another.example",
                     {"href": "https://another.example"})
    ]


def test_parse_command_line_some_pages():
    args = acrawler.parse_args(
        "--max-pages=42 "
        "https://example.com https://example.org https://example.net".split())
    assert args.roots == [
        "https://example.com",
        "https://example.org",
        "https://example.net",
    ]
    assert args.max_pages == 42
    assert not args.all


def test_parse_command_line_all_pages():
    args = acrawler.parse_args(
        "--all https://example.com".split())
    assert args.roots == ["https://example.com"]
    assert args.max_pages == math.inf
    assert args.all


def test_resolve_url():
    assert acrawler.resolve_url(
        "https://example.com", "https://www.iana.org/domains/example") == \
        "https://www.iana.org/domains/example"
    assert acrawler.resolve_url("https://example.com", "baz/bar") == \
        "https://example.com/baz/bar"
    assert acrawler.resolve_url("https://example.com",
        "https://example.com/") == \
        "https://example.com"
    assert acrawler.resolve_url("https://example.com",
        "https://example.com#fragment") == \
        "https://example.com"


def SimpleSchedulerOption():
    return []

def RedisSchedulerOption():
    return ["--redis=redis://localhost"]

@pytest.fixture(params=[SimpleSchedulerOption, RedisSchedulerOption])
def command_options(request):
    return request.param()

# FIXME Requires internet connectivity to test, so make that a fixture too
@pytest.mark.asyncio
async def test_run_acrawler(command_options, capsys):
    argv = command_options + ["https://example.com"]
    await acrawler.main(argv)
    captured = capsys.readouterr()
    assert captured.out == """\
- !Tag
  name: a
  url: https://www.iana.org/domains/example
  attrs:
    href: https://www.iana.org/domains/example
"""
    
    yaml = YAML()
    yaml.register_class(Tag)
    sitemap = yaml.load(captured.out)
    assert sitemap == [
        Tag("a", "https://www.iana.org/domains/example",
            {"href": "https://www.iana.org/domains/example"})]
