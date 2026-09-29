"""Pure-logic tests for chunking, stable IDs, and classification: no deps, fully offline."""
import pytest

from ragpack.chunk import chunk_text, classify_chunk, clean_text, content_hash, stable_id


def test_clean_text_collapses_whitespace():
    assert clean_text("a\r\n\r\n\r\n\r\nb   c") == "a\n\n\nb c"


def test_chunk_text_empty():
    assert chunk_text("") == []


def test_chunk_text_respects_max_and_overlaps():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(10))
    chunks = chunk_text(text, max_chars=400, overlap=80)
    assert len(chunks) > 1
    assert all(len(c) <= 400 + 80 for c in chunks)


def test_chunk_text_hard_splits_a_giant_block():
    chunks = chunk_text("x" * 5000, max_chars=1000, overlap=100)
    assert len(chunks) >= 5


def test_chunk_text_hard_split_overlap_does_not_split_words():
    # regression: the overlap-merge step always inserted "\n\n" between a chunk's
    # carried-over tail and the next chunk. For two hard-split tiles of the SAME
    # oversized block, that boundary falls mid-content (often mid-word) rather than
    # at a real paragraph break, so inserting "\n\n" there corrupted a word straddling
    # the split point (observed on a real PDF: "subse" + "\n\n" + "quent"). Distinct
    # per-position tokens (no blank lines, one giant block) make a corrupted word
    # detectable: a split token is not a member of the original token set.
    # A raw tile's own leading/trailing edge can legitimately land mid-word (plain
    # character-count slicing, same as any basic chunker); overlap exists to give
    # the *next* chunk that missing context, not to make this chunk's own edge a
    # whole word. The bug under test is different: a separator erroneously injected
    # into the *interior* of a chunk, corrupting a word nowhere near either edge.
    words = [f"word{i:04d}" for i in range(600)]
    text = " ".join(words)
    valid_tokens = set(words)
    chunks = chunk_text(text, max_chars=500, overlap=80)
    assert len(chunks) >= 3
    for c in chunks:
        tokens = c.replace("\n\n", " ").split()
        for token in tokens[1:-1]:  # interior tokens only; edges may be legitimately truncated
            assert token in valid_tokens, f"chunk contains a corrupted interior fragment: {token!r} (chunk: {c!r})"


def test_chunk_text_hard_split_overlap_not_duplicated():
    # regression: a single paragraph (no blank lines) larger than max_chars used to
    # get its own baked-in sliding-window overlap in the hard-split branch, and then
    # the final overlap pass prepended the same tail AGAIN, so each chunk after the
    # first contained the boundary text twice. Distinct words per position (not a
    # repeated char) make a duplicated span detectable.
    words = [f"w{i:04d}" for i in range(1200)]  # "w0000 w0001 ... " one giant paragraph
    text = " ".join(words)
    chunks = chunk_text(text, max_chars=1000, overlap=100)
    assert len(chunks) >= 3
    for c in chunks:
        tokens = c.split()
        assert len(tokens) == len(set(tokens)), f"chunk has duplicated tokens: {c!r}"


def test_stable_id_deterministic_and_path_independent():
    h = content_hash("hello")
    a = stable_id("docs/a.md", "docs/a.md", 0, h)
    b = stable_id("docs/a.md", "docs\\a.md", 0, h)   # backslashes normalized
    assert a == b
    assert a != stable_id("docs/a.md", "docs/a.md", 1, h)   # different chunk index -> different id


def test_classify_chunk():
    assert classify_chunk("def foo():\n    return 1 + (2 * 3)", ".py") == "code"
    assert classify_chunk("Just some ordinary prose about a topic and its background.") == "prose"
    assert classify_chunk("| a | b | c |\n| - | - | - |\n| 1 | 2 | 3 |") == "table"
    blob = "\n".join("deadbeef" * 40 for _ in range(5))
    assert classify_chunk(blob) == "blob"


def test_chunk_text_rejects_nonpositive_max_chars():
    with pytest.raises(ValueError):
        chunk_text("hello world", max_chars=0)
    with pytest.raises(ValueError):
        chunk_text("hello world", max_chars=-100)


def test_chunk_text_clamps_overlap_no_char_explosion():
    # regression (stress #10/#12): overlap >= max_chars must NOT degenerate to one chunk per char
    chunks = chunk_text("x" * 1000, max_chars=200, overlap=300)
    assert len(chunks) < 50
    assert all(len(c) <= 200 + 199 for c in chunks)
