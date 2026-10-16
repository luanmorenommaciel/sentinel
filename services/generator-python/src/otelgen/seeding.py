from __future__ import annotations

import random


def make_rng(seed: int) -> random.Random:
    """Return a seeded, isolated Random instance for deterministic runs."""
    # Reproducibility IS the contract here: SEED=42 must replay the golden
    # fixture byte for byte. A CSPRNG would make the generator unseedable, so
    # bandit's B311 does not apply to synthetic telemetry.
    return random.Random(seed)  # nosec B311


def new_trace_id(rng: random.Random) -> str:
    """Return a 32-hex-character trace ID."""
    return format(rng.getrandbits(128), "032x")


def new_span_id(rng: random.Random) -> str:
    """Return a 16-hex-character span ID."""
    return format(rng.getrandbits(64), "016x")
