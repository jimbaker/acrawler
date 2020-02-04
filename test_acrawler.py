import pytest
import acrawler


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


def test_tag_parser():
    tag_parser = acrawler.TagParser({"a"})
    assert list(tag_parser.consume(example_html)) == [
        acrawler.Tag("a", {"href": "https://www.iana.org/domains/example"})]


# Requires internet connectivity to test
@pytest.mark.asyncio
async def test_run_acrawler(capsys):
    await acrawler.crawl("https://example.com")
    captured = capsys.readouterr()
    assert captured.out == """\
- !Tag
  name: a
  attrs:
    href: https://www.iana.org/domains/example
"""

