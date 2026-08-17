"""Beginner-friendly teaching components used throughout NovaPlan."""

from __future__ import annotations

from collections.abc import Sequence

from dash import html


def learning_guide(
    question: str,
    steps: Sequence[tuple[str, str]],
    *,
    concepts: Sequence[str] | None = None,
    open_by_default: bool = False,
) -> html.Details:
    """Explain how a beginner should read and use one decision page."""
    return html.Details(
        [
            html.Summary(
                "Need help reading this page?"
            ),
            html.Div(
                [
                    html.P(question, className="learning-question"),
                    html.Ol(
                        [
                            html.Li(
                                [
                                    html.Strong(title),
                                    html.P(body),
                                ],
                                className="learning-step",
                            )
                            for title, body in steps
                        ],
                        className="learning-steps",
                    ),
                    html.P(
                        [
                            html.Strong("Terms used: "),
                            ", ".join(concepts or []),
                        ],
                        className="concept-list",
                    )
                    if concepts
                    else None,
                ],
                className="learning-guide-body",
            ),
        ],
        className="learning-guide",
        open=open_by_default,
    )


def chart_guide(text: str) -> html.Div:
    """Add a short, plain-language instruction beneath a chart heading."""
    return html.P(text, className="chart-guide")


def teaching_callout(
    title: str,
    definition: str,
    *,
    formula: str | None = None,
    example: str | None = None,
) -> html.Div:
    """Present a concept with definition, formula, and simple example."""
    return html.Div(
        [
            html.Div(
                [
                    html.H4(title),
                    html.P(definition),
                    html.Div([html.Span("Formula"), html.Code(formula)], className="teaching-formula")
                    if formula
                    else None,
                    html.P([html.Strong("Example: "), example], className="teaching-example")
                    if example
                    else None,
                ]
            ),
        ],
        className="teaching-callout",
    )
