# Inverted-Index Search Engine

A command-line search tool that crawls [quotes.toscrape.com](https://quotes.toscrape.com/), builds an inverted index with positional postings, and supports single- and multi-word queries with TF–IDF ranking.

> **Module:** COMP3011 Web Services and Web Data — University of Leeds
> **Coursework:** CW2 (2025–2026)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Installation](#installation)
4. [Usage](#usage)
5. [Design Decisions](#design-decisions)
6. [Testing](#testing)
7. [Project Structure](#project-structure)
8. [Development Workflow](#development-workflow)
9. [GenAI Usage](#genai-usage)
10. [References](#references)

## Overview

This project implements a small but complete search engine pipeline:

- A **polite web crawler** that respects `robots.txt`, observes a 6-second politeness window with jitter, and gracefully handles network errors.
- An **inverted index** with positional postings — each term maps to a list of `(doc_id, term_frequency, [positions])` records — alongside a document table and corpus-level statistics.
- **Persistent storage** of the index as JSON, with `build` and `load` commands.
- **Search** supporting single-word lookup, multi-word AND queries, and TF–IDF ranked results.

## Architecture

````
                ┌─────────────────────────────────────────────────────┐
                │                   main.py (CLI)                      │
                └──────────────┬──────────────────┬───────────────────┘
                               │                  │
                  ┌────────────┘                  └────────────┐
                  ▼                                            ▼
           ┌─────────────┐    builds            queries  ┌─────────────┐
           │ crawler.py  │─────────────► index ◄─────────│  search.py  │
           └─────────────┘   indexer.py                  └─────────────┘
                  │                  ▲
                  ▼                  │
           quotes.toscrape.com   data/index.json
````

The four modules cleanly separate concerns: the crawler knows about HTTP and politeness, the indexer knows about tokens and postings, the searcher knows about ranking, and `main.py` is a thin REPL that wires them together.

## Installation

Requires **Python 3.10+**.

````bash
git clone https://github.com/kylamcdonagh01/comp3011-search-engine.git
cd comp3011-search-engine
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
````

## Usage

Launch the interactive CLI:

````bash
python -m src.main
````

You will see a `>` prompt. The four commands required by the brief:

### `build`

Crawls quotes.toscrape.com, builds the inverted index, and saves it to `data/index.json`.

````
> build
[crawler] starting from https://quotes.toscrape.com/
[crawler] fetched page 1/10 (politeness window: 6.4s)
...
[indexer] indexed 100 quotes across 10 pages, 1,247 unique terms
[indexer] index saved to data/index.json
````

### `load`

Loads a previously built index from disk.

````
> load
[indexer] loaded index: 10 documents, 1,247 terms
````

### `print <word>`

Prints the inverted list (postings) for a single term.

````
> print nonsense
'nonsense' appears in 1 document(s):
  doc 4 (https://quotes.toscrape.com/page/4/)
    term frequency: 1
    positions: [87]
````

### `find <query>`

Finds all documents containing every word in the query, ranked by TF–IDF.

````
> find indifference
1 result(s) for 'indifference':
  1. https://quotes.toscrape.com/page/2/   (score: 4.32)

> find good friends
3 result(s) for 'good friends':
  1. https://quotes.toscrape.com/page/1/   (score: 6.18)
  2. https://quotes.toscrape.com/page/5/   (score: 3.91)
  3. https://quotes.toscrape.com/page/8/   (score: 1.07)
````

Type `help` at the prompt for a full command list, or `quit` to exit.

## Design Decisions

**Why JSON for the index?** The corpus is small (≈ 100 quotes across 10 pages), so the readability and inspectability of JSON outweighs the ~30% size penalty over pickle. It also lets markers open the file and verify the structure visually.

**Why positional postings?** The brief specifies that the index should store statistics including frequency *and position*. Storing positions makes phrase queries possible as a future extension and is the canonical structure described in Lectures.

**Why a 6.0–7.5 s randomised politeness window?** It was noted in Lectures that monotonous request timing is itself a bot signature; jitter mimics human-like access patterns and keeps us safely above the 6 s minimum.

**Why TF–IDF instead of raw counts for ranking?** Raw term frequency biases toward long documents and toward common words. TF–IDF down-weights terms that appear in many documents, producing more relevant rankings using advanced query processing.

## Testing

The project uses `pytest` with `pytest-cov`. To run the full suite:

````bash
pytest # quick run
pytest --cov=src --cov-report=term-missing # with coverage report
pytest --cov=src --cov-report=html # HTML report in htmlcov/
````

Crawler tests use the `responses` library to mock HTTP responses, so the suite runs in well under a second and never hits the live site. Target coverage: **≥ 85% on `src/`**.

See [`docs/testing.md`](docs/testing.md) for the full testing strategy.

## Project Structure

````
comp3011-search-engine/
├── src/
│   ├── __init__.py
│   ├── crawler.py          # Polite web crawler with robots.txt support
│   ├── indexer.py          # Inverted index + persistence
│   ├── search.py           # Query processing + TF-IDF ranking
│   └── main.py             # Interactive CLI
├── tests/
│   ├── test_crawler.py     # Mocked HTTP, politeness, robots.txt
│   ├── test_indexer.py     # Tokenisation, postings, save/load
│   └── test_search.py      # print, find, multi-word, ranking
├── data/
│   └── index.json          # Compiled index (generated by `build`)
├── docs/
│   ├── testing.md          # Testing strategy and coverage analysis
│   └── design-notes.md     # Trade-offs and complexity analysis
├── .github/workflows/
│   └── ci.yml              # GitHub Actions: lint + test on push
├── requirements.txt
├── README.md
├── GENAI_LOG.md            # Declared GenAI usage
└── .gitignore
````

## Development Workflow

This project follows a simple but disciplined workflow:

- **Conventional commits**: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`.
- **Feature branches**: each module developed on its own branch (`feat/crawler`, `feat/indexer`, …) and merged via PR.
- **Tagged releases**: `v1.0.0` marks the submitted version.
- **Continuous integration**: every push runs the test suite via GitHub Actions.

## GenAI Usage

This coursework is classified GREEN; GenAI tools may be used with declaration. Uses are logged in [`GENAI_LOG.md`](GENAI_LOG.md) with specific examples of where AI assistance helped, where it produced incorrect output that required correction, and reflection on the impact on learning.

## References

- Croft, Metzler & Strohman, *Search Engines: Information Retrieval in Practice* (2010) — primary reference for inverted-index design and ranking functions.
- COMP3011 Lecture 9: Web Crawling.
- COMP3011 Lecture 11: Parsing and Tokenisation.
- COMP3011 Lecture 12: Indexing.
- COMP3011 Lecture 13: Query Processing.
- [Python Requests documentation](https://requests.readthedocs.io/)
- [BeautifulSoup documentation](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [quotes.toscrape.com](https://quotes.toscrape.com/) — target site for crawling.
````
````
