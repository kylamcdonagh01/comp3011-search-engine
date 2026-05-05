"""
Tests for src.indexer.

Covers tokenisation, posting-list construction, position correctness,
JSON round-trip persistence, and edge cases (unicode, empty input,
duplicate doc_id, missing files).
"""

import json

import pytest

from src.indexer import (
    DEFAULT_STOPWORDS,
    DocumentRecord,
    InvertedIndex,
    Posting,
    Tokeniser,
)


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------


class TestTokeniser:
    def test_lowercases(self):
        t = Tokeniser()
        assert t.tokenise("Hello WORLD") == ["hello", "world"]

    def test_splits_on_punctuation(self):
        t = Tokeniser()
        assert t.tokenise("hello, world! good-bye?") == ["hello", "world", "good", "bye"]

    def test_keeps_contractions(self):
        t = Tokeniser()
        assert t.tokenise("don't can't won't") == ["don't", "can't", "won't"]

    def test_empty_string(self):
        t = Tokeniser()
        assert t.tokenise("") == []

    def test_only_punctuation(self):
        t = Tokeniser()
        assert t.tokenise("!!! ??? ...") == []

    def test_handles_unicode(self):
        t = Tokeniser()
        # Accented letters do not match [a-z], so they get split.
        # We assert the *behaviour*, which is consistent: we don't crash.
        result = t.tokenise("café résumé")
        assert isinstance(result, list)
        # ASCII letters survive even when adjacent to non-ASCII ones.
        assert "caf" in result
        assert "r" in result

    def test_numbers_are_tokens(self):
        t = Tokeniser()
        assert t.tokenise("year 2026 quotes") == ["year", "2026", "quotes"]

    def test_stopwords_kept_by_default(self):
        t = Tokeniser()
        assert "the" in t.tokenise("the quick brown fox")

    def test_stopwords_removed_when_flag_set(self):
        t = Tokeniser(remove_stopwords=True)
        result = t.tokenise("the quick brown fox")
        assert "the" not in result
        assert "quick" in result

    def test_strips_html_tags(self):
        t = Tokeniser()
        tokens, title = t.tokenise_html("<p>Hello <b>world</b></p>")
        assert tokens == ["hello", "world"]

    def test_extracts_title(self):
        t = Tokeniser()
        html = "<html><head><title>My Page</title></head><body>x</body></html>"
        _, title = t.tokenise_html(html)
        assert title == "My Page"

    def test_drops_script_and_style_content(self):
        t = Tokeniser()
        html = """
            <html>
              <head>
                <style>body { color: red; }</style>
                <script>var secret = 42;</script>
              </head>
              <body>visible</body>
            </html>
        """
        tokens, _ = t.tokenise_html(html)
        # Body text is indexed; CSS/JS contents are not.
        assert "visible" in tokens
        assert "secret" not in tokens
        assert "color" not in tokens
        assert "var" not in tokens

    def test_separates_adjacent_tags(self):
        t = Tokeniser()
        tokens, _ = t.tokenise_html("<b>Hello</b><b>World</b>")
        assert tokens == ["hello", "world"]


# ---------------------------------------------------------------------------
# Posting / DocumentRecord round-trip
# ---------------------------------------------------------------------------


class TestPostingRoundTrip:
    def test_to_dict_and_back(self):
        original = Posting(doc_id=3, tf=5, positions=[1, 7, 19, 42, 99])
        round_tripped = Posting.from_dict(original.to_dict())
        assert round_tripped == original

    def test_document_record_round_trip(self):
        original = DocumentRecord(url="https://example.com/a", length=42, title="A")
        round_tripped = DocumentRecord.from_dict(original.to_dict())
        assert round_tripped == original


# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------


