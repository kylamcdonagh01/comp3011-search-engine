"""
Inverted-index construction and persistence.

The index maps each lowercase token to a list of postings. Each posting
records (doc_id, term_frequency, [positions]). A separate documents
table maps doc_ids back to URLs and stores per-document metadata such
as length, which is needed for ranking.

In this structure, an index term
points to an inverted list of postings, and a separate document table
maps document IDs to URLs.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

# A small English stopword list. Kept short and obvious; users can
# supply their own via Tokeniser(stopwords=...) if they want a richer
# list. The brief specifies case-insensitive matching, so the list is
# checked after lowercasing.
DEFAULT_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "he", "in", "is", "it", "its", "of", "on", "that", "the",
    "to", "was", "were", "will", "with",
})

# Pattern: one or more letters/digits/apostrophes. Keeps contractions
# like "don't" together; excludes underscores (unlike \w).
_TOKEN_RE = re.compile(r"[a-z0-9']+")


@dataclass
class Tokeniser:
    """
    Turns a string of HTML or plain text into a list of lowercase tokens.

    Parameters
    ----------
    remove_stopwords:
        If True, drop tokens in `stopwords`. Default False — Lecture 11
        notes that some valid queries (e.g. "to be or not to be") are
        entirely stopwords, so removal is opt-in.
    stopwords:
        Set of stopwords to remove. Only consulted if remove_stopwords
        is True. Defaults to a small built-in list.
    """

    remove_stopwords: bool = False
    stopwords: frozenset[str] = DEFAULT_STOPWORDS

    def tokenise(self, text: str) -> list[str]:
        """Tokenise plain text — does NOT strip HTML."""
        tokens = _TOKEN_RE.findall(text.lower())
        # Drop bare-apostrophe tokens that arise from things like " ' ".
        tokens = [t for t in tokens if t.strip("'")]
        if self.remove_stopwords:
            tokens = [t for t in tokens if t not in self.stopwords]
        return tokens

    def tokenise_html(self, html: str) -> tuple[list[str], str]:
        """
        Strip HTML, then tokenise. Returns (tokens, document_title).

        <script> and <style> contents are removed entirely — their text
        is never visible to the user, so it must not pollute the index.
        """
        soup = BeautifulSoup(html, "lxml")

        for tag in soup(["script", "style"]):
            tag.decompose()

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Use a space separator so adjacent tags don't merge words:
        # "<b>Hello</b><b>World</b>" -> "Hello World", not "HelloWorld".
        text = soup.get_text(separator=" ")
        return self.tokenise(text), title


# ---------------------------------------------------------------------------
# Inverted index
# ---------------------------------------------------------------------------


@dataclass
class Posting:
    """One entry in an inverted list: which doc, how often, where."""
    doc_id: int
    tf: int
    positions: list[int]

    def to_dict(self) -> dict:
        return {"doc_id": self.doc_id, "tf": self.tf, "positions": self.positions}

    @classmethod
    def from_dict(cls, data: dict) -> "Posting":
        return cls(
            doc_id=int(data["doc_id"]),
            tf=int(data["tf"]),
            positions=list(data["positions"]),
        )


@dataclass
class DocumentRecord:
    """Metadata about a single indexed document."""
    url: str
    length: int          # number of tokens after tokenisation
    title: str = ""

    def to_dict(self) -> dict:
        return {"url": self.url, "length": self.length, "title": self.title}

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentRecord":
        return cls(
            url=data["url"],
            length=int(data["length"]),
            title=data.get("title", ""),
        )


@dataclass
class InvertedIndex:
    """
    An inverted index mapping lowercase terms to posting lists.

    The class is mutable: call `add_document()` for each (doc_id, url,
    html) you want to index, then `save()` to persist. Use the class
    method `load()` to read a previously built index back.
    """

    tokeniser: Tokeniser = field(default_factory=Tokeniser)
    tokens: dict[str, list[Posting]] = field(default_factory=dict)
    documents: dict[int, DocumentRecord] = field(default_factory=dict)
    build_time: str = ""

    # ---- mutation -----------------------------------------------------

    def add_document(self, doc_id: int, url: str, html: str) -> None:
        """Tokenise `html` and merge its postings into the index."""
        if doc_id in self.documents:
            raise ValueError(f"doc_id {doc_id} already indexed")

        tokens, title = self.tokeniser.tokenise_html(html)

        # Build per-term stats for THIS document in one pass.
        # term -> list of positions (first appearance order preserved).
        per_doc: dict[str, list[int]] = {}
        for position, token in enumerate(tokens):
            per_doc.setdefault(token, []).append(position)

        # Merge into the global postings.
        for term, positions in per_doc.items():
            posting = Posting(doc_id=doc_id, tf=len(positions), positions=positions)
            self.tokens.setdefault(term, []).append(posting)

        self.documents[doc_id] = DocumentRecord(
            url=url, length=len(tokens), title=title
        )

    def add_documents(self, docs: Iterable[tuple[int, str, str]]) -> None:
        """Convenience: index a batch of (doc_id, url, html) records."""
        for doc_id, url, html in docs:
            self.add_document(doc_id, url, html)

    # ---- queries ------------------------------------------------------

    def postings(self, term: str) -> list[Posting]:
        """
        Return the inverted list for `term`, or an empty list if the
        term is not in the vocabulary. Term lookup is case-insensitive,
        consistent with the tokeniser.
        """
        return self.tokens.get(term.lower(), [])

    def document_frequency(self, term: str) -> int:
        """How many distinct documents contain `term`?"""
        return len(self.postings(term))

    @property
    def num_documents(self) -> int:
        return len(self.documents)

    @property
    def avg_doc_length(self) -> float:
        if not self.documents:
            return 0.0
        total = sum(d.length for d in self.documents.values())
        return total / len(self.documents)

    # ---- persistence --------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Serialise the index to JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        self.build_time = datetime.now(timezone.utc).isoformat(timespec="seconds")

        payload = {
            "tokens": {
                term: [p.to_dict() for p in postings]
                for term, postings in self.tokens.items()
            },
            "documents": {
                str(doc_id): record.to_dict()
                for doc_id, record in self.documents.items()
            },
            "stats": {
                "N": self.num_documents,
                "avg_doc_len": self.avg_doc_length,
                "build_time_iso": self.build_time,
            },
        }

        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.info(
            "saved index: %d docs, %d terms -> %s",
            self.num_documents, len(self.tokens), path,
        )

    @classmethod
    def load(cls, path: str | Path, tokeniser: Tokeniser | None = None) -> "InvertedIndex":
        """Deserialise an index previously written by `save()`."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"no index file at {path}")

        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        index = cls(tokeniser=tokeniser or Tokeniser())
        index.tokens = {
            term: [Posting.from_dict(p) for p in postings]
            for term, postings in payload.get("tokens", {}).items()
        }
        index.documents = {
            int(doc_id): DocumentRecord.from_dict(record)
            for doc_id, record in payload.get("documents", {}).items()
        }
        index.build_time = payload.get("stats", {}).get("build_time_iso", "")

        logger.info(
            "loaded index: %d docs, %d terms from %s",
            index.num_documents, len(index.tokens), path,
        )
        return index