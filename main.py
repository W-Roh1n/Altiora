"""Command-line demo of the Altiora LBO engine.

Prints the Monster Beverage hypothetical LBO. Filing anchors are historical.
The purchase multiple, acquisition debt, fees, growth path, and exit multiple
are assumptions. Not a valuation and not investment advice.
The Streamlit application lives in app.py.
"""

from __future__ import annotations

import pandas as pd

from src.assumptions import STANDARD_SCENARIOS, apply_scenario
from src.filings import monster_hypothetical_case
from src.lbo_model import LBOResult, run_lbo

pd.set_option("display.float_format", lambda x: f"{x:,.2f}")
pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 20)


def _print_result(result: LBOResult) -> None:
    a = result.assumptions
    t = result.transaction
    print("=" * 78)
    print(f"{a.company_name}")
    print(a.notes)
    print(f"Units: {a.units} {a.currency}  |  Scenario: {result.scenario_name}")
    print("-" * 78)
    print("Transaction")
    print(f"  LTM EBITDA                 {a.ltm_ebitda:,.2f}")
    print(f"  Entry EV ({a.entry_ebitda_multiple:.1f}x)         {t.entry_enterprise_value:,.2f}")
    print(f"  Sponsor equity             {t.sponsor_equity:,.2f}")
    print(f"  Total uses                 {t.total_uses:,.2f}")
    print(f"  Total sources              {t.total_sources:,.2f}")
    print()
    print("Sources")
    print(result.sources.to_string())
    print()
    print("Uses")
    print(result.uses.to_string())
    print()
    print("Operating schedule")
    print(result.operating_schedule.to_string())
    print()
    print("Debt schedule")
    print(result.debt_schedule.to_string())
    print()
    print("Cash / FCF schedule")
    print(result.cash_schedule.to_string())
    print()
    print("Returns (gross sponsor, before fund fees and carry)")
    print(f"  Exit EV                    {result.exit_enterprise_value:,.2f}")
    last = a.year_labels[-1]
    print(f"  Gross debt at exit         {float(result.debt_schedule.loc['Closing total debt', last]):,.2f}")
    print(f"  Closing cash               {float(result.cash_schedule.loc['Closing cash', last]):,.2f}")
    print(f"  Minimum cash (not surplus) {a.minimum_cash:,.2f}")
    print(f"  Surplus cash               {result.excess_cash_at_exit:,.2f}")
    print(f"  Exit net debt              {result.exit_net_debt:,.2f}")
    print(f"  Exit equity value          {result.exit_equity_value:,.2f}")
    print(f"  Sponsor CF t=0 (equity)    {result.sponsor_cash_flows[0]:,.2f}")
    print(f"  Sponsor CF t=N (exit)      {result.sponsor_cash_flows[-1]:,.2f}")
    print(f"  Gross MOIC                 {result.gross_moic:.2f}x")
    print(f"  Gross IRR (annual)         {result.irr:.1%}")
    passed = [c.name for c in result.checks if c.passed]
    flagged = [c for c in result.checks if not c.passed]
    print("Validation passed:", ", ".join(passed))
    if flagged:
        print("FLAGS:", "; ".join(f"{c.name}: {c.detail}" for c in flagged))
    elif result.financing.has_shortfall:
        print("FLAGS:", "; ".join(result.financing.notes))
    print()


def main() -> None:
    base = monster_hypothetical_case()
    print("Altiora — educational LBO model")
    print(
        "Monster Beverage historical anchors are from the FY2025 Form 10-K. "
        "The acquisition case is hypothetical and is not investment advice.\n"
    )
    for key, adj in STANDARD_SCENARIOS.items():
        case = apply_scenario(base, adj) if key != "base" else base
        result = run_lbo(case, scenario_name=key)
        _print_result(result)


if __name__ == "__main__":
    main()
