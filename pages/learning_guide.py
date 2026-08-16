"""Plain-language learning centre for finance, planning, and model terminology."""

from __future__ import annotations

from collections import defaultdict

import dash
from dash import Input, Output, callback, dcc, html

from components.cards import status_pill
from components.learning import learning_guide, teaching_callout


dash.register_page(
    __name__,
    path="/learning-guide",
    name="Learning Guide",
    title="NovaPlan | Learning Guide",
)


TERMS = [
    # Operating drivers
    {
        "category": "1. Operating drivers",
        "term": "Headcount",
        "definition": "The total number of employees at a point in time, including billable consultants and support staff.",
        "why": "More people create more delivery capacity, but payroll rises immediately—even before new hires become productive.",
        "formula": "Ending headcount = Beginning headcount + Hires − Attrition",
        "example": "270 people + 8 hires − 3 leavers = 275 ending headcount.",
    },
    {
        "category": "1. Operating drivers",
        "term": "Billable headcount",
        "definition": "Employees whose time can be charged to customer projects.",
        "why": "A professional-services company earns most of its revenue from billable people, not total employees.",
        "formula": "Billable headcount = Headcount × Billable share",
        "example": "275 employees × 83% billable share ≈ 228 billable employees.",
    },
    {
        "category": "1. Operating drivers",
        "term": "Billable share",
        "definition": "The percentage of the workforce that can work on revenue-generating customer projects.",
        "why": "A lower share means more of payroll supports the business rather than directly producing billable work.",
        "formula": "Billable share = Billable headcount ÷ Total headcount",
        "example": "228 billable people ÷ 275 total people = 82.9%.",
    },
    {
        "category": "1. Operating drivers",
        "term": "Billable capacity hours",
        "definition": "The maximum project hours the billable workforce could theoretically deliver in a month.",
        "why": "This is the starting point of the revenue model before allowing for idle time, training, leave, or sales gaps.",
        "formula": "Headcount × Billable share × Working days × Hours per day",
        "example": "275 × 83% × 21 days × 8 hours ≈ 38,300 capacity hours.",
    },
    {
        "category": "1. Operating drivers",
        "term": "Utilization",
        "definition": "The percentage of available billable capacity that is actually used on customer work.",
        "why": "Utilization is usually the fastest profitability lever in a people-driven business: payroll is paid whether consultants are busy or not.",
        "formula": "Utilization = Billable hours ÷ Billable capacity hours",
        "example": "29,500 billable hours ÷ 38,300 available hours = 77% utilization.",
    },
    {
        "category": "1. Operating drivers",
        "term": "Working days",
        "definition": "Weekdays available in a month after weekends; holidays and leave effects are reflected indirectly in utilization.",
        "why": "February naturally has less revenue capacity than a long month if all other drivers stay the same.",
        "formula": "Calendar weekdays in the month",
        "example": "A month with 22 working days has roughly 10% more capacity than one with 20 days.",
    },
    {
        "category": "1. Operating drivers",
        "term": "Average billing rate",
        "definition": "The average hourly amount charged for delivered customer work, blended across roles and service lines.",
        "why": "Rate improvements can increase revenue without adding people, although aggressive pricing can sometimes reduce demand.",
        "formula": "Billed value ÷ Billable hours",
        "example": "€2.1m billed across 30,000 hours means an average rate of €70 per hour.",
    },
    {
        "category": "1. Operating drivers",
        "term": "Realization rate",
        "definition": "The share of standard billable value that becomes recognized revenue after discounts, write-downs, and commercial adjustments.",
        "why": "A high headline rate is less valuable if discounts or unapproved time prevent the business from realizing it.",
        "formula": "Recognized core revenue ÷ Standard billable value",
        "example": "€970k recognized from €1.0m of standard billable value = 97% realization.",
    },
    {
        "category": "1. Operating drivers",
        "term": "Backlog",
        "definition": "Contracted or highly committed customer work that has not yet been delivered and recognized as revenue.",
        "why": "Backlog provides demand visibility, but it is not revenue or cash until the work is delivered, invoiced, and collected.",
        "example": "A signed €900k project delivered over six months adds demand visibility, not €900k of immediate revenue.",
    },
    {
        "category": "1. Operating drivers",
        "term": "Attrition",
        "definition": "Employees leaving the company during a period.",
        "why": "Attrition reduces capacity and may create recruiting costs, but can temporarily lower payroll if departures are not replaced.",
        "formula": "Attrition rate = Leavers ÷ Average headcount",
        "example": "3 leavers from an average workforce of 275 in one month equals about 1.1% monthly attrition.",
    },
    # Profitability
    {
        "category": "2. Profitability",
        "term": "Revenue",
        "definition": "The value of services delivered to customers during the period. Revenue is recognized when work is performed—not when cash arrives.",
        "why": "Revenue measures commercial output, but it must be compared with cost and collections to understand profit and liquidity.",
        "formula": "Billable hours × Billing rate × Realization + other delivery effects",
        "example": "30,000 hours × €70 × 97% ≈ €2.04m of core services revenue.",
    },
    {
        "category": "2. Profitability",
        "term": "Payroll",
        "definition": "The recurring employer cost of employees, including salary and illustrative on-cost, benefits, and bonus assumptions.",
        "why": "Payroll is NovaBridge’s largest cost and is paid before customer invoices may be collected.",
        "example": "Hiring ahead of demand increases payroll immediately while revenue builds gradually during ramp-up.",
    },
    {
        "category": "2. Profitability",
        "term": "Operating expenses (OPEX)",
        "definition": "Day-to-day business costs such as cloud, software, travel, rent, insurance, and professional services.",
        "why": "Some OPEX changes with activity; other items remain fixed even when revenue falls.",
        "example": "Travel is partly discretionary, while office rent is relatively fixed in the short term.",
    },
    {
        "category": "2. Profitability",
        "term": "EBITDA",
        "definition": "Profit from normal operations before interest, tax, depreciation, and amortization.",
        "why": "EBITDA shows operating profitability, but it is not the same as cash because invoices may remain unpaid and capex still consumes cash.",
        "formula": "Revenue − Payroll − Contractor cost − Other OPEX",
        "example": "€2.0m revenue − €1.35m operating costs = €650k EBITDA.",
    },
    {
        "category": "2. Profitability",
        "term": "EBITDA margin",
        "definition": "The share of each euro of revenue left as EBITDA.",
        "why": "It allows profitability comparison across months or companies of different size.",
        "formula": "EBITDA ÷ Revenue",
        "example": "€400k EBITDA ÷ €2.0m revenue = 20% EBITDA margin.",
    },
    {
        "category": "2. Profitability",
        "term": "Capital expenditure (Capex)",
        "definition": "Cash spent on assets that provide value for more than one period, such as laptops or office improvements.",
        "why": "Capex reduces cash immediately but does not reduce EBITDA immediately; its cost enters profit gradually through depreciation.",
        "formula": "Planned asset purchases + New hires × Equipment cost",
        "example": "Ten new laptops at €1,800 each consume €18k of cash when purchased.",
    },
    {
        "category": "2. Profitability",
        "term": "Depreciation",
        "definition": "The accounting allocation of an asset’s cost across its useful life.",
        "why": "Depreciation reduces accounting profit below EBITDA but does not represent a new cash payment in that month.",
        "formula": "Asset cost ÷ Useful-life months (simplified straight line)",
        "example": "A €1,800 laptop over 36 months creates about €50 monthly depreciation.",
    },
    {
        "category": "2. Profitability",
        "term": "EBIT",
        "definition": "Earnings before interest and tax, after depreciation has been recognized.",
        "why": "EBIT includes the economic use of long-lived assets while remaining independent of financing choices and tax.",
        "formula": "EBITDA − Depreciation",
        "example": "€500k EBITDA − €40k depreciation = €460k EBIT.",
    },
    {
        "category": "2. Profitability",
        "term": "Net income",
        "definition": "Accounting profit remaining after operating costs, depreciation, interest, and tax.",
        "why": "Net income adds to retained earnings, but it still differs from cash flow because of working-capital timing and capex.",
        "formula": "EBIT − Interest − Tax",
        "example": "€460k EBIT − €10k interest − €72k tax = €378k net income.",
    },
    # Working capital and liquidity
    {
        "category": "3. Working capital & liquidity",
        "term": "Accounts receivable (AR)",
        "definition": "Customer invoices recognized as revenue but not yet collected in cash.",
        "why": "AR explains how revenue can increase while cash falls: the business has earned the money but customers have not paid yet.",
        "formula": "Beginning AR + Invoices − Collections − Write-offs = Ending AR",
        "example": "€3m opening AR + €2m invoices − €1.6m collections = €3.4m ending AR.",
    },
    {
        "category": "3. Working capital & liquidity",
        "term": "Days sales outstanding (DSO)",
        "definition": "An estimate of how many days of revenue are tied up in unpaid customer invoices.",
        "why": "Higher DSO usually means slower collections, more AR, and less near-term cash—without directly reducing recognized revenue.",
        "formula": "AR ÷ Monthly revenue × Average days in month",
        "example": "Moving from 50 to 65 DSO means roughly 15 extra days of sales remain uncollected.",
    },
    {
        "category": "3. Working capital & liquidity",
        "term": "Cash collections",
        "definition": "Cash actually received from customers during the period.",
        "why": "Collections fund payroll and suppliers. They may be lower or higher than revenue because invoices are paid later.",
        "formula": "Beginning AR + Invoices − Write-offs − Ending AR",
        "example": "Revenue can be €2m while collections are €1.5m if AR increases by €500k.",
    },
    {
        "category": "3. Working capital & liquidity",
        "term": "Accounts payable (AP)",
        "definition": "Supplier costs already incurred but not yet paid in cash.",
        "why": "Higher AP temporarily preserves cash, but it represents an obligation that must be settled later.",
        "formula": "Beginning AP + Vendor expenses − Vendor payments = Ending AP",
        "example": "Delaying €100k of valid supplier payments increases AP and temporarily increases cash by €100k.",
    },
    {
        "category": "3. Working capital & liquidity",
        "term": "Days payable outstanding (DPO)",
        "definition": "An estimate of how many days the company takes to pay suppliers.",
        "why": "Longer DPO can preserve cash, but excessive delays can damage supplier relationships or breach payment terms.",
        "formula": "AP ÷ Monthly vendor expenses × Average days in month",
        "example": "Increasing DPO from 30 to 40 days means supplier cash leaves about ten days later on average.",
    },
    {
        "category": "3. Working capital & liquidity",
        "term": "Operating cash flow",
        "definition": "Cash generated by normal business operations after working-capital movements and tax payments.",
        "why": "It connects operating profit to actual cash generation.",
        "formula": "EBITDA − Tax − Increase in AR + Increase in AP (simplified)",
        "example": "€500k EBITDA can become €100k operating cash flow if AR rises by €400k.",
    },
    {
        "category": "3. Working capital & liquidity",
        "term": "Free cash flow",
        "definition": "Cash left after normal operations and capital expenditure.",
        "why": "Free cash flow is available to build cash reserves, repay debt, or fund growth.",
        "formula": "Operating cash flow − Capex",
        "example": "€300k operating cash flow − €80k capex = €220k free cash flow.",
    },
    {
        "category": "3. Working capital & liquidity",
        "term": "Closing cash",
        "definition": "Cash available at the end of a week or month after all modeled inflows and outflows.",
        "why": "Closing cash determines whether the company can meet upcoming obligations.",
        "formula": "Opening cash + Net change in cash",
        "example": "€5m opening cash − €300k net outflow = €4.7m closing cash.",
    },
    {
        "category": "3. Working capital & liquidity",
        "term": "Minimum forecast cash",
        "definition": "The lowest closing cash balance reached anywhere in the forecast horizon.",
        "why": "A healthy year-end balance can hide a temporary mid-year cash shortfall; the minimum reveals that low point.",
        "formula": "Minimum of all forecast closing-cash balances",
        "example": "Cash may end at €5m but fall to €2.8m in August, making €2.8m the minimum forecast cash.",
    },
    {
        "category": "3. Working capital & liquidity",
        "term": "Minimum cash threshold",
        "definition": "A management-chosen safety floor for the amount of cash the company wants to preserve.",
        "why": "It is a policy assumption, not an accounting rule. It provides a buffer for uncertainty and unexpected payments.",
        "example": "NovaPlan uses an illustrative €3m default threshold.",
    },
    {
        "category": "3. Working capital & liquidity",
        "term": "Liquidity headroom",
        "definition": "The amount by which cash is above—or below—the chosen minimum cash threshold.",
        "why": "Positive headroom is a safety buffer; negative headroom signals that the plan breaches management’s policy floor.",
        "formula": "Cash − Minimum cash threshold",
        "example": "€3.8m cash − €3.0m threshold = €800k headroom.",
    },
    {
        "category": "3. Working capital & liquidity",
        "term": "Funding requirement",
        "definition": "The extra cash needed to bring a forecast balance back to the minimum threshold.",
        "why": "It identifies the size and timing of a potential financing or mitigation need.",
        "formula": "Maximum of (Threshold − Cash, 0)",
        "example": "€2.6m cash against a €3m floor creates a €400k funding requirement.",
    },
    # Planning and scenarios
    {
        "category": "4. Forecasts & scenarios",
        "term": "Actual",
        "definition": "A value already observed in the historical synthetic data.",
        "why": "Actuals are facts in the model’s timeline and provide the base for calibration and comparison.",
        "example": "December 2025 revenue is marked Actual; January 2026 is Forecast.",
    },
    {
        "category": "4. Forecasts & scenarios",
        "term": "Model baseline forecast",
        "definition": "The model’s forecast before any manual management adjustment.",
        "why": "Keeping it visible prevents human judgment from silently overwriting what the model calculated.",
        "example": "The model predicts €2.1m revenue before management adds information about a signed contract.",
    },
    {
        "category": "4. Forecasts & scenarios",
        "term": "Management adjustment",
        "definition": "A transparent manual change applied because management knows something the baseline model does not.",
        "why": "Judgment is useful, but it should have a rationale and audit trail so users can distinguish it from model output.",
        "formula": "Entered amount or percentage change",
        "example": "Management adds 3% with the rationale: ‘New contract signed after the data cut-off.’",
    },
    {
        "category": "4. Forecasts & scenarios",
        "term": "Final forecast",
        "definition": "The forecast used for planning after combining the model baseline and any management adjustment.",
        "why": "It is the decision view, while the baseline and adjustment remain separately traceable.",
        "formula": "Model baseline + Management adjustment",
        "example": "€2.10m baseline + €0.15m adjustment = €2.25m final forecast.",
    },
    {
        "category": "4. Forecasts & scenarios",
        "term": "Scenario",
        "definition": "A coherent set of assumptions used to answer a ‘what if?’ question—not a prediction that must happen.",
        "why": "Scenarios reveal trade-offs and help management prepare actions before conditions change.",
        "example": "The Risk Case combines slower collections, lower utilization, and higher salary inflation.",
    },
    {
        "category": "4. Forecasts & scenarios",
        "term": "Base case",
        "definition": "Management’s central or most likely planning assumptions.",
        "why": "Other scenarios are compared with Base so the incremental effect of each decision is visible.",
        "example": "A +€300k cash delta means the scenario ends €300k above the Base case.",
    },
    {
        "category": "4. Forecasts & scenarios",
        "term": "Delta (Δ) vs Base",
        "definition": "The difference between a scenario result and the Base result.",
        "why": "Delta isolates the effect of changing assumptions instead of asking users to compare two large numbers mentally.",
        "formula": "Scenario result − Base result",
        "example": "€5.2m scenario cash − €4.8m Base cash = +€0.4m delta.",
    },
    {
        "category": "4. Forecasts & scenarios",
        "term": "13-week direct cash forecast",
        "definition": "A short-term weekly schedule of expected cash receipts and payments.",
        "why": "It is designed for liquidity control: it answers when cash moves, not just whether the business is profitable.",
        "formula": "Opening cash + Collections − Payroll − Suppliers − Tax − Capex − Other payments",
        "example": "A customer paying two weeks late shifts the cash receipt to a later forecast week.",
    },
    {
        "category": "4. Forecasts & scenarios",
        "term": "18-month rolling forecast",
        "definition": "A monthly outlook that is refreshed over time so the company always looks forward a consistent number of months.",
        "why": "It supports medium-term hiring, pricing, profitability, working-capital, and funding decisions.",
        "example": "When one month becomes Actual, a new forecast month is added at the end.",
    },
    # Risk and validation
    {
        "category": "5. Risk & forecast quality",
        "term": "Monte Carlo simulation",
        "definition": "A method that runs the financial model many times with different plausible driver outcomes.",
        "why": "A single forecast hides uncertainty. Monte Carlo shows the range and probability of possible results.",
        "example": "NovaPlan varies utilization, DSO, salary inflation, attrition, realization, backlog conversion, and FX over 10,000 runs.",
    },
    {
        "category": "5. Risk & forecast quality",
        "term": "Probability",
        "definition": "The share of simulations in which an event occurs, expressed between 0% and 100%.",
        "why": "It converts uncertainty into a decision-relevant risk estimate, not a guarantee.",
        "formula": "Runs where event occurs ÷ Total runs",
        "example": "600 threshold breaches in 10,000 runs = 6% modeled probability.",
    },
    {
        "category": "5. Risk & forecast quality",
        "term": "Percentile (P5, P50, P95)",
        "definition": "A point in the ordered simulation outcomes. P50 is the median; P5 is a severe downside outcome; P95 is a strong upside outcome.",
        "why": "Percentiles show ranges without assuming the average tells the whole story.",
        "example": "P5 cash of €2.4m means 5% of modeled outcomes are lower and 95% are higher.",
    },
    {
        "category": "5. Risk & forecast quality",
        "term": "Cash fan chart",
        "definition": "A chart showing how forecast uncertainty widens over time using percentile bands.",
        "why": "The dark central band shows more common outcomes; the lighter outer band shows a wider plausible range.",
        "example": "If the P5 band crosses the threshold, a downside liquidity risk exists even when the median remains safe.",
    },
    {
        "category": "5. Risk & forecast quality",
        "term": "MAE",
        "definition": "Mean Absolute Error: the average size of forecast mistakes, ignoring whether they were high or low.",
        "why": "It is easy to interpret in the same unit as the metric. Lower is better.",
        "formula": "Average of |Actual − Predicted|",
        "example": "Revenue MAE of €120k means predictions missed actual revenue by €120k on average.",
    },
    {
        "category": "5. Risk & forecast quality",
        "term": "RMSE",
        "definition": "Root Mean Squared Error: an error measure that penalizes large misses more heavily than MAE.",
        "why": "RMSE helps identify models that usually perform well but occasionally make a very large mistake. Lower is better.",
        "formula": "Square root of average squared forecast errors",
        "example": "A single very large miss will increase RMSE more strongly than MAE.",
    },
    {
        "category": "5. Risk & forecast quality",
        "term": "WAPE",
        "definition": "Weighted Absolute Percentage Error: total absolute forecast error divided by total actual value.",
        "why": "It summarizes forecast error as a percentage and is safer than MAPE when individual values may be near zero. Lower is better.",
        "formula": "Σ|Actual − Predicted| ÷ Σ|Actual|",
        "example": "€1m total absolute error across €20m actual revenue = 5% WAPE.",
    },
    {
        "category": "5. Risk & forecast quality",
        "term": "Directional accuracy",
        "definition": "The percentage of periods where the model correctly predicts whether the metric rises or falls.",
        "why": "A model can miss the exact amount but still be useful if it consistently identifies turning points.",
        "formula": "Correct up/down predictions ÷ Evaluated periods",
        "example": "Correctly predicting direction in 7 of 10 months gives 70% directional accuracy.",
    },
    {
        "category": "5. Risk & forecast quality",
        "term": "Residual",
        "definition": "The difference between an actual value and the model’s prediction.",
        "why": "Residuals reveal bias. A good model should not consistently over-predict or under-predict.",
        "formula": "Actual − Predicted",
        "example": "€2.0m actual − €1.9m predicted = +€100k residual.",
    },
    {
        "category": "5. Risk & forecast quality",
        "term": "Walk-forward validation",
        "definition": "A time-safe test that trains on the past, predicts the next period, then moves forward and repeats.",
        "why": "It imitates real forecasting and avoids giving a model access to future information.",
        "example": "Train through Dec 2023, predict Jan 2024; then train through Jan and predict Feb.",
    },
    # Workforce economics and governance
    {
        "category": "6. Workforce economics & governance",
        "term": "Annual employer cost",
        "definition": "The recurring annual cost of employing one person under the model’s illustrative assumptions.",
        "why": "Base salary alone understates the financial commitment of a hire.",
        "formula": "Base salary + Employer on-cost + Bonus + Benefits",
        "example": "€42k salary plus illustrative loads may create roughly €51k recurring annual employer cost.",
    },
    {
        "category": "6. Workforce economics & governance",
        "term": "Contribution margin",
        "definition": "Revenue generated by a hire after deducting that hire’s recurring employer cost.",
        "why": "It shows whether the role economically contributes before broader company overhead.",
        "formula": "Expected billable revenue − Recurring employee cost",
        "example": "€95k revenue − €51k employee cost = €44k contribution.",
    },
    {
        "category": "6. Workforce economics & governance",
        "term": "Break-even utilization",
        "definition": "The minimum utilization required for expected billable revenue to cover recurring employee cost.",
        "why": "If planned utilization is below break-even, the hire does not cover recurring cost under the selected rate and assumptions.",
        "formula": "Recurring employee cost ÷ (Billing rate × Available hours × Realization)",
        "example": "A 48% break-even level with 74% planned utilization provides a 26-point operating cushion.",
    },
    {
        "category": "6. Workforce economics & governance",
        "term": "Payback period",
        "definition": "The number of months until cumulative contribution recovers recruiting, equipment, and early ramp-up cash costs.",
        "why": "A hire can be profitable over a year but still create temporary cash pressure before payback.",
        "formula": "First month where cumulative hire cash effect reaches zero or more",
        "example": "If cumulative cash turns positive in month 8, the modeled payback period is eight months.",
    },
    {
        "category": "6. Workforce economics & governance",
        "term": "Compensation band",
        "definition": "An analytical range based on synthetic internal peers and placeholder market logic.",
        "why": "It supports planning and internal-equity discussion but does not determine a legally or objectively correct salary.",
        "example": "P25–P75 describes the middle half of synthetic salaries for employees at the selected level.",
    },
    {
        "category": "6. Workforce economics & governance",
        "term": "Observed",
        "definition": "A value present in the historical synthetic dataset rather than created by a forecast assumption.",
        "why": "Users should know which values are treated as historical facts in the demonstration.",
        "example": "Historical headcount and invoice dates are classified as Observed.",
    },
    {
        "category": "6. Workforce economics & governance",
        "term": "Calculated",
        "definition": "A value produced directly by a defined formula from other inputs.",
        "why": "Calculated values are traceable and repeatable rather than chosen by management or statistically estimated.",
        "example": "EBITDA margin is calculated as EBITDA divided by revenue.",
    },
    {
        "category": "6. Workforce economics & governance",
        "term": "Management assumption",
        "definition": "A judgment entered by a user, such as planned hiring, a cash threshold, or expected DSO.",
        "why": "Assumptions should be visible, editable, and supported by a rationale because they are not observed facts.",
        "example": "Choosing a €3m minimum cash threshold is a management policy assumption.",
    },
    {
        "category": "6. Workforce economics & governance",
        "term": "Model estimate",
        "definition": "A value inferred by a forecasting or risk method rather than directly observed or manually chosen.",
        "why": "Estimates contain uncertainty and should be validated against future actual results.",
        "example": "P5 year-end cash from Monte Carlo is a model estimate.",
    },
    {
        "category": "6. Workforce economics & governance",
        "term": "Audit trail",
        "definition": "A record of who changed an assumption, when it changed, the old and new values, and the rationale.",
        "why": "It makes human judgment transparent and prevents unexplained forecast changes.",
        "example": "A saved 3% revenue adjustment records ‘Demo User’ and the entered explanation.",
    },
    {
        "category": "6. Workforce economics & governance",
        "term": "Balance-sheet reconciliation",
        "definition": "A control confirming that modeled assets equal liabilities plus equity within a small rounding tolerance.",
        "why": "If the identity fails, the integrated financial statements contain a modeling or data error.",
        "formula": "Assets = Liabilities + Equity",
        "example": "A difference below €0.01 is treated as rounding; a material difference triggers a warning.",
    },
]


