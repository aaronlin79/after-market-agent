"""Similarity helpers for article clustering."""

from __future__ import annotations

import math


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""

    if len(vec1) != len(vec2) or not vec1 or not vec2:
        return 0.0

    dot_product = sum(left * right for left, right in zip(vec1, vec2, strict=True))
    left_norm = math.sqrt(sum(value * value for value in vec1))
    right_norm = math.sqrt(sum(value * value for value in vec2))

    if left_norm == 0 or right_norm == 0:
        return 0.0

    return dot_product / (left_norm * right_norm)
