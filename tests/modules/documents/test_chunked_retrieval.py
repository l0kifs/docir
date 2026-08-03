"""The defect chunking exists to fix, driven through the real model.

``bge-small-en-v1.5`` reads roughly 512 tokens and silently ignores the rest.
Measured on this project's own prose that is about 1,900 characters, and 83 of
the 103 documents in docir's own store are longer than that — their tails were
not ranked badly, they were **absent from the semantic index**. Appending a
sentence past the window leaves the vector bit-identical.

These tests are ``slow`` and use the real model on purpose: the hermetic default
(`DeterministicEmbedder`) is signed feature hashing with no token limit at all,
so it cannot exhibit the bug and would pass either way. A test that cannot fail
has not been shown to work.

The isolation matters as much as the model. Full-text search covers the *whole*
body, so on any query sharing vocabulary with the document, FTS5 finds the tail
and RRF pulls the document to rank 1 whether or not the vector saw it. Every
test here therefore asks the semantic side alone, in words the document does not
use.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import Container, build_container
from docir.entry_points.dispatch import Dispatcher
from docir.platform.embedding.fastembed import FastEmbedEmbedder

pytestmark = pytest.mark.slow

#: Padding placed *before* the answer so the answer falls outside the window.
#: Real prose on unrelated subjects rather than repeated filler: a degenerate
#: string tokenizes differently and would put the boundary somewhere no document
#: ever hits. Measured — one copy (1,687 chars) is still *inside* the window at
#: cosine 0.971, two copies (3,374) are fully past it at 1.000000 — which is why
#: `_LONG_BODY` doubles it rather than trusting the round number.
_PADDING = """\
## Queue topology

Each consumer owns a primary queue and a dead-letter queue. A message is retried
in place three times with exponential backoff, then moved to the dead-letter
queue with its failure reason attached. Dead-letter queues are monitored but
never drained automatically, because replaying a batch that already failed tends
to reproduce the failure at volume.

## Settlement reconciliation

The provider publishes a settlement file once a day. A nightly job matches each
settled line against our captured payments and writes a reconciliation record.
Real-time reconciliation was rejected because the provider's own figures are not
final until the file lands, and reconciling against provisional numbers produced
corrections that were themselves wrong.

## Order state machine

An order is one of pending, authorized, captured, settled, refunded or
cancelled, and the legal transitions between them are declared in one table.
Anything else is rejected at write time rather than discovered later in a
report. The table is the specification; there is no second copy of it in code.

## Currency rounding

Amounts are stored as integer minor units, never as floats. Where a division is
unavoidable, such as splitting a discount across line items, we round half to
even so repeated splits do not drift upward. The remainder is assigned to the
largest line item, which keeps the sum exact.

## Idempotency

The capture endpoint accepts an idempotency key. The first request for a key
performs the capture and stores the response; any later request with the same
key replays that stored response without contacting the gateway. Keys are scoped
per merchant and expire after 24 hours.
"""

#: The answer. Placed last, past the window, and phrased so it shares no
#: distinctive vocabulary with the query that finds it — "hibernation" and
#: "burrow" appear nowhere in it, so FTS5 cannot rescue the document.
_BURIED_ANSWER = """\
## Winter dormancy of the common dormouse

The animal spends the cold months curled in a nest of woven grass beneath the
leaf litter, its body temperature falling to that of the surrounding soil. It
neither eats nor drinks for as long as six months, drawing on fat laid down in
autumn, and rouses only briefly when a warm spell reaches the nest floor.
"""

#: Shares no content word with the section it must retrieve, so nothing but the
#: vector can connect the two. It is not asserted that FTS5 returns *nothing* —
#: FTS5 has no stopword list, so "which" and "through" match any English text at
#: a negligible score. The tests below assert on `similarity`, the raw cosine,
#: which no lexical match can influence at all.
_PARAPHRASED_QUERY = "which creature hibernates through winter underground"

#: Two copies of the padding, so the answer is unambiguously past the window.
_LONG_BODY = _PADDING + _PADDING + "\n" + _BURIED_ANSWER


@pytest.fixture
def real_container(tmp_path, monkeypatch) -> Iterator[Container]:
    """A store using the real ONNX model, which is the only one that truncates."""
    monkeypatch.setenv("DOCIR_HOME", str(tmp_path / "docir"))
    monkeypatch.setenv("DOCIR_NO_DAEMON", "1")
    monkeypatch.delenv("DOCIR_EMBEDDER", raising=False)
    built = build_container(Settings.resolve(), background_embeddings=False)
    try:
        yield built
    finally:
        built.close()


def _add_long_document(dispatcher: Dispatcher) -> str:
    view = dispatcher.dispatch(
        "add",
        {
            "type": "architecture",
            "title": "Payment platform notes",
            "description": "Assorted notes on the payment platform.",
            "body": _LONG_BODY,
            "wait_embeddings": True,
        },
    )
    return view["id"]


def test_the_model_really_does_truncate(real_container: Container) -> None:
    """The premise, asserted rather than assumed.

    If a future model reads the whole body, chunking stops being a correctness
    fix and becomes a precision tweak — and this test says so out loud instead
    of leaving the other tests in this file mysteriously redundant.
    """
    embedder = FastEmbedEmbedder()
    head = _PADDING + _PADDING
    identical = embedder.embed(head).cosine_similarity(embedder.embed(head + _BURIED_ANSWER))
    assert identical == pytest.approx(1.0, abs=1e-9), (
        "the model now reads past ~512 tokens; revisit whether chunking is still a fix"
    )


def test_a_buried_section_is_what_the_query_matches(real_container: Container) -> None:
    """The bug: text past the window was absent from the semantic index.

    Asserts on ``similarity`` — the raw cosine — rather than on rank, and that
    is the whole point of the test. Rank is decided by RRF over the lexical and
    semantic lists, so in a small store a document reaches rank 1 on a stopword
    match alone and the assertion would hold with chunking ripped out.
    ``similarity`` cannot be reached by the lexical side at all.

    The expected value is computed here rather than hardcoded: what the document
    should score is what its buried section scores, because that section is now
    a vector of its own. Without chunking it scores what the *truncated* body
    scores, which is measurably lower — the two bounds are asserted separately
    so a failure says which way it went.
    """
    doc_id = _add_long_document(real_container.dispatcher)
    embedder = FastEmbedEmbedder()
    query = embedder.embed(_PARAPHRASED_QUERY)
    answer_alone = query.cosine_similarity(embedder.embed(_BURIED_ANSWER))
    truncated_document = query.cosine_similarity(embedder.embed(_LONG_BODY))

    results = real_container.dispatcher.dispatch(
        "context", {"task": _PARAPHRASED_QUERY, "limit": 5, "expand": 0}
    )
    matched = next(row for row in results if row["id"] == doc_id)

    assert matched["similarity"] > truncated_document, (
        "the document scored no better than its truncated whole-body vector — "
        "the buried section is not in the index"
    )
    # The chunk carries a title prefix, so it does not score *identically* to
    # the raw section; it must land near it rather than near the truncated body.
    assert matched["similarity"] == pytest.approx(answer_alone, abs=0.15)


def test_the_head_of_the_document_still_ranks(real_container: Container) -> None:
    """Chunking must add reach, not move it.

    The head was always inside the window and always findable; a chunking bug
    that replaced the document vector rather than supplementing it would break
    this while leaving the buried-section test green.
    """
    doc_id = _add_long_document(real_container.dispatcher)
    results = real_container.dispatcher.dispatch(
        "context", {"task": "retry a failed message from the dead letter queue", "limit": 5}
    )
    assert doc_id in [row["id"] for row in results]
