"""Build the illustrated NovaPlan white paper from live synthetic model outputs.

The builder intentionally uses the bundled document runtime and creates both
the figures and editable Word artifact deterministically.
"""

from __future__ import annotations

import math
import os
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.cashflow import build_13_week_forecast
from models.forecast import build_monthly_forecast
from models.monte_carlo import run_monte_carlo
from models.scenarios import expansion_decision_cases, run_scenario
from models.sensitivity import run_sensitivity


OUT_DIR = ROOT / "whitepaper"
FIG_DIR = OUT_DIR / "figures"
DOCX_PATH = OUT_DIR / "NovaPlan_White_Paper_v0.1.docx"
DATA_DIR = ROOT / "data"

FIG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Design system: standard_business_brief + named editorial_cover override.
# ---------------------------------------------------------------------------

PAGE_WIDTH_IN = 8.5
PAGE_HEIGHT_IN = 11.0
MARGIN_IN = 1.0
CONTENT_WIDTH_IN = 6.5
CONTENT_WIDTH_DXA = 9360
TABLE_INDENT_DXA = 120
CELL_MARGIN_DXA = {"top": 80, "bottom": 80, "start": 120, "end": 120}

INK = "17252B"
INK_SOFT = "33454C"
MUTED = "6B7780"
TEAL = "16706F"
TEAL_SOFT = "E7F2F0"
GREEN = "2F7D5B"
GREEN_SOFT = "E9F4ED"
RED = "C45A55"
RED_SOFT = "FAECEA"
AMBER = "C7893B"
AMBER_SOFT = "FBF1DF"
BLUE = "56759A"
PURPLE = "75658D"
GRID = "E3E9E6"
SURFACE = "FFFFFF"
CANVAS = "F4F6F5"

CHART_W = 1600
CHART_H = 900
FONT_REGULAR = Path("C:/Windows/Fonts/segoeui.ttf")
FONT_SEMIBOLD = Path("C:/Windows/Fonts/seguisb.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/segoeuib.ttf")


def rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def font(size: int, bold: bool = False, semibold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_SEMIBOLD if semibold else FONT_REGULAR
    return ImageFont.truetype(str(path), size=size)


def fmt_eur(value: float, decimals: int = 1) -> str:
    sign = "-" if value < 0 else ""
    absolute = abs(float(value))
    if absolute >= 1_000_000:
        return f"{sign}EUR {absolute / 1_000_000:.{decimals}f}m"
    if absolute >= 1_000:
        return f"{sign}EUR {absolute / 1_000:.{decimals}f}k"
    return f"{sign}EUR {absolute:,.0f}"


def fmt_m(value: float, decimals: int = 1) -> str:
    return f"{value / 1_000_000:.{decimals}f}m"


def fmt_pct(value: float, decimals: int = 1) -> str:
    return f"{value * 100:.{decimals}f}%"


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def dashed_line(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    width: int = 3,
    dash: int = 14,
    gap: int = 10,
) -> None:
    x1, y1, x2, y2 = xy
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        return
    dx = (x2 - x1) / length
    dy = (y2 - y1) / length
    position = 0.0
    while position < length:
        end = min(position + dash, length)
        draw.line(
            (
                x1 + dx * position,
                y1 + dy * position,
                x1 + dx * end,
                y1 + dy * end,
            ),
            fill=fill,
            width=width,
        )
        position += dash + gap


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: str = MUTED,
    width: int = 5,
) -> None:
    color_rgb = rgb(color)
    draw.line([start, end], fill=color_rgb, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head = 17
    for delta in (math.pi * 0.84, -math.pi * 0.84):
        point = (
            end[0] + head * math.cos(angle + delta),
            end[1] + head * math.sin(angle + delta),
        )
        draw.line([end, point], fill=color_rgb, width=width)


def new_canvas(title: str, subtitle: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (CHART_W, CHART_H), rgb(SURFACE))
    draw = ImageDraw.Draw(image)
    draw.text((65, 45), title, fill=rgb(INK), font=font(42, bold=True))
    if subtitle:
        draw.text((65, 101), subtitle, fill=rgb(MUTED), font=font(22))
    draw.rounded_rectangle((48, 30, CHART_W - 48, CHART_H - 32), radius=22, outline=rgb(GRID), width=2)
    return image, draw


def save_canvas(image: Image.Image, name: str) -> Path:
    path = FIG_DIR / name
    image.save(path, format="PNG", optimize=True, dpi=(220, 220))
    return path


def y_scale(values: Sequence[float], plot_top: int, plot_bottom: int, zero_floor: bool = False):
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    minimum = float(finite.min()) if len(finite) else 0.0
    maximum = float(finite.max()) if len(finite) else 1.0
    if zero_floor and minimum > 0:
        minimum = 0.0
    span = maximum - minimum
    if span == 0:
        span = max(abs(maximum), 1.0)
    padding = span * 0.10
    minimum -= padding if not zero_floor else 0
    maximum += padding

    def convert(value: float) -> int:
        return int(plot_bottom - (value - minimum) / (maximum - minimum) * (plot_bottom - plot_top))

    return minimum, maximum, convert


def line_chart(
    name: str,
    title: str,
    subtitle: str,
    x_labels: Sequence[str],
    series: Sequence[dict],
    *,
    value_formatter: Callable[[float], str] = lambda value: f"{value:.1f}",
    threshold: tuple[float, str] | None = None,
    zero_floor: bool = False,
    forecast_marker: tuple[int, str] | None = None,
    bands: Sequence[dict] | None = None,
) -> Path:
    image, draw = new_canvas(title, subtitle)
    left, top, right, bottom = 150, 205, 1510, 760
    all_values: list[float] = []
    for item in series:
        all_values.extend(item["values"])
    for band in bands or []:
        all_values.extend(band["low"])
        all_values.extend(band["high"])
    if threshold:
        all_values.append(threshold[0])
    minimum, maximum, to_y = y_scale(all_values, top, bottom, zero_floor)
    for step in range(6):
        value = lerp(minimum, maximum, step / 5)
        y = to_y(value)
        draw.line((left, y, right, y), fill=rgb(GRID), width=2)
        label = value_formatter(value)
        box = draw.textbbox((0, 0), label, font=font(18))
        draw.text((left - 18 - (box[2] - box[0]), y - 11), label, fill=rgb(MUTED), font=font(18))
    count = max(len(x_labels), 2)

    def to_x(index: int) -> int:
        return int(left + index / (count - 1) * (right - left))

    tick_indices = sorted(set(np.linspace(0, count - 1, min(7, count), dtype=int).tolist()))
    for index in tick_indices:
        x = to_x(index)
        draw.line((x, bottom, x, bottom + 8), fill=rgb(GRID), width=2)
        label = str(x_labels[index])
        box = draw.textbbox((0, 0), label, font=font(18))
        draw.text((x - (box[2] - box[0]) / 2, bottom + 17), label, fill=rgb(MUTED), font=font(18))

    for band in bands or []:
        upper = [(to_x(i), to_y(value)) for i, value in enumerate(band["high"])]
        lower = [(to_x(i), to_y(value)) for i, value in reversed(list(enumerate(band["low"])))]
        draw.polygon(upper + lower, fill=rgb(band["fill"]))

    if forecast_marker:
        marker_index, marker_label = forecast_marker
        x = to_x(marker_index)
        dashed_line(draw, (x, top, x, bottom), rgb(MUTED), width=2, dash=10, gap=8)
        draw.text((x + 12, top + 8), marker_label, fill=rgb(MUTED), font=font(17, semibold=True))

    if threshold:
        value, label = threshold
        y = to_y(value)
        dashed_line(draw, (left, y, right, y), rgb(AMBER), width=3)
        text_box = draw.textbbox((0, 0), label, font=font(18, semibold=True))
        tx = right - (text_box[2] - text_box[0]) - 10
        draw.rounded_rectangle((tx - 8, y - 33, right, y - 4), radius=6, fill=rgb(AMBER_SOFT))
        draw.text((tx, y - 30), label, fill=rgb(AMBER), font=font(18, semibold=True))

    for item in series:
        points = [(to_x(index), to_y(value)) for index, value in enumerate(item["values"])]
        if item.get("dash"):
            for first, second in zip(points[:-1], points[1:]):
                dashed_line(draw, (*first, *second), rgb(item["color"]), width=item.get("width", 5), dash=13, gap=8)
        else:
            draw.line(points, fill=rgb(item["color"]), width=item.get("width", 6), joint="curve")
        if item.get("markers", False):
            for x, y in points:
                draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=rgb(item["color"]))

    legend_font = font(19, semibold=True)
    legend_widths = [78 + draw.textlength(item["label"], font=legend_font) for item in series]
    legend_x = max(65, (CHART_W - sum(legend_widths)) / 2)
    for item in series:
        color = rgb(item["color"])
        draw.line((legend_x, 158, legend_x + 34, 158), fill=color, width=6)
        draw.text((legend_x + 44, 143), item["label"], fill=rgb(INK_SOFT), font=legend_font)
        legend_x += 78 + draw.textlength(item["label"], font=legend_font)
    draw.text((65, 823), "Source: NovaPlan synthetic demonstration model (seed 42).", fill=rgb(MUTED), font=font(17))
    return save_canvas(image, name)


def grouped_bar_chart(
    name: str,
    title: str,
    subtitle: str,
    categories: Sequence[str],
    series: Sequence[dict],
    *,
    value_formatter: Callable[[float], str] = lambda value: f"{value:.1f}",
    zero_line: bool = True,
) -> Path:
    image, draw = new_canvas(title, subtitle)
    left, top, right, bottom = 150, 210, 1510, 750
    values = [value for item in series for value in item["values"]]
    minimum, maximum, to_y = y_scale(values + ([0] if zero_line else []), top, bottom, False)
    for step in range(6):
        value = lerp(minimum, maximum, step / 5)
        y = to_y(value)
        draw.line((left, y, right, y), fill=rgb(GRID), width=2)
        label = value_formatter(value)
        box = draw.textbbox((0, 0), label, font=font(18))
        draw.text((left - 18 - (box[2] - box[0]), y - 11), label, fill=rgb(MUTED), font=font(18))
    if minimum < 0 < maximum:
        draw.line((left, to_y(0), right, to_y(0)), fill=rgb(INK_SOFT), width=2)
    group_width = (right - left) / max(len(categories), 1)
    bar_gap = 8
    bar_width = min(86, (group_width - 32) / max(len(series), 1) - bar_gap)
    for category_index, category in enumerate(categories):
        center = left + group_width * (category_index + 0.5)
        total_width = len(series) * bar_width + (len(series) - 1) * bar_gap
        start_x = center - total_width / 2
        for series_index, item in enumerate(series):
            value = item["values"][category_index]
            x0 = start_x + series_index * (bar_width + bar_gap)
            x1 = x0 + bar_width
            y0 = to_y(max(value, 0))
            y1 = to_y(min(value, 0))
            draw.rounded_rectangle((x0, min(y0, y1), x1, max(y0, y1)), radius=5, fill=rgb(item["color"]))
        wrapped = category.replace(" ", "\n") if len(category) > 14 else category
        for line_index, line in enumerate(wrapped.split("\n")):
            box = draw.textbbox((0, 0), line, font=font(18))
            draw.text((center - (box[2] - box[0]) / 2, bottom + 16 + line_index * 22), line, fill=rgb(MUTED), font=font(18))
    legend_font = font(18, semibold=True)
    legend_widths = [70 + draw.textlength(item["label"], font=legend_font) for item in series]
    legend_x = max(65, (CHART_W - sum(legend_widths)) / 2)
    for item in series:
        draw.rounded_rectangle((legend_x, 146, legend_x + 24, 170), radius=4, fill=rgb(item["color"]))
        draw.text((legend_x + 34, 141), item["label"], fill=rgb(INK_SOFT), font=legend_font)
        legend_x += 70 + draw.textlength(item["label"], font=legend_font)
    draw.text((65, 823), "Source: NovaPlan synthetic demonstration model (seed 42).", fill=rgb(MUTED), font=font(17))
    return save_canvas(image, name)


def horizontal_bar_chart(
    name: str,
    title: str,
    subtitle: str,
    labels: Sequence[str],
    values: Sequence[float],
    *,
    colors: Sequence[str] | None = None,
    value_formatter: Callable[[float], str] = lambda value: f"{value:.2f}",
    symmetric: bool = False,
) -> Path:
    image, draw = new_canvas(title, subtitle)
    left, top, right, bottom = 385, 180, 1450, 760
    labels = list(labels)
    values = list(map(float, values))
    if symmetric:
        limit = max(max(abs(value) for value in values), 1e-9) * 1.10
        minimum, maximum = -limit, limit
    else:
        minimum = min(0.0, min(values))
        maximum = max(values) * 1.12 if max(values) else 1.0

    def to_x(value: float) -> int:
        return int(left + (value - minimum) / (maximum - minimum) * (right - left))

    zero_x = to_x(0)
    draw.line((zero_x, top, zero_x, bottom), fill=rgb(INK_SOFT), width=2)
    row_height = (bottom - top) / max(len(labels), 1)
    for index, (label, value) in enumerate(zip(labels, values)):
        center_y = int(top + row_height * (index + 0.5))
        draw.line((left, center_y + row_height / 2 - 2, right, center_y + row_height / 2 - 2), fill=rgb(GRID), width=1)
        label_box = draw.textbbox((0, 0), label, font=font(20, semibold=True))
        draw.text((left - 22 - (label_box[2] - label_box[0]), center_y - 13), label, fill=rgb(INK_SOFT), font=font(20, semibold=True))
        x_value = to_x(value)
        color = colors[index] if colors else (TEAL if value >= 0 else RED)
        x0, x1 = sorted((zero_x, x_value))
        if x1 - x0 < 4:
            x1 = x0 + 4
        draw.rounded_rectangle((x0, center_y - 15, x1, center_y + 15), radius=6, fill=rgb(color))
        value_text = value_formatter(value)
        if value >= 0:
            draw.text((x1 + 10, center_y - 12), value_text, fill=rgb(color), font=font(18, semibold=True))
        else:
            box = draw.textbbox((0, 0), value_text, font=font(18, semibold=True))
            draw.text((x0 - 10 - (box[2] - box[0]), center_y - 12), value_text, fill=rgb(color), font=font(18, semibold=True))
    draw.text((65, 823), "Source: NovaPlan synthetic demonstration model (seed 42).", fill=rgb(MUTED), font=font(17))
    return save_canvas(image, name)


