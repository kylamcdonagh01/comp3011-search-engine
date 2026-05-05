# Testing Strategy

This document describes the testing approach for the search engine. It is referenced from the README and is intended to satisfy the "documented testing strategy" criterion of the COMP3011 CW2 marking rubric.

## Goals

1. **Correctness.** Every public function in `src/` has at least one happy-path test and at least one edge-case test.
2. **Coverage.** ≥ 85% line coverage on the `src/` package, measured by `pytest-cov`.
3. **Speed.** The full suite runs in under one second so it can be re-run on every save during development. This is achieved by mocking all HTTP traffic.
4. **Determinism.** No test depends on network conditions, the system clock, or filesystem state outside `tmp_path`.

## Test types

### Unit tests

Each module has a dedicated test file targeting its public surface in isolation:

- **`test_crawler.py`** — URL filtering, robots.txt parsing, politeness-window enforcement (with `time.sleep` patched), HTTP error handling, link extraction.
- **`test_indexer.py`** — Tokenisation (casing, punctuation, contractions, empty input, unicode), posting list construction (single doc, repeated terms, position correctness), JSON round-trip persistence.
- **`test_search.py`** — Single-term lookup, multi-term AND intersection, queries with no results, TF-IDF ranking order, query normalisation matching index normalisation.

### Integration tests

Marked with `@pytest.mark.integration`, these wire multiple modules together:

- Build an index from a small set of fixture HTML files, then run a series of `find` queries and assert correct ranked results.
- Round-trip a built index through `save` → `load` and confirm semantic equivalence.

### Mocking strategy

- **HTTP**: every test that touches the crawler uses `responses` (or `unittest.mock.patch` on `requests.get`) to return canned HTML. We never hit `quotes.toscrape.com` from a test.
- **Time**: politeness-window tests patch `time.sleep` so the suite is not bottlenecked by 6-second pauses; we instead assert that `sleep` was called with an argument ≥ 6.
- **Filesystem**: persistence tests use `pytest`'s `tmp_path` fixture to keep tests hermetic.

## Edge cases explicitly covered

The brief calls out several edge cases ("non-existent words, empty queries, special characters"). Each appears in at least one test:

| Edge case | Test |
|---|---|
| Empty query string | `test_search_rejects_empty_query` |
| Single-word query, no results | `test_search_no_results_for_unknown_word` |
| Multi-word query, partial match | `test_search_intersection_excludes_partial_matches` |
| Punctuation in query | `test_search_normalises_query_punctuation` |
| Unicode in document text | `test_indexer_handles_unicode` |
| Very long token | `test_indexer_handles_long_token` |
| `print` for unknown word | `test_print_unknown_word` |
| Network failure during crawl | `test_crawler_handles_request_exception` |
| `robots.txt` disallows path | `test_crawler_respects_robots_disallow` |
| `load` before `build` | `test_load_without_index_raises_clear_error` |

## Running the suite

```bash
pytest                                          # quick run
pytest -v                                       # verbose
pytest --cov=src --cov-report=term-missing      # with coverage
pytest --cov=src --cov-report=html              # HTML report → htmlcov/
pytest -m "not slow"                            # skip slow tests
pytest tests/test_indexer.py::test_tokenise     # single test
```

## Continuous Integration

`.github/workflows/ci.yml` runs the full suite (with coverage) on every push and pull request, against Python 3.10, 3.11, and 3.12. Failed CI blocks merging to `main`.