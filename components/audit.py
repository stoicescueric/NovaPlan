"""Tiny file-backed audit trail for the demonstration planning workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import pandas as pd


AUDIT_PATH = Path(__file__).resolve().parents[1] / "data" / "audit_log.csv"
AUDIT_COLUMNS = [
    "timestamp",
    "scenario",
    "variable",
    "old_value",
    "new_value",
    "user",
    "rationale",
]
_LOCK = Lock()


def read_audit_log() -> pd.DataFrame:
    """Read the audit log, returning an empty shaped frame when absent."""
    if not AUDIT_PATH.exists():
        return pd.DataFrame(columns=AUDIT_COLUMNS)
    return pd.read_csv(AUDIT_PATH)


def append_audit_entry(
    scenario: str,
    variable: str,
    old_value,
    new_value,
    rationale: str,
) -> None:
    """Append one transparent management adjustment to the demo audit log."""
    row = pd.DataFrame(
        [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "scenario": scenario,
                "variable": variable,
                "old_value": old_value,
                "new_value": new_value,
                "user": "Demo User",
                "rationale": rationale.strip(),
            }
        ],
        columns=AUDIT_COLUMNS,
    )
    with _LOCK:
        existing = read_audit_log()
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        pd.concat([existing, row], ignore_index=True).to_csv(AUDIT_PATH, index=False)
