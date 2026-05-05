"""
Tests for src.search.

Builds small in-memory indices via InvertedIndex.add_document and
exercises the Search class against them. Covers print/find behaviour,
multi-word AND semantics, TF-IDF ranking, and edge cases (empty
queries, unknown words, queries that match nothing).
"""

import math

import pytest

from src.indexer import InvertedIndex, Tokeniser
from src.search import PrintEntry, Search, SearchResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def index_three_docs():
    """A small corpus useful for several tests."""
    idx = InvertedIndex()
    idx.add_document(0, "https://example.com/0", "<p>good morning good friends</p>")
    idx.add_document(1, "https://example.com/1", "<p>good evening</p>")
    idx.add_document(2, "https://example.com/2", "<p>see you friends</p>")
    return idx


@pytest.fixture
def searcher(index_three_docs):
    return Search(index=index_three_docs)


# ---------------------------------------------------------------------------
# print_term
# ---------------------------------------------------------------------------


class TestPrintTerm:
    def test_returns_postings_for_known_term(self, searcher):
        entries = searcher.print_term("good")
        assert len(entries) == 2
        assert {e.doc_id for e in entries} == {0, 1}

    def test_print_entry_has_url_and_positions(self, searcher):
        entries = searcher.print_term("good")
        for entry in entries:
            assert isinstance(entry, PrintEntry)
            assert entry.url.startswith("https://example.com/")
            assert isinstance(entry.positions, list)
            assert entry.tf == len(entry.positions)

    def test_unknown_term_returns_empty_list(self, searcher):
        assert searcher.print_term("nonexistent") == []

    def test_empty_term_returns_empty_list(self, searcher):
        assert searcher.print_term("") == []
        assert searcher.print_term("   ") == []

    def test_punctuation_only_returns_empty_list(self, searcher):
        assert searcher.print_term("!!!") == []

    def test_case_insensitive(self, searcher):
        lower = searcher.print_term("good")
        upper = searcher.print_term("GOOD")
        assert {e.doc_id for e in lower} == {e.doc_id for e in upper}


# ---------------------------------------------------------------------------
# find: basic semantics
# ---------------------------------------------------------------------------


class TestFindSingleWord:
    def test_finds_documents_containing_term(self, searcher):
        results = searcher.find("good")
        assert {r.doc_id for r in results} == {0, 1}

    def test_returns_search_result_objects(self, searcher):
        results = searcher.find("good")
        for r in results:
            assert isinstance(r, SearchResult)
            assert r.url
            assert r.score > 0

    def test_unknown_word_returns_empty(self, searcher):
        assert searcher.find("xyz") == []

    def test_empty_query_returns_empty(self, searcher):
        assert searcher.find("") == []
        assert searcher.find("    ") == []

    def test_punctuation_only_query_returns_empty(self, searcher):
        assert searcher.find("???") == []

    def test_case_insensitive(self, searcher):
        lower = {r.doc_id for r in searcher.find("good")}
        upper = {r.doc_id for r in searcher.find("GOOD")}
        assert lower == upper


# ---------------------------------------------------------------------------
# find: multi-word AND semantics
# ---------------------------------------------------------------------------


class TestFindMultiWord:
    def test_intersection_of_postings(self, searcher):
        # "good" -> {0, 1}; "friends" -> {0, 2}; AND -> {0}
        results = searcher.find("good friends")
        assert {r.doc_id for r in results} == {0}

    def test_partial_match_excluded(self, searcher):
        # doc 1 has "good" but not "friends"; should not appear.
        results = searcher.find("good friends")
        assert 1 not in {r.doc_id for r in results}

    def test_no_intersection_returns_empty(self, searcher):
        # "evening" appears only in doc 1; "friends" appears in {0, 2}.
        # AND -> empty.
        assert searcher.find("evening friends") == []

    def test_one_unknown_word_makes_query_empty(self, searcher):
        # Even though "good" matches, an unknown second term forces the
        # AND result to empty.
        assert searcher.find("good NOTAWORD") == []

    def test_duplicate_query_terms_do_not_double_count(self, searcher):
        single = searcher.find("good")
        triple = searcher.find("good good good")
        # Same documents.
        assert {r.doc_id for r in single} == {r.doc_id for r in triple}
        # Same scores (dedup → identical computation).
        single_by_id = {r.doc_id: r.score for r in single}
        triple_by_id = {r.doc_id: r.score for r in triple}
        for doc_id, score in single_by_id.items():
            assert triple_by_id[doc_id] == pytest.approx(score)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


