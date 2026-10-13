"""Orchestrate entry, operations, debt, exit, and sponsor returns.

This module is the only place that wires the other calculation modules
together. It does not print or render UI.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.assumptions import DealAssumptions
from src.debt_schedule import cash_available_for_debt_paydown, roll_debt_period
from src.operating_model import (
    period_fcf_before_principal,
    period_taxes,
    period_taxable_income,
    project_operations,
)
from src.returns import (
    annualized_irr,
    exit_enterprise_value,
    exit_equity_value,
    exit_net_debt,
    gross_moic,
    surplus_cash,
)
from src.validation import CheckResult, validate_lbo_result


@dataclass(frozen=True)
class TransactionStructure:
    entry_enterprise_value: float
    equity_purchase_price: float
    refinanced_net_debt: float
    transaction_fees: float
    cash_to_balance_sheet: float
    new_senior_debt: float
    new_subordinated_debt: float
    sponsor_equity: float
    total_uses: float
    total_sources: float


@dataclass(frozen=True)
class FinancingStatus:
    """Credit / liquidity flags. These do not rewrite the amort schedule."""

    has_shortfall: bool
    total_amortization_shortfall: float
    total_min_cash_breach: float
    notes: tuple[str, ...]


@dataclass
class LBOResult:
    assumptions: DealAssumptions
    scenario_name: str
    transaction: TransactionStructure
    sources: pd.Series
    uses: pd.Series
    operating_schedule: pd.DataFrame
    debt_schedule: pd.DataFrame
    cash_schedule: pd.DataFrame
    exit_enterprise_value: float
    exit_equity_value: float
    exit_net_debt: float
    excess_cash_at_exit: float
    sponsor_cash_flows: list[float]
    gross_moic: float
    irr: float
    financing: FinancingStatus
    checks: list[CheckResult]


def build_transaction(assumptions: DealAssumptions) -> TransactionStructure:
    """Entry EV, sources & uses, and sponsor equity plug.

    Uses
        Equity purchase price = Entry EV − existing net debt
        Refinance existing net debt
        Transaction fees = fee % × Entry EV
        Cash to the closing balance sheet
    Sources
        New senior debt = senior leverage × LTM EBITDA
        New subordinated debt = subordinated leverage × LTM EBITDA
        Sponsor equity (plug so that sources = uses)

    Identity: equity purchase + refinance = entry EV, so
    total uses = entry EV + fees + cash to B/S.
    """
    entry_ev = assumptions.ltm_ebitda * assumptions.entry_ebitda_multiple
    fees = assumptions.transaction_fees_pct_of_ev * entry_ev
    equity_purchase = entry_ev - assumptions.existing_net_debt
    if equity_purchase <= 0:
        raise ValueError("Entry EV must exceed existing net debt")

    uses_total = (
        equity_purchase
        + assumptions.existing_net_debt
        + fees
        + assumptions.cash_to_balance_sheet
    )
    senior = assumptions.senior_leverage * assumptions.ltm_ebitda
    sub = assumptions.subordinated_leverage * assumptions.ltm_ebitda
    sponsor = uses_total - senior - sub
    if sponsor <= 0:
        raise ValueError("Debt financing exceeds uses; sponsor equity would not be positive")

    return TransactionStructure(
        entry_enterprise_value=entry_ev,
        equity_purchase_price=equity_purchase,
        refinanced_net_debt=assumptions.existing_net_debt,
        transaction_fees=fees,
        cash_to_balance_sheet=assumptions.cash_to_balance_sheet,
        new_senior_debt=senior,
        new_subordinated_debt=sub,
        sponsor_equity=sponsor,
        total_uses=uses_total,
        total_sources=senior + sub + sponsor,
    )


def _sources_uses_series(txn: TransactionStructure) -> tuple[pd.Series, pd.Series]:
    uses = pd.Series(
        {
            "Equity purchase price": txn.equity_purchase_price,
            "Refinance existing net debt": txn.refinanced_net_debt,
            "Transaction fees": txn.transaction_fees,
            "Cash to balance sheet": txn.cash_to_balance_sheet,
        },
        name="Uses",
    )
    sources = pd.Series(
        {
            "New senior debt": txn.new_senior_debt,
            "New subordinated debt": txn.new_subordinated_debt,
            "Sponsor equity": txn.sponsor_equity,
        },
        name="Sources",
    )
    return sources, uses


def run_lbo(assumptions: DealAssumptions, scenario_name: str = "base") -> LBOResult:
    """Run the full LBO from assumptions through validated returns."""
    txn = build_transaction(assumptions)
    sources, uses = _sources_uses_series(txn)
    ops = project_operations(assumptions)

    years = list(assumptions.year_labels)
    debt_rows = [
        "Opening senior",
        "Opening subordinated",
        "Opening total debt",
        "Senior interest",
        "Subordinated interest",
        "Total interest",
        "Scheduled mandatory amortization",
        "Mandatory amortization",
        "Amortization shortfall",
        "Optional cash sweep",
        "Total senior repayment",
        "Closing senior",
        "Closing subordinated",
        "Closing total debt",
    ]
    cash_rows = [
        "Opening cash",
        "EBITDA",
        "Cash interest",
        "EBT",
        "Taxes",
        "Net income",
        "D&A",
        "Capex",
        "Change in NWC",
        "FCF before principal",
        "Debt principal repaid",
        "Closing cash",
        "Minimum cash",
        "Surplus cash",
        "Min-cash breach",
    ]
    debt = pd.DataFrame(index=debt_rows, columns=["Close"] + years, dtype=float)
    cash = pd.DataFrame(index=cash_rows, columns=["Close"] + years, dtype=float)
    ops_full = ops.copy()
    for extra in ("Interest", "EBT", "Taxes", "Net income", "FCF before principal"):
        ops_full.loc[extra] = 0.0

    debt.loc["Opening senior", "Close"] = 0.0
    debt.loc["Opening subordinated", "Close"] = 0.0
    debt.loc["Opening total debt", "Close"] = 0.0
    debt.loc["Senior interest", "Close"] = 0.0
    debt.loc["Subordinated interest", "Close"] = 0.0
    debt.loc["Total interest", "Close"] = 0.0
    debt.loc["Scheduled mandatory amortization", "Close"] = 0.0
    debt.loc["Mandatory amortization", "Close"] = 0.0
    debt.loc["Amortization shortfall", "Close"] = 0.0
    debt.loc["Optional cash sweep", "Close"] = 0.0
    debt.loc["Total senior repayment", "Close"] = 0.0
    debt.loc["Closing senior", "Close"] = txn.new_senior_debt
    debt.loc["Closing subordinated", "Close"] = txn.new_subordinated_debt
    debt.loc["Closing total debt", "Close"] = txn.new_senior_debt + txn.new_subordinated_debt

    cash.loc[:, "Close"] = 0.0
    # Funding is instantaneous. P&L and cash-flow lines are not measured at Close;
    # leave them blank rather than showing a calculated zero.
    for row in (
        "EBITDA",
        "Cash interest",
        "EBT",
        "Taxes",
        "Net income",
        "D&A",
        "Capex",
        "Change in NWC",
        "FCF before principal",
        "Debt principal repaid",
    ):
        cash.loc[row, "Close"] = float("nan")
    cash.loc["Closing cash", "Close"] = assumptions.cash_to_balance_sheet
    cash.loc["Minimum cash", "Close"] = assumptions.minimum_cash
    cash.loc["Surplus cash", "Close"] = surplus_cash(
        assumptions.cash_to_balance_sheet, assumptions.minimum_cash
    )
    cash.loc["Min-cash breach", "Close"] = max(
        0.0, assumptions.minimum_cash - assumptions.cash_to_balance_sheet
    )

    opening_senior = txn.new_senior_debt
    opening_sub = txn.new_subordinated_debt
    opening_cash = assumptions.cash_to_balance_sheet
    original_senior = txn.new_senior_debt
    shortfall_notes: list[str] = []

    for year in years:
        # Interest uses opening balances (independent of this year's sweep).
        interest = (
            opening_senior * assumptions.senior_interest_rate
            + opening_sub * assumptions.subordinated_interest_rate
        )
        ebit = float(ops.loc["EBIT", year])
        ebitda = float(ops.loc["EBITDA", year])
        da = float(ops.loc["D&A", year])
        capex = float(ops.loc["Capex", year])
        delta_nwc = float(ops.loc["Change in NWC", year])
        ebt = period_taxable_income(ebit, interest)
        taxes = period_taxes(ebt, assumptions.tax_rate)
        ni = ebt - taxes
        fcf = period_fcf_before_principal(ebitda, interest, taxes, capex, delta_nwc)
        available = cash_available_for_debt_paydown(
            opening_cash, fcf, assumptions.minimum_cash
        )
        period = roll_debt_period(
            opening_senior=opening_senior,
            opening_subordinated=opening_sub,
            original_senior=original_senior,
            senior_interest_rate=assumptions.senior_interest_rate,
            subordinated_interest_rate=assumptions.subordinated_interest_rate,
            mandatory_amort_pct=assumptions.senior_mandatory_amort_pct,
            cash_sweep_pct=assumptions.cash_sweep_pct,
            cash_available=available,
        )
        closing_cash = opening_cash + fcf - period.total_repayment
        min_cash_breach = max(0.0, assumptions.minimum_cash - closing_cash)
        if period.amortization_shortfall > 1e-9:
            shortfall_notes.append(
                f"{year}: scheduled mandatory {period.scheduled_mandatory:.4f} "
                f"exceeds cash available after min-cash reserve "
                f"({period.cash_available_for_debt:.4f}); unpaid "
                f"{period.amortization_shortfall:.4f}. Minimum cash was not drawn."
            )
        if min_cash_breach > 1e-9:
            shortfall_notes.append(
                f"{year}: closing cash {closing_cash:.4f} is below minimum cash "
                f"{assumptions.minimum_cash:.4f} even with no further principal "
                f"(operating / interest cash hole of {min_cash_breach:.4f})."
            )

        debt.loc["Opening senior", year] = period.opening_senior
        debt.loc["Opening subordinated", year] = period.opening_subordinated
        debt.loc["Opening total debt", year] = (
            period.opening_senior + period.opening_subordinated
        )
        debt.loc["Senior interest", year] = period.senior_interest
        debt.loc["Subordinated interest", year] = period.subordinated_interest
        debt.loc["Total interest", year] = period.total_interest
        debt.loc["Scheduled mandatory amortization", year] = period.scheduled_mandatory
        debt.loc["Mandatory amortization", year] = period.mandatory_amortization
        debt.loc["Amortization shortfall", year] = period.amortization_shortfall
        debt.loc["Optional cash sweep", year] = period.optional_repayment
        debt.loc["Total senior repayment", year] = period.total_repayment
        debt.loc["Closing senior", year] = period.closing_senior
        debt.loc["Closing subordinated", year] = period.closing_subordinated
        debt.loc["Closing total debt", year] = period.closing_total

        cash.loc["Opening cash", year] = opening_cash
        cash.loc["EBITDA", year] = ebitda
        cash.loc["Cash interest", year] = interest
        cash.loc["EBT", year] = ebt
        cash.loc["Taxes", year] = taxes
        cash.loc["Net income", year] = ni
        cash.loc["D&A", year] = da
        cash.loc["Capex", year] = capex
        cash.loc["Change in NWC", year] = delta_nwc
        cash.loc["FCF before principal", year] = fcf
        cash.loc["Debt principal repaid", year] = period.total_repayment
        cash.loc["Closing cash", year] = closing_cash
        cash.loc["Minimum cash", year] = assumptions.minimum_cash
        cash.loc["Surplus cash", year] = surplus_cash(closing_cash, assumptions.minimum_cash)
        cash.loc["Min-cash breach", year] = min_cash_breach

        ops_full.loc["Interest", year] = interest
        ops_full.loc["EBT", year] = ebt
        ops_full.loc["Taxes", year] = taxes
        ops_full.loc["Net income", year] = ni
        ops_full.loc["FCF before principal", year] = fcf

        opening_senior = period.closing_senior
        opening_sub = period.closing_subordinated
        opening_cash = closing_cash

    exit_year = years[-1]
    exit_ebitda = float(ops.loc["EBITDA", exit_year])
    exit_ev = exit_enterprise_value(exit_ebitda, assumptions.exit_ebitda_multiple)
    closing_debt = float(debt.loc["Closing total debt", exit_year])
    closing_cash = float(cash.loc["Closing cash", exit_year])
    exit_eq = exit_equity_value(
        exit_ev, closing_debt, closing_cash, assumptions.minimum_cash
    )
    exit_nd = exit_net_debt(closing_debt, closing_cash, assumptions.minimum_cash)
    excess_at_exit = surplus_cash(closing_cash, assumptions.minimum_cash)

    sponsor_cfs = [-txn.sponsor_equity] + [0.0] * (assumptions.holding_period_years - 1) + [exit_eq]
    moic = 0.0 if exit_eq <= 0 else gross_moic(exit_eq, txn.sponsor_equity)
    irr = annualized_irr(sponsor_cfs)

    amort_short_total = float(debt.loc["Amortization shortfall", years].sum())
    min_cash_breach_total = float(cash.loc["Min-cash breach", years].sum())
    financing = FinancingStatus(
        has_shortfall=amort_short_total > 1e-9 or min_cash_breach_total > 1e-9,
        total_amortization_shortfall=amort_short_total,
        total_min_cash_breach=min_cash_breach_total,
        notes=tuple(shortfall_notes),
    )

    result = LBOResult(
        assumptions=assumptions,
        scenario_name=scenario_name,
        transaction=txn,
        sources=sources,
        uses=uses,
        operating_schedule=ops_full,
        debt_schedule=debt,
        cash_schedule=cash,
        exit_enterprise_value=exit_ev,
        exit_equity_value=exit_eq,
        exit_net_debt=exit_nd,
        excess_cash_at_exit=excess_at_exit,
        sponsor_cash_flows=sponsor_cfs,
        gross_moic=moic,
        irr=irr,
        financing=financing,
        checks=[],
    )
    result.checks = validate_lbo_result(result)
    return result