def histogram_chart(
    name: str,
    title: str,
    subtitle: str,
    values: Sequence[float],
    *,
    bins: int = 34,
    threshold: tuple[float, str] | None = None,
) -> Path:
    image, draw = new_canvas(title, subtitle)
    left, top, right, bottom = 150, 190, 1510, 750
    counts, edges = np.histogram(np.asarray(values, dtype=float), bins=bins)
    max_count = max(int(counts.max()), 1)
    for step in range(6):
        value = int(round(max_count * step / 5))
        y = int(bottom - value / max_count * (bottom - top))
        draw.line((left, y, right, y), fill=rgb(GRID), width=2)
        label = f"{value:,}"
        box = draw.textbbox((0, 0), label, font=font(18))
        draw.text((left - 18 - (box[2] - box[0]), y - 11), label, fill=rgb(MUTED), font=font(18))
    bar_width = (right - left) / bins
    for index, count in enumerate(counts):
        x0 = left + index * bar_width + 1
        x1 = left + (index + 1) * bar_width - 1
        y = bottom - count / max_count * (bottom - top)
        draw.rectangle((x0, y, x1, bottom), fill=rgb(TEAL))
    tick_values = np.linspace(edges[0], edges[-1], 6)
    for value in tick_values:
        x = left + (value - edges[0]) / (edges[-1] - edges[0]) * (right - left)
        label = fmt_m(value)
        box = draw.textbbox((0, 0), label, font=font(18))
        draw.text((x - (box[2] - box[0]) / 2, bottom + 17), label, fill=rgb(MUTED), font=font(18))
    if threshold and edges[0] <= threshold[0] <= edges[-1]:
        x = left + (threshold[0] - edges[0]) / (edges[-1] - edges[0]) * (right - left)
        dashed_line(draw, (int(x), top, int(x), bottom), rgb(AMBER), width=3)
        draw.text((x + 10, top + 5), threshold[1], fill=rgb(AMBER), font=font(18, semibold=True))
    median = float(np.median(values))
    median_x = left + (median - edges[0]) / (edges[-1] - edges[0]) * (right - left)
    draw.line((median_x, top, median_x, bottom), fill=rgb(INK), width=4)
    draw.text((median_x + 10, top + 42), f"Median {fmt_m(median)}", fill=rgb(INK), font=font(18, semibold=True))
    draw.text((65, 823), "Source: 10,000 NovaPlan simulations; seed 42.", fill=rgb(MUTED), font=font(17))
    return save_canvas(image, name)


def box(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    title: str,
    body: str,
    *,
    fill: str = TEAL_SOFT,
    outline: str = TEAL,
    title_color: str = INK,
) -> None:
    draw.rounded_rectangle(bounds, radius=18, fill=rgb(fill), outline=rgb(outline), width=3)
    x0, y0, x1, _ = bounds
    draw.text((x0 + 22, y0 + 18), title, fill=rgb(title_color), font=font(24, bold=True))
    words = body.split()
    lines: list[str] = []
    current = ""
    max_width = x1 - x0 - 44
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=font(18)) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    for index, line in enumerate(lines[:4]):
        draw.text((x0 + 22, y0 + 59 + index * 25), line, fill=rgb(MUTED), font=font(18))


def architecture_figure() -> Path:
    image, draw = new_canvas(
        "One project, four connected layers",
        "The dashboard is the visible decision surface; every output remains traceable to data and formulas.",
    )
    xs = [75, 455, 835, 1215]
    titles = ["Synthetic evidence", "Analytical core", "Decision engines", "Management experience"]
    bodies = [
        "72 monthly periods, invoices, customers, employees, OPEX, capex and weekly cash",
        "Revenue drivers, workforce, working capital, statements and cash reconciliation",
        "Forecasts, named scenarios, sensitivity, model benchmarks and Monte Carlo",
        "Nine learning-first pages, editable assumptions, audit trail and CSV exports",
    ]
    fills = ["EEF3F7", TEAL_SOFT, "F4F0F7", AMBER_SOFT]
    outlines = [BLUE, TEAL, PURPLE, AMBER]
    for index, x in enumerate(xs):
        box(draw, (x, 245, x + 305, 505), titles[index], bodies[index], fill=fills[index], outline=outlines[index])
        if index < len(xs) - 1:
            arrow(draw, (x + 310, 375), (xs[index + 1] - 10, 375), color=MUTED, width=5)
    draw.rounded_rectangle((260, 610, 1340, 710), radius=18, fill=rgb(CANVAS), outline=rgb(GRID), width=2)
    draw.text((300, 628), "GOVERNANCE SPINE", fill=rgb(TEAL), font=font(18, bold=True))
    draw.text((520, 622), "Assumption types  |  model baseline vs human adjustment  |  rationale  |  reconciliation  |  tests", fill=rgb(INK_SOFT), font=font(20, semibold=True))
    draw.text((65, 823), "Source: NovaPlan application architecture.", fill=rgb(MUTED), font=font(17))
    return save_canvas(image, "figure_01_architecture.png")


def data_ecosystem_figure(dataset_shapes: dict[str, tuple[int, int]]) -> Path:
    image, draw = new_canvas(
        "Synthetic data ecosystem",
        "Separate datasets recreate the operating, commercial and cash timing of a people-driven consulting company.",
    )
    items = [
        ("Monthly KPIs", "monthly_kpis", BLUE),
        ("Invoices", "invoices", TEAL),
        ("Customers", "customers", PURPLE),
        ("Employees", "employees", GREEN),
        ("Hiring plan", "hiring_plan", AMBER),
        ("Operating costs", "opex", RED),
        ("Capital spending", "capex", BLUE),
        ("Weekly cash actuals", "weekly_cash_actuals", TEAL),
    ]
    positions = [(85, 210), (450, 210), (815, 210), (1180, 210), (85, 540), (450, 540), (815, 540), (1180, 540)]
    center = (800, 450)
    for (title, key, color), (x, y) in zip(items, positions):
        rows, columns = dataset_shapes[key]
        bounds = (x, y, x + 280, y + 145)
        draw.rounded_rectangle(bounds, radius=16, fill=rgb(SURFACE), outline=rgb(color), width=3)
        draw.text((x + 18, y + 18), title, fill=rgb(INK), font=font(22, bold=True))
        draw.text((x + 18, y + 58), f"{rows:,} rows  |  {columns} fields", fill=rgb(color), font=font(18, semibold=True))
        draw.text((x + 18, y + 94), "Deterministic seed: 42", fill=rgb(MUTED), font=font(16))
        if x < 700:
            arrow(draw, (x + 280, y + 73), center, color=GRID, width=3)
        else:
            arrow(draw, (x, y + 73), center, color=GRID, width=3)
    draw.ellipse((center[0] - 86, center[1] - 86, center[0] + 86, center[1] + 86), fill=rgb(INK), outline=rgb(TEAL), width=5)
    draw.text((center[0] - 49, center[1] - 28), "ONE", fill=rgb(SURFACE), font=font(21, bold=True))
    draw.text((center[0] - 67, center[1] + 2), "COMPANY", fill=rgb(SURFACE), font=font(21, bold=True))
    draw.text((65, 823), "Source: Generated CSV datasets in the NovaPlan project.", fill=rgb(MUTED), font=font(17))
    return save_canvas(image, "figure_03_data_ecosystem.png")


def driver_tree_figure() -> Path:
    image, draw = new_canvas(
        "The revenue driver tree",
        "Revenue is not extrapolated as a standalone accounting line; it is produced by capacity, delivery and commercial assumptions.",
    )
    nodes = [
        ("Workforce capacity", "Headcount x billable share x working days x 8 hours", BLUE),
        ("Billable hours", "Capacity hours x utilization", TEAL),
        ("Core services revenue", "Billable hours x billing rate x realization", GREEN),
        ("Recognized revenue", "Core revenue + contractor and backlog effects", AMBER),
    ]
    xs = [65, 445, 825, 1205]
    for index, ((title, body, color), x) in enumerate(zip(nodes, xs)):
        box(draw, (x, 270, x + 315, 510), title, body, fill=SURFACE, outline=color)
        if index < 3:
            arrow(draw, (x + 315, 390), (xs[index + 1] - 12, 390), color=color, width=5)
    draw.rounded_rectangle((300, 605, 1300, 700), radius=18, fill=rgb(TEAL_SOFT), outline=rgb(TEAL), width=2)
    draw.text((335, 625), "Interpretation", fill=rgb(TEAL), font=font(18, bold=True))
    draw.text((500, 619), "A change in utilization or price moves revenue immediately; hiring moves capacity only after joining and ramp-up.", fill=rgb(INK_SOFT), font=font(20, semibold=True))
    draw.text((65, 823), "Source: models/driver_tree.py and models/revenue.py.", fill=rgb(MUTED), font=font(17))
    return save_canvas(image, "figure_04_driver_tree.png")


def working_capital_figure() -> Path:
    image, draw = new_canvas(
        "Why profit and cash can diverge",
        "The working-capital bridge preserves the timing difference between delivering work and receiving money.",
    )
    nodes = [
        ((80, 250, 365, 460), "Services delivered", "Revenue and EBITDA can be recognized now", BLUE),
        ((465, 250, 750, 460), "Invoice issued", "The customer owes cash; accounts receivable rises", TEAL),
        ((850, 250, 1135, 460), "Payment delay", "Terms and customer behavior determine DSO", AMBER),
        ((1235, 250, 1520, 460), "Cash collected", "Accounts receivable falls and cash rises", GREEN),
    ]
    for index, (bounds, title, body, color) in enumerate(nodes):
        box(draw, bounds, title, body, fill=SURFACE, outline=color)
        if index < len(nodes) - 1:
            arrow(draw, (bounds[2], 355), (nodes[index + 1][0][0] - 10, 355), color=MUTED, width=5)
    draw.rounded_rectangle((240, 570, 1360, 705), radius=18, fill=rgb(RED_SOFT), outline=rgb(RED), width=2)
    draw.text((275, 592), "If DSO increases", fill=rgb(RED), font=font(22, bold=True))
    draw.text((500, 588), "Accounts receivable increases and near-term cash falls, but recognized revenue does not automatically change.", fill=rgb(INK_SOFT), font=font(21, semibold=True))
    draw.text((65, 823), "Source: models/working_capital.py and models/forecast.py.", fill=rgb(MUTED), font=font(17))
    return save_canvas(image, "figure_05_working_capital.png")


# ---------------------------------------------------------------------------
# Word helpers.
# ---------------------------------------------------------------------------


def set_run_font(
    run,
    *,
    name: str = "Calibri",
    size: float | None = None,
    color: str | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
) -> None:
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        tc_pr.append(shading)
    shading.set(qn("w:fill"), fill)
    shading.set(qn("w:val"), "clear")


def set_cell_margins(cell, margins: dict[str, int] = CELL_MARGIN_DXA) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for edge, value in margins.items():
        tag = "start" if edge == "left" else "end" if edge == "right" else edge
        node = tc_mar.find(qn(f"w:{tag}"))
        if node is None:
            node = OxmlElement(f"w:{tag}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths_dxa: Sequence[int], indent_dxa: int = TABLE_INDENT_DXA) -> None:
    total = int(sum(widths_dxa))
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl_pr = table._tbl.tblPr
    tbl_layout = tbl_pr.find(qn("w:tblLayout"))
    if tbl_layout is None:
        tbl_layout = OxmlElement("w:tblLayout")
        tbl_pr.append(tbl_layout)
    tbl_layout.set(qn("w:type"), "fixed")
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(indent_dxa))
    tbl_ind.set(qn("w:type"), "dxa")

    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths_dxa:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(int(width)))
        grid.append(col)
    for row in table.rows:
        for cell, width in zip(row.cells, widths_dxa):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(int(width)))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def set_paragraph_shading(paragraph, fill: str) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    shading = p_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        p_pr.append(shading)
    shading.set(qn("w:fill"), fill)


def set_paragraph_border(paragraph, color: str, side: str = "left", size: str = "18") -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    edge = OxmlElement(f"w:{side}")
    edge.set(qn("w:val"), "single")
    edge.set(qn("w:sz"), size)
    edge.set(qn("w:space"), "8")
    edge.set(qn("w:color"), color)
    p_bdr.append(edge)


def add_page_field(paragraph) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for element in (begin, instruction, separate, text, end):
        run._r.append(element)
    set_run_font(run, size=9, color=MUTED)


def configure_styles(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal.font.size = Pt(11)
    normal.font.color.rgb = RGBColor.from_string(INK)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.10

    heading_tokens = {
        "Heading 1": (16, TEAL, 16, 8),
        "Heading 2": (13, TEAL, 12, 6),
        "Heading 3": (12, INK_SOFT, 8, 4),
    }
    for name, (size, color, before, after) in heading_tokens.items():
        style = doc.styles[name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    caption = doc.styles["Caption"]
    caption.font.name = "Calibri"
    caption._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    caption._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    caption.font.size = Pt(9)
    caption.font.color.rgb = RGBColor.from_string(MUTED)
    caption.font.italic = True
    caption.paragraph_format.space_before = Pt(3)
    caption.paragraph_format.space_after = Pt(9)
    caption.paragraph_format.keep_together = True

    if "Figure Source" not in [style.name for style in doc.styles]:
        source_style = doc.styles.add_style("Figure Source", 1)
        source_style.base_style = normal
        source_style.font.name = "Calibri"
        source_style.font.size = Pt(8)
        source_style.font.color.rgb = RGBColor.from_string(MUTED)
        source_style.paragraph_format.space_before = Pt(0)
        source_style.paragraph_format.space_after = Pt(7)


def configure_page(section) -> None:
    section.page_width = Inches(PAGE_WIDTH_IN)
    section.page_height = Inches(PAGE_HEIGHT_IN)
    section.top_margin = Inches(MARGIN_IN)
    section.right_margin = Inches(MARGIN_IN)
    section.bottom_margin = Inches(MARGIN_IN)
    section.left_margin = Inches(MARGIN_IN)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)


def configure_header_footer(section) -> None:
    header = section.header
    header.is_linked_to_previous = False
    paragraph = header.paragraphs[0]
    paragraph.clear()
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(6.5))
    left = paragraph.add_run("NOVAPLAN | ILLUSTRATED WHITE PAPER")
    set_run_font(left, size=8.5, color=MUTED, bold=True)
    right = paragraph.add_run("\tVERSION 0.1 | AUGUST 2026")
    set_run_font(right, size=8.5, color=MUTED, bold=True)
    set_paragraph_border(paragraph, GRID, side="bottom", size="8")

    footer = section.footer
    footer.is_linked_to_previous = False
    paragraph = footer.paragraphs[0]
    paragraph.clear()
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.tab_stops.add_tab_stop(
        Inches(CONTENT_WIDTH_IN), WD_TAB_ALIGNMENT.RIGHT
    )
    left_run = paragraph.add_run("Synthetic-data decision-support prototype")
    set_run_font(left_run, size=8.5, color=MUTED)
    page_run = paragraph.add_run("\tPage ")
    set_run_font(page_run, size=8.5, color=MUTED)
    add_page_field(paragraph)


def add_para(
    doc: Document,
    text: str = "",
    *,
    bold_lead: str | None = None,
    style: str | None = None,
    align: WD_ALIGN_PARAGRAPH | None = None,
    color: str | None = None,
    size: float | None = None,
    italic: bool = False,
    keep_with_next: bool = False,
) -> object:
    paragraph = doc.add_paragraph(style=style)
    paragraph.paragraph_format.keep_with_next = keep_with_next
    if align is not None:
        paragraph.alignment = align
    if bold_lead and text.startswith(bold_lead):
        lead = paragraph.add_run(bold_lead)
        set_run_font(lead, bold=True, color=color, size=size)
        remainder = paragraph.add_run(text[len(bold_lead) :])
        set_run_font(remainder, color=color, size=size, italic=italic)
    else:
        run = paragraph.add_run(text)
        set_run_font(run, color=color, size=size, italic=italic)
    return paragraph


def add_heading(doc: Document, text: str, level: int = 1) -> object:
    return doc.add_heading(text, level=level)


