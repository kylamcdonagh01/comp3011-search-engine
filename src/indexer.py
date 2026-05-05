"""
Inverted-index construction and persistence.

The index maps each lowercase token to a list of postings. Each posting
records (doc_id, term_frequency, [positions]). A separate documents
table maps doc_ids back to URLs and stores per-document metadata such
as length, which is needed for ranking.

This structure follows the model presented in Lecture 12: an index term
points to an inverted list of postings, and a separate document table
maps document IDs to URLs.
"""

# Implementation will be added on the feat/indexer branch.