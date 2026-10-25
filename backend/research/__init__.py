"""Comparable Shorts discovery and grounded clip grading."""

class ResearchConfigError(RuntimeError):
    """Research setup error with a safe user-facing message."""


class QuotaBudgetExceeded(RuntimeError):
    """Research quota is unavailable; the caller should retry on another day."""
