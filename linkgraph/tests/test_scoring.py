"""Co-mention scoring: plausibility checked via RELATIVE inequalities (more
shared documents -> a strictly higher score), never a magic constant."""
from linkgraph.scoring import co_mention_scores


def test_more_shared_documents_scores_strictly_higher():
    doc_groups = {
        "doc-1": ["a", "b"],
        "doc-2": ["a", "b"],
        "doc-3": ["a", "c"],  # a+c share only this one doc
    }
    scores = co_mention_scores(doc_groups)
    assert scores[("a", "b")] > scores[("a", "c")]


def test_never_co_mentioned_pair_has_no_entry():
    doc_groups = {"doc-1": ["a", "b"], "doc-2": ["c", "d"]}
    scores = co_mention_scores(doc_groups)
    assert ("a", "c") not in scores
    assert ("a", "d") not in scores


def test_repeated_mention_of_one_entity_in_one_doc_does_not_inflate_the_score():
    # entity "a" mentioned 3x in the SAME doc as "b" once -- still one document
    # of shared evidence, not three.
    doc_groups = {"doc-1": ["a", "a", "a", "b"]}
    scores = co_mention_scores(doc_groups)
    assert scores[("a", "b")] == 1


def test_score_key_is_canonically_sorted():
    scores = co_mention_scores({"doc-1": ["z", "a"]})
    assert ("a", "z") in scores
    assert ("z", "a") not in scores


def test_deterministic_across_repeated_calls():
    doc_groups = {"doc-1": ["a", "b", "c"], "doc-2": ["b", "c"]}
    assert co_mention_scores(doc_groups) == co_mention_scores(doc_groups)
