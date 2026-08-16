"""Small, consistent number-formatting helpers used across the UI."""

from __future__ import annotations


def euro(value: float, decimals: int = 1) -> str:
    """Format a euro value compactly for executive displays."""
    absolute = abs(float(value))
    sign = "−" if value < 0 else ""
    if absolute >= 1_000_000:
        return f"{sign}€{absolute / 1_000_000:.{decimals}f}m"
    if absolute >= 1_000:
        return f"{sign}€{absolute / 1_000:.{decimals}f}k"
    return f"{sign}€{absolute:,.0f}"


def percent(value: float, decimals: int = 1) -> str:
    """Format a decimal ratio as a percentage."""
    return f"{float(value) * 100:.{decimals}f}%"


def number(value: float, decimals: int = 0) -> str:
    """Format a plain number with thousands separators."""
    return f"{float(value):,.{decimals}f}"


def pp(value: float, decimals: int = 1) -> str:
    """Format a decimal difference in percentage points."""
    sign = "+" if value > 0 else ""
    return f"{sign}{float(value) * 100:.{decimals}f}pp"

