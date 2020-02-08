import asyncio
import collections
import contextlib
import functools
import math
import unittest
import unittest.mock

import acrawler
import pytest
from acrawler import Tag
from ruamel.yaml import YAML


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
    # The aiohttp client is a bit complex, so creating a fake is likewise complex!

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


@pytest.mark.asyncio
async def test_crawler():
    fake_session_maker = functools.partial(
        make_fake_http_session, bytes(example_html, "utf-8"))

    tags = []
    def serializer(objects):
        tags.append(objects)

    crawler = acrawler.Crawler(
        fake_session_maker, serializer,
        ["https://url-is.invalid", "https://another-url-is.invalid"],
        num_workers=1, max_pages=1)
    await crawler.crawl()
    assert tags == [[Tag(
        "a", "https://www.iana.org/domains/example",
        {"href": "https://www.iana.org/domains/example"})]]
    assert crawler.frontier.qsize() == 0
    assert len(crawler.seen) == 1


@pytest.mark.asyncio
async def test_reference_loop():
    fake_session_maker = functools.partial(
        make_fake_http_session, bytes(reference_loop_html, "utf-8"))

    tags = []
    def serializer(objects):
        tags.append(objects)

    crawler = acrawler.Crawler(
        fake_session_maker, serializer,
        ["https://reference-loop.example"])
    await crawler.crawl()
    assert tags == [[Tag(
        "a", "https://reference-loop.example",
        {"href": "https://reference-loop.example"})]]
    assert crawler.frontier.qsize() == 0
    assert crawler.seen == {"https://reference-loop.example"}


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


# Requires internet connectivity to test
@pytest.mark.asyncio
async def test_run_acrawler(capsys):
    await acrawler.main(["https://example.com"])
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
