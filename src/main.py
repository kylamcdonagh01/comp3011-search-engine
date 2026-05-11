"""
Interactive command-line interface for the search engine.

Built on the standard library's `cmd.Cmd` framework, which gives us a
clean REPL with built-in history, help, and quit handling. Supported
commands:

  build           -- crawl the target site and persist an index.
  load            -- load a previously built index from disk.
  print <word>    -- show the inverted list for a single term.
  find <query>    -- search for one or more space-separated terms.
"""

from __future__ import annotations

import cmd
import logging
import sys
from pathlib import Path

from src.crawler import Crawler
from src.indexer import InvertedIndex
from src.search import Search

# Configure logging once at module level. Crawler and indexer log
# progress at INFO; we route everything to stderr so it doesn't muddle
# the command output that goes to stdout.
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stderr,
)


DEFAULT_SEED = "https://quotes.toscrape.com/"
DEFAULT_INDEX_PATH = Path("data/index.json")
DEFAULT_MAX_PAGES = 1000

class SearchShell(cmd.Cmd):
    """Interactive shell for the search engine."""

    intro = (
        "COMP3011 Search Engine\n"
        "Commands: build | load | print <word> | find <query> | help | quit\n"
    )
    prompt = "> "

    def __init__(
        self,
        seed_url: str = DEFAULT_SEED,
        index_path: Path = DEFAULT_INDEX_PATH,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
    ):
        super().__init__()
        self.seed_url = seed_url
        self.index_path = Path(index_path)
        self.max_pages = max_pages
        self._index: InvertedIndex | None = None
        self._search: Search | None = None

    # ---- helpers ------------------------------------------------------

    def _require_index(self) -> bool:
        """Print a friendly message and return False if no index is loaded."""
        if self._index is None or self._search is None:
            print("No index in memory. Run `build` to crawl, or `load` if you")
            print("have already built one.")
            return False
        return True

    def _attach_index(self, index: InvertedIndex) -> None:
        """Wire a freshly built or loaded index into the shell."""
        self._index = index
        self._search = Search(index=index)

    # ---- commands -----------------------------------------------------

    def do_build(self, _arg: str) -> None:
        """build : crawl the target site and write an inverted index to disk."""
        print(f"[crawler] starting from {self.seed_url}")
        crawler = Crawler(seed_url=self.seed_url, max_pages=self.max_pages)
        index = InvertedIndex()
        page_count = 0
        for result in crawler.crawl():
            page_count += 1
            print(f"[crawler] fetched ({page_count}) {result.url}")
            index.add_document(result.doc_id, result.url, result.html)

        if page_count == 0:
            print("[crawler] no pages were retrieved; nothing to index.")
            return

        index.save(self.index_path)
        print(
            f"[indexer] indexed {index.num_documents} documents, "
            f"{len(index.tokens)} unique terms"
        )
        print(f"[indexer] index saved to {self.index_path}")
        self._attach_index(index)

    def do_load(self, _arg: str) -> None:
        """load : load a previously built index from disk."""
        try:
            index = InvertedIndex.load(self.index_path)
        except FileNotFoundError:
            print(f"No index file at {self.index_path}.")
            print("Run `build` first to create one.")
            return

        self._attach_index(index)
        print(
            f"[indexer] loaded index: {index.num_documents} documents, "
            f"{len(index.tokens)} terms"
        )

    def do_print(self, arg: str) -> None:
        """print <word> : show the inverted list (postings) for a single term."""
        if not self._require_index():
            return
        word = arg.strip()
        if not word:
            print("Usage: print <word>")
            return

        entries = self._search.print_term(word)
        if not entries:
            print(f"'{word}' was not found in the index.")
            return

        print(f"'{word}' appears in {len(entries)} document(s):")
        for entry in entries:
            print(f"  doc {entry.doc_id} ({entry.url})")
            print(f"    term frequency: {entry.tf}")
            print(f"    positions: {entry.positions}")

    def do_find(self, arg: str) -> None:
        """find <query> : find pages containing ALL words in the query, ranked by TF-IDF."""
        if not self._require_index():
            return
        query = arg.strip()
        if not query:
            print("Usage: find <word> [<word> ...]")
            return

        results = self._search.find(query)
        if not results:
            print(f"No results for '{query}'.")
            return

        print(f"{len(results)} result(s) for '{query}':")
        for rank, result in enumerate(results, start=1):
            print(f"  {rank}. {result.url}   (score: {result.score:.2f})")

    def do_quit(self, _arg: str) -> bool:
        """quit : exit the search engine."""
        print("bye.")
        return True

    # `exit` and EOF (Ctrl-D / Ctrl-Z) as aliases for quit.
    do_exit = do_quit

    def do_EOF(self, _arg: str) -> bool:
        """End-of-file: same as quit."""
        print()
        return True

    def emptyline(self) -> bool:
        """Pressing Enter on an empty line should do nothing (default repeats last cmd)."""
        return False

    def default(self, line: str) -> None:
        """Called for unknown commands."""
        print(f"Unknown command: {line!r}. Type `help` for a list of commands.")


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m src.main`."""
    shell = SearchShell()
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print()  # newline after ^C
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())