class TestRanking:
    def test_higher_tf_ranks_higher(self, searcher):
        # doc 0 has "good" twice; doc 1 has it once. Doc 0 should rank first.
        results = searcher.find("good")
        assert results[0].doc_id == 0
        assert results[0].score > results[1].score

    def test_results_sorted_descending_by_score(self):
        idx = InvertedIndex()
        idx.add_document(0, "u0", "<p>alpha</p>")
        idx.add_document(1, "u1", "<p>alpha alpha</p>")
        idx.add_document(2, "u2", "<p>alpha alpha alpha</p>")
        results = Search(index=idx).find("alpha")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_idf_zero_when_term_in_every_doc(self):
        # If a term appears in *every* document, log(N/df) = log(1) = 0,
        # so it contributes nothing to ranking.
        idx = InvertedIndex()
        for i in range(3):
            idx.add_document(i, f"u{i}", "<p>everywhere</p>")
        results = Search(index=idx).find("everywhere")
        for r in results:
            assert r.score == pytest.approx(0.0)

    def test_rare_term_outranks_common_term_contribution(self):
        # In a 3-doc corpus where "common" appears in all 3 and
        # "rare" appears in 1, the rare term contributes more weight.
        idx = InvertedIndex()
        idx.add_document(0, "u0", "<p>rare common</p>")
        idx.add_document(1, "u1", "<p>common</p>")
        idx.add_document(2, "u2", "<p>common</p>")

        common_only = Search(index=idx).find("common")
        # "rare common" matches only doc 0; "common" matches all 3.
        # Doc 0's score for "rare common" should beat its score for
        # "common" alone, because "rare" carries non-zero IDF.
        rare_combined = Search(index=idx).find("rare common")
        d0_combined = next(r.score for r in rare_combined if r.doc_id == 0)
        d0_common = next(r.score for r in common_only if r.doc_id == 0)
        assert d0_combined > d0_common

    def test_tie_break_is_deterministic(self):
        # Two docs identical in everything but doc_id should come back
        # in doc_id order.
        idx = InvertedIndex()
        idx.add_document(0, "u0", "<p>same same</p>")
        idx.add_document(1, "u1", "<p>same same</p>")
        results = Search(index=idx).find("same")
        assert [r.doc_id for r in results] == [0, 1]

    def test_score_matches_manual_tfidf_calculation(self):
        # Hand-verifiable example. 2 docs, query "alpha":
        #   doc 0: "alpha"           -> tf=1
        #   doc 1: "alpha alpha"     -> tf=2
        # df("alpha") = 2; N = 2 → idf = log(2/2) = 0.
        # Both scores should be exactly 0.
        idx = InvertedIndex()
        idx.add_document(0, "u0", "<p>alpha</p>")
        idx.add_document(1, "u1", "<p>alpha alpha</p>")
        results = Search(index=idx).find("alpha")
        for r in results:
            assert r.score == pytest.approx(0.0)

    def test_score_with_nonzero_idf(self):
        # df=1, N=2 → idf = log(2). doc 0 tf=1 → tf_weight = 1.
        # Score = 1 * log(2).
        idx = InvertedIndex()
        idx.add_document(0, "u0", "<p>unique</p>")
        idx.add_document(1, "u1", "<p>other</p>")
        results = Search(index=idx).find("unique")
        assert results[0].score == pytest.approx(math.log(2))


# ---------------------------------------------------------------------------
# Integration: matches the brief's exact examples
# ---------------------------------------------------------------------------


class TestBriefExamples:
    """The coursework brief gives three example commands; verify each."""

    def test_print_nonsense(self):
        # "> print nonsense" — single-doc match.
        idx = InvertedIndex()
        idx.add_document(0, "https://example.com/0", "<p>this is plain</p>")
        idx.add_document(1, "https://example.com/1", "<p>complete nonsense here</p>")
        idx.add_document(2, "https://example.com/2", "<p>nothing relevant</p>")
        entries = Search(index=idx).print_term("nonsense")
        assert len(entries) == 1
        assert entries[0].doc_id == 1
        assert entries[0].tf == 1

    def test_find_indifference(self):
        # "> find indifference" — single-word find.
        idx = InvertedIndex()
        idx.add_document(0, "u0", "<p>love and hate</p>")
        idx.add_document(1, "u1", "<p>indifference is worse</p>")
        results = Search(index=idx).find("indifference")
        assert len(results) == 1
        assert results[0].doc_id == 1

    def test_find_good_friends(self):
        # "> find good friends" — multi-word find.
        idx = InvertedIndex()
        idx.add_document(0, "u0", "<p>good friends are precious</p>")
        idx.add_document(1, "u1", "<p>good food only</p>")
        idx.add_document(2, "u2", "<p>old friends always</p>")
        idx.add_document(3, "u3", "<p>good good friends forever</p>")
        results = Search(index=idx).find("good friends")
        assert {r.doc_id for r in results} == {0, 3}
        # doc 3 has tf("good")=2; doc 0 has tf("good")=1. Doc 3 ranks first.
        assert results[0].doc_id == 3