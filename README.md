# NovaPlan — Student Business Planning Project

NovaPlan is a small educational dashboard made for a fictional high-school
internship project. It asks one practical question:

> Can a consulting company hire more people without running short of cash?

The project is not a real Deloitte tool. It uses only synthetic (invented) data
and simplified finance rules.

## What the dashboard contains

The main navigation has six pages:

1. **Project Overview** — the question, the fictional company and the main result.
2. **What-if Experiment** — change hires, utilization, billing rate and customer
   payment time.
3. **13-Week Cash Check** — test a payment delay, new hires or an unexpected bill.
4. **Risk Simulation** — run the forecast many times with different uncertainty.
5. **How It Works** — data, formulas, testing and limitations.
6. **Robot Rental Experiment** — a second fictional company rents robots by the
   hour; find the lowest safe uptime and test whether it can run out of cash while
   still reporting a profit.

The original detailed pages remain available as optional examples, but they are
not needed to understand the student project.

### Robot Rental Experiment

The sixth page uses a second invented company, RoboHire SRL, which buys robots
up front and rents them to factories by the hour, while customers pay weeks
later. It finds the lowest uptime at which cash never falls below a minimum
floor, then runs a Monte Carlo over uptime, payment delay and booked hours to
show how often cash runs short and how many of those runs were still profitable
on paper. Like the rest of the project it uses only fictional data: every default
is an illustrative assumption in `config/robot_rental.yaml`, not real market data.

## The simple financial idea

```text
People × productive time × hourly price → revenue
Revenue − operating costs              → profit
Opening cash + receipts − payments     → closing cash
```

Profit and cash are not the same. A company can record revenue today and receive
the customer payment several weeks later. New employees also receive salary
before they are fully productive.

## Synthetic data

The fictional company has six years of monthly history from January 2020 to
December 2025. The generator also creates invoices, customers, employees, a
hiring plan, operating costs, capital purchases and weekly cash records.

The data is designed to connect correctly:

- invoice values reconcile to revenue;
- unpaid invoices become accounts receivable;
- cash collections reduce accounts receivable;
- opening cash plus cash movement equals closing cash;
- the same seed (`42`) recreates the same fictional history.

Synthetic data is useful for learning and software testing. It does not prove
that the model predicts a real company accurately.

## Monte Carlo experiment

Monte Carlo repeats the forecast many times. Each run slightly changes business
drivers such as utilization, customer payment time, billing realization, salary
inflation, attrition, backlog conversion and foreign exchange.

The main control is **Uncertainty level**:

- `0%` removes the random changes, so every run is identical;
- `100%` uses the normal demonstration ranges;
- `200%` makes the ranges twice as wide before safety limits are applied.

The **cash safety target** only classifies the simulated paths. It should change
the breach percentage, but it should not move the paths themselves. The number
of runs makes estimates steadier; it does not make the business more risky.

## Running the project

Requirements: Python 3.12 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python synthetic/generate_company.py
python -m pytest -q
python app.py
```

Open [http://127.0.0.1:8050](http://127.0.0.1:8050).

## What is tested

The automated checks cover both calculations and interactive-control behavior:

- more utilization or a higher billing rate increases revenue;
- slower customer payment reduces cash without changing earned revenue;
- higher salaries reduce profit and cash;
- hiring adds cost before employees finish ramping up;
- financial statements and cash balances reconcile;
- the same Monte Carlo seed reproduces the same paths;
- zero uncertainty produces one deterministic path;
- higher uncertainty widens the simulated cash range;
- changing the cash target changes the breach rate, not the paths;
- every student-facing control reaches the model and moves the intended output.

Run the checks with:

```powershell
python -m pytest -q
```

## Limitations

- All data is fictional.
- Tax, hiring, invoice and accounting rules are simplified.
- The probability ranges are teaching assumptions, not estimates calibrated to
  a real company or financial crisis.
- The dashboard is a local prototype without production authentication,
  approvals or live ERP/bank connections.

NovaPlan is an educational proof-of-concept built using entirely synthetic
data. It is not an official Deloitte product, does not represent Deloitte
proprietary methodologies, and should not be used as financial, tax, accounting,
or investment advice.
