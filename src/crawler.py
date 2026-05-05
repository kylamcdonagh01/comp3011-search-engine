"""
Polite web crawler for the COMP3011 search engine coursework.

This module is responsible for discovering and downloading pages from a
single target website (https://quotes.toscrape.com/), respecting:

  - the site's robots.txt rules (parsed via urllib.robotparser),
  - a politeness window of at least 6 seconds between requests, with
    randomised jitter so the request pattern does not look monotonous
    (Lecture 9 notes that constant-interval requests are themselves a
    bot signature),
  - basic error handling for network and HTTP failures.

The crawler does not perform any indexing itself; it yields a stream of
(url, html) pairs which the indexer consumes.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Iterator
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    """One successfully fetched page."""
    url: str
    html: str
    doc_id: int


@dataclass
class Crawler:
    """
    A polite, single-domain breadth-first web crawler.

    Parameters
    ----------
    seed_url:
        The URL to start crawling from. The crawler will only follow
        links that share the same network location (host) as the seed.
    user_agent:
        The User-Agent header sent on every request, also used when
        consulting robots.txt.
    min_delay:
        Minimum seconds between successive requests to the host. The
        coursework brief mandates >= 6.
    jitter:
        Maximum extra random delay added on top of `min_delay`, in
        seconds. The actual delay each request is uniformly distributed
        in [min_delay, min_delay + jitter].
    timeout:
        Per-request HTTP timeout in seconds.
    max_pages:
        Hard cap on the number of pages fetched. Useful for tests and
        as a safety net against infinite frontiers.
    """

    seed_url: str
    user_agent: str = "COMP3011-CourseworkCrawler/1.0"
    min_delay: float = 6.0
    jitter: float = 1.5
    timeout: float = 10.0
    max_pages: int = 1000

    # Internal state — leading underscore marks these as private.
    _visited: set[str] = field(default_factory=set, init=False)
    _frontier: list[str] = field(default_factory=list, init=False)
    _robots: RobotFileParser | None = field(default=None, init=False)

    def crawl(self) -> Iterator[CrawlResult]:
        """
        Yield one CrawlResult per successfully fetched page.

        The first request (to robots.txt) is not subject to the
        politeness delay; the politeness delay applies *between*
        page fetches.
        """
        self._load_robots()
        self._frontier.append(self._normalise(self.seed_url))

        doc_id = 0
        first_request = True

        while self._frontier and doc_id < self.max_pages:
            url = self._frontier.pop(0)  # FIFO -> breadth-first
            if url in self._visited:
                continue
            self._visited.add(url)

            if not self._allowed(url):
                logger.info("robots.txt disallows %s; skipping", url)
                continue

            # Respect the politeness window between requests.
            if not first_request:
                delay = self.min_delay + random.uniform(0, self.jitter)
                logger.debug("sleeping %.2fs before fetching %s", delay, url)
                time.sleep(delay)
            first_request = False

            html = self._fetch(url)
            if html is None:
                continue

            yield CrawlResult(url=url, html=html, doc_id=doc_id)
            doc_id += 1

            for link in self._extract_links(html, base_url=url):
                if link not in self._visited and link not in self._frontier:
                    self._frontier.append(link)

    # ---- internals ---------------------------------------------------

    def _load_robots(self) -> None:
        """Fetch and parse the target site's robots.txt, if present."""
        parsed = urlparse(self.seed_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            response = requests.get(
                robots_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("could not read robots.txt (%s); proceeding without", exc)
            self._robots = None
            return

        rp = RobotFileParser()
        rp.parse(response.text.splitlines())
        self._robots = rp
        logger.info("loaded robots.txt from %s", robots_url)

    def _allowed(self, url: str) -> bool:
        """True if robots.txt permits us to fetch this URL."""
        if self._robots is None:
            return True
        return self._robots.can_fetch(self.user_agent, url)

    def _fetch(self, url: str) -> str | None:
        """Return the HTML at `url`, or None on any failure."""
        try:
            response = requests.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("failed to fetch %s: %s", url, exc)
            return None

        # Only index HTML.
        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            logger.debug("skipping non-HTML content at %s (%s)", url, content_type)
            return None

        return response.text

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        """Return all in-domain, normalised links found in the HTML."""
        soup = BeautifulSoup(html, "lxml")
        seed_host = urlparse(self.seed_url).netloc

        links: list[str] = []
        for anchor in soup.find_all("a", href=True):
            absolute = urljoin(base_url, anchor["href"])
            absolute = self._normalise(absolute)

            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            if parsed.netloc != seed_host:
                continue  # stay within the target domain
            links.append(absolute)
        return links

    @staticmethod
    def _normalise(url: str) -> str:
        """
        Canonicalise a URL so that visiting it twice via different
        textual forms is detected as the same URL.

        - Strip the fragment (`#section`).
        - Lowercase the scheme and host.
        - Remove a trailing slash from the path (except for the root).
        """
        url, _ = urldefrag(url)
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        rebuilt = f"{scheme}://{netloc}{path}"
        if parsed.query:
            rebuilt += f"?{parsed.query}"
        return rebuilt