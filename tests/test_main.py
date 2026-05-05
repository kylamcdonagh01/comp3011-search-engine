"""
Tests for src.main (the SearchShell CLI).

The CLI orchestrates the crawler, indexer, and searcher. We mock the
crawler so tests don't hit the network, build small in-memory indices
to exercise print/find, and capture stdout via the `capsys` fixture
to verify output formatting.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.crawler import CrawlResult
from src.indexer import InvertedIndex
from src.main import SearchShell


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def shell(tmp_path):
    """A SearchShell pointed at a temp dir, no live network involvement."""
    return SearchShell(
        seed_url="https://quotes.toscrape.com/",
        index_path=tmp_path / "index.json",
        max_pages=5,
    )


@pytest.fixture
def shell_with_index(shell):
    """A shell with a small index already loaded (no build/load needed)."""
    idx = InvertedIndex()
    idx.add_document(0, "https://example.com/0", "<p>good morning good friends</p>")
    idx.add_document(1, "https://example.com/1", "<p>good evening</p>")
    idx.add_document(2, "https://example.com/2", "<p>see you friends</p>")
    shell._attach_index(idx)
    return shell


# ---------------------------------------------------------------------------
# require_index guard
# ---------------------------------------------------------------------------


class TestRequireIndex:
    def test_print_without_index_warns(self, shell, capsys):
        shell.do_print("good")
        captured = capsys.readouterr()
        assert "No index in memory" in captured.out

    def test_find_without_index_warns(self, shell, capsys):
        shell.do_find("good")
        captured = capsys.readouterr()
        assert "No index in memory" in captured.out


# ---------------------------------------------------------------------------
# print
# ---------------------------------------------------------------------------


class TestDoPrint:
    def test_known_word_lists_postings(self, shell_with_index, capsys):
        shell_with_index.do_print("good")
        captured = capsys.readouterr()
        assert "'good' appears in 2 document(s)" in captured.out
        assert "term frequency:" in captured.out
        assert "positions:" in captured.out

    def test_unknown_word_reports_missing(self, shell_with_index, capsys):
        shell_with_index.do_print("nonsense")
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_empty_argument_shows_usage(self, shell_with_index, capsys):
        shell_with_index.do_print("")
        captured = capsys.readouterr()
        assert "Usage" in captured.out

    def test_whitespace_argument_shows_usage(self, shell_with_index, capsys):
        shell_with_index.do_print("   ")
        captured = capsys.readouterr()
        assert "Usage" in captured.out


# ---------------------------------------------------------------------------
# find
# ---------------------------------------------------------------------------


class TestDoFind:
    def test_single_word_finds_documents(self, shell_with_index, capsys):
        shell_with_index.do_find("good")
        captured = capsys.readouterr()
        assert "result(s) for 'good'" in captured.out
        assert "score:" in captured.out

    def test_multi_word_intersection(self, shell_with_index, capsys):
        shell_with_index.do_find("good friends")
        captured = capsys.readouterr()
        assert "1 result(s) for 'good friends'" in captured.out
        assert "https://example.com/0" in captured.out

    def test_no_results_message(self, shell_with_index, capsys):
        shell_with_index.do_find("xyz")
        captured = capsys.readouterr()
        assert "No results" in captured.out

    def test_empty_query_shows_usage(self, shell_with_index, capsys):
        shell_with_index.do_find("")
        captured = capsys.readouterr()
        assert "Usage" in captured.out

    def test_results_numbered_in_output(self, shell_with_index, capsys):
        shell_with_index.do_find("good")
        captured = capsys.readouterr()
        # Two results -> lines starting with "  1." and "  2."
        assert "1." in captured.out
        assert "2." in captured.out


# ---------------------------------------------------------------------------
# build (with a mocked crawler)
# ---------------------------------------------------------------------------


class TestDoBuild:
    def test_builds_and_persists_index(self, shell, capsys, tmp_path):
        # Mock Crawler.crawl to yield two pre-baked CrawlResults so we
        # never hit the network.
        fake_results = [
            CrawlResult(
                url="https://example.com/0",
                html="<p>alpha beta gamma</p>",
                doc_id=0,
            ),
            CrawlResult(
                url="https://example.com/1",
                html="<p>alpha delta</p>",
                doc_id=1,
            ),
        ]
        with patch("src.main.Crawler") as MockCrawler:
            MockCrawler.return_value.crawl.return_value = iter(fake_results)
            shell.do_build("")

        captured = capsys.readouterr()
        assert "indexed 2 documents" in captured.out
        assert shell.index_path.exists()
        # And the shell now has an index in memory.
        assert shell._index is not None
        assert shell._search is not None

    def test_build_with_no_results_reports_gracefully(self, shell, capsys):
        with patch("src.main.Crawler") as MockCrawler:
            MockCrawler.return_value.crawl.return_value = iter([])
            shell.do_build("")
        captured = capsys.readouterr()
        assert "no pages were retrieved" in captured.out
        assert shell._index is None


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


class TestDoLoad:
    def test_load_missing_file(self, shell, capsys):
        # index_path was set to a non-existent file in the fixture.
        shell.do_load("")
        captured = capsys.readouterr()
        assert "No index file" in captured.out
        assert shell._index is None

    def test_load_after_save(self, shell, capsys):
        # First create an index file at shell.index_path.
        idx = InvertedIndex()
        idx.add_document(0, "https://example.com/", "<p>hello world</p>")
        idx.save(shell.index_path)

        shell.do_load("")
        captured = capsys.readouterr()
        assert "loaded index" in captured.out
        assert shell._index is not None
        assert shell._search is not None


# ---------------------------------------------------------------------------
# quit / EOF / unknown
# ---------------------------------------------------------------------------


class TestQuitAndUnknown:
    def test_quit_returns_true(self, shell):
        # Returning True from a do_* method tells cmd.Cmd to exit the loop.
        assert shell.do_quit("") is True

    def test_exit_alias(self, shell):
        assert shell.do_exit("") is True

    def test_eof_returns_true(self, shell):
        assert shell.do_EOF("") is True

    def test_unknown_command_message(self, shell, capsys):
        shell.default("frobnicate")
        captured = capsys.readouterr()
        assert "Unknown command" in captured.out

    def test_emptyline_does_nothing(self, shell):
        # Default cmd.Cmd repeats the last command; ours should not.
        assert shell.emptyline() is False