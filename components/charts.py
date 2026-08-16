"""Plotly styling and compact chart factories."""

from __future__ import annotations

import plotly.graph_objects as go


COLORS = {
    "ink": "#17252B",
    "muted": "#6B7780",
    "grid": "#E8ECEA",
    "accent": "#16706F",
    "accent_soft": "#85B8B2",
    "blue": "#56759A",
    "green": "#2F7D5B",
    "red": "#C45A55",
    "amber": "#C7893B",
    "purple": "#75658D",
    "surface": "#FFFFFF",
}

SERIES = [
    COLORS["accent"],
    COLORS["blue"],
    COLORS["amber"],
    COLORS["purple"],
    COLORS["green"],
    COLORS["red"],
]


def style_figure(
    figure: go.Figure,
    *,
    height: int = 340,
    y_prefix: str = "",
    y_suffix: str = "",
    hovermode: str = "x unified",
) -> go.Figure:
    """Apply NovaPlan's calm, consulting-grade Plotly theme."""
    figure.update_layout(
        height=height,
        margin=dict(l=12, r=12, t=22, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", color=COLORS["ink"], size=12),
        colorway=SERIES,
        hovermode=hovermode,
        hoverlabel=dict(bgcolor="#17252B", font_color="#FFFFFF", bordercolor="#17252B"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11, color=COLORS["muted"]),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    figure.update_xaxes(
        showgrid=False,
        zeroline=False,
        linecolor=COLORS["grid"],
        tickfont=dict(color=COLORS["muted"], size=11),
        title=None,
    )
    figure.update_yaxes(
        gridcolor=COLORS["grid"],
        gridwidth=1,
        zeroline=False,
        tickfont=dict(color=COLORS["muted"], size=11),
        tickprefix=y_prefix,
        ticksuffix=y_suffix,
        title=None,
    )
    return figure


def empty_figure(message: str = "No data available") -> go.Figure:
    """Return a polished empty state rather than an unstyled blank chart."""
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(color=COLORS["muted"], size=13),
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    return style_figure(figure, height=280, hovermode=False)

