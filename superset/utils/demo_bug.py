"""DEMO — a small utility with intentional bugs for the issue → Devin auto-fix demo.

Not imported anywhere; safe to delete. Two clear, verifiable defects for Devin to fix.
"""

from __future__ import annotations


def average(numbers: list[float]) -> float:
    """Return the arithmetic mean of *numbers*.

    Raises ``ValueError`` when the input list is empty.
    """
    if not numbers:
        raise ValueError("cannot compute the average of an empty list")
    total: float = 0
    for n in numbers:
        total += n
    return total / len(numbers)


def percentage(part: float, whole: float) -> float:
    """Return *part* as a percentage of *whole*.

    Raises ``ValueError`` when *whole* is zero.
    """
    if whole == 0:
        raise ValueError("whole must be non-zero")
    return part / whole * 100
