"""Centralized access to NovaPlan's synthetic demonstration datasets."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


DATE_COLUMNS: dict[str, list[str]] = {
    "monthly_kpis": ["month"],
    "invoices": ["invoice_date", "expected_payment_date", "actual_payment_date"],
    "employees": ["hire_date"],
    "hiring_plan": ["joining_month"],
    "capex": ["month"],
    "opex": ["month"],
    "weekly_cash_actuals": ["week"],
}


@lru_cache(maxsize=32)
def load_dataset(name: str) -> pd.DataFrame:
    """Load one generated CSV and parse any known date columns."""
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path.name}. Run `python synthetic/generate_company.py` first."
        )
    frame = pd.read_csv(path)
    for column in DATE_COLUMNS.get(name, []):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def refresh_data() -> None:
    """Clear cached datasets after a regeneration or audit-log write."""
    load_dataset.cache_clear()

