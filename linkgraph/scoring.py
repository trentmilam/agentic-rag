"""Co-mention scoring: the isolated, unit-testable rule behind the
``co_mentions`` edge type.

Scoring rule (documented, not a magic constant): the score of a pair
``(u, v)`` is the number of DISTINCT ``doc_id``s in which both appear at least
once. Two mentions of the same entity within one document count once, not
per-mention -- co-mention is a document-level "these two things showed up
together" signal, not a token-frequency one, so double-mentioning one entity
in a document it already shares with another should not inflate their score.
Raw counts (not a normalized fraction) are used because, unlike a document-
length-sensitive metric, "how many separate documents put these two together"
is directly interpretable on its own and gets more confident with more
evidence -- exactly the property a weak, corroborating signal needs.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Iterable, Mapping


def co_mention_scores(doc_groups: Mapping[str, Iterable[str]]) -> dict[tuple[str, str], int]:
    """``doc_groups``: ``doc_id -> the node ids mentioned in that document``.

    Returns ``{(a, b): count}`` for every pair that co-occurs in at least one
    document, keyed by a canonical ``a < b`` sorted tuple.
    """
    counts: Counter[tuple[str, str]] = Counter()
    for entity_ids in doc_groups.values():
        uniq = sorted(set(entity_ids))
        for a, b in combinations(uniq, 2):
            counts[(a, b)] += 1
    return dict(counts)
