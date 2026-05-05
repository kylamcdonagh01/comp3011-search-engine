# Design Notes

This document records the non-trivial design decisions made during development, the alternatives considered, and the trade-offs involved. It is intended to support the "code walkthrough & design decisions" segment of the video demonstration.

## Index data structure

**Chosen:** `dict[str, list[Posting]]` where `Posting` is `{doc_id: int, tf: int, positions: list[int]}`.

**Considered alternatives:**

- `dict[str, dict[int, dict]]` keyed by `doc_id`. Faster lookup of a specific (term, doc) pair (O(1) instead of O(|postings|)), but JSON requires string keys, forcing `str(doc_id)` round-trips and obscuring the structure on disk. Lecture 12 also describes the inverted *list* model, so a list more closely matches the canonical structure.
- `dict[str, list[tuple[int, int, list[int]]]]` (tuples instead of dicts). Smaller in memory, but tuples become arrays in JSON and lose their named-field readability.

## Tokenisation

**Chosen:** lowercase the document text, then `re.findall(r"[a-z0-9']+", text)`. Keeps contractions (`don't`, `it's`) as single tokens. Stopword removal and stemming are off by default but available as constructor flags.

**Why not strip stopwords?** Lecture 11 notes that a query like "to be or not to be" is entirely stopwords. Hard-removing them at index time would make such queries unanswerable. We make it a configuration choice.

**Why not stem by default?** English stemming yields only a 5–10% improvement on average (Lecture 11) and complicates the user model — `find swim` matching `swimming` may surprise users. Available as an opt-in.

## Politeness window

**Chosen:** 6.0–7.5 second uniform jitter via `time.sleep(6 + random.uniform(0, 1.5))`.

**Why jitter?** The brief mandates *at least* 6 seconds; Lecture 9 separately notes that perfectly periodic requests are themselves a bot signature, so adding jitter both satisfies the brief and follows the lecture's guidance for well-behaved crawlers.

## Storage format

**Chosen:** JSON.

**Trade-offs:**

| Format | Size | Read speed | Inspectable | Schema-safe |
|---|---|---|---|---|
| JSON | baseline | slow | ✅ | ❌ |
| Pickle | ~70% | fast | ❌ | ❌ |
| MessagePack | ~50% | fast | ❌ | ❌ |
| SQLite | varies | very fast | partial | ✅ |

For a corpus of ~10 pages and ~1000 unique terms, the index is on the order of 100 KB. Storage size and read speed are both negligible. Inspectability is the deciding factor — markers can open the file and verify its structure, and the format is human-readable for debugging.

## Ranking

**Chosen:** TF–IDF, computed as `score(d, q) = Σ_{t ∈ q} (1 + log(tf_{t,d})) · log(N / df_t)`.

**Why log-TF?** Pure term frequency over-rewards documents that repeat a word; log-scaling dampens this effect.

**Why this isn't BM25:** BM25 adds a length normalisation term and a saturation parameter. With only ~10 documents of similar length, the additional parameters add complexity without measurably improving rankings on this corpus. TF–IDF is the lecture's framework and is sufficient here.

## Complexity

For a corpus of N documents, V unique terms, and a query of k terms:

| Operation | Time | Space |
|---|---|---|
| Build (single pass over corpus) | O(total tokens) | O(V × avg postings/term) |
| `print word` | O(\|postings(word)\|) | O(1) extra |
| `find` (single term) | O(\|postings(term)\|) | O(\|postings(term)\|) |
| `find` (k terms, AND) | O(k · min(\|postings\|)) | O(min(\|postings\|)) |
| TF–IDF ranking | O(k · \|matched docs\|) | O(\|matched docs\|) |

Set intersection always starts from the smallest posting list — a standard optimisation that turns worst-case k·max into k·min.

## Error handling

The crawler treats network and parse failures as soft errors: log, skip the page, continue. The indexer treats malformed HTML as soft errors. Only the CLI raises hard errors, on the principle that an interactive user wants to know immediately when something is wrong with their command.