"""NovaPlan — Business Planning & Liquidity Simulator.

Run with ``python app.py`` and open http://127.0.0.1:8050.
"""

from __future__ import annotations

from datetime import datetime

import dash
from dash import ALL, Dash, Input, Output, dcc, html


NAV_ITEMS = [
    ("/", "Project Overview", "1"),
    ("/what-if", "What-if Experiment", "2"),
    ("/cash-check", "13-Week Cash Check", "3"),
    ("/monte-carlo", "Risk Simulation", "4"),
    ("/how-it-works", "How It Works", "?"),
]


app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    title="NovaPlan | Business Planning & Liquidity",
    update_title=None,
)
server = app.server


def navigation() -> html.Nav:
    """Build the primary sidebar navigation."""
    return html.Nav(
        [
            dcc.Link(
                [html.Span(code, className="nav-icon"), html.Span(label)],
                href=path,
                id={"type": "nav-link", "index": path},
                className="nav-link",
            )
            for path, label, code in NAV_ITEMS
        ],
        className="nav-list",
        **{"aria-label": "Primary navigation"},
    )


def app_layout() -> html.Div:
    """Create the persistent application shell around the Dash page container."""
    return html.Div(
        [
            dcc.Location(id="shell-location"),
            dcc.Store(id="global-audit-version", data=0, storage_type="memory"),
            html.A("Skip to content", href="#main-content", className="skip-link"),
            html.Aside(
                [
                    html.Div(
                        [
                            html.Div("N", className="brand-mark"),
                            html.Div(
                                [
                                    html.Div("NovaPlan", className="brand-name"),
                                    html.Div("Business planning project", className="brand-tagline"),
                                ]
                            ),
                        ],
                        className="brand",
                    ),
                    html.Div("Explore the project", className="nav-section-label"),
                    navigation(),
                    html.Div(
                        [
                            html.Div(
                                [html.Span(className="status-dot"), html.Span("Using fictional data")],
                                className="model-status",
                            ),
                            html.P("Synthetic demonstration data", className="sidebar-note"),
                            html.P(
                                f"Last refreshed · {datetime.now():%d %b %Y}",
                                className="sidebar-timestamp",
                            ),
                        ],
                        className="sidebar-footer",
                    ),
                ],
                className="sidebar",
            ),
            html.Main(
                [
                    html.Header(
                        [
                            html.Div(
                                [
                                    html.Span("NovaBridge Digital SRL", className="company-name"),
                                    html.Span("Student internship project", className="cycle-badge"),
                                ],
                                className="topbar-context",
                            ),
                            html.Div(
                                [
                                    html.Span("EUR", className="currency-badge"),
                                ],
                                className="topbar-actions",
                            ),
                        ],
                        className="topbar",
                    ),
                    html.Div(dash.page_container, id="main-content", className="page-container"),
                ],
                className="main-shell",
            ),
        ],
        className="app-shell",
    )


app.layout = app_layout


@app.callback(
    Output({"type": "nav-link", "index": ALL}, "className"),
    Input("shell-location", "pathname"),
)
def mark_active_navigation(pathname: str | None) -> list[str]:
    """Highlight the current page in the persistent navigation."""
    active_path = pathname or "/"
    return [
        "nav-link active" if path == active_path else "nav-link"
        for path, _, _ in NAV_ITEMS
    ]


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)
