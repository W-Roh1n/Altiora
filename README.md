# Altiora — Private Markets Intelligence

Live Demo: https://altiora.streamlit.app/

A Python-based LBO modelling and financial analysis application focused on Monster Beverage Corporation (NASDAQ: MNST).

Altiora is an independent educational project I built to explore leveraged-buyout modelling, financial analysis, Python development and automated testing. It is not affiliated with Monster Beverage Corporation, is not an official company model, and is not intended for making or recording investment decisions.

The opening case is a hypothetical LBO of Monster Beverage Corporation. It is not an announced or completed acquisition. Historical financial data is drawn from the company's Form 10-K for the fiscal year ended December 31, 2025, while acquisition terms and projections are model assumptions.

## What it does

You edit deal assumptions. The model calculates:

1. Entry enterprise value and the sources and uses of funds.
2. A five-year operating projection, or another holding period you set.
3. Interest, mandatory amortization, a cash sweep, and closing debt.
4. Exit enterprise value, exit net debt, and exit equity.
5. Sponsor cash flows, gross IRR, and gross MOIC.
6. Base, downside, and upside cases, plus a small sensitivity grid.
7. Identity checks, and warnings when debt cannot be paid without breaking the cash floor.

`src/` does the calculation. `app.py` only displays it. `main.py` prints the same result in the terminal.

## Workflow

```text
assumptions → sources & uses → operating projection
    → debt and cash → exit equity → sponsor IRR and MOIC → checks
```

| Idea | What the model does |
| --- | --- |
| Entry EV | LTM EBITDA × entry EV/EBITDA multiple |
| Equity purchase price | Entry EV − existing net debt |
| Uses | Equity purchase + refinance existing net debt + fees + cash to the balance sheet |
| Sources | New senior debt + new subordinated debt + sponsor equity (the plug) |
| Revenue | Prior revenue × (1 + that year's growth), starting from LTM revenue |
| EBITDA, D&A, capex, NWC | Percent of that year's revenue. The change in NWC uses LTM NWC as year 0 |
| Interest | Cash interest on opening principal, so the sweep does not create a circular reference |
| Tax | Tax rate × max(EBT, 0). Losses do not create a cash refund |
| Free cash flow | EBITDA − cash interest − tax − capex − change in NWC, before principal |
| Mandatory amortization | Scheduled as a percent of original senior principal, capped by the opening balance. Paid only from cash above minimum cash. The unpaid part is a financing shortfall |
| Cash sweep | A percent of cash left after mandatory amortization, senior debt only |
| Subordinated debt | Interest-only until exit. It is repaid through the exit equity bridge |
| Exit EV | Exit-year EBITDA × exit multiple. The multiple is cash-free and debt-free |
| Surplus cash | Closing cash − minimum cash |
| Exit net debt | Gross debt − surplus cash |
| Exit equity | max(0, exit EV − exit net debt). Minimum cash is not counted as extra value |
| Gross MOIC | Exit equity / sponsor equity |
| Gross IRR | Annual IRR of the actual sponsor cash flows, solved by Newton-Raphson |

Amounts are **USD millions**. Rates inside the engine are decimals (`0.18` = 18%). The app edits rates as percents. Cash flows are annual and year-end.

The standard scenarios keep the same capital structure:

- **Base** — the assumptions as entered
- **Downside** — growth −3 percentage points, EBITDA margin −1.5 percentage points, exit multiple −1.0x
- **Upside** — growth +2 percentage points, EBITDA margin +1.0 percentage point, exit multiple +1.0x

If an overlay breaks validation, that case is omitted and the error is shown. The model does not fill the gap with an estimated return.

## Technology and layout

Python, pandas, Streamlit, Altair, and openpyxl. Tests use pytest. There is no database, account system, or external API.

```text
Altiora/
    src/
        assumptions.py      # validated inputs and scenario overlays
        filings.py          # FY2025 Monster 10-K register and hypothetical LBO anchors
        operating_model.py  # revenue through free cash flow
        debt_schedule.py    # interest, amortization, cash sweep
        lbo_model.py        # wires entry, operations, debt, and exit
        returns.py          # exit value, MOIC, IRR
        validation.py       # identity checks and financing flags
        reporting.py        # scenarios, sensitivity, display formatting, Excel
    tests/
        test_lbo_model.py
        test_altiora.py
    app.py                  # local Streamlit workspace
    main.py                 # terminal print of the same engine
    requirements.txt
    README.md
```

## Run it

From the project folder on Windows, using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m pytest -v
```

The app opens at http://localhost:8501. A new environment is:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Pages: Overview, Deal Assumptions, Operating Model, Debt Schedule, Returns & Sensitivity, Model Checks, and Export. The Excel file contains the assumptions and the schedules the engine produced. Screen tables are rounded; the workbook keeps full precision of those same values.

## Validation

Assumptions are rejected when they are incomplete or implausible, including a non-positive entry value, margins outside (0, 1), or closing cash below minimum cash. `run_lbo` then checks that sources equal uses, the debt roll-forward holds, debt does not go negative, and the exit bridge matches the sponsor cash flows. A financing shortfall or a minimum-cash breach is reported and does not rewrite the amortization schedule. Tests recalculate the sample deal independently and compare that result with the engine.

## What is implemented, and what is simplified

Implemented: one senior facility, one subordinated bullet, annual operations, a cash sweep, three scenarios, an exit-multiple and revenue-growth sensitivity, validation flags, a local interface, and an Excel export.

Simplified, and not a planned claim of completeness:

- No revolver, PIK, OID, or delayed-draw term loan
- No management rollover, preferred equity, or option pool
- No quarterly periods, mid-year convention, or daily interest
- No NOLs, deferred tax, or interest-deductibility limits
- No dividend before exit
- Gross sponsor returns only: no management fee, carried interest, or investor tax
- Minimum cash is a floor, not a revolving credit line
- The sensitivity grid varies exit multiple and revenue growth, not every input

These are modelling choices for a personal project. They are not a statement that the output has been checked by an investment firm or is safe to use on a live deal.
