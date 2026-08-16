"""Dash DataTable factory with a consistent NovaPlan visual system."""

from __future__ import annotations

from dash import dash_table


def data_table(
    table_id: str,
    data: list[dict],
    columns: list[dict] | None = None,
    *,
    page_size: int = 10,
    selectable: str | bool = False,
) -> dash_table.DataTable:
    """Create a clean, sortable, horizontally scrollable table."""
    if columns is None and data:
        columns = [{"name": key.replace("_", " ").title(), "id": key} for key in data[0]]
    return dash_table.DataTable(
        id=table_id,
        data=data,
        columns=columns or [],
        page_size=page_size,
        sort_action="native",
        filter_action="none",
        row_selectable=selectable,
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "#F6F8F7",
            "color": "#526067",
            "fontWeight": 600,
            "fontSize": "11px",
            "textTransform": "uppercase",
            "letterSpacing": "0.05em",
            "border": "none",
            "borderBottom": "1px solid #DDE3E0",
            "padding": "12px 14px",
        },
        style_cell={
            "fontFamily": "Inter, Segoe UI, Arial, sans-serif",
            "fontSize": "12px",
            "color": "#26363C",
            "backgroundColor": "#FFFFFF",
            "border": "none",
            "borderBottom": "1px solid #EDF0EF",
            "padding": "12px 14px",
            "textAlign": "left",
            "minWidth": "105px",
            "maxWidth": "240px",
            "whiteSpace": "normal",
        },
        style_data_conditional=[
            {"if": {"state": "active"}, "backgroundColor": "#EAF3F1", "border": "none"},
            {"if": {"state": "selected"}, "backgroundColor": "#EAF3F1", "border": "none"},
        ],
        css=[{"selector": ".dash-spreadsheet-menu", "rule": "display: none"}],
    )

