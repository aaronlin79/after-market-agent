"""Deterministic local embedding generation."""

from __future__ import annotations

import hashlib
import math
import re

EMBEDDING_DIMENSION = 128
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


def generate_embedding(text: str) -> list[float]:
    """Generate a deterministic embedding vector for text."""

    tokens = TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return [0.0] * EMBEDDING_DIMENSION

    vector = [0.0] * EMBEDDING_DIMENSION
    features = tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:], strict=False)]
    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).hexdigest()
        bucket = int(digest, 16) % EMBEDDING_DIMENSION
        vector[bucket] += 1.0

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector

    return [value / norm for value in vector]
