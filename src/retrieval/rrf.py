"""Reciprocal Rank Fusion (RRF) and candidate rank combination."""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[T, float]]],
    key_func,
    k: int = 60,
) -> list[tuple[T, float]]:
    """Combines multiple ranked candidate lists using RRF score formula: sum(1 / (k + rank))."""
    scores: dict[str, float] = {}
    item_map: dict[str, T] = {}

    for ranked_list in ranked_lists:
        for rank, (item, _) in enumerate(ranked_list, start=1):
            key = key_func(item)
            item_map[key] = item
            if key not in scores:
                scores[key] = 0.0
            scores[key] += 1.0 / (k + rank)

    sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return [(item_map[k], scores[k]) for k in sorted_keys]
