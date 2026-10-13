# Altiora

Personal LBO model. I built it to practice a full leveraged-buyout calculation in Python, check it with automated tests, and show the result in a local interface. It is an independent educational project. It is not affiliated with Monster Beverage Corporation, it is not a product, and it is not for making or recording investment decisions.

The opening case is an educational LBO of Monster Beverage Corporation. It is not an announced or completed acquisition. Reported history comes from the Form 10-K for the fiscal year ended December 31, 2025, in USD thousands on the face statements and stored here in USD millions:

https://www.sec.gov/Archives/edgar/data/865752/000110465926020831/mnst-20251231x10k.htm

The income statement in that filing supplies net sales, cost of sales, gross profit, operating expenses, operating income, and net income for 2023, 2024, and 2025. Those lines reconcile: net sales minus cost of sales equals gross profit, and gross profit minus operating expenses equals operating income. EBITDA is not in the filing. The model derives 2025 EBITDA as operating income plus the cash-flow depreciation and amortization add-back, and labels it derived. Capex, cash, debt, and trade working capital are also taken from that filing where a line exists. Blank items stay blank.

The cover page reports 978,270,734 common shares outstanding on February 13, 2026, and an aggregate market value of common equity held by non-affiliates of $56,505,471,480 using the Nasdaq close on June 30, 2025. That dollar figure excludes affiliates, so it is not total market capitalization. It is not enterprise value, and it is not a current price. No same-date share price, share count, cash, and debt were available together, so the app does not calculate a market enterprise value. The 15.0x entry and exit multiples are editable assumptions.

Growth, acquisition debt, fees, and closing cash are also assumptions. Monster's historical cash is not on the closing balance sheet, and its lack of year-end debt does not mean the acquisition is unlevered. Gross IRR and MOIC are hypothetical results of the case, not actual investor returns. The filing register lists what was checked, what was derived, and what was left blank.

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
