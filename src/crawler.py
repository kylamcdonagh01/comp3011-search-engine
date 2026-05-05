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

# Implementation will be added on the feat/crawler branch.
