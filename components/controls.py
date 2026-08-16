"""Small form-control wrappers that keep page layouts readable."""

from __future__ import annotations

from dash import dcc, html


def field(label: str, control, hint: str | None = None) -> html.Div:
    """Wrap any control with a consistent label and optional hint."""
    return html.Div(
        [
            html.Label(label),
            control,
            html.Small(hint, className="field-hint") if hint else None,
        ],
        className="field",
    )


def number_input(
    component_id: str,
    label: str,
    value: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float = 1,
    suffix: str | None = None,
    hint: str | None = None,
) -> html.Div:
    """Create an accessible numeric input with an optional unit suffix."""
    control = html.Div(
        [
            dcc.Input(
                id=component_id,
                type="number",
                value=value,
                min=minimum,
                max=maximum,
                step=step,
                debounce=True,
            ),
            html.Span(suffix, className="input-suffix") if suffix else None,
        ],
        className="input-with-suffix",
    )
    return field(label, control, hint)


def dropdown(
    component_id: str,
    label: str,
    options: list,
    value,
    *,
    clearable: bool = False,
    hint: str | None = None,
) -> html.Div:
    """Create a labeled dropdown."""
    return field(
        label,
        dcc.Dropdown(
            id=component_id,
            options=options,
            value=value,
            clearable=clearable,
            searchable=False,
        ),
        hint,
    )

