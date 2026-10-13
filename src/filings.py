"""Monster Beverage figures taken from its FY2025 Form 10-K.

Amounts below are copied from the filing, or labeled as a derivation or an
assumption. Nothing in this module is a forecast from the company, a market
price, or an acquisition financing term.

Source
------
Monster Beverage Corporation, Form 10-K for the fiscal year ended
December 31, 2025.
https://www.sec.gov/Archives/edgar/data/865752/000110465926020831/mnst-20251231x10k.htm

The face statements are in thousands of USD. This module stores USD millions
(thousands divided by 1,000). Narrative amounts that the filing already
rounded to billions stay labeled as narrative.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.assumptions import DealAssumptions

FILING_URL = (
    "https://www.sec.gov/Archives/edgar/data/865752/"
    "000110465926020831/mnst-20251231x10k.htm"
)
FILING_NAME = "Form 10-K for the fiscal year ended December 31, 2025"
COMPANY = "Monster Beverage Corporation"

# Face-statement amounts, USD thousands, as printed in the filing.
_NET_SALES = {2025: 8_294_343, 2024: 7_492_709, 2023: 7_140_027}
_COST_OF_SALES = {2025: 3_662_148, 2024: 3_443_831, 2023: 3_345_821}
_GROSS_PROFIT = {2025: 4_632_195, 2024: 4_048_878, 2023: 3_794_206}
_OPERATING_EXPENSES = {2025: 2_212_841, 2024: 2_118_584, 2023: 1_840_851}
_OPERATING_INCOME = {2025: 2_419_354, 2024: 1_930_294, 2023: 1_953_355}
_NET_INCOME = {2025: 1_905_432, 2024: 1_509_048, 2023: 1_630_988}
# Cover page. A share count, not a dollar amount.
SHARES_OUTSTANDING = 978_270_734
SHARES_AS_OF = "February 13, 2026"
# Cover page. Equity of non-affiliates only, not total market cap and not enterprise value.
NONAFFILIATE_EQUITY_USD = 56_505_471_480
NONAFFILIATE_AS_OF = "June 30, 2025"
_DEPRECIATION = {2025: 114_441, 2024: 80_434, 2023: 68_898}
_CAPEX = {2025: 132_275, 2024: 264_074, 2023: 221_428}
_PRETAX_INCOME = {2025: 2_482_529}
_TAX_PROVISION = {2025: 577_097}
_CASH = {2025: 2_088_117, 2024: 1_533_287}
_SHORT_TERM_INVESTMENTS = {2025: 677_084}
_LONG_TERM_INVESTMENTS = {2025: 487_329}
_RECEIVABLES = {2025: 1_618_072}
_INVENTORIES = {2025: 799_623}
_PAYABLES = {2025: 565_974}
_PROMOTIONAL_ALLOWANCES = {2025: 384_070}
_LONG_TERM_DEBT = {2025: 0, 2024: 373_951}
_SHORT_TERM_DEBT_PAYMENTS = {2025: 10_344}

_INCOME_STATEMENT = "Item 8, Consolidated Statements of Income"
_MDA = "Item 7, Management's Discussion and Analysis"
_BALANCE_SHEET = "Item 8, Consolidated Balance Sheets"
_CASH_FLOW = "Item 8, Consolidated Statements of Cash Flows"
_ITEM_1 = "Item 1, Business"
_SEGMENTS = "Item 8, Note on segment information, year ended December 31, 2025"
_LIQUIDITY = "Item 7, Liquidity and Capital Resources"


@dataclass(frozen=True)
class FilingRow:
    """One historical item, with its status kept separate from the LBO."""

    item: str
    fiscal_year: str
    amount_usd_millions: float | None
    status: str
    section: str
    used_in_lbo: str
    note: str


def _millions(thousands: int) -> float:
    return thousands / 1000.0


def _ratio(numerator: int, denominator: int) -> float:
    """Six-decimal ratio, matching the percent widgets on the assumptions page."""
    return round(numerator / denominator, 6)


def reported_net_sales(year: int) -> float:
    return _millions(_NET_SALES[year])


def reported_cost_of_sales(year: int) -> float:
    return _millions(_COST_OF_SALES[year])


def reported_gross_profit(year: int) -> float:
    return _millions(_GROSS_PROFIT[year])


def reported_operating_expenses(year: int) -> float:
    return _millions(_OPERATING_EXPENSES[year])


def reported_operating_income(year: int) -> float:
    return _millions(_OPERATING_INCOME[year])


def reported_net_income(year: int) -> float:
    return _millions(_NET_INCOME[year])


def income_statement_ties(year: int) -> bool:
    """Face statement: net sales − cost of sales = gross profit; gross profit − expenses = operating income."""
    return (
        _NET_SALES[year] - _COST_OF_SALES[year] == _GROSS_PROFIT[year]
        and _GROSS_PROFIT[year] - _OPERATING_EXPENSES[year] == _OPERATING_INCOME[year]
    )


def nonaffiliate_equity_usd_millions() -> float:
    """Cover-page non-affiliate equity value, in USD millions. Not enterprise value."""
    return NONAFFILIATE_EQUITY_USD / 1_000_000.0


def reported_depreciation(year: int) -> float:
    return _millions(_DEPRECIATION[year])


def derived_ebitda(year: int = 2025) -> float:
    """Operating income plus depreciation and amortization.

    The 10-K does not report EBITDA. This is that sum, in USD millions.
    It does not add back the $38.411 million Alcohol Brands intangibles
    impairment included in 2025 operating expenses.
    """
    return _millions(_OPERATING_INCOME[year] + _DEPRECIATION[year])


def engine_ebitda_margin(year: int = 2025) -> float:
    return _ratio(_OPERATING_INCOME[year] + _DEPRECIATION[year], _NET_SALES[year])


def engine_da_pct(year: int = 2025) -> float:
    return _ratio(_DEPRECIATION[year], _NET_SALES[year])


def engine_capex_pct(year: int = 2025) -> float:
    return _ratio(_CAPEX[year], _NET_SALES[year])


def trade_nwc(year: int = 2025) -> float:
    """Receivables + inventories − accounts payable. USD millions."""
    return _millions(_RECEIVABLES[year] + _INVENTORIES[year] - _PAYABLES[year])


def engine_nwc_pct(year: int = 2025) -> float:
    numerator = _RECEIVABLES[year] + _INVENTORIES[year] - _PAYABLES[year]
    return _ratio(numerator, _NET_SALES[year])


def filing_register() -> tuple[FilingRow, ...]:
    """Reported, derived, and explicitly unverified historical rows."""
    rows: list[FilingRow] = []
    for year in (2025, 2024, 2023):
        rows.append(
            FilingRow(
                f"Net sales",
                f"Year ended December 31, {year}",
                reported_net_sales(year),
                "reported",
                f"{_INCOME_STATEMENT}; also {_MDA}",
                "2025 amount is the LTM revenue anchor" if year == 2025 else "history only",
                "USD thousands on the face of the income statement.",
            )
        )
        rows.append(
            FilingRow(
                "Cost of sales",
                f"Year ended December 31, {year}",
                reported_cost_of_sales(year),
                "reported",
                _INCOME_STATEMENT,
                "history only; not a forecast line",
                "Face of the income statement. The engine has no cost-of-sales forecast.",
            )
        )
        rows.append(
            FilingRow(
                "Gross profit",
                f"Year ended December 31, {year}",
                reported_gross_profit(year),
                "reported",
                _INCOME_STATEMENT,
                "history only; not a forecast line",
                "Printed on the income statement. Equals net sales minus cost of sales.",
            )
        )
        rows.append(
            FilingRow(
                "Operating expenses",
                f"Year ended December 31, {year}",
                reported_operating_expenses(year),
                "reported",
                _INCOME_STATEMENT,
                "history only; not a forecast line",
                "One consolidated line. Marketing and distribution are not split out here.",
            )
        )
        rows.append(
            FilingRow(
                "Operating income",
                f"Year ended December 31, {year}",
                reported_operating_income(year),
                "reported",
                _INCOME_STATEMENT,
                "2025 amount is an EBITDA component" if year == 2025 else "history only",
                "After operating expenses, including impairment charges.",
            )
        )
        rows.append(
            FilingRow(
                "Depreciation and amortization",
                f"Year ended December 31, {year}",
                reported_depreciation(year),
                "reported",
                _CASH_FLOW,
                "2025 amount is an EBITDA and D&A component" if year == 2025 else "history only",
                "Cash-flow add-back, not a separate income-statement line.",
            )
        )
        rows.append(
            FilingRow(
                "Net income",
                f"Year ended December 31, {year}",
                reported_net_income(year),
                "reported",
                _INCOME_STATEMENT,
                "history only; not a forecast line",
                "Face of the income statement. The model's forecast net income is not this figure.",
            )
        )
        rows.append(
            FilingRow(
                "Purchases of property and equipment",
                f"Year ended December 31, {year}",
                _millions(_CAPEX[year]),
                "reported",
                _CASH_FLOW,
                "2025 amount sets the capex ratio" if year == 2025 else "history only",
                "Investing cash flow. Not a maintenance-versus-growth split.",
            )
        )

    rows.extend(
        [
            FilingRow(
                "EBITDA",
                "Year ended December 31, 2025",
                derived_ebitda(2025),
                "derived",
                f"{_INCOME_STATEMENT} and {_CASH_FLOW}",
                "Rounded margin is the LTM EBITDA margin",
                "Operating income 2,419.354 + depreciation and amortization 114.441. "
                "Not a GAAP line. The $38.411 million intangibles impairment is not added back. "
                f"The engine stores the margin rounded to six decimals ({engine_ebitda_margin():.6f}).",
            ),
            FilingRow(
                "Income before taxes",
                "Year ended December 31, 2025",
                _millions(_PRETAX_INCOME[2025]),
                "reported",
                _INCOME_STATEMENT,
                "not a model line",
                "Used only to identify the disclosed effective tax rate.",
            ),
            FilingRow(
                "Provision for income taxes",
                "Year ended December 31, 2025",
                _millions(_TAX_PROVISION[2025]),
                "reported",
                _INCOME_STATEMENT,
                "not a model line",
                "Item 7 discloses income taxes as 23.2% of income before taxes.",
            ),
            FilingRow(
                "Effective tax rate",
                "Year ended December 31, 2025",
                None,
                "reported",
                _MDA,
                "flat 23.2% tax-rate assumption",
                "Disclosed as 23.2% of income before taxes. Stored in the note, not the amount "
                "column, so a percent is not shown as USD millions. This is the rounded Item 7 "
                "rate, not the unrounded provision divided by pretax income. The engine applies "
                "it to positive EBT only.",
            ),
            FilingRow(
                "Cash and cash equivalents",
                "December 31, 2025",
                _millions(_CASH[2025]),
                "reported",
                _BALANCE_SHEET,
                "not on the closing balance sheet",
                "The engine cannot hold a negative existing net debt, so this cash is excluded "
                "rather than netted against zero debt.",
            ),
            FilingRow(
                "Cash and cash equivalents",
                "December 31, 2024",
                _millions(_CASH[2024]),
                "reported",
                _BALANCE_SHEET,
                "history only",
                "",
            ),
            FilingRow(
                "Short-term investments",
                "December 31, 2025",
                _millions(_SHORT_TERM_INVESTMENTS[2025]),
                "reported",
                _BALANCE_SHEET,
                "not in the model",
                "Item 7 also describes $677.1 million of short-term investments.",
            ),
            FilingRow(
                "Long-term investments",
                "December 31, 2025",
                _millions(_LONG_TERM_INVESTMENTS[2025]),
                "reported",
                _BALANCE_SHEET,
                "not in the model",
                "Investments line. Item 7 describes $487.3 million.",
            ),
            FilingRow(
                "Accounts receivable, net",
                "December 31, 2025",
                _millions(_RECEIVABLES[2025]),
                "reported",
                _BALANCE_SHEET,
                "trade NWC component",
                "",
            ),
            FilingRow(
                "Inventories",
                "December 31, 2025",
                _millions(_INVENTORIES[2025]),
                "reported",
                _BALANCE_SHEET,
                "trade NWC component",
                "",
            ),
            FilingRow(
                "Accounts payable",
                "December 31, 2025",
                _millions(_PAYABLES[2025]),
                "reported",
                _BALANCE_SHEET,
                "trade NWC component",
                "",
            ),
            FilingRow(
                "Accrued promotional allowances",
                "December 31, 2025",
                _millions(_PROMOTIONAL_ALLOWANCES[2025]),
                "reported",
                _BALANCE_SHEET,
                "not in the NWC ratio",
                "Excluded from trade NWC. The engine has one NWC percent, not a full accrual build.",
            ),
            FilingRow(
                "Trade net working capital",
                "December 31, 2025",
                trade_nwc(2025),
                "derived",
                _BALANCE_SHEET,
                "NWC percent of 2025 net sales",
                "Receivables + inventories − accounts payable. "
                f"Engine ratio rounded to six decimals ({engine_nwc_pct():.6f}).",
            ),
            FilingRow(
                "Long-term debt",
                "December 31, 2025",
                0.0,
                "reported",
                f"{_BALANCE_SHEET}; {_LIQUIDITY}",
                "existing net debt anchor is zero",
                "The balance sheet prints a dash. Item 7 says the term loan was repaid in April 2025 "
                "and no borrowings were outstanding under the credit facilities at year-end. "
                "This is historical debt, not acquisition financing. The undrawn revolver had "
                "$500.0 million of availability as of February 26, 2026.",
            ),
            FilingRow(
                "Long-term debt",
                "December 31, 2024",
                _millions(_LONG_TERM_DEBT[2024]),
                "reported",
                _BALANCE_SHEET,
                "not the acquisition-date debt",
                "Repaid in April 2025. Not used as the closing net-debt plug.",
            ),
            FilingRow(
                "Payments on short-term debt",
                "Year ended December 31, 2025",
                _millions(_SHORT_TERM_DEBT_PAYMENTS[2025]),
                "reported",
                _CASH_FLOW,
                "not in existing net debt",
                "A cash-flow payment. A separate year-end short-term debt balance was not "
                "presented in current liabilities.",
            ),
            FilingRow(
                "Net sales outside the United States",
                "Year ended December 31, 2025",
                3_440.0,
                "reported",
                _ITEM_1,
                "not a separate growth driver",
                "Item 1 rounds this to $3.44 billion. 2024 was $2.96 billion and 2023 was $2.71 billion. "
                "Not taken from the face of the income statement.",
            ),
            FilingRow(
                "Selling and marketing expense, Monster Energy Drinks",
                "Year ended December 31, 2025",
                714.958,
                "reported",
                _SEGMENTS,
                "not a model driver",
                "Segment column only. Strategic Brands 61.633, Alcohol Brands 26.447, Other 0.421. "
                "The consolidated total cell was blank in the filing text used here and is not filled in.",
            ),
            FilingRow(
                "Distribution expense, Monster Energy Drinks",
                "Year ended December 31, 2025",
                314.933,
                "reported",
                _SEGMENTS,
                "not a model driver",
                "Segment column only. Strategic Brands 6.257 and Alcohol Brands 9.897. "
                "Other and the consolidated total were blank and are not filled in.",
            ),
            FilingRow(
                "Year-end short-term debt balance",
                "December 31, 2025",
                None,
                "unverified",
                _BALANCE_SHEET,
                "omitted",
                "Not shown as its own current-liability line. Left blank rather than estimated.",
            ),
            FilingRow(
                "Common shares outstanding",
                SHARES_AS_OF,
                None,
                "reported",
                "Cover page",
                "not a valuation input",
                f"{SHARES_OUTSTANDING:,} shares. A share count, so the USD millions column is blank. "
                "Not multiplied by a price.",
            ),
            FilingRow(
                "Aggregate market value of common equity held by non-affiliates",
                NONAFFILIATE_AS_OF,
                nonaffiliate_equity_usd_millions(),
                "reported",
                "Cover page",
                "not the entry enterprise value",
                "Computed in the filing from the Nasdaq closing price on June 30, 2025. "
                "It excludes affiliates, so it is not total market capitalization. "
                "It is not enterprise value: cash and debt are not in this figure, and the date "
                "is not December 31, 2025. It is not used as the entry multiple.",
            ),
            FilingRow(
                "Current market enterprise value",
                "Not loaded",
                None,
                "unverified",
                "not in the 10-K",
                "entry and exit multiples stay user assumptions",
                "No same-date share price, share count, cash, and debt were available together. "
                "A live quote was not stored, because it would not match the February 13, 2026 "
                "share count or the December 31, 2025 cash and debt. The entry multiple is an "
                "editable assumption and is not filled from this blank.",
            ),
            FilingRow(
                "Price, volume, and product-mix breakdown of net sales growth",
                "Years ended December 31, 2025 and 2024",
                None,
                "unverified",
                _MDA,
                "not modeled",
                "Item 7 attributes the 2025 net-sales increase primarily to Monster Energy demand. "
                "It does not give a price, volume, and mix bridge the engine can use.",
            ),
            FilingRow(
                "Company forecast or guidance",
                "Not reported as a forecast in the figures used here",
                None,
                "unverified",
                _LIQUIDITY,
                "not used",
                "Item 7 says planned capital expenditures, excluding share repurchases, are likely "
                "to be less than $250 million through at least the next 12 months. That sentence is "
                "not used as the five-year capex ratio.",
            ),
        ]
    )
    return tuple(rows)


def monster_hypothetical_case() -> DealAssumptions:
    """Hypothetical LBO using FY2025 anchors where the engine has an input.

    Acquisition leverage, interest, multiples, fees, cash, and the growth path
    are assumptions. Historical long-term debt of zero does not set them.
    """
    years = 5
    margin = engine_ebitda_margin(2025)
    return DealAssumptions(
        company_name="Monster Beverage Corporation (illustrative LBO)",
        is_illustrative=True,
        currency="USD",
        units="millions",
        ltm_revenue=reported_net_sales(2025),
        ltm_ebitda_margin=margin,
        revenue_growth=(0.08, 0.07, 0.06, 0.05, 0.05),
        ebitda_margin=(0.304, 0.302, 0.300, 0.298, 0.296),
        da_pct_of_revenue=engine_da_pct(2025),
        capex_pct_of_revenue=engine_capex_pct(2025),
        nwc_pct_of_revenue=engine_nwc_pct(2025),
        entry_ebitda_multiple=15.0,
        exit_ebitda_multiple=15.0,
        holding_period_years=years,
        senior_leverage=3.0,
        subordinated_leverage=1.0,
        senior_interest_rate=0.065,
        subordinated_interest_rate=0.095,
        senior_mandatory_amort_pct=0.05,
        cash_sweep_pct=0.50,
        tax_rate=0.232,
        transaction_fees_pct_of_ev=0.015,
        cash_to_balance_sheet=250.0,
        minimum_cash=200.0,
        existing_net_debt=0.0,
        notes=(
            "HYPOTHETICAL LBO. LTM net sales, the EBITDA margin (operating income plus "
            "depreciation and amortization, margin rounded to six decimals), D&A, capex, "
            "trade NWC, a zero existing-debt plug, and the 23.2% tax rate are anchored to "
            f"the {FILING_NAME}. {FILING_URL} "
            "Cost of sales, gross profit, operating expenses, and net income are on the filing "
            "register and are not forecast lines. "
            "Growth, forecast margins, 15.0x entry and exit multiples, 3.0x senior and 1.0x "
            "subordinated acquisition debt, interest rates, fees, the cash sweep, and the "
            "$250 million closing cash are assumptions, not reported results. "
            "Historical cash of $2,088.117 million and the investment balances are excluded. "
            "New acquisition debt is not Monster's historical borrowings."
        ),
    )


def filing_anchor_gaps(assumptions: DealAssumptions) -> tuple[str, ...]:
    """Say which stored filing anchors the current case no longer matches."""
    anchor = monster_hypothetical_case()
    checks = (
        ("LTM revenue", assumptions.ltm_revenue, anchor.ltm_revenue),
        ("LTM EBITDA margin", assumptions.ltm_ebitda_margin, anchor.ltm_ebitda_margin),
        ("D&A / revenue", assumptions.da_pct_of_revenue, anchor.da_pct_of_revenue),
        ("Capex / revenue", assumptions.capex_pct_of_revenue, anchor.capex_pct_of_revenue),
        ("NWC / revenue", assumptions.nwc_pct_of_revenue, anchor.nwc_pct_of_revenue),
        ("Tax rate", assumptions.tax_rate, anchor.tax_rate),
        ("Existing net debt", assumptions.existing_net_debt, anchor.existing_net_debt),
    )
    gaps = [
        f"{label} is {current:,.6f}; the FY2025 anchor is {expected:,.6f}."
        for label, current, expected in checks
        if abs(current - expected) > 1e-9
    ]
    return tuple(gaps)


def register_frame_records() -> list[dict[str, object]]:
    """Rows for the screen and the Excel filing register."""
    return [
        {
            "Item": row.item,
            "Fiscal period": row.fiscal_year,
            "Amount (USD millions)": row.amount_usd_millions,
            "Status": row.status,
            "Filing section": row.section,
            "Role in this model": row.used_in_lbo,
            "Note": row.note,
            "Source": FILING_URL,
        }
        for row in filing_register()
    ]
