"""Statistical distribution samplers for realistic data generation."""

from __future__ import annotations

import math
import random
from typing import Any, List, Optional, Sequence, TypeVar

T = TypeVar("T")


def sample_uniform(low: float = 0.0, high: float = 1.0) -> float:
    """Sample from uniform continuous distribution [low, high)."""
    return random.uniform(low, high)


def sample_normal(
    mean: float = 0.0,
    std_dev: float = 1.0,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> float:
    """Sample from Gaussian (normal) distribution with optional truncation boundaries."""
    val = random.gauss(mean, std_dev)
    if min_val is not None:
        val = max(min_val, val)
    if max_val is not None:
        val = min(max_val, val)
    return val


def sample_lognormal(
    mean: float = 0.0,
    sigma: float = 1.0,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> float:
    """Sample from log-normal distribution (ideal for prices, transaction amounts, sizes)."""
    val = random.lognormvariate(mean, sigma)
    if min_val is not None:
        val = max(min_val, val)
    if max_val is not None:
        val = min(max_val, val)
    return val


def sample_exponential(
    scale: float = 1.0,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> float:
    """Sample from exponential distribution (e.g., inter-arrival times, durations)."""
    lam = 1.0 / max(scale, 1e-6)
    val = random.expovariate(lam)
    if min_val is not None:
        val = max(min_val, val)
    if max_val is not None:
        val = min(max_val, val)
    return val


def sample_poisson(lam: float = 1.0) -> int:
    """Sample from Poisson distribution (count of occurrences)."""
    # Knuth algorithm for generating Poisson random variable
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1


def sample_categorical(items: Sequence[T], weights: Optional[Sequence[float]] = None) -> T:
    """Sample item from a categorical distribution with optional weights."""
    if not items:
        raise ValueError("Cannot sample from empty sequence")
    if weights is not None:
        return random.choices(items, weights=weights, k=1)[0]
    return random.choice(items)
