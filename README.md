# acrawler

acrawler, an asyncio-based crawler, is yet another crawler to demonstrate how to
scalably crawl web sites. It can also be readily adapted to crawl APIs, such as
YouTube's API.

* To install dependencies: `make init`
* To run tests: `make test`
* To create a coverage report `make coverage`

NOTE: This code requires the use of Python 3.8 (possibly lower). I recommend
using the standard support for virtual enviroments, namely something like the
following before running the make commands above:

```bash
$ python3.8 -m venv env_acrawler
$ . env_acrawler/bin/activate
$ make init
```

The above sets `python` to the appropriate version. You can then run with this
command:

```bash
$ python acrawler.py https://example.com
```

which will produce this YAML-serialized sitemap:

```yaml
- !Tag
  name: a
  url: https://www.iana.org/domains/example
  attrs:
    href: https://www.iana.org/domains/example
```

If you are feeling bold, you can try running the crawler with the `--all` option
-- it will crawl all pages under the specified root. *This could be a large
result set.*

## Testing

The code currently has 100% coverage (excluding two *no cover* lines used for
`__main__` script support). To generate a detailed coverage report into the
directory `htmlcov`:

```bash
$ pytest --cov=acrawler --cov-report=html:htmlcov test_acrawler.py
```

FIXME add label support for this in GitHub.

The current coverage feels quite good. In particular, there's minimal branching
in the code, since it follows a generator-based approach, and my attempt to
bring back coverage to 100% removed some conditional complexity.

All but one test is a unit test. Non-async unit testing follows the typical
pattern of setup-apply-test. Async unit testing also can follow this pattern,
but with a bit more subtlety. Here are the considerations:

* Use the `pytest.mark.asyncio` decorator such that async functions can get a
  corresponding event loop during testing, plus such checking as all coroutines
  are run to completion.

* No usage of sleeps in test code (or the code itself, unless there is a
  specific interop consideration, eg we are implementing polling, etc). Note
  that one exception here is the special case of `asyncio.sleep(0)`, which
  simply yields back to the event loop.
  
* Use of constant coroutines. By using `asyncio.Future` allows for the
  writing of constant coroutines and without introducing unnecessary `async` and
  `await` keywords in these tests. Because we should test exceptional paths as
  well, a TODO is to use `fake_reponse.set_exception` to cook an appropriate
  exception and validate any cprresponding logic, such as attempting to retry,
  other recovery, or failing appropriately.

In particular, testing a fake HTTP client (instead of
`aiohttp.ClientSession`) required writing code with this pattern to support
`async with` usage:

```python
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
```

See [PEP 492 -- Coroutines with async and await
syntax](https://www.python.org/dev/peps/pep-0492/#asynchronous-context-managers-and-async-with)
for more details on this protocol with `__aenter__` and `__aexit__` methods.

## Redis support

Now added with `RedisScheduler`, which parallels `SimpleScheduler` (built on
`asyncio.Queue`) but more work to be done.

Note that we want to keep track of work items in Redis, not jobs/tasks as we see
in tools like [arq](https://arq-docs.helpmanual.io/) or
[Celery](http://www.celeryproject.org/). This is because we have homogeneous
tasks, and for an at-scale crawl, we want to do more interesting scheduling of
this work based on the characteristics of these work items.

Next steps also include considering how to cluster. While in general URLs would
be a great partition key, we cannot just use `...{url}...` in our keys given
that the `seen` and `frontier` keys are global! So some additional work.

## Typing

Adding static type annotations is a forthcoming step.

## TODOs

There are a number of straightforward TODOs in the code. Some additions:

**Collector**

* Pluggable to determine what is of interest for collecting, and how to extract the relevant tags.
* Support 301 Redirections, `robots.txt`,
  [timeouts](https://docs.aiohttp.org/en/stable/client_quickstart.html#timeouts),
  and other crawling niceties.
* API support, with some additions on setting up the client connection, eg for
  API keys. One possible demo: GraphQL client consuming GitHub as part of an API
  crawler demo.

Multiple plugins make sense here, to handle different types of URLs.

**Scheduler**

* Support for a scalable queue system like Redis. It would be straightforward to
  map FIFO queues onto a Redis queue, including [async
  support](https://aioredis.readthedocs.io/). Such support should use [reliable
  queue ops](https://redis.io/commands/RPOPLPUSH). Now you would have the
  potential to rival Google in your crawling ability, or at least
  [Scrapy](https://scrapy.org/)!

**Storage**

Storage options include the following:

* Serialize/Deserialize on the YAML sitemap format (partially implemented).
* Redis-based storage using sorted sets -- this approach could be useful for
  periodically rescanning URLs based on a global or specific timeliness metric.
* Support indexing into ElasticSearch.

Multiple plugins also make sense - one might want to both index **and** create a sitemap.

## Branches

This project is a demonstration on how to approach the building of a scalable web
crawler by using asyncio. Therefore I have attached the sequence of branches
needed for this implementation.

### Basics branch

1. Package layout - https://docs.python-guide.org/writing/structure/
2. Async testing with pytest
3. asyncio "Hello, World" starter shell -
   https://docs.python.org/3/library/asyncio-task.html#coroutines

Plus additions to requirements.txt, etc.

Branch: https://github.com/jimbaker/acrawler/tree/basics

### Crawl operations branch

1. Use aiohttp client to fetch pages
2. Wrap stdlib html.parser.HTMLParser to parse pages
3. Change crawl function to fetch and parse a page, not just sleep, and output a
   very basic sitemap based on YAML serialization

Branch: https://github.com/jimbaker/acrawler/tree/operations

### Crawler branch

1. Implement basic crawling logic, including a set of seen URLs and a frontier
   that is used for scheduling.
2. Basic resolution of URLs from relative to absolute

Branch: https://github.com/jimbaker/acrawler/tree/crawler

## Task branch

1. Use asyncio's support for task management and use asyncio.Queue to manage the
   frontier.
2. Support draining the queue.
3. Output image tags as well in the sitemap.
3. Various updates to the README and more control of the crawling process.

Branch: https://github.com/jimbaker/acrawler/tree/task