def create_numbering(doc: Document, num_fmt: str = "bullet") -> int:
    numbering = doc.part.numbering_part.element
    abstract_ids = [int(node.get(qn("w:abstractNumId"))) for node in numbering.findall(qn("w:abstractNum"))]
    num_ids = [int(node.get(qn("w:numId"))) for node in numbering.findall(qn("w:num"))]
    abstract_id = max(abstract_ids, default=-1) + 1
    num_id = max(num_ids, default=0) + 1

    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), str(abstract_id))
    multi = OxmlElement("w:multiLevelType")
    multi.set(qn("w:val"), "singleLevel")
    abstract.append(multi)
    level = OxmlElement("w:lvl")
    level.set(qn("w:ilvl"), "0")
    start = OxmlElement("w:start")
    start.set(qn("w:val"), "1")
    level.append(start)
    num_format = OxmlElement("w:numFmt")
    num_format.set(qn("w:val"), num_fmt)
    level.append(num_format)
    level_text = OxmlElement("w:lvlText")
    level_text.set(qn("w:val"), "•" if num_fmt == "bullet" else "%1.")
    level.append(level_text)
    suffix = OxmlElement("w:suff")
    suffix.set(qn("w:val"), "tab")
    level.append(suffix)
    p_pr = OxmlElement("w:pPr")
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "num")
    tab.set(qn("w:pos"), "720")
    tabs.append(tab)
    p_pr.append(tabs)
    indent = OxmlElement("w:ind")
    indent.set(qn("w:left"), "720")
    indent.set(qn("w:hanging"), "360")
    p_pr.append(indent)
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:after"), "160")
    spacing.set(qn("w:line"), "280")
    spacing.set(qn("w:lineRule"), "auto")
    p_pr.append(spacing)
    level.append(p_pr)
    abstract.append(level)
    numbering.append(abstract)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), str(abstract_id))
    num.append(abstract_ref)
    numbering.append(num)
    return num_id


def add_list_item(doc: Document, text: str, num_id: int) -> object:
    paragraph = doc.add_paragraph()
    p_pr = paragraph._p.get_or_add_pPr()
    num_pr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    num_pr.append(ilvl)
    num_id_element = OxmlElement("w:numId")
    num_id_element.set(qn("w:val"), str(num_id))
    num_pr.append(num_id_element)
    p_pr.append(num_pr)
    run = paragraph.add_run(text)
    set_run_font(run)
    return paragraph


def add_callout(doc: Document, label: str, text: str, *, tone: str = "teal") -> object:
    fills = {"teal": TEAL_SOFT, "amber": AMBER_SOFT, "red": RED_SOFT, "blue": "EEF3F7"}
    accents = {"teal": TEAL, "amber": AMBER, "red": RED, "blue": BLUE}
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Inches(0.08)
    paragraph.paragraph_format.right_indent = Inches(0.08)
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.space_after = Pt(10)
    paragraph.paragraph_format.keep_together = True
    set_paragraph_shading(paragraph, fills[tone])
    set_paragraph_border(paragraph, accents[tone], side="left", size="24")
    lead = paragraph.add_run(f"{label.upper()}  ")
    set_run_font(lead, size=9, color=accents[tone], bold=True)
    body = paragraph.add_run(text)
    set_run_font(body, size=10.5, color=INK_SOFT)
    return paragraph


def add_figure(doc: Document, path: Path, caption: str, *, width: float = 6.25, alt_text: str = "") -> None:
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run()
    shape = run.add_picture(str(path), width=Inches(width))
    shape._inline.docPr.set("descr", alt_text or caption)
    caption_paragraph = doc.add_paragraph(style="Caption")
    caption_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption_run = caption_paragraph.add_run(caption)
    set_run_font(caption_run, size=9, color=MUTED, italic=True)


def add_table(
    doc: Document,
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    widths_dxa: Sequence[int],
    *,
    alignments: Sequence[WD_ALIGN_PARAGRAPH] | None = None,
    font_size: float = 9.0,
) -> object:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    set_table_geometry(table, widths_dxa)
    header_row = table.rows[0]
    set_repeat_table_header(header_row)
    for index, (cell, value) in enumerate(zip(header_row.cells, headers)):
        set_cell_shading(cell, TEAL_SOFT)
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.alignment = (alignments or [WD_ALIGN_PARAGRAPH.LEFT] * len(headers))[index]
        run = paragraph.add_run(str(value))
        set_run_font(run, size=font_size, color=INK, bold=True)
    for row_index, row_values in enumerate(rows):
        row = table.add_row()
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        if row_index % 2:
            for cell in row.cells:
                set_cell_shading(cell, "F8FAF9")
        for index, (cell, value) in enumerate(zip(row.cells, row_values)):
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.05
            paragraph.alignment = (alignments or [WD_ALIGN_PARAGRAPH.LEFT] * len(headers))[index]
            run = paragraph.add_run(str(value))
            set_run_font(run, size=font_size, color=INK_SOFT)
    set_table_geometry(table, widths_dxa)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


def page_break(doc: Document) -> None:
    doc.add_page_break()


