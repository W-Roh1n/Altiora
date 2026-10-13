"""Exit valuation and sponsor return metrics.

Formulas
--------
Exit EV = exit-year EBITDA × exit EV / EBITDA multiple

Cash in the equity bridge
    Enterprise value is a cash-free / debt-free multiple of EBITDA, so it
    already assumes the business has the cash required to operate.
    Surplus cash = closing cash − minimum cash (can be negative if cash
    has fallen below the operating floor).
    Exit net debt = closing gross debt − surplus cash
                  = closing gross debt − closing cash + minimum cash
    Exit equity   = max(0, Exit EV − exit net debt)
                  = max(0, Exit EV − gross debt + closing cash − minimum cash)

    Using all closing cash (including minimum cash) as a net-debt
    reduction would credit trapped operating cash a second time.

Sponsor MOIC (gross) = total sponsor inflows / total sponsor outflows
Sponsor IRR is the annual rate r solving Σ CF_t / (1+r)^t = 0
  over actual modeled cash flows (entry at t=0, exit at t=N, interim
  dividends if any). Newton-Raphson is used; no closed-form shortcut
  that ignores interim cash flows.
"""

from __future__ import annotations

from typing import Sequence


class ReturnsError(ValueError):
    """Raised when return metrics cannot be computed from the cash flows."""


def exit_enterprise_value(exit_ebitda: float, exit_multiple: float) -> float:
    return exit_ebitda * exit_multiple


def surplus_cash(closing_cash: float, minimum_cash: float) -> float:
    """Cash above the operating floor; negative if the floor is breached."""
    return closing_cash - minimum_cash


def exit_net_debt(closing_debt: float, closing_cash: float, minimum_cash: float) -> float:
    """Gross debt minus surplus cash (minimum cash is not treated as surplus)."""
    return closing_debt - surplus_cash(closing_cash, minimum_cash)


def exit_equity_value(
    exit_ev: float,
    closing_debt: float,
    closing_cash: float,
    minimum_cash: float = 0.0,
) -> float:
    """Equity proceeds on exit, floored at zero (limited liability)."""
    return max(0.0, exit_ev - exit_net_debt(closing_debt, closing_cash, minimum_cash))


def gross_moic(inflows: float, outflows: float) -> float:
    if outflows <= 0:
        raise ReturnsError("Sponsor equity outflow must be positive to compute MOIC")
    return inflows / outflows


def npv(rate: float, cash_flows: Sequence[float]) -> float:
    return sum(cf / (1.0 + rate) ** t for t, cf in enumerate(cash_flows))


def npv_derivative(rate: float, cash_flows: Sequence[float]) -> float:
    return sum(-t * cf / (1.0 + rate) ** (t + 1) for t, cf in enumerate(cash_flows))


def annualized_irr(
    cash_flows: Sequence[float],
    guess: float = 0.15,
    tolerance: float = 1e-10,
    max_iterations: int = 100,
) -> float:
    """IRR of equally spaced annual cash flows via Newton-Raphson.

    Returns float('nan') if the series has no sign change (undefined IRR).
    """
    flows = [float(x) for x in cash_flows]
    if len(flows) < 2:
        raise ReturnsError("IRR requires at least two cash flows")
    if not any(x > 0 for x in flows) or not any(x < 0 for x in flows):
        return float("nan")

    rate = guess
    for _ in range(max_iterations):
        value = npv(rate, flows)
        deriv = npv_derivative(rate, flows)
        if abs(deriv) < 1e-16:
            break
        next_rate = rate - value / deriv
        if next_rate <= -0.999999:
            next_rate = -0.999999
        if abs(next_rate - rate) < tolerance:
            return next_rate
        rate = next_rate
    return rate
