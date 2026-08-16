"""Presentation components shared by all NovaPlan pages."""

from __future__ import annotations

from dash import html


def metric_card(
    label: str,
    value: str,
    delta: str | None = None,
    *,
    tone: str = "neutral",
    note: str | None = None,
    explanation: str | None = None,
    formula: str | None = None,
) -> html.Div:
    """Create an executive KPI card with an optional beginner explanation."""
    footer = []
    if delta:
        footer.append(html.Span(delta, className=f"metric-delta {tone}"))
    if note:
        footer.append(html.Span(note, className="metric-note"))
    return html.Div(
        [
            html.Div(
                [html.Span(label)],
                className="metric-label",
            ),
            html.Div(value, className="metric-value"),
            html.Div(footer, className="metric-footer") if footer else None,
            html.Details(
                [
                    html.Summary("What this means"),
                    html.P(explanation),
                    html.Div(
                        [html.Span("Formula", className="explanation-formula-label"), html.Code(formula)],
                        className="explanation-formula",
                    )
                    if formula
                    else None,
                ],
                className="metric-explanation",
            )
            if explanation
            else None,
        ],
        className="metric-card",
    )


def section_header(
    eyebrow: str,
    title: str,
    description: str | None = None,
    action=None,
) -> html.Div:
    """Create a consistent page section heading."""
    return html.Div(
        [
            html.Div(
                [
                    html.Div(eyebrow, className="eyebrow"),
                    html.H2(title),
                    html.P(description) if description else None,
                ],
                className="section-copy",
            ),
            html.Div(action, className="section-action") if action else None,
        ],
        className="section-header",
    )


def insight_card(number: str, title: str, body: str, tone: str = "accent") -> html.Div:
    """Create a decision-oriented observation card."""
    return html.Div(
        [
            html.Div(number, className=f"insight-number {tone}"),
            html.Div([html.H4(title), html.P(body)], className="insight-copy"),
        ],
        className="insight-card",
    )


def status_pill(text: str, tone: str = "neutral") -> html.Span:
    """Create a small status badge."""
    return html.Span(text, className=f"status-pill {tone}")


def callout(title: str, body: str, tone: str = "info") -> html.Div:
    """Create a highlighted analytical conclusion."""
    return html.Div(
        [html.Div(className="callout-mark"), html.Div([html.H4(title), html.P(body)])],
        className=f"callout {tone}",
    )


def explained_label(term: str, explanation: str) -> html.Span:
    """Render jargon with an accessible hover/click definition cue."""
    return html.Span(
        [term, html.Span("?", className="inline-help-icon", **{"aria-hidden": "true"})],
        className="explained-term",
        title=explanation,
        tabIndex=0,
        **{"aria-label": f"{term}: {explanation}"},
    )