def add_section_kicker(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run(text.upper())
    set_run_font(run, size=8.5, color=AMBER, bold=True)


def add_formula(doc: Document, formula: str, explanation: str = "") -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Inches(0.25)
    paragraph.paragraph_format.right_indent = Inches(0.25)
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(8)
    paragraph.paragraph_format.keep_together = True
    set_paragraph_shading(paragraph, CANVAS)
    formula_run = paragraph.add_run(formula)
    set_run_font(formula_run, name="Consolas", size=10.5, color=TEAL, bold=True)
    if explanation:
        explanation_run = paragraph.add_run(f"\n{explanation}")
        set_run_font(explanation_run, size=9.5, color=MUTED)


# ---------------------------------------------------------------------------
# Live analytics and publication figures.
# ---------------------------------------------------------------------------


def collect_analytics() -> dict[str, object]:
    """Read the checked-in synthetic evidence and rerun all decision engines."""

    datasets: dict[str, pd.DataFrame] = {}
    for key in (
        "monthly_kpis",
        "invoices",
        "customers",
        "employees",
        "hiring_plan",
        "opex",
        "capex",
        "weekly_cash_actuals",
    ):
        datasets[key] = pd.read_csv(DATA_DIR / f"{key}.csv")

    monthly = datasets["monthly_kpis"].copy()
    monthly["month"] = pd.to_datetime(monthly["month"])
    invoices = datasets["invoices"].copy()
    for column in ("invoice_date", "due_date", "forecast_payment_date", "actual_payment_date"):
        if column in invoices:
            invoices[column] = pd.to_datetime(invoices[column], errors="coerce")

    annual = (
        monthly.assign(year=monthly["month"].dt.year)
        .groupby("year", as_index=False)
        .agg(
            revenue_eur=("revenue_eur", "sum"),
            ebitda_eur=("ebitda_eur", "sum"),
            utilization=("utilization", "mean"),
            dso=("dso", "mean"),
            operating_cash_flow_eur=("operating_cash_flow_eur", "sum"),
            closing_cash_eur=("closing_cash_eur", "last"),
            headcount=("headcount", "last"),
        )
    )
    annual["ebitda_margin"] = annual["ebitda_eur"] / annual["revenue_eur"]
    annual["revenue_growth"] = annual["revenue_eur"].pct_change()

    base_forecast = build_monthly_forecast(monthly, months=18)
    liquidity = build_13_week_forecast(monthly, invoices=invoices)
    decision_cases = expansion_decision_cases(monthly, months=18)
    case_forecasts: dict[str, pd.DataFrame] = {}
    for name in ("Base", "2026 Expansion Decision", "Risk", "Mitigation"):
        label = "Expansion" if name == "2026 Expansion Decision" else name
        case_forecasts[label] = run_scenario(monthly, name, months=18)["forecast"]
    sensitivity = run_sensitivity(monthly, months=18)
    monte_carlo = run_monte_carlo(
        monthly,
        n_simulations=10_000,
        seed=42,
        threshold=3_000_000.0,
        ebitda_margin_target=0.10,
    )

    model_wape = pd.DataFrame(
        {
            "target": ["Revenue", "Utilization", "Collections", "EBITDA", "Closing cash"],
            "Seasonal Naive": [11.8034, 4.1079, 16.8429, 24.7267, 17.0941],
            "Driver Regression": [6.5501, 3.5946, 13.7616, 24.0391, 8.9654],
            "ElasticNet": [2.0919, 2.9581, 14.2711, 9.3194, 5.7113],
            "Gradient Boosting": [6.1690, 3.6825, 13.5441, 17.9195, 9.8891],
        }
    )

    return {
        "datasets": datasets,
        "dataset_shapes": {key: value.shape for key, value in datasets.items()},
        "monthly": monthly,
        "annual": annual,
        "liquidity": liquidity,
        "base_forecast": base_forecast,
        "decision_cases": decision_cases,
        "case_forecasts": case_forecasts,
        "sensitivity": sensitivity,
        "monte_carlo": monte_carlo,
        "model_wape": model_wape,
    }


def walk_forward_figure() -> Path:
    image, draw = new_canvas(
        "Walk-forward validation respects time",
        "Every prediction is made using only information available before that forecast month.",
    )
    months_x0, months_x1 = 160, 1450
    cell_w = (months_x1 - months_x0) / 12
    draw.text((70, 202), "Fold 1", fill=rgb(INK), font=font(22, bold=True))
    draw.text((70, 382), "Fold 2", fill=rgb(INK), font=font(22, bold=True))
    draw.text((70, 562), "Fold 3", fill=rgb(INK), font=font(22, bold=True))
    for row, train_end in enumerate((7, 8, 9)):
        y = 190 + row * 180
        for index in range(12):
            x0 = months_x0 + index * cell_w
            x1 = x0 + cell_w - 6
            if index < train_end:
                fill, outline = TEAL_SOFT, TEAL
                label = "Train" if index == train_end // 2 else ""
            elif index == train_end:
                fill, outline = AMBER_SOFT, AMBER
                label = "Predict"
            else:
                fill, outline, label = CANVAS, GRID, ""
            draw.rounded_rectangle((x0, y, x1, y + 86), radius=9, fill=rgb(fill), outline=rgb(outline), width=2)
            if label:
                text_box = draw.textbbox((0, 0), label, font=font(17, semibold=True))
                draw.text((x0 + (cell_w - 6 - (text_box[2] - text_box[0])) / 2, y + 31), label, fill=rgb(outline), font=font(17, semibold=True))
    draw.rounded_rectangle((270, 735, 1330, 795), radius=14, fill=rgb(CANVAS), outline=rgb(GRID), width=2)
    draw.text((330, 750), "The training window expands by one month; there is no shuffle and no future leakage.", fill=rgb(INK_SOFT), font=font(20, semibold=True))
    draw.text((65, 823), "Source: forecasting/validation.py; illustration is schematic.", fill=rgb(MUTED), font=font(17))
    return save_canvas(image, "figure_10_walk_forward.png")


def monte_carlo_flow_figure() -> Path:
    image, draw = new_canvas(
        "Monte Carlo samples drivers, not cash",
        "Each run follows the same financial logic as the Base forecast, but with correlated operating shocks.",
    )
    items = [
        ("1. Base forecast", "18 monthly operating and cash values", BLUE),
        ("2. Driver shocks", "Utilization, DSO, billing realization, salary, attrition, backlog and FX", PURPLE),
        ("3. Recalculation", "Revenue, payroll, EBITDA, tax, AR, AP and free cash flow", TEAL),
        ("4. Cash path", "One internally coherent 18-month trajectory", GREEN),
        ("5. Risk summary", "Percentiles, breach probability and driver associations", AMBER),
    ]
    xs = [60, 365, 670, 975, 1280]
    for index, ((title, body, color), x) in enumerate(zip(items, xs)):
        box(draw, (x, 250, x + 255, 535), title, body, fill=SURFACE, outline=color)
        if index < len(items) - 1:
            arrow(draw, (x + 255, 392), (xs[index + 1] - 9, 392), color=MUTED, width=4)
    draw.rounded_rectangle((270, 640, 1330, 720), radius=17, fill=rgb(TEAL_SOFT), outline=rgb(TEAL), width=2)
    draw.text((315, 660), "Repeat 10,000 times with seed 42", fill=rgb(TEAL), font=font(20, bold=True))
    draw.text((690, 655), "Reproducible sampling turns a point forecast into a distribution of possible paths.", fill=rgb(INK_SOFT), font=font(20, semibold=True))
    draw.text((65, 823), "Source: models/monte_carlo.py.", fill=rgb(MUTED), font=font(17))
    return save_canvas(image, "figure_11_monte_carlo_flow.png")


def build_figures(analytics: dict[str, object]) -> dict[str, Path]:
    annual = analytics["annual"]
    liquidity = analytics["liquidity"]
    cases = analytics["decision_cases"].copy()
    case_forecasts = analytics["case_forecasts"]
    monte_carlo = analytics["monte_carlo"]
    sensitivity = analytics["sensitivity"]
    model_wape = analytics["model_wape"]

    figures: dict[str, Path] = {
        "architecture": architecture_figure(),
        "ecosystem": data_ecosystem_figure(analytics["dataset_shapes"]),
        "driver_tree": driver_tree_figure(),
        "working_capital": working_capital_figure(),
        "walk_forward": walk_forward_figure(),
        "monte_carlo_flow": monte_carlo_flow_figure(),
    }
    years = annual["year"].astype(str).tolist()
    figures["history"] = line_chart(
        "figure_02_historical_performance.png",
        "Six years of synthetic operating history",
        "Revenue, EBITDA and closing cash tell related but different parts of the company story.",
        years,
        [
            {"label": "Revenue", "values": annual["revenue_eur"].tolist(), "color": BLUE, "markers": True},
            {"label": "EBITDA", "values": annual["ebitda_eur"].tolist(), "color": AMBER, "markers": True},
            {"label": "Closing cash", "values": annual["closing_cash_eur"].tolist(), "color": TEAL, "markers": True},
        ],
        value_formatter=lambda value: fmt_m(value),
        zero_floor=True,
    )
    figures["liquidity"] = line_chart(
        "figure_06_liquidity.png",
        "The 13-week direct cash forecast",
        "Weekly receipts and payments reveal near-term timing pressure hidden by monthly profit.",
        [f"W{int(value)}" for value in liquidity["week_number"]],
        [{"label": "Closing cash", "values": liquidity["closing_cash_eur"].tolist(), "color": TEAL, "markers": True}],
        value_formatter=lambda value: fmt_m(value),
        threshold=(3_000_000.0, "EUR 3m policy floor"),
        zero_floor=True,
    )
    scenario_series = []
    scenario_colors = {"Base": BLUE, "Expansion": TEAL, "Risk": RED, "Mitigation": GREEN}
    for label in ("Base", "Expansion", "Risk", "Mitigation"):
        forecast = case_forecasts[label]
        scenario_series.append(
            {"label": label, "values": forecast["closing_cash_eur"].tolist(), "color": scenario_colors[label], "width": 6}
        )
    scenario_months = [pd.Timestamp(value).strftime("%b %y") for value in case_forecasts["Base"]["month"]]
    figures["scenario_paths"] = line_chart(
        "figure_07_scenario_cash_paths.png",
        "Expansion is a profit-and-liquidity decision",
        "Four coherent management stories are compared across the same January 2026 to June 2027 horizon.",
        scenario_months,
        scenario_series,
        value_formatter=lambda value: fmt_m(value),
        threshold=(3_000_000.0, "EUR 3m policy floor"),
        zero_floor=True,
    )
    cases["scenario"] = cases["scenario"].replace({"2026 Expansion Decision": "Expansion"})
    base = cases.loc[cases["scenario"].eq("Base")].iloc[0]
    compare = cases.loc[cases["scenario"].ne("Base")].set_index("scenario")
    figures["scenario_deltas"] = grouped_bar_chart(
        "figure_08_expansion_deltas.png",
        "Scenario outcomes versus Base",
        "Positive bars improve the metric; negative bars reduce it. Cash is measured at June 2027 and at the path minimum.",
        ["Expansion", "Risk", "Mitigation"],
        [
            {"label": "Revenue", "values": [(compare.loc[name, "revenue_eur"] - base["revenue_eur"]) / 1e6 for name in compare.index], "color": BLUE},
            {"label": "EBITDA", "values": [(compare.loc[name, "ebitda_eur"] - base["ebitda_eur"]) / 1e6 for name in compare.index], "color": AMBER},
            {"label": "Forecast-end cash", "values": [(compare.loc[name, "year_end_cash_eur"] - base["year_end_cash_eur"]) / 1e6 for name in compare.index], "color": TEAL},
            {"label": "Minimum cash", "values": [(compare.loc[name, "minimum_cash_eur"] - base["minimum_cash_eur"]) / 1e6 for name in compare.index], "color": PURPLE},
        ],
        value_formatter=lambda value: f"{value:.1f}m",
    )
    figures["model_wape"] = grouped_bar_chart(
        "figure_09_model_wape.png",
        "Forecasting algorithms: out-of-sample WAPE",
        "Lower is better. ElasticNet is the strongest general benchmark on this particular synthetic history.",
        model_wape["target"].tolist(),
        [
            {"label": "Seasonal Naive", "values": model_wape["Seasonal Naive"].tolist(), "color": MUTED},
            {"label": "Driver Regression", "values": model_wape["Driver Regression"].tolist(), "color": BLUE},
            {"label": "ElasticNet", "values": model_wape["ElasticNet"].tolist(), "color": TEAL},
            {"label": "Gradient Boosting", "values": model_wape["Gradient Boosting"].tolist(), "color": PURPLE},
        ],
        value_formatter=lambda value: f"{value:.0f}%",
        zero_line=False,
    )
    fan = monte_carlo["fan_chart"]
    figures["monte_carlo_fan"] = line_chart(
        "figure_12_monte_carlo_fan.png",
        "10,000 simulated liquidity paths",
        "The light band is P5-P95, the dark band P25-P75, and the line the monthly median.",
        [pd.Timestamp(value).strftime("%b %y") for value in fan["month"]],
        [{"label": "Median cash", "values": fan["p50_cash_eur"].tolist(), "color": TEAL, "width": 7}],
        bands=[
            {"low": fan["p5_cash_eur"].tolist(), "high": fan["p95_cash_eur"].tolist(), "fill": "E9F4F2"},
            {"low": fan["p25_cash_eur"].tolist(), "high": fan["p75_cash_eur"].tolist(), "fill": "BFDCD7"},
        ],
        value_formatter=lambda value: fmt_m(value),
        threshold=(3_000_000.0, "EUR 3m policy floor"),
        zero_floor=True,
    )
    figures["monte_carlo_histogram"] = histogram_chart(
        "figure_13_monte_carlo_histogram.png",
        "Distribution of forecast-end cash",
        "June 2027 cash outcomes across 10,000 fixed-seed simulations.",
        monte_carlo["year_end_cash_eur"],
        bins=40,
    )
    ranking = monte_carlo["risk_driver_ranking"]
    figures["risk_drivers"] = horizontal_bar_chart(
        "figure_14_risk_driver_correlations.png",
        "Risk-driver association with forecast-end cash",
        "Signed correlation describes association, not isolated causation or share of variance explained.",
        ranking["driver"].tolist(),
        ranking["correlation_with_year_end_cash"].tolist(),
        colors=[GREEN if value >= 0 else RED for value in ranking["correlation_with_year_end_cash"]],
        value_formatter=lambda value: f"{value:+.2f}",
        symmetric=True,
    )
    sensitivity_plot = sensitivity.sort_values(["rank", "direction"], ascending=[True, False]).copy()
    sensitivity_labels = [f"{row.driver} {row.shock}" for row in sensitivity_plot.itertuples()]
    sensitivity_values = sensitivity_plot["year_end_cash_impact_eur"].to_numpy(float) / 1e6
    figures["sensitivity"] = horizontal_bar_chart(
        "figure_15_sensitivity_tornado.png",
        "One-at-a-time sensitivity of forecast-end cash",
        "Each row changes one driver while holding the remaining planning assumptions constant.",
        sensitivity_labels,
        sensitivity_values,
        colors=[GREEN if value >= 0 else RED for value in sensitivity_values],
        value_formatter=lambda value: f"{value:+.2f}m",
        symmetric=True,
    )
    return figures


# ---------------------------------------------------------------------------
# White-paper narrative.
# ---------------------------------------------------------------------------


def build_document(analytics: dict[str, object], figures: dict[str, Path]) -> Path:
    monthly: pd.DataFrame = analytics["monthly"]
    annual: pd.DataFrame = analytics["annual"]
    datasets: dict[str, pd.DataFrame] = analytics["datasets"]
    base_forecast: pd.DataFrame = analytics["base_forecast"]
    liquidity: pd.DataFrame = analytics["liquidity"]
    cases: pd.DataFrame = analytics["decision_cases"].copy()
    cases["scenario"] = cases["scenario"].replace({"2026 Expansion Decision": "Expansion"})
    monte_carlo: dict[str, object] = analytics["monte_carlo"]
    sensitivity: pd.DataFrame = analytics["sensitivity"]
    model_wape: pd.DataFrame = analytics["model_wape"]

    latest = monthly.iloc[-1]
    ltm = annual.iloc[-1]
    prior = annual.iloc[-2]
    base_summary = cases.loc[cases["scenario"].eq("Base")].iloc[0]
    expansion_summary = cases.loc[cases["scenario"].eq("Expansion")].iloc[0]
    risk_summary = cases.loc[cases["scenario"].eq("Risk")].iloc[0]
    mitigation_summary = cases.loc[cases["scenario"].eq("Mitigation")].iloc[0]
    mc_summary = monte_carlo["summary"]

    doc = Document()
    configure_styles(doc)
    configure_page(doc.sections[0])
    doc.core_properties.title = "NovaPlan: From Operating Drivers to Liquidity Decisions"
    doc.core_properties.subject = "Illustrated white paper for a synthetic business-planning and liquidity simulator"
    doc.core_properties.author = "NovaPlan project team"
    doc.core_properties.keywords = "business planning, liquidity, forecasting, Monte Carlo, synthetic data, KPI education"
    doc.core_properties.comments = "Version 0.1; generated from the checked-in seed-42 synthetic model outputs."

    # Editorial cover.
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(84)
    spacer.paragraph_format.space_after = Pt(0)
    add_section_kicker(doc, "Illustrated technical white paper | Version 0.1")
    title = doc.add_paragraph()
    title.paragraph_format.space_before = Pt(8)
    title.paragraph_format.space_after = Pt(12)
    title_run = title.add_run("NovaPlan")
    set_run_font(title_run, size=34, color=TEAL, bold=True)
    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(22)
    subtitle_run = subtitle.add_run("From operating drivers to liquidity decisions")
    set_run_font(subtitle_run, size=21, color=INK, bold=True)
    descriptor = doc.add_paragraph()
    descriptor.paragraph_format.space_after = Pt(30)
    descriptor_run = descriptor.add_run(
        "How one synthetic company becomes a connected teaching model for KPIs, forecasts, scenarios, hiring economics, cash planning and Monte Carlo risk."
    )
    set_run_font(descriptor_run, size=13, color=INK_SOFT)
    add_callout(
        doc,
        "The management question",
        "Can NovaBridge Digital hire 40 consultants and still create value without putting short-term liquidity at risk?",
        tone="teal",
    )
    cover_meta = doc.add_paragraph()
    cover_meta.paragraph_format.space_before = Pt(30)
    cover_meta.paragraph_format.space_after = Pt(8)
    cover_meta_run = cover_meta.add_run("NovaBridge Digital SRL | Fictional Romanian technology consultancy | EUR reporting")
    set_run_font(cover_meta_run, size=10.5, color=MUTED, bold=True)
    add_para(doc, "Prepared 12 August 2026", color=MUTED, size=10)
    legal = doc.add_paragraph()
    legal.paragraph_format.space_before = Pt(52)
    legal.paragraph_format.space_after = Pt(0)
    legal_run = legal.add_run(
        "Educational proof-of-concept. All companies, customers, employees, invoices and financial observations in this paper are synthetic."
    )
    set_run_font(legal_run, size=9, color=MUTED, italic=True)

    body_section = doc.add_section(WD_SECTION.NEW_PAGE)
    configure_page(body_section)
    configure_header_footer(body_section)

    add_section_kicker(doc, "Abstract")
    add_heading(doc, "A decision system, not a collection of charts", level=1)
    add_para(
        doc,
        "NovaPlan is an educational business-planning and liquidity simulator for a fictional people-driven consulting company. It connects operating assumptions to productive capacity, revenue, payroll, profitability, invoices, working capital and cash. The same connected model powers an 18-month rolling forecast, a 13-week direct cash forecast, named management scenarios, deterministic sensitivity tests, algorithm comparisons and a 10,000-run Monte Carlo simulation.",
    )
    add_para(
        doc,
        "The paper is written for readers who are new to finance or analytics. Every major metric is defined in plain language, its formula is shown where useful, and its management meaning is explained. The values are illustrative and come from a reproducible seed-42 synthetic dataset covering January 2020 through December 2025.",
    )
    add_callout(
        doc,
        "Central teaching idea",
        "People and demand create productive hours; productive hours create revenue; profit is then translated into cash through collection timing, supplier timing, tax, capital spending and financing decisions.",
        tone="blue",
    )

    add_heading(doc, "Executive summary", level=1)
    bullet_id = create_numbering(doc, "bullet")
    for item in (
        "NovaPlan models decisions through drivers. Revenue is built from workforce capacity, utilization, pricing and realization rather than extended as an isolated accounting line.",
        "The synthetic history is internally connected. Monthly revenue reconciles to invoices; accounts receivable reconciles to collections; cash reconciles from its opening balance to its closing balance.",
        f"The latest synthetic year records {fmt_eur(ltm.revenue_eur, 2)} revenue, {fmt_eur(ltm.ebitda_eur, 2)} EBITDA, a {ltm.ebitda_margin * 100:.1f}% margin and {fmt_eur(ltm.closing_cash_eur, 2)} closing cash.",
        f"The Base planning case produces {fmt_eur(base_summary.ebitda_eur, 2)} EBITDA and {fmt_eur(base_summary.year_end_cash_eur, 2)} cash at June 2027. The expansion adds profit but temporarily uses cash during onboarding and collection delays.",
        "Four forecasting algorithms are tested with chronological walk-forward validation. ElasticNet is the best general benchmark on this synthetic history, but the diagnostic is conditional on known or planned same-month drivers.",
        f"The 10,000-run Monte Carlo produces a median June 2027 cash balance of {fmt_eur(mc_summary['median_year_end_cash_eur'], 2)}. No run breaches the EUR 3m policy floor under the selected distributions; this is conditional evidence, not a guarantee.",
    ):
        add_list_item(doc, item, bullet_id)
    add_figure(
        doc,
        figures["architecture"],
        "Figure 1. NovaPlan joins evidence, financial logic, decision engines and a teaching-first interface under one governance spine.",
        alt_text="Four connected NovaPlan layers: synthetic evidence, analytical core, decision engines and management experience, with a governance spine beneath them.",
    )

    page_break(doc)
    add_section_kicker(doc, "Contents")
    add_heading(doc, "How to read this paper", level=1)
    add_para(doc, "The narrative follows the same chain as the application: evidence first, economics second, decisions third, uncertainty last.")
    contents_rows = [
        ("1", "Project and company story", "What decision is NovaPlan designed to support?"),
        ("2", "Synthetic data as connected evidence", "What is generated, from which parameters, and why can it reconcile?"),
        ("3", "Financial engine", "How do people, price and timing become profit and cash?"),
        ("4", "KPI teaching system", "What does every major metric mean and how should it be read?"),
        ("5", "Two forecast horizons", "Why are 13 weeks and 18 months both necessary?"),
        ("6", "Scenario Lab", "What changes when the company hires 40 consultants?"),
        ("7", "Forecasting algorithms", "How are four models compared without looking into the future?"),
        ("8", "Monte Carlo", "How are operating uncertainties propagated into liquidity risk?"),
        ("9", "Sensitivity and insights", "Which levers matter, and how are results narrated?"),
        ("10", "Experience and governance", "How does the dashboard preserve assumptions and human judgment?"),
        ("11", "Validation, limitations and roadmap", "What is proven, what remains simplified, and what comes next?"),
        ("A-C", "Appendices", "Datasets, formulas, assumptions and reproducibility record"),
    ]
    add_table(doc, ["Section", "Topic", "Reader question"], contents_rows, [950, 3000, 5410], font_size=9.2)
    add_callout(
        doc,
        "Reading convention",
        "EUR m means millions of euros. Percentage points describe absolute changes in a rate; for example, 75% to 78% is +3 percentage points, not +3%.",
        tone="amber",
    )

    page_break(doc)
    add_section_kicker(doc, "1 | Project context")
    add_heading(doc, "The company and the decision", level=1)
    add_para(
        doc,
        "NovaBridge Digital SRL is a fictional Romanian IT consulting and software-engineering company operating from Bucharest and Cluj-Napoca. It sells project work to 24 fictional Western European customers and reports in euros. Its economic engine is people: consultants are hired, trained, assigned to client work, billed by the hour and paid before every customer has necessarily settled its invoice.",
    )
    add_para(
        doc,
        "The dashboard turns one management question into a connected analytical project: should the company add 40 consultants in 2026? A responsible answer cannot stop at incremental revenue. Management also needs to see salary cost, onboarding, utilization, customer-payment delays, equipment purchases, profit, cash headroom and uncertainty.",
    )
    add_formula(
        doc,
        "People and demand -> productive hours -> revenue and cost -> profit -> working capital -> cash -> decision",
        "This sequence is the organizing principle for both the software and this paper.",
    )

    add_heading(doc, "The latest synthetic operating position", level=2)
    current_rows = [
        ("Revenue", fmt_eur(ltm.revenue_eur, 2), f"{(ltm.revenue_eur / prior.revenue_eur - 1) * 100:+.1f}% vs 2024", "Value of services recognized during 2025"),
        ("EBITDA", fmt_eur(ltm.ebitda_eur, 2), f"{ltm.ebitda_margin * 100:.1f}% margin", "Operating profit before interest, tax, depreciation and amortization"),
        ("Operating cash flow", fmt_eur(ltm.operating_cash_flow_eur, 2), f"{(ltm.operating_cash_flow_eur / prior.operating_cash_flow_eur - 1) * 100:+.1f}% vs 2024", "Cash generated by operations after working-capital timing"),
        ("Closing cash", fmt_eur(ltm.closing_cash_eur, 2), f"{fmt_eur(ltm.closing_cash_eur - prior.closing_cash_eur, 2)} YoY", "Cash available at 31 December 2025"),
        ("Headcount", f"{int(ltm.headcount):,}", f"{int(ltm.headcount - prior.headcount):+d} YoY", "Employees at period end"),
        ("Utilization", f"{ltm.utilization * 100:.1f}%", f"Latest month {latest.utilization * 100:.1f}%", "Share of billable capacity used on chargeable work"),
        ("DSO", f"{ltm.dso:.1f} days", f"Latest month {latest.dso:.1f}", "Approximate collection time embedded in receivables"),
    ]
    add_table(doc, ["Metric", "2025 actual", "Context", "Plain-language meaning"], current_rows, [1760, 1600, 1900, 4100], font_size=8.7)
    add_figure(
        doc,
        figures["history"],
        "Figure 2. The synthetic company grows over six years, while EBITDA and cash follow different timing patterns.",
        alt_text="Line chart for 2020 to 2025 showing synthetic annual revenue, EBITDA and closing cash in euros.",
    )

    add_heading(doc, "The six-year teaching story", level=2)
    story_id = create_numbering(doc, "number")
    for item in (
        "2020 shock and stabilization. Demand weakens, collection stress rises and August utilization falls to 62.5%. Headcount ends the year at 258.",
        "2021 recovery. Utilization and hiring return, lifting revenue 14.3% to EUR 20.68m.",
        "2022 scale-up. Strong demand and backlog drive 119 hires; revenue rises 29.4% and headcount reaches 369.",
        "2023 pressure. A strong first half is followed by slower demand and collections. September DSO reaches 67.8 days.",
        "2024-2025 recovery. Collection discipline improves, cash rebuilds and 2025 revenue reaches EUR 36.83m with a 22.5% EBITDA margin.",
    ):
        add_list_item(doc, item, story_id)
    add_callout(
        doc,
        "Profit is not cash",
        "In September 2023 the company earns about EUR 503k of EBITDA but records negative EUR 378k operating cash flow because customer collections lag. In May 2023, a shareholder distribution reduces cash even though the month produces positive free cash flow.",
        tone="amber",
    )

    page_break(doc)
    add_section_kicker(doc, "2 | Synthetic evidence")
    add_heading(doc, "Synthetic data as one causal company", level=1)
    add_para(
        doc,
        "Synthetic data is information created by rules rather than observed from a real company. In NovaPlan, synthetic does not mean arbitrary. The generator begins with customers and a workforce, introduces a designed demand story, calculates capacity and revenue, creates invoices, applies payment behavior, calculates costs and capital spending, and finally reconciles working capital and cash. One output becomes the next input.",
    )
    add_callout(
        doc,
        "Designed causality",
        "The code intentionally makes variables affect one another. That creates a coherent learning environment, but it is not empirical proof that a real company would react with the same coefficients.",
        tone="blue",
    )
    add_figure(
        doc,
        figures["ecosystem"],
        "Figure 3. Eight datasets represent different grains of the same fictional company.",
        alt_text="Eight synthetic datasets surrounding one company: monthly KPIs, invoices, customers, employees, hiring plan, operating costs, capital spending and weekly cash actuals.",
    )

    add_heading(doc, "What is generated", level=2)
    inventory_rows = [
        ("monthly_kpis", "Month", "Jan 2020-Dec 2025", "72 x 53", "Integrated operating, statement and cash record"),
        ("invoices", "Invoice", "Jan 2020-Dec 2025", "3,035 x 12", "Terms, due dates, payments, delays and status"),
        ("customers", "Customer", "Static profiles", "24 x 14", "Segment, country, terms, concentration and payment behavior"),
        ("employees", "Active employee", "31 Dec 2025", "411 x 15", "Role, level, salary, billing rate, utilization and location"),
        ("hiring_plan", "Hiring cohort", "Jan-Jun 2026", "18 x 16", "40 proposed hires split 12 Junior, 18 Mid and 10 Senior"),
        ("opex", "Month/category", "Jan 2020-Dec 2025", "792 x 6", "Eleven fixed, semi-variable and variable cost categories"),
        ("capex", "Asset event", "Jan 2020-Dec 2025", "144 x 7", "Equipment, replacements, offices and strategic technology"),
        ("weekly_cash_actuals", "Week", "Jan 2024-Dec 2025", "105 x 13", "Monthly cash amounts allocated into a weekly teaching bridge"),
    ]
    add_table(doc, ["Dataset", "Grain", "Coverage", "Size", "Teaching purpose"], inventory_rows, [1700, 1250, 1600, 1100, 3710], font_size=8.2)
    add_para(
        doc,
        "The monthly dataset is the backbone, but the other files provide the evidence behind it. Invoice value totals EUR 166.129m and reconciles to recognized monthly revenue. Open and overdue invoice value reconciles to December 2025 accounts receivable. The active employee file contains the 411 people still employed at the cut-off; departed employees are not retained as a historical roster.",
    )

    add_heading(doc, "Historical generator parameters", level=2)
    parameter_rows = [
        ("Time and reproducibility", "Jan 2020-Dec 2025; data cut-off 31 Dec 2025; seed 42"),
        ("Opening company", "272 employees; EUR 5.20m backlog; EUR 4.70m cash; EUR 2.52m AR; EUR 0.67m AP"),
        ("People cost", "2.25% employer on-cost for generated history; EUR 205 monthly benefits; level-specific bonuses"),
        ("New-hire productivity", "35%, 65%, 85%, then 100% over the first four stages"),
        ("Commercial", "96.5% base realization; 1.42x contractor markup; pricing and demand evolve over time"),
        ("Collections", "30/45/60-day terms; delays -7 to +55 days; exceptional delay on 5.5% of invoices"),
        ("Liquidity", "EUR 3.00m policy floor; 60% of prior positive net income distributed in May"),
        ("Capital and tax", "EUR 1,800 equipment per hire; EUR 1,450 laptop replacement over 36 months; simplified 16% tax"),
    ]
    add_table(doc, ["Area", "Main parameters"], parameter_rows, [2200, 7160], font_size=8.8)
    add_callout(
        doc,
        "Do not mix assumption scopes",
        "The YAML file is the contract for synthetic history. The interactive planner has its own explicit defaults. Proposed-hire economics use 8% employer on-cost and an 8% bonus, while generated history uses 2.25% on-cost and level-specific bonuses. The scopes should be labelled, not blended.",
        tone="amber",
    )

    add_heading(doc, "How realism is introduced", level=2)
    realism_id = create_numbering(doc, "bullet")
    for item in (
        "Demand follows an explicit pandemic, recovery, scale-up, pressure and recovery storyline rather than a flat trend.",
        "Hiring responds with a lag to utilization and backlog; attrition is bounded; new people ramp before becoming fully productive.",
        "Utilization includes summer and December seasonality plus small noise, and is clipped to realistic teaching bounds.",
        "Customer concentration is intentional: the top five customers represent about 55.6% of invoiced revenue.",
        "Payment dates combine contractual terms, customer behavior, stress periods, exceptional delays and random variation.",
        "Accounts receivable, accounts payable and cash use explicit roll-forwards rather than being sampled independently.",
    ):
        add_list_item(doc, item, realism_id)
    add_para(
        doc,
        "Before writing the CSVs, the generator validates headcount, invoice totals, revenue, accounts receivable, EBITDA and cash identities. CSV values are rounded to four decimals, so recomputing formulas from serialized drivers can leave immaterial rounding residuals even when the unrounded generator reconciles exactly.",
    )

    add_section_kicker(doc, "3 | Financial engine")
    add_heading(doc, "From productive capacity to recognized revenue", level=1)
    add_figure(
        doc,
        figures["driver_tree"],
        "Figure 4. Revenue is produced by an auditable driver tree rather than guessed as a standalone total.",
        alt_text="Revenue driver tree from workforce capacity to billable hours, core services revenue and recognized revenue.",
    )
    add_formula(doc, "Capacity hours = Headcount x Billable share x Working days x Hours per day")
    add_formula(doc, "Billable hours = Capacity hours x Utilization")
    add_formula(doc, "Core revenue = Billable hours x Billing rate x Realization x Service-mix factor")
    add_formula(doc, "Total revenue = Core revenue + Backlog recognized + Contractor revenue")
    add_para(
        doc,
        "Headcount measures how many people are employed. Billable share asks how many can be sold to customers. Utilization asks how much of their available capacity is actually used on chargeable work. Billing rate sets the nominal hourly price, while realization removes discounts and write-downs. Backlog represents contracted work not yet recognized as revenue.",
    )
    add_callout(
        doc,
        "Worked example",
        "With 280 employees, 82% billable share, 20 working days, eight hours per day, 72% utilization, a EUR 62 rate and 97% realization, the model produces 36,736 capacity hours, 26,450 billable hours and about EUR 1.591m revenue. Raising utilization to 78% increases revenue to about EUR 1.723m.",
        tone="teal",
    )

    add_heading(doc, "Workforce and hire economics", level=2)
    add_formula(doc, "Ending headcount = Beginning headcount + Hires - Attrition")
    add_formula(doc, "Ramp factor = minimum(Months since joining / Ramp months, 100%)")
    add_para(
        doc,
        "A new employee costs cash from the joining date but does not create a full productive equivalent immediately. With a three-month linear ramp, the cohort contributes roughly one-third, two-thirds and then 100% productive capacity. This is why physical headcount and productive headcount are shown separately.",
    )
    hire_rows = [
        ("Annual salary", "EUR 42,000", "Contractual pay before employer on-cost and bonus"),
        ("Recurring employer cost", "EUR 51,120", "Salary, 8% on-cost and 8% bonus in the proposed-hire module"),
        ("Year-one cash cost", "EUR 55,920", "Recurring cost plus recruiting and equipment"),
        ("Steady-state revenue", "EUR 90,960", "Expected annual revenue at full productivity"),
        ("Ramped year-one revenue", "EUR 83,380", "Revenue after the onboarding ramp"),
        ("Year-one EBITDA effect", "+EUR 29,260", "Ramped revenue less recurring cost and shared overhead allocation"),
        ("Break-even utilization", "41.6%", "Utilization required for employer cost to be covered"),
        ("Cash payback", "Month 4", "First month cumulative hire cash becomes non-negative"),
    ]
    add_table(doc, ["Hire metric", "Illustrative result", "Meaning"], hire_rows, [2300, 1900, 5160], font_size=8.7)

    add_heading(doc, "Profit, working capital and cash", level=2)
    add_formula(doc, "EBITDA = Revenue - Payroll - Contractor cost - Other operating expense")
    add_formula(doc, "EBIT = EBITDA - Depreciation;  Net income = EBIT - Interest - Tax")
    add_figure(
        doc,
        figures["working_capital"],
        "Figure 5. Service delivery and cash collection occur at different times; accounts receivable carries that timing gap.",
        alt_text="Sequence from services delivered to invoice, payment delay and cash collection, with an explanation that higher DSO raises receivables and lowers near-term cash.",
    )
    add_formula(
        doc,
        "Planner AR = Monthly revenue x DSO / 30.4375\nHistorical DSO = Ending AR / trailing 3-month average revenue x 30.4375",
    )
    add_formula(doc, "Accounts payable = Vendor expense x DPO / 30.4375")
    add_formula(doc, "Operating cash flow = Net income + Depreciation - Change in AR + Change in AP + other working-capital movements")
    add_formula(doc, "Free cash flow = Operating cash flow - Capital expenditure")
    add_para(
        doc,
        "DSO is the approximate number of days revenue remains unpaid. The planner converts an assumed DSO and current monthly revenue into forecast AR; the synthetic historical KPI divides ending AR by trailing three-month average revenue to smooth monthly seasonality. Higher DSO normally increases receivables and reduces near-term cash without changing earned revenue or EBITDA. DPO is the approximate time the company takes to pay suppliers. Higher DPO preserves cash for longer, although excessively slow payment may damage supplier relationships.",
    )
    add_callout(
        doc,
        "Capex versus depreciation",
        "Capital expenditure uses cash when equipment or technology is purchased. Depreciation spreads that asset cost through profit over time. Therefore capex changes cash immediately but does not reduce EBITDA; depreciation reduces EBIT but not cash in the period.",
        tone="blue",
    )
    add_heading(doc, "Reconciled statements and the lighter planner", level=2)
    add_para(
        doc,
        "The project contains a full three-statement engine that builds the income statement, balance sheet and cash-flow statement and checks both the balance-sheet identity and cash roll-forward to a EUR 1 tolerance. The interactive 18-month planner is intentionally lighter: it calculates the decision lines needed for revenue, EBITDA, receivables, payables, operating cash flow, free cash flow and closing cash. These are separate implementations in the MVP and should not be described as one identical calculation path.",
    )

    add_section_kicker(doc, "4 | KPI teaching system")
    add_heading(doc, "How to read a metric", level=1)
    add_para(
        doc,
        "A KPI is a key performance indicator: a number chosen because it helps management understand performance, a driver or a risk. A good KPI explanation answers four questions: what is measured, how it is calculated, why it matters and which trade-off prevents a simplistic good-or-bad interpretation.",
    )
    add_callout(
        doc,
        "Direction is contextual",
        "Higher revenue, EBITDA and cash are usually favorable, but even these must be read with quality and risk. Higher utilization can improve profit but become unsustainable; higher DPO can preserve cash while straining suppliers; lower attrition can protect capability but may increase payroll if demand weakens.",
        tone="amber",
    )

    add_heading(doc, "Operating and workforce KPIs", level=2)
    operating_kpis = [
        ("Headcount", "Employees at period end", "Opening + hires - attrition", "Scale of the cost base and future capacity"),
        ("Hires", "People joining in the period", "Count of joining employees", "Adds cost immediately and capacity after ramp-up"),
        ("Attrition", "People leaving", "Departures / average headcount", "High attrition can reduce capacity and create replacement cost"),
        ("Billable headcount", "Employees whose work can be charged", "Count of billable employees", "Separates revenue-producing roles from support roles"),
        ("Billable share", "Workforce mix", "Billable headcount / total headcount", "Shows how much of the organization can directly generate revenue"),
        ("Working days", "Available business days", "Calendar-based monthly count", "Explains seasonal capacity without implying weaker demand"),
        ("Capacity hours", "Potential billable time", "HC x billable share x days x hours/day", "Upper bound before utilization"),
        ("Billable hours", "Chargeable time delivered", "Capacity hours x utilization", "Immediate volume driver of service revenue"),
        ("Utilization", "Use of billable capacity", "Billable hours / capacity hours", "Central productivity lever; very high levels may be hard to sustain"),
        ("Billing rate", "Nominal price per hour", "Contracted/effective hourly rate", "Commercial pricing lever"),
        ("Realization", "Value retained after discounts", "Recognized value / nominal billed value", "Separates list price from collected economic value"),
        ("Demand index", "Relative market demand", "Synthetic index around 1.0", "Connects market conditions to work availability"),
        ("Bookings", "New contracted work", "Value of work signed in period", "Leading signal for future delivery"),
        ("Backlog", "Contracted work not yet recognized", "Opening + bookings - recognized work", "Provides future revenue cover"),
        ("Contractor FTE", "External delivery capacity", "Equivalent full-time contractors", "Adds flexible capacity at a different cost structure"),
        ("Revenue per FTE", "Combined productivity", "Annualized revenue / headcount", "Brings price, utilization and mix into one indicator"),
        ("Payroll per FTE", "Average workforce cost", "Payroll / headcount", "Shows salary and workforce-mix pressure"),
    ]
    add_table(doc, ["Metric", "Plain meaning", "Formula or basis", "Management use"], operating_kpis, [1650, 2500, 2500, 2710], font_size=7.9)

    add_heading(doc, "Profit and statement KPIs", level=2)
    profit_kpis = [
        ("Revenue", "Value of services earned", "Capacity, price, realization, backlog and contractors", "Growth and commercial performance"),
        ("Payroll", "Employee compensation cost", "Salary + bonus + on-cost + benefits", "Largest recurring people cost"),
        ("Contractor cost", "External delivery cost", "Contractor FTE and compensation assumptions", "Flexible capacity cost"),
        ("Other OPEX", "Operating cost beyond people/contractors", "Facilities, software, sales and administration", "Cost discipline and operating leverage"),
        ("EBITDA", "Operating profit before non-cash depreciation and financing/tax", "Revenue - payroll - contractor - other OPEX", "Core operating profitability"),
        ("EBITDA margin", "EBITDA earned per euro of revenue", "EBITDA / revenue", "Compares profitability across periods and scenarios"),
        ("Capex", "Cash invested in long-lived assets", "Equipment, office and technology purchases", "Consumes cash but is not an EBITDA expense"),
        ("Depreciation", "Periodic asset-cost allocation", "Asset cost / useful life", "Reduces EBIT without current-period cash outflow"),
        ("EBIT", "Profit after depreciation", "EBITDA - depreciation", "Operating profit on an accounting basis"),
        ("Interest", "Cost of financing", "Debt-balance/interest assumption", "Links capital structure to profit"),
        ("Tax expense", "Simplified corporate tax charge", "Positive pre-tax profit x 16%", "Educational estimate, not tax guidance"),
        ("Net income", "Profit after operating, asset, financing and tax costs", "EBIT - interest - tax", "Bottom-line accounting result"),
    ]
    add_table(doc, ["Metric", "Plain meaning", "Formula or basis", "Management use"], profit_kpis, [1650, 2500, 2500, 2710], font_size=7.9)

    add_heading(doc, "Working-capital and liquidity KPIs", level=2)
    cash_kpis = [
        ("Accounts receivable (AR)", "Customer amounts still unpaid", "Beginning AR + invoices - collections - write-offs", "Cash tied up after revenue is earned"),
        ("Cash collections", "Customer money received", "Invoice-payment schedule", "Turns receivables into cash"),
        ("Write-offs", "Receivables judged uncollectible", "Written-off invoice value", "Credit loss and revenue-quality signal"),
        ("DSO", "Approximate collection time", "Planner: AR / monthly revenue; history: AR / 3-month average revenue; both x 30.4375", "Higher values usually reduce near-term liquidity"),
        ("Accounts payable (AP)", "Supplier amounts still unpaid", "Beginning AP + purchases - payments", "Temporary supplier financing"),
        ("Vendor payments", "Cash paid to suppliers", "Payables schedule and current purchases", "Major cash-disbursement line"),
        ("DPO", "Approximate supplier-payment time", "AP / vendor expense x 30.4375", "Higher values preserve cash longer but may strain suppliers"),
        ("Operating cash flow", "Cash generated by operations", "Profit adjusted for non-cash items and working capital", "Measures conversion of operations into cash"),
        ("Free cash flow", "Cash after capital investment", "Operating cash flow - capex", "Cash available before financing and distributions"),
        ("Financing cash flow", "Borrowing, repayment or distribution cash", "Borrowings - repayments - dividends", "Explains cash changes outside operations/investing"),
        ("Opening cash", "Cash at period start", "Prior period closing cash", "Starting point for liquidity"),
        ("Net change in cash", "Period movement", "Operating + investing + financing cash", "Explains whether cash grew or fell"),
        ("Closing cash", "Cash at period end", "Opening cash + net cash change", "Headline liquidity balance"),
        ("Policy floor", "Minimum desired cash", "Management threshold; EUR 3m default", "Operating-risk guardrail, not a legal minimum"),
        ("Liquidity headroom", "Buffer above the floor", "Minimum forecast cash - policy floor", "Capacity to absorb downside before intervention"),
        ("Funding requirement", "Cash needed to restore the floor", "max(floor - cash, 0)", "Signals an external funding or mitigation need"),
    ]
    add_table(doc, ["Metric", "Plain meaning", "Formula or basis", "Management use"], cash_kpis, [1650, 2500, 2500, 2710], font_size=7.8)

    add_heading(doc, "Forecast, scenario and risk KPIs", level=2)
    model_kpis = [
        ("Model baseline", "Forecast before human judgment", "Driver-based model output", "Preserves an objective reference"),
        ("Management adjustment", "Visible human overlay", "Entered amount or percentage plus rationale", "Separates judgment from model output"),
        ("Final forecast", "Value presented after adjustment", "Baseline + entered/visible management adjustment", "Current planning view"),
        ("Scenario delta", "Difference from Base", "Scenario result - Base result", "Isolates the financial effect of changed assumptions"),
        ("MAE", "Average absolute forecast miss", "mean(abs(actual - prediction))", "Typical error in the metric's own unit"),
        ("RMSE", "Error measure that punishes large misses", "sqrt(mean(error squared))", "Highlights occasional large forecast failures"),
        ("WAPE", "Total absolute error relative to total actual", "sum(abs(error)) / sum(abs(actual))", "Comparable percentage accuracy score; lower is better"),
        ("Directional accuracy", "Share of correctly predicted rises/falls", "Matched movement signs / tested periods", "Tests whether turning points are anticipated"),
        ("P5 / P50 / P95", "Low, median and high simulated outcomes", "Cross-sectional percentiles", "Shows range and central case without claiming certainty"),
        ("Breach probability", "Share of simulations below a limit", "Runs with any breach / total runs", "Model-conditional frequency of liquidity stress"),
        ("Expected funding need", "Average simulated shortfall", "mean(max(floor - path minimum, 0))", "Combines probability and severity"),
        ("Driver correlation", "Association with forecast-end cash", "Pearson correlation across runs", "Ranks co-movement; not an isolated causal effect"),
        ("Sensitivity impact", "Change after one lever is shocked", "Shocked result - Base result", "Cleaner one-at-a-time lever materiality"),
    ]
    add_table(doc, ["Metric", "Plain meaning", "Formula or basis", "Management use"], model_kpis, [1650, 2500, 2500, 2710], font_size=7.8)

    add_section_kicker(doc, "5 | Forecast horizons")
    add_heading(doc, "Two horizons answer two different questions", level=1)
    add_para(
        doc,
        "The 13-week forecast asks whether the company can meet near-term obligations week by week. The 18-month forecast asks whether strategic choices create value and remain liquid over a longer operating horizon. Weekly detail is better for payment timing; monthly detail is better for staffing, pricing, demand and profitability. Neither horizon replaces the other.",
    )
    horizon_rows = [
        ("13-week direct cash", "Week", "Collections and disbursements", "Will cash fall below the policy floor soon?", "Treasury and immediate interventions"),
        ("18-month rolling forecast", "Month", "Operating drivers and working capital", "What do demand, price, hiring and collections do to profit and cash?", "Management planning and scenarios"),
    ]
    add_table(doc, ["Forecast", "Grain", "Primary engine", "Question", "Best use"], horizon_rows, [1900, 850, 2150, 2700, 1760], font_size=8.5)

    add_heading(doc, "The 13-week direct cash forecast", level=2)
    add_formula(doc, "Weekly net cash flow = Customer collections - Payroll - Vendor payments - Tax - Capex - Other payments")
    add_formula(doc, "Weekly closing cash = Weekly opening cash + Weekly net cash flow")
    liq_stats = [
        ("Opening cash", fmt_eur(liquidity["opening_cash_eur"].iloc[0], 2)),
        ("13-week collections", fmt_eur(liquidity["customer_collections_eur"].sum(), 2)),
        ("13-week disbursements", fmt_eur(liquidity["total_disbursements_eur"].sum(), 2)),
        ("Lowest weekly cash", fmt_eur(liquidity["closing_cash_eur"].min(), 2)),
        ("Forecast-end cash", fmt_eur(liquidity["closing_cash_eur"].iloc[-1], 2)),
        ("Weeks below EUR 3m", str(int(liquidity["below_minimum_cash"].sum()))),
    ]
    add_table(doc, ["Liquidity measure", "Base result"], liq_stats, [4200, 5160], font_size=9.2)
    add_figure(
        doc,
        figures["liquidity"],
        "Figure 6. The Base 13-week cash forecast remains comfortably above the EUR 3m policy floor.",
        alt_text="Thirteen-week closing-cash line chart with a horizontal EUR 3 million policy floor.",
    )
    add_para(
        doc,
        "Known invoices are used where available; a recent historical weekly baseline fills later periods for work not yet invoiced at the start date. Controls can delay collections, change payroll or vendor spending, move capex, add a large customer payment, or add hires. The lowest week matters because a strong quarter-end balance can hide a temporary payment bottleneck.",
    )

    add_heading(doc, "The 18-month driver-based forecast", level=2)
    forecast_rows = [
        ("Horizon", "Jan 2026-Jun 2027", "18 monthly periods"),
        ("Revenue", fmt_eur(base_summary.revenue_eur, 2), "Demand, capacity, utilization, rate, realization and calibration"),
        ("EBITDA", fmt_eur(base_summary.ebitda_eur, 2), f"{base_summary.ebitda_margin * 100:.2f}% aggregate margin"),
        ("Operating cash flow", fmt_eur(base_summary.operating_cash_flow_eur, 2), "EBITDA, tax, AR and AP timing"),
        ("Forecast-end cash", fmt_eur(base_summary.year_end_cash_eur, 2), "Cash at June 2027; code field name is year_end_cash"),
        ("Minimum cash", fmt_eur(base_summary.minimum_cash_eur, 2), f"{fmt_eur(base_summary.liquidity_headroom_eur, 2)} headroom above floor"),
        ("Ending headcount", f"{base_summary.headcount:.0f}", "Includes baseline hiring and attrition"),
        ("Average utilization", f"{base_summary.utilization * 100:.2f}%", "Bounded between 55% and 90%"),
        ("Average DSO", f"{base_summary.dso:.2f} days", "Collection timing carried into AR and cash"),
    ]
    add_table(doc, ["Measure", "Base result", "Interpretation"], forecast_rows, [2400, 2100, 4860], font_size=8.7)
    add_para(
        doc,
        "Default planning assumptions include 5% annual demand growth, 3% annual billing-rate growth, 6% salary inflation, 3.5% other-OPEX inflation and a EUR 3m liquidity floor. Historical calibration aligns the transparent driver tree with the recent synthetic revenue run-rate. The planner also applies monthly seasonality and new-hire productivity ramps.",
    )
    add_callout(
        doc,
        "Governed forecast",
        "The core forecast stores model baseline revenue, management adjustment and final revenue as separate fields. A rationale can accompany the adjustment. The generic page-level overlay for another selected metric is currently a presentation/export adjustment and does not rerun every dependent statement line.",
        tone="amber",
    )

    add_section_kicker(doc, "6 | Scenario Lab")
    add_heading(doc, "Scenarios are coherent management stories", level=1)
    add_para(
        doc,
        "A forecast is one internally consistent view. A scenario changes a group of assumptions to represent a management story. NovaPlan's executable runtime scenarios are defined in the Python scenario library. The separate scenarios YAML file is not loaded by the app and currently differs; this source-of-truth drift is disclosed in Section 11.",
    )
    scenario_assumptions_rows = [
        ("Base", "No incremental scenario levers", "Reference case"),
        ("Expansion", "40 hires over 6 months; 3-month ramp; DSO 58 days", "Growth plan with a moderate collection drag"),
        ("Risk", "Same hires; DSO 70; utilization -5 pp; salary inflation 8%", "Demand/productivity and collection stress"),
        ("Mitigation", "40 hires over 9 months; DSO 50; rate +2%", "Slower hiring, faster collections and modest pricing"),
    ]
    add_table(doc, ["Case", "Executable assumptions", "Management story"], scenario_assumptions_rows, [1500, 4300, 3560], font_size=8.8)
    add_figure(
        doc,
        figures["scenario_paths"],
        "Figure 7. All four scenario cash paths remain above the EUR 3m floor, but their liquidity trajectories separate materially.",
        alt_text="Monthly closing-cash paths for Base, Expansion, Risk and Mitigation from January 2026 to June 2027, all above a EUR 3 million floor.",
    )

    add_heading(doc, "The expansion decision", level=2)
    scenario_results = []
    for row in cases.itertuples():
        scenario_results.append(
            (
                row.scenario,
                fmt_eur(row.revenue_eur, 2),
                fmt_eur(row.ebitda_eur, 2),
                f"{row.ebitda_margin * 100:.2f}%",
                fmt_eur(row.year_end_cash_eur, 2),
                fmt_eur(row.minimum_cash_eur, 2),
            )
        )
    add_table(
        doc,
        ["Case", "Revenue", "EBITDA", "Margin", "Jun 2027 cash", "Minimum cash"],
        scenario_results,
        [1450, 1630, 1630, 1250, 1780, 1620],
        font_size=8.4,
    )
    add_figure(
        doc,
        figures["scenario_deltas"],
        "Figure 8. Scenario deltas reveal the trade-off between cumulative profitability and the path of cash.",
        alt_text="Grouped bars showing revenue, EBITDA, forecast-end cash and minimum-cash deltas versus Base for Expansion, Risk and Mitigation.",
    )
    add_callout(
        doc,
        "Decision reading",
        f"Expansion adds {fmt_eur(expansion_summary.revenue_eur - base_summary.revenue_eur, 2)} revenue and {fmt_eur(expansion_summary.ebitda_eur - base_summary.ebitda_eur, 2)} EBITDA, yet minimum cash falls by {fmt_eur(abs(expansion_summary.minimum_cash_eur - base_summary.minimum_cash_eur), 2)} during ramp-up. Risk nearly preserves revenue but loses {fmt_eur(abs(risk_summary.ebitda_eur - base_summary.ebitda_eur), 2)} EBITDA because capacity, salaries and collections deteriorate together. Mitigation produces the strongest combined profit and cash result.",
        tone="teal",
    )
    add_para(
        doc,
        "The scenario table is not probability-weighted. Each case is a deterministic answer to an explicit what-if question. It should be paired with sensitivity for lever size and Monte Carlo for probability distributions.",
    )

    page_break(doc)
    add_section_kicker(doc, "7 | Forecasting algorithms")
    add_heading(doc, "Four models, one governance question", level=1)
    add_para(
        doc,
        "The forecasting diagnostics do not automatically replace the driver-based financial plan. They benchmark whether increasingly complex statistical algorithms improve one-month-ahead estimates of selected metrics. The governance question is simple: does complexity reduce out-of-sample error enough to justify harder explanation and maintenance?",
    )
    algorithm_rows = [
        ("Seasonal Naive", "Repeats the same month one year earlier", "Transparent baseline and seasonal reference", "Cannot use current operational drivers"),
        ("Driver Regression", "Ordinary multivariate linear regression after median imputation", "Interpretable coefficients and driver relationships", "Assumes stable linear effects"),
        ("ElasticNet", "Standardized linear model with L1 and L2 regularization", "Stabilizes correlated drivers and shrinks weak effects", "Still fundamentally linear"),
        ("Gradient Boosting", "Conservative histogram-based nonlinear trees", "Learns thresholds and interactions", "Higher complexity and overfit risk with only 72 months"),
    ]
    add_table(doc, ["Algorithm", "How it works", "Why include it", "Main limitation"], algorithm_rows, [1900, 2900, 2600, 1960], font_size=8.4)
    add_callout(
        doc,
        "ElasticNet settings",
        "alpha 0.01, L1 ratio 0.25 and maximum 20,000 iterations. Gradient boosting uses 120 iterations, learning rate 0.05, at most 15 leaves, at least six observations per leaf, L2 regularization 0.1 and seed 42.",
        tone="blue",
    )

    add_heading(doc, "Chronological walk-forward validation", level=2)
    add_figure(
        doc,
        figures["walk_forward"],
        "Figure 9. The training window expands one month at a time; each next month is predicted before it is added to training.",
        alt_text="Schematic of three walk-forward folds: an expanding teal training window followed by one amber prediction month and unused future months.",
    )
    add_para(
        doc,
        "With 72 monthly observations and an initial 36-month training window, each model produces 36 chronological test predictions. Data is never shuffled. This mirrors real use: the future is unavailable when a forecast is created.",
    )
    add_formula(doc, "MAE = mean(abs(Actual - Predicted))", "Average miss in the target's native unit.")
    add_formula(doc, "RMSE = sqrt(mean((Actual - Predicted)^2))", "Gives extra weight to unusually large misses.")
    add_formula(doc, "WAPE = sum(abs(Actual - Predicted)) / sum(abs(Actual))", "Primary comparable error score; lower is better.")
    add_formula(doc, "Directional accuracy = matched rise/fall directions / tested periods", "Higher is better.")

    add_heading(doc, "What the current backtest says", level=2)
    add_figure(
        doc,
        figures["model_wape"],
        "Figure 10. No algorithm wins every target, although ElasticNet is strongest overall on the current synthetic history.",
        alt_text="Grouped WAPE bars for five targets and four forecasting algorithms; lower bars indicate better accuracy.",
    )
    revenue_rows = [
        ("ElasticNet", "EUR 58.4k", "EUR 69.8k", "2.09%", "94.4%"),
        ("Gradient Boosting", "EUR 172.4k", "EUR 215.9k", "6.17%", "80.6%"),
        ("Driver Regression", "EUR 183.0k", "EUR 221.9k", "6.55%", "80.6%"),
        ("Seasonal Naive", "EUR 329.8k", "EUR 377.2k", "11.80%", "69.4%"),
    ]
    add_table(doc, ["Revenue model", "MAE", "RMSE", "WAPE", "Direction"], revenue_rows, [2300, 1750, 1750, 1750, 1810], font_size=8.8)
    add_callout(
        doc,
        "Interpretation boundary",
        "The feature-based backtest uses observed same-month driver values. It therefore answers: how well can the target be estimated when these drivers are known or planned? It is a conditional benchmark, not a fully autonomous forecast of both the drivers and the outcome.",
        tone="amber",
    )

    add_section_kicker(doc, "8 | Monte Carlo risk")
    add_heading(doc, "From one forecast to a distribution of outcomes", level=1)
    add_para(
        doc,
        "A deterministic scenario asks what happens under one chosen set of assumptions. Monte Carlo asks what range of results appears when several uncertain drivers vary together thousands of times. NovaPlan does not draw a random cash balance directly. It perturbs operating drivers, recalculates the financial chain and then obtains one cash path. Repeating that process 10,000 times produces a distribution.",
    )
    add_figure(
        doc,
        figures["monte_carlo_flow"],
        "Figure 11. The simulation preserves an auditable path from uncertain business drivers to cash.",
        alt_text="Five-step Monte Carlo flow from Base forecast through driver shocks, financial recalculation, cash path and risk summary, repeated 10,000 times.",
    )
    add_callout(
        doc,
        "Reproducibility",
        "The random seed is 42 and NumPy uses the PCG64 bit generator. The same code, input data, assumptions and software environment reproduce the same draws and results. A seed alone is not sufficient if code or package versions change.",
        tone="blue",
    )

    add_heading(doc, "How correlated uncertainty is created", level=2)
    add_formula(doc, "Shared shock S_i ~ N(0,1); monthly innovation E_it ~ N(0,1)")
    add_formula(doc, "M_i1 = 0.65 S_i + 0.35 E_i1;  M_it = 0.70 M_i,t-1 + 0.30 E_it")
    add_para(
        doc,
        "The shared shock gives each simulation a broad favorable or unfavorable environment. The monthly macro path is persistent, so a weak month tends to be followed by another partly weak month. That macro path simultaneously supports utilization, billing, backlog conversion and demand while reducing DSO in favorable conditions. This creates economically coherent co-movement instead of seven independent dice rolls.",
    )
    sampling_rows = [
        ("Utilization", "Base + 1.2 pp x macro + monthly noise of 1.8 pp", "55%-90%"),
        ("DSO", "Base - 3 days x macro + monthly noise of 4 days", "30-95 days"),
        ("Billing realization factor", "1 + 0.6% x macro + monthly noise of 1.5%", "90%-108%"),
        ("Salary inflation shock", "Normal(0, 1.8 pp), constant within each run", "-5 pp to +8 pp"),
        ("Attrition shock", "-0.5 pp x shared shock + Normal(0, 2 pp)", "-6 pp to +8 pp"),
        ("Backlog conversion factor", "1 + 2.5% x macro + monthly noise of 4%", "82%-118%"),
        ("EUR/RON shock", "Normal(0, 1.5%), constant within each run", "-5% to +5%"),
        ("Demand factor", "1 + 2% x macro", "90%-110%"),
    ]
    add_table(doc, ["Uncertain driver", "Sampling rule", "Hard bound"], sampling_rows, [2300, 5200, 1860], font_size=8.5)
    add_para(
        doc,
        "The engine clips draws outside a hard bound to that bound. This is a clipped normal distribution, not a formal truncated normal that repeatedly resamples out-of-bound observations. DPO, capex, depreciation, the tax rate, working days and the Base hiring schedule remain deterministic in the default simulation.",
    )

    add_heading(doc, "How shocks become cash", level=2)
    add_formula(doc, "Headcount factor = exp(-Attrition shock x Elapsed years)")
    add_formula(doc, "Revenue = Base revenue x Utilization factor x Billing factor x Backlog factor x Demand factor x Headcount factor")
    add_formula(doc, "Payroll = Base payroll x Headcount factor x Salary factor / FX factor")
    add_formula(doc, "EBITDA = Revenue - Payroll - Contractor cost - Other OPEX")
    add_formula(doc, "Operating cash flow = EBITDA - Tax - Change in AR + Change in AP")
    add_formula(doc, "Cash path = Opening cash + cumulative(Operating cash flow - Capex)")
    add_para(
        doc,
        "Contractor cost is partly fixed and partly revenue-linked. Other OPEX responds modestly to salary pressure. Tax is applied to positive EBITDA after Base depreciation. Receivables are rebuilt from simulated revenue and DSO, while payables use simulated vendor expenses and Base DPO. The simulation therefore preserves the same profit-to-cash timing taught elsewhere in the project.",
    )

    add_heading(doc, "The 10,000-run result", level=2)
    end_cash = np.asarray(monte_carlo["year_end_cash_eur"], dtype=float)
    minimum_cash_paths = np.asarray(monte_carlo["minimum_cash_eur"], dtype=float)
    aggregate_margin = np.asarray(monte_carlo["ebitda_margin"], dtype=float)
    result_rows = [
        ("Expected / mean Jun 2027 cash", fmt_eur(mc_summary["expected_year_end_cash_eur"], 2), "Average across all simulated runs"),
        ("P5", fmt_eur(mc_summary["p5_year_end_cash_eur"], 2), "Only 5% of forecast-end balances are lower"),
        ("Median / P50", fmt_eur(mc_summary["median_year_end_cash_eur"], 2), "Half the outcomes are lower and half higher"),
        ("P95", fmt_eur(mc_summary["p95_year_end_cash_eur"], 2), "Only 5% of forecast-end balances are higher"),
        ("Standard deviation", fmt_eur(float(end_cash.std()), 2), "Dispersion of forecast-end cash"),
        ("Lowest observed path minimum", fmt_eur(float(minimum_cash_paths.min()), 2), "Lowest monthly cash observed in all runs"),
        ("P5 aggregate EBITDA margin", f"{np.percentile(aggregate_margin, 5) * 100:.2f}%", "Lower-tail profitability across the full horizon"),
        ("Cash-floor breach probability", f"{mc_summary['probability_cash_below_threshold'] * 100:.2f}%", "Share of runs below EUR 3m in any month"),
        ("Negative-cash probability", f"{mc_summary['probability_external_funding_required'] * 100:.2f}%", "Share of runs with cash below zero"),
    ]
    add_table(doc, ["Risk measure", "Result", "Beginner interpretation"], result_rows, [3300, 1900, 4160], font_size=8.6)
    add_figure(
        doc,
        figures["monte_carlo_fan"],
        "Figure 12. The dark band contains the middle 50% of monthly cash outcomes and the light band P5-P95.",
        alt_text="Monte Carlo cash fan chart from January 2026 to June 2027 with median line, middle 50 percent band, P5 to P95 band and EUR 3 million floor.",
    )
    add_para(
        doc,
        "Each monthly percentile is calculated across all simulations at that month. The P5 line is therefore not one single unlucky company path. Similarly, the minimum cash distribution scans each complete path, so it answers a different question from any one monthly percentile.",
    )

    add_figure(
        doc,
        figures["monte_carlo_histogram"],
        "Figure 13. Forecast-end cash is concentrated around EUR 28.8m, with a P5-P95 spread of about EUR 4.73m.",
        alt_text="Histogram of June 2027 cash across 10,000 simulations, centered around a median of approximately EUR 28.8 million.",
    )
    add_callout(
        doc,
        "Zero events is not zero risk",
        "No run breaches EUR 3m or a 10% aggregate EBITDA margin under the selected model and synthetic opening position. This does not prove that breach is impossible. With zero events in 10,000 independent runs, the rule of three gives an approximate model-conditional 95% upper bound of 0.03%.",
        tone="red",
    )

    add_heading(doc, "Risk appetite changes the answer", level=2)
    policy_rows = []
    for threshold in (15_000_000.0, 16_000_000.0, 16_500_000.0, 17_000_000.0):
        probability = float(np.mean(minimum_cash_paths < threshold))
        policy_rows.append((fmt_eur(threshold, 1), f"{probability * 100:.2f}%", "Share of paths falling below the alternative management buffer"))
    add_table(doc, ["Alternative cash buffer", "Modeled breach frequency", "Interpretation"], policy_rows, [2600, 2400, 4360], font_size=8.8)
    add_para(
        doc,
        "The default EUR 3m floor is far below the current synthetic cash position. A board that requires a EUR 16m operating buffer would see a meaningful breach frequency even though the modeled zero-cash shortfall risk remains remote. Risk appetite is therefore an input to the decision, not a statistic discovered by the model.",
    )

    add_heading(doc, "Which simulated drivers move with cash?", level=2)
    add_figure(
        doc,
        figures["risk_drivers"],
        "Figure 14. Backlog conversion and utilization have the strongest positive associations; higher DSO has the strongest negative association.",
        alt_text="Signed horizontal correlation bars for backlog conversion, utilization, DSO, billing realization, salary inflation, EUR/RON and attrition versus forecast-end cash.",
    )
    ranking = monte_carlo["risk_driver_ranking"]
    ranking_rows = [
        (int(row["rank"]), row["driver"], f"{row['correlation_with_year_end_cash']:+.3f}", row["direction"])
        for _, row in ranking.iterrows()
    ]
    add_table(doc, ["Rank", "Driver", "Correlation", "Observed association"], ranking_rows, [900, 3000, 1900, 3560], font_size=8.8)
    add_para(
        doc,
        "Correlation is not an isolated causal effect and is not the percentage of cash variance explained. Several drivers share the same macro factor, so one bar may carry co-movement with other drivers. The next section's deterministic sensitivity is the cleaner turn-one-knob test.",
    )

    page_break(doc)
    add_section_kicker(doc, "9 | Sensitivity and insight")
    add_heading(doc, "One lever at a time", level=1)
    add_para(
        doc,
        "Sensitivity analysis holds the Base assumptions constant and changes one major driver in a low and high direction. It measures materiality, not likelihood. A large bar means the lever can matter if the tested shock occurs; it does not say the shock is probable.",
    )
    add_figure(
        doc,
        figures["sensitivity"],
        "Figure 15. Utilization and billing rate have the largest forecast-end cash effects among the tested one-at-a-time shocks.",
        alt_text="Horizontal tornado-style bars showing positive and negative June 2027 cash impacts for utilization, billing rate, salary cost, DSO, EUR/RON, attrition and capex shocks.",
    )
    sensitivity_rows = []
    for driver in sensitivity.sort_values("rank")["driver"].drop_duplicates():
        pair = sensitivity.loc[sensitivity["driver"].eq(driver)].set_index("direction")
        sensitivity_rows.append(
            (
                driver,
                f"{pair.loc['Low', 'shock']}: {fmt_eur(pair.loc['Low', 'year_end_cash_impact_eur'], 2)}",
                f"{pair.loc['High', 'shock']}: {fmt_eur(pair.loc['High', 'year_end_cash_impact_eur'], 2)}",
                f"{fmt_eur(max(abs(pair.loc['Low', 'ebitda_impact_eur']), abs(pair.loc['High', 'ebitda_impact_eur'])), 2)}",
            )
        )
    add_table(doc, ["Driver", "Low-shock cash impact", "High-shock cash impact", "Largest abs. EBITDA impact"], sensitivity_rows, [1800, 2780, 2780, 2000], font_size=8.4)
    add_callout(
        doc,
        "DSO lesson",
        "Ten days slower collections reduces forecast-end cash by about EUR 1.43m and minimum cash by about EUR 1.15m, while EBITDA is unchanged. Capex behaves similarly: it changes cash but not EBITDA. These separations are important economic invariants in the test suite.",
        tone="teal",
    )

    add_heading(doc, "Deterministic versus probabilistic analysis", level=2)
    comparison_rows = [
        ("Scenario", "A coherent named management story", "What if expansion, risk or mitigation assumptions occur together?", "No"),
        ("Sensitivity", "One lever is changed at a time", "Which tested lever has the largest financial effect?", "No"),
        ("Monte Carlo", "Multiple uncertain drivers vary together", "What distribution and breach frequency arise under stated distributions?", "Yes"),
    ]
    add_table(doc, ["Method", "Mechanism", "Question answered", "Probability output"], comparison_rows, [1700, 2700, 3760, 1200], font_size=8.7)

    add_heading(doc, "The rule-based insight narrator", level=2)
    add_para(
        doc,
        "NovaPlan's insight layer is deliberately transparent. It is not a language model and does not create a new forecast. It reads scenario, sensitivity and Monte Carlo outputs, applies fixed rules, removes duplicates and returns a short set of observations. A current example would note that expansion is EBITDA-accretive but reduces minimum cash during ramp-up, that liquidity stays above the selected floor and that the P5 forecast-end cash outcome is approximately EUR 26.45m.",
    )
    add_callout(
        doc,
        "Why rules matter",
        "A rule-based narrator is easy to audit: every sentence can be traced to a model field and threshold. The trade-off is that it cannot reason beyond the rules or understand context that is not encoded.",
        tone="blue",
    )

    add_section_kicker(doc, "10 | Experience and governance")
    add_heading(doc, "The dashboard is organized by management question", level=1)
    page_rows = [
        ("Overview", "What is happening now?", "Actual KPI cards, trends, cash bridge and narrative"),
        ("Rolling Forecast", "Where are we heading over 18 months?", "Model baseline, management overlay and final forecast"),
        ("Scenario Lab", "What if assumptions change together?", "Named presets, custom levers and comparison deltas"),
        ("Workforce", "What does hiring cost and when does it pay back?", "Headcount, ramped FTE, salary, contribution and payback"),
        ("Liquidity", "Can we pay obligations during the next 13 weeks?", "Direct receipts/disbursements, low week and funding need"),
        ("Monte Carlo", "How wide is the risk distribution?", "Confidence fan, histogram, breach probability and driver ranking"),
        ("Diagnostics", "Which algorithm forecasts each metric best?", "Walk-forward MAE, RMSE, WAPE and directional accuracy"),
        ("Data & Assumptions", "Where did the values come from?", "Dataset register, planning parameters and audit entries"),
        ("Learning Guide", "What does each control and metric mean?", "Plain-language concepts, formulas, examples and glossary"),
    ]
    add_table(doc, ["Page", "Management question", "Teaching content"], page_rows, [1900, 3400, 4060], font_size=8.5)

    add_heading(doc, "Four kinds of information", level=2)
    provenance_rows = [
        ("Observed synthetic actual", "Generated historical record", "Revenue for December 2025"),
        ("Calculated value", "Deterministic formula applied to inputs", "EBITDA, DSO or cash roll-forward"),
        ("Management assumption", "Human-selected planning input", "Rate increase, DSO change or hiring schedule"),
        ("Model estimate", "Forecast or simulated outcome", "June 2027 cash or Monte Carlo P5"),
    ]
    add_table(doc, ["Information type", "Meaning", "Example"], provenance_rows, [2300, 3600, 3460], font_size=8.8)
    add_para(
        doc,
        "Separating these types prevents a common planning problem: human judgment can otherwise disappear inside a model output and look more objective than it is. NovaPlan keeps the baseline visible next to the adjustment and asks for a rationale when a scenario is saved.",
    )

    add_heading(doc, "Audit trail and current boundary", level=2)
    audit_id = create_numbering(doc, "bullet")
    for item in (
        "Each saved nonzero scenario lever can create an audit entry with UTC timestamp, scenario, variable, old value, new value, user and rationale.",
        "The file-backed log is append-oriented and shown newest first; baseline data remains separate from the scenario overlay.",
        "The current user is the fixed label Demo User. There is no authentication, approval workflow, immutable storage, digital signature, complete version snapshot or scenario replay.",
        "The audit CSV can be edited outside the application, so it is an educational record rather than a production-grade control.",
    ):
        add_list_item(doc, item, audit_id)
    add_callout(
        doc,
        "Governance principle",
        "A model result is useful only when a reader can identify its input data, formula, assumption owner, adjustment rationale, version and validation status.",
        tone="teal",
    )

    add_section_kicker(doc, "11 | Validation and roadmap")
    add_heading(doc, "What has been verified", level=1)
    validation_rows = [
        ("Economic invariants", "Rate and utilization changes move revenue in the expected direction; DSO affects cash/AR rather than EBITDA; capex affects cash rather than EBITDA"),
        ("Workforce economics", "Hiring cost, ramp, salary pressure, contribution, payback and expansion propagation"),
        ("Statement integrity", "Balance-sheet and cash identities reconcile within tolerance"),
        ("Direct cash", "Weekly cash closes from opening cash plus collections less disbursements"),
        ("Forecast governance", "Baseline, adjustment and final fields remain distinguishable"),
        ("Monte Carlo", "Same seed reproduces the same arrays and summary; a different seed changes outcomes"),
        ("Synthetic generator", "Seeded data is deterministic and invoices, revenue, AR and cash reconcile"),
        ("Application integration", "All routes and primary callbacks load; the automated suite contains 33 passing tests"),
    ]
    add_table(doc, ["Control area", "Verified behavior"], validation_rows, [2400, 6960], font_size=8.7)

    add_heading(doc, "Known limitations", level=2)
    limits_id = create_numbering(doc, "bullet")
    for item in (
        "Synthetic observations cannot establish real-world forecast performance or prove causal coefficients.",
        "One company and 72 monthly observations provide limited statistical power, especially for nonlinear algorithms and extreme tails.",
        "The customer population is static; there is no churn, acquisition, renegotiation or credit migration. Backlog is aggregate rather than contract-level.",
        "The employee dataset is an active snapshot without leaver history, timesheets, promotions or project assignments. The generated 40-hire plan contains 12 Junior, 18 Mid and 10 Senior hires and no Managers because small monthly-cohort rounding removes the intended Manager allocation.",
        "Accounts payable is derived from a DPO target rather than vendor invoices. Weekly historical cash is allocated from monthly totals and is not bank-statement evidence.",
        "Tax, interest and distributions are simplified educational mechanics, not Romanian accounting or tax guidance.",
        "The historical period does not contain a severe EUR 3m-floor breach, limiting direct evidence about financial distress.",
        "The default Monte Carlo wraps the Base forecast. It does not automatically simulate the selected 40-hire scenario through the page, although forecast overrides can do so programmatically.",
        "The full statement engine and lighter interactive planner are separate implementations. A generic page-level metric overlay does not propagate across all statements.",
    ):
        add_list_item(doc, item, limits_id)

    add_heading(doc, "Source-of-truth issues to resolve", level=2)
    source_rows = [
        ("Scenario presets", "Runtime values are hard-coded in models/scenarios.py; config/scenarios.yaml is unused and differs", "Make one validated scenario registry and load it everywhere"),
        ("Assumptions", "config/assumptions.yaml governs history generation, while planning defaults are duplicated in model/page code", "Create a typed, versioned registry with clearly separated scopes"),
        ("People cost labels", "Historical on-cost/bonuses and proposed-hire defaults differ but the UI can appear global", "Label history, planning and proposal values explicitly"),
        ("Weekly date schema", "The data access registry names week while the CSV contains week_start and week_end", "Validate schema at load time and generate a data contract"),
        ("Reproducibility", "Seeded results also depend on input/code/package versions", "Archive data hash, code commit and lockfile with every published run"),
    ]
    add_table(doc, ["Area", "Current state", "Production-strength improvement"], source_rows, [1900, 4000, 3460], font_size=8.3)

    add_heading(doc, "Practical roadmap", level=2)
    roadmap_id = create_numbering(doc, "number")
    for item in (
        "Unify assumptions and scenarios into one typed source of truth with effective dates, owners and version identifiers.",
        "Replace CSV audit storage with authenticated users, immutable event history, approvals and reproducible scenario snapshots.",
        "Connect actual ERP, time-sheet, CRM, payroll and bank data through governed ingestion and reconciliation controls.",
        "Calibrate forecast and Monte Carlo distributions from real residuals, stress periods and business-owner ranges; backtest interval coverage as well as point accuracy.",
        "Unify the full statement engine and the interactive planner so every management overlay propagates consistently through all dependent lines.",
        "Add portfolio/customer/project concentration, debt facilities, covenant testing, tax schedules and scenario-specific Monte Carlo runs.",
    ):
        add_list_item(doc, item, roadmap_id)

    add_heading(doc, "Conclusion", level=1)
    add_para(
        doc,
        "NovaPlan demonstrates how a dashboard can become teaching material rather than a decorative reporting layer. Its strongest idea is the continuity of the model: operating choices create capacity, capacity creates revenue, profitability is converted into cash through working capital, and uncertainty is applied to the same drivers before liquidity is summarized. The result is explainable enough for a beginner and structured enough to support serious discussion about hiring, pricing, collections and risk.",
    )
    add_para(
        doc,
        "The synthetic Base position is comfortable, so the 40-hire expansion is not a rescue decision. It is a controlled trade-off: incremental payroll and onboarding arrive before full productivity, while DSO determines how quickly earned value becomes cash. The Mitigation case shows that pacing hiring, protecting collections and making a modest price adjustment can improve both economics and liquidity. In a real deployment, these conclusions would need real data, calibrated assumptions and production-grade governance.",
    )

    add_section_kicker(doc, "Appendix A")
    add_heading(doc, "Selected implementation map", level=1)
    implementation_rows = [
        ("Synthetic company", "synthetic/generate_company.py", "Customers, workforce, monthly causal history, invoices, OPEX, capex and weekly cash"),
        ("Generator assumptions", "config/assumptions.yaml", "Historical synthetic-data contract only"),
        ("Revenue drivers", "models/driver_tree.py; models/revenue.py", "Capacity, hours, rates, realization, backlog and contractor revenue"),
        ("Workforce", "models/workforce.py", "Roll-forward, ramp, proposed-hire economics and hiring-plan simulation"),
        ("Working capital", "models/working_capital.py", "AR, AP, DSO, DPO and invoice collection timing"),
        ("Statements", "models/statements.py", "Income statement, balance sheet, cash flow and reconciliation"),
        ("Monthly planner", "models/forecast.py", "18-month driver-based forecast and management revenue adjustment"),
        ("Weekly liquidity", "models/cashflow.py", "13-week direct cash forecast and controls"),
        ("Scenarios", "models/scenarios.py", "Executable scenario library and Base deltas"),
        ("Sensitivity", "models/sensitivity.py", "One-at-a-time driver shocks"),
        ("Algorithms", "forecasting/models.py; forecasting/validation.py", "Four benchmarks and chronological walk-forward validation"),
        ("Monte Carlo", "models/monte_carlo.py", "Correlated driver sampling, cash paths and risk summaries"),
        ("Insights and audit", "models/insights.py; components/audit.py", "Rule-based narration and file-backed rationale log"),
        ("Teaching UI", "pages/*.py; components/metric_guide.py", "Nine management/learning pages and metric explanations"),
        ("Validation", "tests/*.py", "Economic invariants, reconciliation and reproducibility checks"),
    ]
    add_table(doc, ["Capability", "Primary source", "Role"], implementation_rows, [1900, 3000, 4460], font_size=8.0)

    add_heading(doc, "Dataset ranges at the cut-off", level=2)
    range_rows = [
        ("Headcount", f"{monthly.headcount.min():.0f}-{monthly.headcount.max():.0f}", "People"),
        ("Billable share", f"{monthly.billable_share.min() * 100:.1f}%-{monthly.billable_share.max() * 100:.1f}%", "Workforce mix"),
        ("Utilization", f"{monthly.utilization.min() * 100:.2f}%-{monthly.utilization.max() * 100:.2f}%", "Capacity use"),
        ("Billing rate", f"EUR {monthly.billing_rate_eur.min():.2f}-EUR {monthly.billing_rate_eur.max():.2f}", "Price/hour"),
        ("Realization", f"{monthly.realization_rate.min() * 100:.2f}%-{monthly.realization_rate.max() * 100:.2f}%", "Value retention"),
        ("Monthly revenue", f"{fmt_eur(monthly.revenue_eur.min(), 2)}-{fmt_eur(monthly.revenue_eur.max(), 2)}", "Recognized value"),
        ("EBITDA margin", f"{monthly.ebitda_margin.min() * 100:.2f}%-{monthly.ebitda_margin.max() * 100:.2f}%", "Profitability"),
        ("DSO", f"{monthly.dso.min():.2f}-{monthly.dso.max():.2f} days", "Collection timing"),
        ("DPO", f"{monthly.dpo.min():.2f}-{monthly.dpo.max():.2f} days", "Supplier timing"),
        ("Closing cash", f"{fmt_eur(monthly.closing_cash_eur.min(), 2)}-{fmt_eur(monthly.closing_cash_eur.max(), 2)}", "Liquidity"),
        ("EUR/RON", f"{monthly.eur_ron.min():.4f}-{monthly.eur_ron.max():.4f}", "Synthetic FX path"),
    ]
    add_table(doc, ["Metric", "Observed synthetic range", "Meaning"], range_rows, [2700, 3300, 3360], font_size=8.8)

    add_section_kicker(doc, "Appendix B")
    add_heading(doc, "Assumption register by scope", level=1)
    assumption_rows = [
        ("Historical generator", "Random seed", "42", "Recreates the fictional actual history"),
        ("Historical generator", "Opening headcount / cash", "272 / EUR 4.70m", "Starting position in Jan 2020"),
        ("Historical generator", "On-cost / benefits", "2.25% / EUR 205 monthly", "Generated employee cost"),
        ("Historical generator", "Base realization", "96.5%", "Commercial value retained"),
        ("Historical generator", "Base DPO", "37 days", "Supplier timing anchor"),
        ("Historical generator", "Corporate tax", "16% simplified", "Educational tax mechanic"),
        ("Monthly planner", "Horizon", "18 months", "Jan 2026-Jun 2027"),
        ("Monthly planner", "Demand / rate growth", "5% / 3% annual", "Base growth assumptions"),
        ("Monthly planner", "Salary / other OPEX inflation", "6% / 3.5% annual", "Base cost assumptions"),
        ("Monthly planner", "Utilization bounds", "55%-90%", "Planning guardrails"),
        ("Liquidity", "Horizon / floor", "13 weeks / EUR 3m", "Near-term cash policy"),
        ("Proposed hire", "On-cost / bonus", "8% / 8%", "Interactive proposal defaults"),
        ("Monte Carlo", "Runs / seed", "10,000 / 42", "Default reproducible simulation"),
        ("Monte Carlo", "Margin target", "10%", "Aggregate EBITDA risk threshold"),
    ]
    add_table(doc, ["Scope", "Parameter", "Value", "Use"], assumption_rows, [2100, 2600, 1900, 2760], font_size=8.4)
    add_callout(
        doc,
        "Important",
        "An assumption has meaning only inside its scope. The historical generator parameters describe how the fictional past was built; they are not automatically the defaults used by every interactive model.",
        tone="amber",
    )

    add_heading(doc, "Core identities", level=2)
    formula_rows = [
        ("Workforce", "Ending HC = Beginning HC + Hires - Attrition"),
        ("Capacity", "HC x Billable share x Working days x Hours/day"),
        ("Billable hours", "Capacity x Utilization"),
        ("Core revenue", "Billable hours x Rate x Realization x Service mix"),
        ("EBITDA", "Revenue - Payroll - Contractors - Other OPEX"),
        ("EBIT", "EBITDA - Depreciation"),
        ("Net income", "EBIT - Interest - Tax"),
        ("AR roll-forward", "Beginning AR + Invoices - Collections - Write-offs = Ending AR"),
        ("AP roll-forward", "Beginning AP + Vendor expense - Vendor payments = Ending AP"),
        ("OCF", "Net income + non-cash items - Change in operating assets + Change in operating liabilities"),
        ("FCF", "OCF - Capex"),
        ("Cash", "Opening cash + Operating + Investing + Financing cash flow = Closing cash"),
    ]
    add_table(doc, ["Area", "Identity"], formula_rows, [2200, 7160], font_size=8.7)

    add_section_kicker(doc, "Appendix C")
    add_heading(doc, "Monte Carlo reproduction record", level=1)
    reproduction_rows = [
        ("Input", "data/monthly_kpis.csv"),
        ("History through", "December 2025"),
        ("Input SHA-256", "CB387AFAC7B585D1873B661A957671CE40EDC035BD3FA01A841B327ADAC0A436"),
        ("Forecast horizon", "18 months: January 2026-June 2027"),
        ("Simulations", "10,000"),
        ("Seed / bit generator", "42 / PCG64"),
        ("Liquidity floor", "EUR 3,000,000"),
        ("Aggregate EBITDA margin target", "10%"),
        ("Forecast overrides", "None; Base forecast"),
        ("Python / NumPy", "Python 3.12.13 / NumPy 2.3.5 for published figures"),
    ]
    add_table(doc, ["Field", "Published run"], reproduction_rows, [3000, 6360], font_size=8.8)
    add_para(
        doc,
        "For exact publication reproducibility, archive the input hash, code commit, package lock and model parameters with the output. The broad version ranges in a requirements file are useful for installation but are not a bitwise reproducibility lock.",
    )

    add_heading(doc, "Disclaimer", level=1)
    add_callout(
        doc,
        "Educational use only",
        "NovaPlan is an educational proof-of-concept built using entirely synthetic data. It is not an official Deloitte product, does not represent Deloitte proprietary methodologies, and should not be used as financial, tax, accounting, or investment advice.",
        tone="red",
    )
    add_para(
        doc,
        "Version 0.1 is intentionally a starting white paper. It documents the executable behavior and current model boundaries as of 12 August 2026 so future versions can distinguish improvements in data, methods, governance and user experience.",
        color=MUTED,
        italic=True,
    )

    for section in doc.sections:
        configure_page(section)
    DOCX_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(DOCX_PATH)
    return DOCX_PATH


def main() -> None:
    analytics = collect_analytics()
    figures = build_figures(analytics)
    path = build_document(analytics, figures)
    print(f"Created {path}")
    print(f"Generated {len(figures)} publication figures in {FIG_DIR}")


if __name__ == "__main__":
    main()
