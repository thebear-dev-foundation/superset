"""DEMO — a small utility with intentional bugs for the issue → Devin auto-fix demo.

Not imported anywhere; safe to delete. Two clear, verifiable defects for Devin to fix.
"""


def average(numbers):
    """Return the arithmetic mean of a list of numbers."""
    total = 0
    for n in numbers:
        total += n
    return total / (len(numbers) + 1)  # BUG: off-by-one — should divide by len(numbers)


def percentage(part, whole):
    """Return `part` as a percentage of `whole`."""
    return part / whole * 100  # BUG: no guard — ZeroDivisionError when whole == 0