def _term_card(item: dict[str, str]) -> html.Details:
    return html.Details(
        [
            html.Summary(item["term"]),
            html.Div(
                [
                    html.P(item["definition"]),
                    html.P([html.Strong("Why it matters: "), item["why"]]),
                    html.Div([html.Strong("Formula: "), html.Code(item["formula"])], className="glossary-formula")
                    if item.get("formula")
                    else None,
                    html.P([html.Strong("Simple example: "), item["example"]])
                    if item.get("example")
                    else None,
                ],
                className="glossary-term-body",
            ),
        ],
        className="glossary-term",
    )


def _render_terms(query: str | None = None):
    search = (query or "").strip().casefold()
    filtered = [
        item
        for item in TERMS
        if not search
        or search
        in " ".join(
            [
                item.get("term", ""),
                item.get("definition", ""),
                item.get("why", ""),
                item.get("formula", ""),
                item.get("category", ""),
            ]
        ).casefold()
    ]
    if not filtered:
        return html.Div(
            [html.H3("No matching term"), html.P("Try a broader search such as ‘cash’, ‘profit’, ‘forecast’, or ‘hiring’.")],
            className="panel",
            style={"textAlign": "center", "marginTop": "16px"},
        )
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in filtered:
        grouped[item["category"]].append(item)
    children = []
    for category, items in grouped.items():
        children.extend(
            [
                html.H2(category, className="glossary-category"),
                html.Div([_term_card(item) for item in items], className="glossary-grid"),
            ]
        )
    return children


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Finance and planning basics", className="page-kicker"),
                            html.H1("Learning guide"),
                            html.P("Plain-language definitions, formulas, reasons, and examples for every important concept used in NovaPlan."),
                        ]
                    ),
                    status_pill(f"{len(TERMS)} explained concepts", "positive"),
                ],
                className="page-heading",
            ),
            learning_guide(
                "You do not need an accounting or data-science background. Use this guide whenever a term in another page is unfamiliar.",
                [
                    ("Start with the business question", "Ask what management is trying to decide: profitability, liquidity, hiring, or risk."),
                    ("Follow the cause and effect", "Operating drivers create revenue and cost; payment timing then converts accounting results into cash."),
                    ("Treat forecasts as ranges", "A forecast is an informed planning view. Scenarios and percentiles show what could change."),
                ],
                concepts=["Drivers", "Profit", "Working capital", "Cash", "Scenarios", "Risk"],
            ),
            html.Div(
                [
                    teaching_callout(
                        "The most important distinction: profit is not cash",
                        "Revenue is recorded when services are delivered. Cash arrives only when customers pay. A company can therefore be profitable and still face liquidity pressure.",
                        formula="Revenue → Invoice/AR → Collection → Cash",
                        example="If €2m of work is delivered but customers pay €1.5m, revenue is €2m while AR increases by €500k and cash collection is only €1.5m.",
                    ),
                    teaching_callout(
                        "How NovaPlan tells the story",
                        "Read from left to right: management changes an operating driver, the financial model calculates outcomes, risk analysis adds uncertainty, and the user compares possible actions.",
                        formula="Drivers → Financial outcomes → Risk → Management action",
                        example="Increase hiring → payroll rises first → new revenue ramps later → minimum cash may fall before EBITDA improves.",
                    ),
                ],
                className="content-grid equal",
            ),
            html.Div(
                [
                    html.Div([html.H3("Search the glossary"), html.P("Search by term, business question, or formula—try ‘DSO’, ‘cash’, ‘error’, or ‘hire’.")]),
                    dcc.Input(
                        id="glossary-search",
                        type="search",
                        placeholder="Search concepts…",
                        debounce=False,
                    ),
                ],
                className="panel glossary-search-panel",
                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "20px", "marginTop": "16px"},
            ),
            html.Div(id="glossary-results", children=_render_terms()),
            html.Div(
                "Examples are simplified and use synthetic values. They teach model logic; they are not accounting, tax, compensation, or investment advice.",
                className="disclaimer",
            ),
        ]
    )


@callback(Output("glossary-results", "children"), Input("glossary-search", "value"))
def filter_glossary(query: str | None):
    return _render_terms(query)
