"""Integrity checks for a completed LBO run.

Checks
------
1. Total sources equal total uses.
2. Debt roll-forward identity holds each year:
   opening − mandatory − optional = closing
3. Closing debt balances are never negative.
4. Principal repaid never exceeds opening principal.
5. Gross MOIC equals total inflows / total outflows from the sponsor CF series.
6. For a two-point cash flow (entry + exit only), IRR agrees with
   MOIC^(1/N) − 1 within tolerance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from src.returns import annualized_irr, exit_equity_value, exit_net_debt, gross_moic


class ValidationError(AssertionError):
    """Raised when an LBO result fails an integrity check."""


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def check_sources_equal_uses(sources: pd.Series, uses: pd.Series) -> CheckResult:
    total_s = float(sources.sum())
    total_u = float(uses.sum())
    ok = _close(total_s, total_u)
    return CheckResult(
        "sources_equal_uses",
        ok,
        f"sources={total_s:.6f} uses={total_u:.6f}",
    )


def check_debt_rollforward(debt: pd.DataFrame) -> CheckResult:
    years = [c for c in debt.columns if str(c).startswith("Year")]
    for year in years:
        opening = float(debt.loc["Opening senior", year])
        mandatory = float(debt.loc["Mandatory amortization", year])
        optional = float(debt.loc["Optional cash sweep", year])
        closing = float(debt.loc["Closing senior", year])
        implied = opening - mandatory - optional
        if not _close(implied, closing):
            return CheckResult(
                "debt_rollforward",
                False,
                f"{year}: opening {opening} − mand {mandatory} − sweep {optional} "
                f"!= closing {closing}",
            )
        if closing < -1e-8 or float(debt.loc["Closing subordinated", year]) < -1e-8:
            return CheckResult("debt_rollforward", False, f"{year}: negative closing debt")
        if mandatory + optional - opening > 1e-8:
            return CheckResult(
                "debt_rollforward",
                False,
                f"{year}: repayments exceed opening senior principal",
            )
    return CheckResult("debt_rollforward", True, "roll-forward identities hold")


def check_non_negative_debt(debt: pd.DataFrame) -> CheckResult:
    numeric = debt.select_dtypes(include="number")
    balances = numeric.loc[
        [
            "Opening senior",
            "Opening subordinated",
            "Closing senior",
            "Closing subordinated",
            "Closing total debt",
        ]
    ]
    if (balances < -1e-8).any().any():
        return CheckResult("non_negative_debt", False, "negative debt balance detected")
    return CheckResult("non_negative_debt", True, "all debt balances >= 0")


def check_exit_bridge(result: object) -> CheckResult:
    """Exit equity = EV − (gross debt − surplus cash); cash is not added again to CFs."""
    years = [c for c in result.debt_schedule.columns if str(c).startswith("Year")]
    exit_year = years[-1]
    closing_debt = float(result.debt_schedule.loc["Closing total debt", exit_year])
    closing_cash = float(result.cash_schedule.loc["Closing cash", exit_year])
    min_cash = float(result.assumptions.minimum_cash)
    expected_nd = exit_net_debt(closing_debt, closing_cash, min_cash)
    expected_eq = exit_equity_value(
        result.exit_enterprise_value, closing_debt, closing_cash, min_cash
    )
    if not _close(expected_nd, result.exit_net_debt):
        return CheckResult(
            "exit_bridge",
            False,
            f"exit net debt {result.exit_net_debt} != EV-bridge {expected_nd}",
        )
    if not _close(expected_eq, result.exit_equity_value):
        return CheckResult(
            "exit_bridge",
            False,
            f"exit equity {result.exit_equity_value} != EV-bridge {expected_eq}",
        )
    if abs(result.exit_equity_value + result.exit_net_debt - result.exit_enterprise_value) > 1e-6:
        # Holds when equity is not floored at zero.
        if result.exit_equity_value > 1e-9:
            return CheckResult(
                "exit_bridge",
                False,
                "exit EV does not equal exit equity + exit net debt",
            )
    if not _close(result.sponsor_cash_flows[-1], result.exit_equity_value):
        return CheckResult(
            "exit_bridge",
            False,
            "sponsor terminal cash flow is not exit equity (possible cash double-count)",
        )
    if not _close(result.sponsor_cash_flows[0], -result.transaction.sponsor_equity):
        return CheckResult(
            "exit_bridge",
            False,
            "sponsor t=0 cash flow is not the sources-and-uses equity plug",
        )
    return CheckResult(
        "exit_bridge",
        True,
        (
            f"equity={result.exit_equity_value:.6f} net_debt={result.exit_net_debt:.6f} "
            f"(min cash {min_cash:.4f} excluded from surplus)"
        ),
    )


def check_financing_shortfall(result: object) -> CheckResult:
    """Failed check = a flag, not an identity error. Caller decides whether to raise."""
    if result.financing.has_shortfall:
        detail = "; ".join(result.financing.notes) or "financing shortfall"
        return CheckResult("financing_shortfall", False, detail)
    return CheckResult("financing_shortfall", True, "scheduled mandatory and min cash held")


def check_returns(sponsor_cash_flows: list[float], moic: float, irr: float) -> CheckResult:
    outflows = -sum(cf for cf in sponsor_cash_flows if cf < 0)
    inflows = sum(cf for cf in sponsor_cash_flows if cf > 0)
    implied_moic = 0.0 if inflows <= 0 else gross_moic(inflows, outflows)
    if not _close(implied_moic, moic, tol=1e-6):
        return CheckResult(
            "returns",
            False,
            f"stored MOIC {moic} != cash-flow MOIC {implied_moic}",
        )

    recomputed = annualized_irr(sponsor_cash_flows)
    if inflows <= 0:
        if not math.isnan(irr) or not math.isnan(recomputed):
            return CheckResult(
                "returns",
                False,
                f"expected undefined IRR when there are no inflows; stored={irr}",
            )
        return CheckResult("returns", True, "total loss: MOIC=0, IRR undefined")

    interim = sponsor_cash_flows[1:-1]
    if all(abs(x) < 1e-10 for x in interim):
        n = len(sponsor_cash_flows) - 1
        closed_form = implied_moic ** (1.0 / n) - 1.0
        if not _close(closed_form, irr, tol=1e-6) or not _close(recomputed, irr, tol=1e-5):
            return CheckResult(
                "returns",
                False,
                f"IRR {irr} inconsistent with MOIC^{{1/{n}}}-1={closed_form} "
                f"or recomputed {recomputed}",
            )
    elif not _close(recomputed, irr, tol=1e-5):
        return CheckResult("returns", False, f"stored IRR {irr} != recomputed {recomputed}")
    return CheckResult("returns", True, f"MOIC={moic:.6f} IRR={irr:.6f}")


def validate_lbo_result(result: object) -> list[CheckResult]:
    """Run integrity checks (raise) and credit flags (record, do not raise)."""
    integrity = [
        check_sources_equal_uses(result.sources, result.uses),
        check_debt_rollforward(result.debt_schedule),
        check_non_negative_debt(result.debt_schedule),
        check_returns(result.sponsor_cash_flows, result.gross_moic, result.irr),
        check_exit_bridge(result),
    ]
    failures = [c for c in integrity if not c.passed]
    if failures:
        detail = "; ".join(f"{c.name}: {c.detail}" for c in failures)
        raise ValidationError(detail)
    return integrity + [check_financing_shortfall(result)]