class TestAddDocument:
    def test_single_document_creates_postings(self):
        idx = InvertedIndex()
        idx.add_document(0, "https://example.com/", "<p>good morning good friends</p>")
        assert "good" in idx.tokens
        good_postings = idx.postings("good")
        assert len(good_postings) == 1
        assert good_postings[0].doc_id == 0
        assert good_postings[0].tf == 2

    def test_positions_recorded_correctly(self):
        idx = InvertedIndex()
        idx.add_document(0, "https://example.com/", "<p>alpha beta alpha gamma</p>")
        alpha_post = idx.postings("alpha")[0]
        assert alpha_post.positions == [0, 2]
        beta_post = idx.postings("beta")[0]
        assert beta_post.positions == [1]

    def test_multiple_documents_extend_posting_list(self):
        idx = InvertedIndex()
        idx.add_document(0, "https://example.com/0", "<p>shared word</p>")
        idx.add_document(1, "https://example.com/1", "<p>shared term</p>")
        shared = idx.postings("shared")
        assert len(shared) == 2
        assert {p.doc_id for p in shared} == {0, 1}

    def test_unknown_term_returns_empty_list(self):
        idx = InvertedIndex()
        idx.add_document(0, "https://example.com/", "<p>only this</p>")
        assert idx.postings("missing") == []

    def test_postings_lookup_is_case_insensitive(self):
        idx = InvertedIndex()
        idx.add_document(0, "https://example.com/", "<p>Cake is good</p>")
        # Index stores lowercase; query in any case still hits.
        assert idx.postings("CAKE") == idx.postings("cake")
        assert len(idx.postings("Cake")) == 1

    def test_duplicate_doc_id_raises(self):
        idx = InvertedIndex()
        idx.add_document(0, "https://example.com/", "<p>first</p>")
        with pytest.raises(ValueError, match="already indexed"):
            idx.add_document(0, "https://example.com/", "<p>second</p>")

    def test_document_frequency(self):
        idx = InvertedIndex()
        idx.add_document(0, "u0", "<p>alpha beta</p>")
        idx.add_document(1, "u1", "<p>alpha gamma</p>")
        idx.add_document(2, "u2", "<p>beta gamma</p>")
        assert idx.document_frequency("alpha") == 2
        assert idx.document_frequency("beta") == 2
        assert idx.document_frequency("delta") == 0

    def test_document_record_stores_metadata(self):
        idx = InvertedIndex()
        html = "<html><head><title>Greetings</title></head><body>hello world</body></html>"
        idx.add_document(0, "https://example.com/", html)
        record = idx.documents[0]
        assert record.url == "https://example.com/"
        assert record.title == "Greetings"
        # Title text is part of the page and is indexed alongside body text:
        # tokens are ["greetings", "hello", "world"].
        assert record.length == 3
        # The title term is also discoverable via the index:
        assert idx.postings("greetings")

    def test_avg_doc_length_with_no_docs(self):
        idx = InvertedIndex()
        assert idx.avg_doc_length == 0.0

    def test_avg_doc_length(self):
        idx = InvertedIndex()
        idx.add_document(0, "u0", "<p>one two three</p>")        # length 3
        idx.add_document(1, "u1", "<p>one two three four five</p>")  # length 5
        assert idx.avg_doc_length == 4.0


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_save_creates_valid_json(self, tmp_path):
        idx = InvertedIndex()
        idx.add_document(0, "https://example.com/", "<p>hello world</p>")
        path = tmp_path / "index.json"
        idx.save(path)

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        assert "tokens" in data
        assert "documents" in data
        assert "stats" in data
        assert data["stats"]["N"] == 1
        assert "hello" in data["tokens"]

    def test_round_trip_preserves_postings(self, tmp_path):
        original = InvertedIndex()
        original.add_document(0, "u0", "<p>alpha beta alpha</p>")
        original.add_document(1, "u1", "<p>beta gamma</p>")
        path = tmp_path / "index.json"
        original.save(path)

        loaded = InvertedIndex.load(path)
        assert loaded.num_documents == original.num_documents
        assert set(loaded.tokens.keys()) == set(original.tokens.keys())

        for term in original.tokens:
            orig_postings = sorted(original.postings(term), key=lambda p: p.doc_id)
            new_postings = sorted(loaded.postings(term), key=lambda p: p.doc_id)
            assert orig_postings == new_postings

    def test_round_trip_preserves_documents(self, tmp_path):
        original = InvertedIndex()
        original.add_document(
            0,
            "https://example.com/page",
            "<html><head><title>Title</title></head><body>hi</body></html>",
        )
        path = tmp_path / "index.json"
        original.save(path)

        loaded = InvertedIndex.load(path)
        assert loaded.documents[0].url == "https://example.com/page"
        assert loaded.documents[0].title == "Title"
        # tokens are ["title", "hi"] — title text is included in the body.
        assert loaded.documents[0].length == 2

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            InvertedIndex.load(tmp_path / "does_not_exist.json")

    def test_save_creates_parent_directory(self, tmp_path):
        idx = InvertedIndex()
        idx.add_document(0, "u", "<p>x</p>")
        nested_path = tmp_path / "deeply" / "nested" / "index.json"
        idx.save(nested_path)
        assert nested_path.exists()

    def test_save_records_build_time(self, tmp_path):
        idx = InvertedIndex()
        idx.add_document(0, "u", "<p>x</p>")
        path = tmp_path / "index.json"
        idx.save(path)
        assert idx.build_time  # non-empty ISO timestamp


# ---------------------------------------------------------------------------
# Stopwords
# ---------------------------------------------------------------------------


class TestStopwords:
    def test_default_stopwords_is_frozenset(self):
        assert isinstance(DEFAULT_STOPWORDS, frozenset)

    def test_index_with_stopword_removal(self):
        idx = InvertedIndex(tokeniser=Tokeniser(remove_stopwords=True))
        idx.add_document(0, "u", "<p>the quick brown fox</p>")
        assert "the" not in idx.tokens
        assert "quick" in idx.tokens