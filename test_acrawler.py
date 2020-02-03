import pytest
import acrawler


@pytest.mark.asyncio
async def test_run_acrawler(capsys):
    await acrawler.crawl("https://example.com")
    captured = capsys.readouterr()
    assert captured.out == "Crawling https://example.com...\nDone.\n"

