import random


def exponential_backoff(
    attempt: int,
    base: float = 0.5,
    cap: float = 30.0,
    jitter: bool = True,
) -> float:
    """
    Exponential backoff with optional jitter.
    """
    delay = min(cap, base * (2 ** attempt))
    if jitter:
        delay *= random.uniform(0.7, 1.3)
    return delay