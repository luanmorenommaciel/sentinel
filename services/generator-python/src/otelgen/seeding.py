from __future__ import annotations

import random


def make_rng(seed: int) -> random.Random:
    """Return a seeded, isolated Random instance for deterministic runs."""
    return random.Random(seed)


def new_trace_id(rng: random.Random) -> str:
    """Return a 32-hex-character trace ID."""
    return format(rng.getrandbits(128), "032x")


def new_span_id(rng: random.Random) -> str:
    """Return a 16-hex-character span ID."""
    return format(rng.getrandbits(64), "016x")
