"""
Tests for the polite web crawler (src.crawler).

These tests exercise the crawler in isolation by mocking all HTTP
traffic via the `responses` library. No test should ever hit the live
network, both for speed and for determinism.
"""

from unittest.mock import patch

import pytest
import responses

from src.crawler import Crawler, CrawlResult


SEED = "https://quotes.toscrape.com/"
SEED_NORMALISED = "https://quotes.toscrape.com"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_sleep():
    """
    Replace time.sleep with a no-op for the duration of a test.

    Lets us verify the politeness window without actually waiting six
    seconds per request.
    """
    with patch("src.crawler.time.sleep") as mock_sleep:
        yield mock_sleep


@pytest.fixture
def mock_robots_allow_all():
    """Register a permissive robots.txt response for the seed host."""
    responses.add(
        responses.GET,
        "https://quotes.toscrape.com/robots.txt",
        body="User-agent: *\nAllow: /\n",
        status=200,
        content_type="text/plain",
    )


# ---------------------------------------------------------------------------
# URL normalisation
# ---------------------------------------------------------------------------


class TestNormalise:
    """Crawler._normalise is small but central to deduplication."""

    def test_strips_fragment(self):
        assert Crawler._normalise("https://example.com/page#top") == "https://example.com/page"

    def test_strips_trailing_slash_except_root(self):
        assert Crawler._normalise("https://example.com/page/") == "https://example.com/page"

    def test_preserves_root_slash(self):
        assert Crawler._normalise("https://example.com/") == "https://example.com/"

    def test_lowercases_host(self):
        assert Crawler._normalise("https://EXAMPLE.com/Page") == "https://example.com/Page"

    def test_preserves_query_string(self):
        assert (
            Crawler._normalise("https://example.com/search?q=hello")
            == "https://example.com/search?q=hello"
        )


# ---------------------------------------------------------------------------
# Politeness window
# ---------------------------------------------------------------------------


class TestPoliteness:
    """The brief mandates >=6s between requests; Lecture 9 adds jitter."""

    @responses.activate
    def test_no_sleep_before_first_request(self, patch_sleep, mock_robots_allow_all):
        responses.add(
            responses.GET, SEED, body="<html></html>", content_type="text/html"
        )
        crawler = Crawler(seed_url=SEED, max_pages=1)
        list(crawler.crawl())
        assert patch_sleep.call_count == 0  # no sleep needed before first fetch

    @responses.activate
    def test_sleeps_at_least_min_delay_between_requests(
        self, patch_sleep, mock_robots_allow_all
    ):
        page1 = '<html><a href="/page/2">next</a></html>'
        responses.add(responses.GET, SEED, body=page1, content_type="text/html")
        responses.add(
            responses.GET,
            "https://quotes.toscrape.com/page/2",
            body="<html></html>",
            content_type="text/html",
        )
        crawler = Crawler(seed_url=SEED, min_delay=6.0, jitter=1.5, max_pages=2)
        list(crawler.crawl())

        # At least one sleep call, and every sleep value is >= 6.0.
        assert patch_sleep.call_count >= 1
        for call in patch_sleep.call_args_list:
            (delay,), _ = call
            assert delay >= 6.0
            assert delay <= 6.0 + 1.5  # within configured jitter band


# ---------------------------------------------------------------------------
# Robots.txt
# ---------------------------------------------------------------------------


class TestRobotsTxt:
    @responses.activate
    def test_respects_disallow_rule(self, patch_sleep):
        # robots.txt forbids /page/2/
        responses.add(
            responses.GET,
            "https://quotes.toscrape.com/robots.txt",
            body="User-agent: *\nDisallow: /page/2\n",
            status=200,
            content_type="text/plain",
        )
        responses.add(
            responses.GET,
            SEED,
            body='<a href="/page/2">forbidden</a>',
            content_type="text/html",
        )
        # The crawler should never request /page/2 because robots.txt forbids it.
        crawler = Crawler(seed_url=SEED, max_pages=10)
        list(crawler.crawl())

        requested = [c.request.url for c in responses.calls]
        assert not any("page/2" in url for url in requested)


# ---------------------------------------------------------------------------
# Link extraction & domain restriction
# ---------------------------------------------------------------------------


