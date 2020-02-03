import asyncio
import sys


async def crawl(site_url):
    print(f"Crawling {site_url}...")
    await asyncio.sleep(1)
    print("Done.")


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(crawl(sys.argv[1]))

