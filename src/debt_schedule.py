"""Debt roll-forward: interest, mandatory amortization, and cash sweep.

Conventions
-----------
- Interest is cash-pay on the *opening* principal (beginning-of-period).
  This avoids a circularity with the cash sweep.
- Mandatory amortization is a percentage of *original* senior principal.
- Subordinated debt is interest-only (bullet at exit).
- Cash sweep applies only to senior debt after mandatory amortization.
- Total principal repaid in a year cannot exceed opening principal.
- Closing principal is never negative.

Year t identities
-----------------
Interest_t = opening_senior_t × r_senior + opening_sub_t × r_sub
Scheduled mandatory_t = min(amort_pct × original_senior, opening_senior)
Mandatory paid_t = min(scheduled mandatory_t, cash_available)
Amortization shortfall_t = scheduled mandatory_t − mandatory paid_t
Optional_t = min(sweep_pct × max(cash_available − mandatory paid_t, 0),
                 opening_senior − mandatory paid_t)
Closing_senior_t = opening_senior_t − mandatory paid_t − Optional_t
Closing_sub_t = opening_sub_t

Cash available is computed *after* reserving minimum cash. Principal is
never paid by drawing cash below that floor. If scheduled mandatory
exceeds cash available, the unpaid amount is an amortization shortfall
(a financing gap), not a rewrite of the amort schedule.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DebtPeriod:
    opening_senior: float
    opening_subordinated: float
    senior_interest: float
    subordinated_interest: float
    total_interest: float
    scheduled_mandatory: float
    mandatory_amortization: float
    amortization_shortfall: float
    optional_repayment: float
    total_repayment: float
    closing_senior: float
    closing_subordinated: float
    closing_total: float
    cash_available_for_debt: float
    unused_sweep_capacity: float


def _clamp_non_negative(value: float) -> float:
    return value if value > 0.0 else 0.0


def cash_available_for_debt_paydown(
    opening_cash: float,
    fcf_before_principal: float,
    minimum_cash: float,
) -> float:
    """Cash that can be used for principal without breaching minimum cash."""
    return _clamp_non_negative(opening_cash + fcf_before_principal - minimum_cash)


def roll_debt_period(
    *,
    opening_senior: float,
    opening_subordinated: float,
    original_senior: float,
    senior_interest_rate: float,
    subordinated_interest_rate: float,
    mandatory_amort_pct: float,
    cash_sweep_pct: float,
    cash_available: float,
) -> DebtPeriod:
    """Advance senior and subordinated balances by one annual period."""
    opening_senior = _clamp_non_negative(opening_senior)
    opening_subordinated = _clamp_non_negative(opening_subordinated)
    cash_available = _clamp_non_negative(cash_available)

    senior_interest = opening_senior * senior_interest_rate
    subordinated_interest = opening_subordinated * subordinated_interest_rate

    scheduled_amort = min(
        _clamp_non_negative(mandatory_amort_pct * original_senior),
        opening_senior,
    )
    mandatory = min(scheduled_amort, cash_available)
    amort_shortfall = _clamp_non_negative(scheduled_amort - mandatory)

    remaining_senior = opening_senior - mandatory
    remaining_cash = cash_available - mandatory
    optional = min(cash_sweep_pct * remaining_cash, remaining_senior)
    optional = _clamp_non_negative(optional)

    total_repayment = mandatory + optional
    if total_repayment - opening_senior > 1e-10:
        raise RuntimeError("Debt repayment exceeded opening senior principal")

    closing_senior = opening_senior - total_repayment
    if closing_senior < -1e-10:
        raise RuntimeError("Senior debt balance went negative")
    closing_senior = _clamp_non_negative(closing_senior)

    closing_sub = opening_subordinated
    return DebtPeriod(
        opening_senior=opening_senior,
        opening_subordinated=opening_subordinated,
        senior_interest=senior_interest,
        subordinated_interest=subordinated_interest,
        total_interest=senior_interest + subordinated_interest,
        scheduled_mandatory=scheduled_amort,
        mandatory_amortization=mandatory,
        amortization_shortfall=amort_shortfall,
        optional_repayment=optional,
        total_repayment=total_repayment,
        closing_senior=closing_senior,
        closing_subordinated=closing_sub,
        closing_total=closing_senior + closing_sub,
        cash_available_for_debt=cash_available,
        unused_sweep_capacity=_clamp_non_negative(remaining_cash - optional),
    )