class TestLinkExtraction:
    @responses.activate
    def test_extracts_in_domain_links(self, patch_sleep, mock_robots_allow_all):
        html = """
        <html>
          <a href="/page/2">internal</a>
          <a href="https://twitter.com/share">external</a>
          <a href="mailto:foo@bar.com">mail</a>
        </html>
        """
        responses.add(responses.GET, SEED, body=html, content_type="text/html")
        responses.add(
            responses.GET,
            "https://quotes.toscrape.com/page/2",
            body="<html></html>",
            content_type="text/html",
        )
        crawler = Crawler(seed_url=SEED, max_pages=10)
        results = list(crawler.crawl())

        urls = [r.url for r in results]
        assert any("page/2" in u for u in urls)
        # External and mailto should never be fetched.
        requested = [c.request.url for c in responses.calls]
        assert not any("twitter.com" in u for u in requested)
        assert not any(u.startswith("mailto:") for u in requested)

    @responses.activate
    def test_does_not_revisit_pages(self, patch_sleep, mock_robots_allow_all):
        # Two pages each linking to each other → without dedup, infinite loop.
        responses.add(
            responses.GET,
            SEED,
            body='<a href="/page/2">2</a>',
            content_type="text/html",
        )
        responses.add(
            responses.GET,
            "https://quotes.toscrape.com/page/2",
            body=f'<a href="{SEED}">home</a>',
            content_type="text/html",
        )
        crawler = Crawler(seed_url=SEED, max_pages=10)
        results = list(crawler.crawl())
        # Exactly two unique pages should be fetched.
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @responses.activate
    def test_handles_404_gracefully(self, patch_sleep, mock_robots_allow_all):
        responses.add(responses.GET, SEED, status=404)
        crawler = Crawler(seed_url=SEED, max_pages=1)
        results = list(crawler.crawl())
        assert results == []  # no crash, no result

    @responses.activate
    def test_handles_connection_error(self, patch_sleep, mock_robots_allow_all):
        import requests as _requests  # avoid shadowing module-level imports
        responses.add(
            responses.GET,
            SEED,
            body=_requests.exceptions.ConnectionError("boom"),
        )
        crawler = Crawler(seed_url=SEED, max_pages=1)
        results = list(crawler.crawl())
        assert results == []

    @responses.activate
    def test_skips_non_html_content(self, patch_sleep, mock_robots_allow_all):
        responses.add(
            responses.GET,
            SEED,
            body=b"\x89PNG\r\n",
            status=200,
            content_type="image/png",
        )
        crawler = Crawler(seed_url=SEED, max_pages=1)
        results = list(crawler.crawl())
        assert results == []  # PNG should be filtered out


# ---------------------------------------------------------------------------
# CrawlResult shape
# ---------------------------------------------------------------------------


class TestCrawlResult:
    @responses.activate
    def test_doc_ids_are_zero_indexed_and_contiguous(
        self, patch_sleep, mock_robots_allow_all
    ):
        responses.add(
            responses.GET,
            SEED,
            body='<a href="/a">a</a> <a href="/b">b</a>',
            content_type="text/html",
        )
        responses.add(
            responses.GET,
            "https://quotes.toscrape.com/a",
            body="<html></html>",
            content_type="text/html",
        )
        responses.add(
            responses.GET,
            "https://quotes.toscrape.com/b",
            body="<html></html>",
            content_type="text/html",
        )
        crawler = Crawler(seed_url=SEED, max_pages=10)
        results = list(crawler.crawl())
        ids = [r.doc_id for r in results]
        assert ids == list(range(len(ids)))  # 0, 1, 2, ...

    @responses.activate
    def test_max_pages_stops_crawl(self, patch_sleep, mock_robots_allow_all):
        responses.add(
            responses.GET,
            SEED,
            body='<a href="/a">a</a> <a href="/b">b</a> <a href="/c">c</a>',
            content_type="text/html",
        )
        for path in ["a", "b", "c"]:
            responses.add(
                responses.GET,
                f"https://quotes.toscrape.com/{path}",
                body="<html></html>",
                content_type="text/html",
            )
        crawler = Crawler(seed_url=SEED, max_pages=2)
        results = list(crawler.crawl())
        assert len(results) == 2