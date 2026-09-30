"""Prometheus metrics for physical weather corroboration and operational monitoring."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# Provider fetch attempts by status and error reason
physical_provider_fetch_total = Counter(
    "physical_provider_fetch_total",
    "Total physical weather provider fetch attempts by provider, status, and reason",
    ["provider", "status", "reason"],
)

# Cache hit ratio counters
physical_cache_requests_total = Counter(
    "physical_cache_requests_total",
    "Total physical grid-hour cache requests by result (hit or miss)",
    ["result"],
)

# Verdict distribution by category
physical_verdicts_total = Counter(
    "physical_verdicts_total",
    "Total physical weather corroboration verdicts by category and verdict",
    ["category", "verdict"],
)

# Recomputation events
physical_recomputes_total = Counter(
    "physical_recomputes_total",
    "Total physical weather corroboration recomputations executed",
)

# Latency histograms
physical_fetch_duration_seconds = Histogram(
    "physical_fetch_duration_seconds",
    "Latency of physical weather observation fetches from providers in seconds",
    ["provider"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

physical_eval_duration_seconds = Histogram(
    "physical_eval_duration_seconds",
    "Latency of pure physical corroboration evaluation logic in seconds",
    ["category"],
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1],
)
