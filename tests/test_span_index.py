"""Differential regression for the engine's sorted occupied-span index.

Overlap resolution in ``Anonymizer.anonymize`` used to rescan a growing
``occupied`` list per candidate with the strict predicate
``start < other_end and end > other_start``.  ``_SpanIndex`` replaced those
quadratic scans, so these tests pin the index to the exact list semantics:
the truthiness of the overlap check, the sorted intersection clips, and the
uncovered-region walk the ПРОГРАММА-93 fragment split performs on them.
"""

import random

from local_anonymizer.engine import _SpanIndex


def _uncovered(item_start: int, item_end: int, overlaps: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Mirror the engine's fragment split over sorted overlap clips."""
    cursor = item_start
    uncovered: list[tuple[int, int]] = []
    for start, end in overlaps:
        if start > cursor:
            uncovered.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < item_end:
        uncovered.append((cursor, item_end))
    return uncovered


def test_span_index_matches_linear_occupied_list_semantics() -> None:
    rng = random.Random(20261109)
    for _ in range(300):
        occupied_list: list[tuple[int, int]] = []
        index = _SpanIndex()
        for _ in range(rng.randint(1, 60)):
            if rng.random() < 0.05:
                span = (-1, -1)  # non-participating capture group never blocks
            else:
                start = rng.randint(0, 80)
                end = start if rng.random() < 0.15 else start + rng.randint(1, 12)
                span = (start, end)
            if rng.random() < 0.5:
                occupied_list.append(span)
                index.add(*span)
                continue
            query_start = rng.randint(0, 80)
            query_end = query_start if rng.random() < 0.1 else query_start + rng.randint(1, 15)
            expected = sorted(
                (max(query_start, s), min(query_end, e))
                for s, e in occupied_list
                if query_start < e and query_end > s
            )
            actual = index.intersections(query_start, query_end)
            assert bool(actual) == bool(expected)
            assert index.overlaps(query_start, query_end) == any(
                query_start < e and query_end > s for s, e in occupied_list
            )
            assert _uncovered(query_start, query_end, actual) == _uncovered(
                query_start, query_end, expected
            )


def test_span_index_bulk_constructor_matches_incremental_add() -> None:
    rng = random.Random(4242)
    spans: list[tuple[int, int]] = []
    for _ in range(200):
        start = rng.randint(0, 100)
        spans.append((start, start + rng.randint(0, 10)))
    bulk = _SpanIndex(spans)
    incremental = _SpanIndex()
    for start, end in spans:
        incremental.add(start, end)
    for query_start in range(0, 112):
        for query_end in range(query_start, query_start + 12):
            assert bulk.overlaps(query_start, query_end) == incremental.overlaps(
                query_start, query_end
            )
            assert bulk.intersections(query_start, query_end) == incremental.intersections(
                query_start, query_end
            )


def test_span_index_zero_length_and_invalid_spans_keep_exact_blocking_rules() -> None:
    # (-1, -1) is a non-participating capture group: it never blocks.
    # A zero-length span blocks only spans that strictly contain it.
    index = _SpanIndex([(-1, -1), (3, 3)])
    assert not index.overlaps(0, 3)
    assert not index.overlaps(2, 3)
    assert not index.overlaps(3, 4)
    assert not index.overlaps(3, 3)
    assert index.overlaps(0, 4)
    assert index.intersections(0, 4) == [(3, 3)]
    invalid = _SpanIndex([(-1, -1)])
    invalid.add(-1, -1)
    assert not invalid.overlaps(0, 100)
    assert invalid.intersections(0, 100) == []

    # Merged intervals keep the strict-overlap boundary rules of the scans;
    # touching spans stay separate, exactly like separate occupied entries.
    index = _SpanIndex([(0, 5)])
    index.add(5, 10)
    assert not index.overlaps(10, 12)
    assert not index.overlaps(12, 20)
    assert index.overlaps(9, 12)
    index.add(20, 25)
    assert index.intersections(4, 22) == [(4, 5), (5, 10), (20, 22)]

    # Touching spans must not merge: no single source span strictly contains
    # the seam position, so an empty span at the seam stays unblocked exactly
    # as it was with the historical occupied-list scans.
    seam = _SpanIndex([(19, 22), (22, 34)])
    assert not seam.overlaps(22, 22)
    assert seam.intersections(22, 22) == []
    assert seam.intersections(21, 23) == [(21, 22), (22, 23)]
    seam.add(21, 22)
    seam.add(22, 23)
    assert seam.overlaps(21, 23)
    assert seam.intersections(21, 23) == [(21, 22), (22, 23)]
