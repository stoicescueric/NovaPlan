"""Create the visually verified PDF edition of the NovaPlan student report."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

import build_student_report as student
import build_whitepaper as wp


OUTPUT_DIR = wp.ROOT / "output" / "pdf"
OUTPUT_PATH = OUTPUT_DIR / "NovaPlan_Student_Internship_Report.pdf"

INK = colors.HexColor("#17252B")
INK_SOFT = colors.HexColor("#33454C")
MUTED = colors.HexColor("#6B7780")
TEAL = colors.HexColor("#16706F")
TEAL_SOFT = colors.HexColor("#E7F2F0")
BLUE = colors.HexColor("#56759A")
BLUE_SOFT = colors.HexColor("#EEF3F7")
AMBER = colors.HexColor("#C7893B")
AMBER_SOFT = colors.HexColor("#FBF1DF")
RED = colors.HexColor("#C45A55")
RED_SOFT = colors.HexColor("#FAECEA")
GRID = colors.HexColor("#DDE5E2")
SURFACE_SOFT = colors.HexColor("#F7F9F8")


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "StudentBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.4,
            leading=14.2,
            textColor=INK,
            spaceAfter=7,
        ),
        "title": ParagraphStyle(
            "StudentTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=33,
            textColor=TEAL,
            alignment=TA_LEFT,
            spaceAfter=14,
        ),
        "subtitle": ParagraphStyle(
            "StudentSubtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=14,
            leading=19,
            textColor=INK_SOFT,
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "StudentH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#2E74B5"),
            spaceBefore=0,
            spaceAfter=10,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "StudentH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            textColor=colors.HexColor("#2E74B5"),
            spaceBefore=9,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "kicker": ParagraphStyle(
            "StudentKicker",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=AMBER,
            spaceAfter=4,
        ),
        "caption": ParagraphStyle(
            "StudentCaption",
            parent=base["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=8.3,
            leading=11,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceBefore=3,
            spaceAfter=8,
        ),
        "callout_label": ParagraphStyle(
            "StudentCalloutLabel",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=TEAL,
            spaceAfter=2,
        ),
        "callout_body": ParagraphStyle(
            "StudentCalloutBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.7,
            leading=13,
            textColor=INK_SOFT,
        ),
        "small": ParagraphStyle(
            "StudentSmall",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=MUTED,
        ),
        "formula": ParagraphStyle(
            "StudentFormula",
            parent=base["BodyText"],
            fontName="Courier-Bold",
            fontSize=9.4,
            leading=13,
            textColor=TEAL,
        ),
    }


STYLES = styles()


def on_page(canvas, document) -> None:
    page = canvas.getPageNumber()
    if page == 1:
        return
    canvas.saveState()
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.5)
    canvas.line(inch, 10.42 * inch, 7.5 * inch, 10.42 * inch)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(inch, 10.55 * inch, "NOVAPLAN | STUDENT INTERNSHIP REPORT")
    canvas.drawRightString(7.5 * inch, 10.55 * inch, "15-PAGE EDITION | AUGUST 2026")
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(inch, 0.55 * inch, "Fictional data | Educational project")
    canvas.drawRightString(7.5 * inch, 0.55 * inch, f"Page {page}")
    canvas.restoreState()


def p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[style])


def heading(story: list, number: int, kicker: str, title: str) -> None:
    story.extend([p(f"{number} | {kicker.upper()}", "kicker"), p(title, "h1")])


def h2(story: list, text: str) -> None:
    story.append(p(text, "h2"))


def callout(label: str, text: str, tone: str = "teal") -> Table:
    fills = {"teal": TEAL_SOFT, "blue": BLUE_SOFT, "amber": AMBER_SOFT, "red": RED_SOFT}
    label_colors = {"teal": TEAL, "blue": BLUE, "amber": AMBER, "red": RED}
    table = Table(
        [[Paragraph(label.upper(), ParagraphStyle("CalloutLabel", parent=STYLES["callout_label"], textColor=label_colors[tone])), p(text, "callout_body")]],
        colWidths=[1.2 * inch, 5.05 * inch],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fills[tone]),
                ("BOX", (0, 0), (-1, -1), 0.5, label_colors[tone]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def figure(path: Path, caption: str, width: float = 5.65) -> KeepTogether:
    img = Image(str(path), width=width * inch, height=width * 9 / 16 * inch)
    img.hAlign = "CENTER"
    return KeepTogether([img, p(caption, "caption")])


def data_table(headers: list[str], rows: list[tuple], widths: list[float], font_size: float = 8.8) -> Table:
    header_style = ParagraphStyle("TableHeader", parent=STYLES["small"], fontName="Helvetica-Bold", fontSize=font_size, leading=font_size + 2, textColor=INK)
    cell_style = ParagraphStyle("TableCell", parent=STYLES["small"], fontSize=font_size, leading=font_size + 2.5, textColor=INK_SOFT)
    data = [[Paragraph(str(value), header_style) for value in headers]]
    data.extend([[Paragraph(str(value), cell_style) for value in row] for row in rows])
    table = Table(data, colWidths=[value * inch for value in widths], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), TEAL_SOFT),
                ("GRID", (0, 0), (-1, -1), 0.35, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def formula(text: str) -> Table:
    table = Table([[p(text, "formula")]], colWidths=[6.25 * inch], hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SURFACE_SOFT), ("BOX", (0, 0), (-1, -1), 0.4, GRID), ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return table


def bullet_list(items: tuple[str, ...], numbered: bool = False) -> ListFlowable:
    options = {
        "bulletType": "1" if numbered else "bullet",
        "leftIndent": 24,
        "bulletFontName": "Helvetica",
        "bulletFontSize": 9,
        "spaceAfter": 6,
    }
    if numbered:
        options["start"] = 1
    else:
        # An ASCII dash is reliable in every PDF viewer and avoids a missing
        # Symbol-font fallback on Windows.
        options["bulletChar"] = "-"
    return ListFlowable([ListItem(p(item)) for item in items], **options)


def build_pdf() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    analytics = wp.collect_analytics()
    results = student.build_live_results(analytics)
    figures = student.build_student_figures(analytics, results)
    annual = analytics["annual"]
    liquidity = analytics["liquidity"]
    latest = annual.iloc[-1]
    base = results["base"]["summary"]
    hire = results["hire_40"]["summary"]

    document = BaseDocTemplate(
        str(OUTPUT_PATH),
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=0.85 * inch,
        bottomMargin=0.78 * inch,
        title="NovaPlan: Student Internship Project",
        author="NovaPlan student project",
        subject="Plain-language report about business planning, cash and Monte Carlo",
    )
    frame = Frame(document.leftMargin, document.bottomMargin, document.width, document.height, id="student-frame")
    document.addPageTemplates([PageTemplate(id="student-pages", frames=[frame], onPage=on_page)])
    story: list = []

    # 1. Cover
    story.extend(
        [
            Spacer(1, 0.75 * inch),
            p("STUDENT INTERNSHIP-STYLE RESEARCH PROJECT", "kicker"),
            p("How can a consulting company grow without running short of cash?", "title"),
            p("A practical dashboard project using a fictional company, simple financial formulas and tested what-if experiments.", "subtitle"),
            callout("The experiment", "I tested what happens when the company hires 40 people, customers pay later, utilization changes, or the future becomes more uncertain."),
            Spacer(1, 0.55 * inch),
            p("<b>NovaBridge Digital SRL</b> | Fictional Romanian consulting company | EUR", "small"),
            p("Prepared in August 2026 | 15-page student edition", "small"),
            Spacer(1, 0.8 * inch),
            p("All people, companies, invoices and results in this report are synthetic.", "small"),
            PageBreak(),
        ]
    )

    # 2. Why
    heading(story, 1, "Why I chose this topic", "A simple business problem with a cash timing twist")
    story.extend(
        [
            p("A consulting company pays salaries every month, but customers often pay invoices several weeks after the work is completed. Hiring can increase future revenue, yet salaries start before every employee is fully productive. Growth is therefore a cash question as well as a profit question."),
            callout("Research question", "Can the fictional company hire 40 people, earn more profit and still keep a comfortable cash balance while the new team ramps up?", "blue"),
        ]
    )
    h2(story, "My three goals")
    story.append(bullet_list(("Understand revenue, operating profit and cash.", "Build a dashboard where a beginner can change assumptions and see a result.", "Test the model so a control cannot look useful while doing nothing."), numbered=True))
    h2(story, "The practical idea")
    story.append(p("I treated the dashboard as a small laboratory. Each page asks a question, lets the user change a few inputs, and explains what moved and why. The aim is learning, not pretending that fictional numbers are a real forecast."))
    story.append(PageBreak())

    # 3. What I built
    heading(story, 2, "What I built", "One project from data to conclusion")
    story.append(figure(figures["flow"], "Figure 1. The project follows five steps instead of presenting many unrelated charts.", 5.8))
    story.append(data_table(["Dashboard page", "Question"], [("Project Overview", "What problem am I studying?"), ("What-if Experiment", "What changes if I hire, sell more time, raise price or wait longer for cash?"), ("13-Week Cash Check", "Will the business have enough cash soon?"), ("Risk Simulation", "What range appears when the future is uncertain?"), ("How It Works", "Where do the data, formulas and tests come from?")], [1.75, 4.75], 8.7))
    story.append(PageBreak())

    # 4. Data
    heading(story, 3, "The fictional data", "Useful for learning, safe for a student project")
    story.append(p("Synthetic data is invented data made to follow selected rules. It lets me show invoices, salaries and cash movements without using confidential company or client information. Seed 42 makes the fictional history repeatable."))
    story.append(figure(figures["data"], "Figure 2. Four understandable data groups support the main story.", 5.65))
    story.append(callout("A useful rule", "The data is invented, but it must still add up: invoices match revenue, unpaid invoices become receivables, and opening cash plus cash movement equals closing cash.", "amber"))
    story.append(PageBreak())

    # 5. History
    heading(story, 4, "The company story", "Six years of growth, pressure and recovery")
    story.append(figure(figures["history"], "Figure 3. Revenue, operating profit and closing cash tell different parts of the 2020-2025 story.", 5.75))
    story.append(data_table(["2025 result", "Value", "Plain meaning"], [("Revenue", wp.fmt_eur(latest.revenue_eur, 1), "Services delivered"), ("Operating profit", wp.fmt_eur(latest.ebitda_eur, 1), "Revenue left after main operating costs"), ("Profit margin", f"{latest.ebitda_margin * 100:.1f}%", "Operating profit divided by revenue"), ("Closing cash", wp.fmt_eur(latest.closing_cash_eur, 1), "Money available at year end")], [1.45, 1.35, 3.7], 8.7))
    story.append(p("The company starts the forecast with a strong cash balance. This project is about funding growth, not rescuing a failing business."))
    story.append(PageBreak())

    # 6. Three numbers
    heading(story, 5, "Three important numbers", "Revenue, operating profit and cash are not the same")
    story.append(data_table(["Number", "Beginner definition", "Small example"], [("Revenue", "Value of work completed", "EUR 100 of work -> EUR 100 revenue"), ("Operating profit", "Revenue minus main operating costs", "EUR 100 - EUR 75 -> EUR 25 profit"), ("Cash", "Money received and still available", "An unpaid invoice is not cash yet")], [1.35, 2.55, 2.6], 8.8))
    story.extend([Spacer(1, 8), formula("Operating profit = Revenue - Payroll - Contractor cost - Other operating cost"), Spacer(1, 7), formula("Closing cash = Opening cash + Cash collected - Cash paid"), Spacer(1, 9), callout("The key lesson", "A profitable month can still use cash when customers have not paid yet, salaries are due now, or the company buys equipment.")])
    h2(story, "Why the dashboard shows all three")
    story.append(p("Revenue explains business activity. Operating profit explains whether the work covers operating costs. Cash explains whether bills can be paid on time. Looking at only one gives an incomplete answer."))
    story.append(PageBreak())

    # 7. Revenue
    heading(story, 6, "How the company makes money", "People and productive time create service revenue")
    story.append(figure(figures["driver_tree"], "Figure 4. The revenue formula is a chain of understandable inputs.", 5.55))
    story.append(formula("Revenue = Employees x Billable share x Available hours x Utilization x Hourly rate"))
    h2(story, "A worked example")
    story.append(p("Suppose 100 employees include 80 billable consultants. At 160 available hours, 75% utilization and EUR 75 per hour, the simple monthly estimate is 80 x 160 x 75% x EUR 75 = EUR 720,000 before discounts or other adjustments."))
    story.append(callout("Why utilization matters", "Hiring creates capacity, but capacity produces revenue only when customers buy the available time. New people do not create full revenue immediately.", "blue"))
    story.append(PageBreak())

    # 8. Profit and cash
    heading(story, 7, "Why profit is not cash", "Customer payment time creates the gap")
    story.append(figure(figures["working_capital"], "Figure 5. Revenue is recorded before cash when the customer pays later.", 5.45))
    story.append(data_table(["Term", "Plain meaning"], [("Invoice", "A request for payment after work is delivered"), ("Customer payment time", "How long the company waits to collect"), ("Accounts receivable", "Invoices customers still owe"), ("Cash collection", "The moment money reaches the company")], [2.0, 4.5], 9.0))
    story.append(callout("Experiment rule", "Making customers pay 15 days later should reduce near-term cash, but not revenue or operating profit already earned.", "amber"))
    story.append(PageBreak())

    # 9. Forecast
    heading(story, 8, "The starting forecast", "Two time horizons answer two questions")
    story.append(data_table(["Forecast", "Question"], [("13 weeks", "Can the company pay near-term salaries, suppliers, taxes and one-time bills?"), ("18 months", "How do hiring, utilization, prices and payments affect profit and cash?")], [1.4, 5.1], 9.0))
    story.append(Spacer(1, 6))
    story.append(figure(figures["liquidity"], "Figure 6. The weekly chart is zoomed so the cash movement is visible.", 5.55))
    story.append(data_table(["Cash check", "Result"], [("Opening cash", wp.fmt_eur(liquidity["opening_cash_eur"].iloc[0], 1)), ("Lowest weekly cash", wp.fmt_eur(liquidity["closing_cash_eur"].min(), 1)), ("Cash after 13 weeks", wp.fmt_eur(liquidity["closing_cash_eur"].iloc[-1], 1))], [3.2, 3.3], 9.1))
    story.append(PageBreak())

    # 10. Hiring
    heading(story, 9, "Experiment 1", "What happens if the company hires 40 people?")
    story.append(figure(figures["hiring"], "Figure 7. The report and dashboard use the same pure 40-hire experiment.", 5.65))
    revenue_change = hire["revenue_eur"] - base["revenue_eur"]
    profit_change = hire["ebitda_eur"] - base["ebitda_eur"]
    minimum_change = hire["minimum_cash_eur"] - base["minimum_cash_eur"]
    story.append(data_table(["What changed", "Result versus Base"], [("Revenue", wp.fmt_eur(revenue_change, 1)), ("Operating profit", wp.fmt_eur(profit_change, 1)), ("Lowest cash point", wp.fmt_eur(minimum_change, 1)), ("Employees at the end", f"{hire['headcount']:.0f}")], [3.0, 3.5], 9.0))
    story.append(callout("What I learned", "Hiring improves revenue and profit over 18 months, while the lowest cash point is slightly lower during ramp-up. This is a timing trade-off, not a simple good-or-bad answer."))
    story.append(PageBreak())

    # 11. Four controls
    heading(story, 10, "Experiment 2", "Which dashboard input changes cash the most?")
    story.append(figure(figures["experiments"], "Figure 8. The four student-facing controls produce different end-of-horizon cash effects.", 5.6))
    rows = []
    for name, scenario in results["experiments"].items():
        summary = scenario["summary"]
        rows.append((name, wp.fmt_eur(summary["year_end_cash_eur"] - base["year_end_cash_eur"], 1), wp.fmt_eur(summary["ebitda_eur"] - base["ebitda_eur"], 1)))
    story.append(data_table(["Experiment", "Cash impact", "Profit impact"], rows, [2.8, 1.85, 1.85], 8.7))
    story.append(callout("Payment-time check", "Slower payment changes cash but leaves operating profit unchanged. This proves the model separates earning revenue from collecting it.", "blue"))
    story.append(PageBreak())

    # 12. Forecast methods
    heading(story, 11, "A small forecasting comparison", "Two simple ways to estimate next month")
    story.append(p("The financial plan uses business assumptions. I also compared two small forecasting ideas. Months stay in order so the model never learns from a future month before predicting it."))
    story.append(figure(figures["walk_forward"], "Figure 9. Walk-forward testing uses past months to predict the next month.", 5.35))
    story.append(data_table(["Method", "How it works", "Average revenue error"], [("Seasonal repeat", "Use the same month one year earlier", "About EUR 330k"), ("Simple driver regression", "Use a straight-line relationship with planned drivers", "About EUR 183k")], [1.65, 3.25, 1.6], 8.8))
    story.append(callout("Honest limit", "The regression assumes its driver values are already known or planned. It is a useful comparison, not an automatic forecast of the whole company.", "amber"))
    story.append(PageBreak())

    # 13. Monte Carlo
    heading(story, 12, "Monte Carlo", "A range of possible futures instead of one answer")
    story.append(p("A normal forecast gives one answer. Monte Carlo repeats the forecast while utilization, customer payment time, prices and salary costs move by small random amounts. Revenue, profit and cash are recalculated in every run."))
    story.append(figure(figures["mc_flow"], "Figure 10. The calculation stays understandable even when repeated 5,000 times.", 5.65))
    story.append(data_table(["Result", "Plain meaning"], [("Low result (P5)", "Only about 5% of ending cash results are lower"), ("Middle result (P50)", "Half are lower and half higher"), ("High result (P95)", "Only about 5% are higher")], [2.0, 4.5], 9.0))
    story.append(PageBreak())

    # 14. Monte Carlo test
    heading(story, 13, "Testing Monte Carlo", "The controls now produce visible and logical changes")
    story.append(figure(figures["mc_test"], "Figure 11. Zero uncertainty collapses the range; high uncertainty makes it much wider.", 5.45))
    mc_rows = []
    for label in ("0%", "100%", "200%"):
        summary = results["mc"][label]["summary"]
        width = summary["p95_year_end_cash_eur"] - summary["p5_year_end_cash_eur"]
        mc_rows.append((label, wp.fmt_eur(summary["p5_year_end_cash_eur"], 1), wp.fmt_eur(summary["median_year_end_cash_eur"], 1), wp.fmt_eur(summary["p95_year_end_cash_eur"], 1), wp.fmt_eur(width, 1)))
    story.append(data_table(["Uncertainty", "P5", "Middle", "P95", "Range"], mc_rows, [1.35, 1.25, 1.35, 1.25, 1.3], 8.5))
    low_p = results["mc_low_target"]["summary"]["probability_cash_below_threshold"] * 100
    high_p = results["mc_high_target"]["summary"]["probability_cash_below_threshold"] * 100
    story.append(callout("The bug I found and fixed", f"The old page exposed controls that did not change business risk. The revised uncertainty control widens the paths. At 200% uncertainty, a EUR 14m target gives {low_p:.1f}% below target and EUR 18m gives {high_p:.1f}%, while the cash paths stay the same.", "red"))
    story.append(PageBreak())

    # 15. Conclusion
    heading(story, 14, "What I learned", "A useful model is one that can be explained and tested")
    story.append(callout("Answer to the question", f"In this fictional Base case, the company can test a 40-person hiring plan without approaching the EUR 3m policy floor. The plan adds about {wp.fmt_eur(profit_change, 1)} of operating profit over 18 months, but salaries and customer payment timing still matter."))
    h2(story, "What I tested")
    story.append(bullet_list(("Revenue responds to utilization and billing rate.", "Slower payment reduces cash but not earned operating profit.", "Hiring includes salary cost and a gradual productivity ramp.", "The weekly cash roll-forward preserves receipts at forecast boundaries.", "Zero Monte Carlo uncertainty gives one path; more uncertainty widens the range.", "All 48 automated tests pass, every route loads, and the five main pages show no browser errors.")))
    h2(story, "Limitations")
    story.append(p("The data is fictional, the business rules are simplified, and the simulated ranges are assumptions rather than proven probabilities. A future version could compare forecasts with later actual results and let users change a few uncertainty drivers separately."))
    h2(story, "Final reflection")
    story.append(p("The most important lesson was not a complicated algorithm. It was connecting a business action to revenue, profit and cash, then proving that each control really reaches the calculation."))
    story.append(callout("Educational use only", "NovaPlan is an educational proof-of-concept built using entirely synthetic data. It is not an official Deloitte product, does not represent Deloitte proprietary methods, and is not financial, tax, accounting or investment advice.", "red"))

    document.build(story)
    return OUTPUT_PATH


def main() -> None:
    print(f"Created {build_pdf()}")


if __name__ == "__main__":
    main()
