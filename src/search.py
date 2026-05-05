"""
Query processing and result ranking.

  - print <word>   -- dump the full posting list for a single term.
  - find <query>   -- return all documents containing every term in the
                       query, ranked by TF-IDF (Lecture 13).

Multi-word queries use AND semantics (set intersection of postings),
matching the example `find good friends`.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable

from src.indexer import InvertedIndex, Posting

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """One ranked hit returned by `find`."""
    doc_id: int
    url: str
    score: float
    title: str = ""

    def __str__(self) -> str:  # pragma: no cover -- formatting only
        return f"{self.url}   (score: {self.score:.2f})"


@dataclass
class PrintEntry:
    """One row in the `print` command's output."""
    doc_id: int
    url: str
    tf: int
    positions: list[int]


@dataclass
class Search:
    """
    Query processor backed by an InvertedIndex.

    The searcher does not own the index — it queries one. This keeps
    concerns separated: the indexer knows how to build, the searcher
    knows how to retrieve. We share the index's Tokeniser so query
    text is normalised exactly the way document text was, eliminating
    the classic "case mismatch" bug where queries silently miss.
    """

    index: InvertedIndex

    # ---- print --------------------------------------------------------

    def print_term(self, term: str) -> list[PrintEntry]:
        """
        Return the inverted list for a single term, with URLs resolved
        from the index's documents table. Used by the `print <word>`
        command in the CLI.

        An empty list means the term is not in the vocabulary.
        """
        if not term or not term.strip():
            return []

        # Tokenise the term to match how documents were processed.
        tokens = self.index.tokeniser.tokenise(term)
        if not tokens:
            return []
        # `print` is single-term per the brief; if the user pastes a
        # multi-word string, just look up the first token.
        normalised = tokens[0]

        entries: list[PrintEntry] = []
        for posting in self.index.postings(normalised):
            doc = self.index.documents.get(posting.doc_id)
            if doc is None:  # pragma: no cover -- invariant violation
                logger.warning("posting refers to missing doc_id %s", posting.doc_id)
                continue
            entries.append(
                PrintEntry(
                    doc_id=posting.doc_id,
                    url=doc.url,
                    tf=posting.tf,
                    positions=list(posting.positions),
                )
            )
        return entries

    # ---- find ---------------------------------------------------------

    def find(self, query: str) -> list[SearchResult]:
        """
        Return all documents matching every term in `query`, ranked by
        TF-IDF descending. Empty or all-stopword queries return [].
        """
        if not query or not query.strip():
            return []

        terms = self.index.tokeniser.tokenise(query)
        if not terms:
            return []

        # Deduplicate while preserving order (Python dict iteration order).
        terms = list(dict.fromkeys(terms))

        # Find candidate documents = intersection of doc_ids across all terms.
        # Start from the rarest term (smallest posting list) for efficiency:
        # this turns the worst case from k * max(|postings|) into k * min.
        terms_with_postings = [
            (t, self.index.postings(t)) for t in terms
        ]
        if any(len(postings) == 0 for _, postings in terms_with_postings):
            # If any query term is not in the index, the AND result is empty.
            return []

        terms_with_postings.sort(key=lambda tp: len(tp[1]))
        candidate_ids: set[int] = {p.doc_id for p in terms_with_postings[0][1]}
        for _, postings in terms_with_postings[1:]:
            candidate_ids &= {p.doc_id for p in postings}
            if not candidate_ids:
                return []

        # Score each candidate using TF-IDF.
        results: list[SearchResult] = []
        N = self.index.num_documents
        for doc_id in candidate_ids:
            score = 0.0
            for term, postings in terms_with_postings:
                tf = self._tf_for(doc_id, postings)
                df = len(postings)
                if tf == 0 or df == 0:
                    continue
                # log-scaled tf, log idf. Both natural logarithms.
                tf_weight = 1.0 + math.log(tf)
                idf_weight = math.log(N / df) if N > 0 else 0.0
                score += tf_weight * idf_weight

            doc = self.index.documents[doc_id]
            results.append(
                SearchResult(
                    doc_id=doc_id,
                    url=doc.url,
                    score=score,
                    title=doc.title,
                )
            )

        # Sort by score descending; tie-break on doc_id for determinism.
        results.sort(key=lambda r: (-r.score, r.doc_id))
        return results

    # ---- internals ----------------------------------------------------

    @staticmethod
    def _tf_for(doc_id: int, postings: Iterable[Posting]) -> int:
        """Return the term frequency in doc_id, or 0 if not present."""
        for posting in postings:
            if posting.doc_id == doc_id:
                return posting.tf
        return 0