"""Automated tests for the Phase 1 LBO engine."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.assumptions import (
    AssumptionError,
    DealAssumptions,
    apply_scenario,
    illustrative_base_case,
    standard_scenarios,
)
from src.debt_schedule import cash_available_for_debt_paydown, roll_debt_period
from src.lbo_model import build_transaction, run_lbo
from src.operating_model import project_operations
from src.returns import annualized_irr, exit_enterprise_value, exit_net_debt, gross_moic
from src.validation import ValidationError, check_sources_equal_uses, validate_lbo_result


def _base(**overrides: object) -> DealAssumptions:
    return illustrative_base_case().with_updates(**overrides)


def test_sample_case_is_labeled_illustrative() -> None:
    case = illustrative_base_case()
    assert case.is_illustrative
    assert "illustrative" in case.notes.lower()
    assert "not actual" in case.notes.lower()


def test_invalid_assumptions_rejected() -> None:
    with pytest.raises(AssumptionError):
        _base(ltm_revenue=0)
    with pytest.raises(AssumptionError):
        _base(holding_period_years=5, revenue_growth=(0.05,))
    with pytest.raises(AssumptionError):
        _base(is_illustrative=False)


def test_entry_ev_and_sources_equal_uses() -> None:
    a = illustrative_base_case()
    txn = build_transaction(a)
    expected_ev = a.ltm_revenue * a.ltm_ebitda_margin * a.entry_ebitda_multiple
    assert txn.entry_enterprise_value == pytest.approx(expected_ev)
    assert txn.equity_purchase_price == pytest.approx(expected_ev - a.existing_net_debt)
    assert txn.new_senior_debt == pytest.approx(a.senior_leverage * a.ltm_ebitda)
    assert txn.new_subordinated_debt == pytest.approx(a.subordinated_leverage * a.ltm_ebitda)
    assert txn.sponsor_equity == pytest.approx(
        txn.total_uses - txn.new_senior_debt - txn.new_subordinated_debt
    )
    assert txn.total_sources == pytest.approx(txn.total_uses)
    result = run_lbo(a)
    check = check_sources_equal_uses(result.sources, result.uses)
    assert check.passed


def test_operating_projections_compound_growth() -> None:
    a = illustrative_base_case()
    ops = project_operations(a)
    revenue = a.ltm_revenue
    for i, year in enumerate(a.year_labels):
        revenue *= 1.0 + a.revenue_growth[i]
        assert ops.loc["Revenue", year] == pytest.approx(revenue)
        assert ops.loc["EBITDA", year] == pytest.approx(revenue * a.ebitda_margin[i])
        assert ops.loc["EBIT", year] == pytest.approx(
            ops.loc["EBITDA", year] - ops.loc["D&A", year]
        )
        assert ops.loc["D&A", year] == pytest.approx(revenue * a.da_pct_of_revenue)
        assert ops.loc["Capex", year] == pytest.approx(revenue * a.capex_pct_of_revenue)


def test_nwc_delta_uses_ltm_as_opening() -> None:
    a = illustrative_base_case()
    ops = project_operations(a)
    opening = a.ltm_revenue * a.nwc_pct_of_revenue
    assert ops.loc["NWC", "LTM"] == pytest.approx(opening)
    assert ops.loc["Change in NWC", "Year 1"] == pytest.approx(
        ops.loc["NWC", "Year 1"] - opening
    )


def test_debt_repayments_cannot_exceed_principal() -> None:
    period = roll_debt_period(
        opening_senior=10.0,
        opening_subordinated=5.0,
        original_senior=100.0,
        senior_interest_rate=0.07,
        subordinated_interest_rate=0.10,
        mandatory_amort_pct=0.05,
        cash_sweep_pct=1.0,
        cash_available=1_000.0,
    )
    assert period.total_repayment == pytest.approx(10.0)
    assert period.closing_senior == pytest.approx(0.0)
    assert period.closing_subordinated == pytest.approx(5.0)
    assert period.closing_total >= 0


def test_mandatory_amort_capped_by_opening_and_cash() -> None:
    cash_constrained = roll_debt_period(
        opening_senior=50.0,
        opening_subordinated=0.0,
        original_senior=50.0,
        senior_interest_rate=0.0,
        subordinated_interest_rate=0.0,
        mandatory_amort_pct=0.20,
        cash_sweep_pct=1.0,
        cash_available=3.0,
    )
    assert cash_constrained.scheduled_mandatory == pytest.approx(10.0)
    assert cash_constrained.mandatory_amortization == pytest.approx(3.0)
    assert cash_constrained.amortization_shortfall == pytest.approx(7.0)
    assert cash_constrained.optional_repayment == pytest.approx(0.0)

    opening_constrained = roll_debt_period(
        opening_senior=2.0,
        opening_subordinated=0.0,
        original_senior=50.0,
        senior_interest_rate=0.0,
        subordinated_interest_rate=0.0,
        mandatory_amort_pct=0.20,
        cash_sweep_pct=0.0,
        cash_available=100.0,
    )
    assert opening_constrained.mandatory_amortization == pytest.approx(2.0)
    assert opening_constrained.closing_senior == pytest.approx(0.0)


def test_cash_available_respects_minimum_cash() -> None:
    assert cash_available_for_debt_paydown(5.0, 10.0, 5.0) == pytest.approx(10.0)
    assert cash_available_for_debt_paydown(5.0, -3.0, 5.0) == pytest.approx(0.0)
    assert cash_available_for_debt_paydown(8.0, -1.0, 5.0) == pytest.approx(2.0)


def test_full_model_debt_never_negative_and_rollforward() -> None:
    result = run_lbo(illustrative_base_case())
    debt = result.debt_schedule
    for year in illustrative_base_case().year_labels:
        opening = debt.loc["Opening senior", year]
        closing = debt.loc["Closing senior", year]
        repaid = debt.loc["Total senior repayment", year]
        assert closing == pytest.approx(opening - repaid)
        assert closing >= -1e-9
        assert repaid <= opening + 1e-9
        assert debt.loc["Closing subordinated", year] >= -1e-9


def test_interest_is_on_opening_balance() -> None:
    a = illustrative_base_case()
    result = run_lbo(a)
    y1 = result.debt_schedule["Year 1"]
    assert y1["Senior interest"] == pytest.approx(
        result.transaction.new_senior_debt * a.senior_interest_rate
    )
    assert y1["Subordinated interest"] == pytest.approx(
        result.transaction.new_subordinated_debt * a.subordinated_interest_rate
    )


def test_exit_and_returns_use_actual_cash_flows() -> None:
    a = illustrative_base_case()
    result = run_lbo(a)
    exit_year = a.year_labels[-1]
    expected_ev = exit_enterprise_value(
        float(result.operating_schedule.loc["EBITDA", exit_year]),
        a.exit_ebitda_multiple,
    )
    assert result.exit_enterprise_value == pytest.approx(expected_ev)
    closing_debt = float(result.debt_schedule.loc["Closing total debt", exit_year])
    closing_cash = float(result.cash_schedule.loc["Closing cash", exit_year])
    expected_nd = exit_net_debt(closing_debt, closing_cash, a.minimum_cash)
    expected_eq = expected_ev - expected_nd
    assert result.exit_net_debt == pytest.approx(expected_nd)
    assert result.exit_equity_value == pytest.approx(expected_eq)
    # Minimum cash is not treated as surplus (would double-count vs cash-free EV).
    assert result.exit_equity_value == pytest.approx(
        expected_ev - closing_debt + closing_cash - a.minimum_cash
    )
    # Closing cash is not added a second time on top of exit equity.
    assert result.sponsor_cash_flows[-1] == pytest.approx(result.exit_equity_value)
    assert result.sponsor_cash_flows[-1] != pytest.approx(
        result.exit_equity_value + closing_cash
    )
    assert result.sponsor_cash_flows[0] == pytest.approx(-result.transaction.sponsor_equity)
    assert result.sponsor_cash_flows[-1] == pytest.approx(result.exit_equity_value)
    assert result.gross_moic == pytest.approx(
        gross_moic(result.exit_equity_value, result.transaction.sponsor_equity)
    )
    n = a.holding_period_years
    expected_irr = result.gross_moic ** (1.0 / n) - 1.0
    assert result.irr == pytest.approx(expected_irr, rel=1e-6)
    assert annualized_irr(result.sponsor_cash_flows) == pytest.approx(result.irr, rel=1e-6)


def test_irr_two_period_known_value() -> None:
    # Invest 100, receive 121 after two years → 10% IRR.
    assert annualized_irr([-100.0, 0.0, 121.0]) == pytest.approx(0.10, rel=1e-8)


def test_irr_undefined_without_sign_change() -> None:
    assert math.isnan(annualized_irr([1.0, 1.0, 1.0]))


def test_taxes_have_zero_floor() -> None:
    high_rate = illustrative_base_case().with_updates(
        senior_interest_rate=0.50,
        subordinated_interest_rate=0.50,
    )
    result = run_lbo(high_rate)
    years = list(high_rate.year_labels)
    taxes = result.cash_schedule.loc["Taxes", years]
    ebt = result.cash_schedule.loc["EBT", years]
    assert (taxes >= -1e-9).all()
    for year in years:
        if ebt[year] <= 0:
            assert taxes[year] == pytest.approx(0.0)
        else:
            assert taxes[year] == pytest.approx(high_rate.tax_rate * ebt[year])


def test_cash_sweep_reduces_senior_debt() -> None:
    swept = run_lbo(illustrative_base_case().with_updates(cash_sweep_pct=1.0))
    unswept = run_lbo(illustrative_base_case().with_updates(cash_sweep_pct=0.0))
    last = illustrative_base_case().year_labels[-1]
    assert swept.debt_schedule.loc["Closing senior", last] < unswept.debt_schedule.loc["Closing senior", last]


def test_base_downside_upside_scenarios() -> None:
    base = illustrative_base_case()
    scenarios = standard_scenarios()
    results = {
        name: run_lbo(apply_scenario(base, adj) if name != "base" else base, scenario_name=name)
        for name, adj in scenarios.items()
    }
    assert results["downside"].irr < results["base"].irr < results["upside"].irr
    assert results["downside"].gross_moic < results["base"].gross_moic < results["upside"].gross_moic
    last = base.year_labels[-1]
    assert (
        results["downside"].operating_schedule.loc["Revenue", last]
        < results["base"].operating_schedule.loc["Revenue", last]
        < results["upside"].operating_schedule.loc["Revenue", last]
    )


def test_validation_rejects_imbalanced_sources() -> None:
    result = run_lbo(illustrative_base_case())
    result.sources = result.sources.copy()
    result.sources.iloc[0] += 10.0
    with pytest.raises(ValidationError):
        validate_lbo_result(result)


def test_exit_equity_excludes_trapped_minimum_cash() -> None:
    result = run_lbo(illustrative_base_case())
    last = illustrative_base_case().year_labels[-1]
    gross_debt = float(result.debt_schedule.loc["Closing total debt", last])
    cash = float(result.cash_schedule.loc["Closing cash", last])
    min_cash = illustrative_base_case().minimum_cash
    naive_all_cash = result.exit_enterprise_value - (gross_debt - cash)
    assert cash == pytest.approx(min_cash)
    assert result.excess_cash_at_exit == pytest.approx(0.0)
    assert result.exit_equity_value == pytest.approx(naive_all_cash - min_cash)
    assert result.exit_net_debt == pytest.approx(gross_debt)


def test_funding_date_does_not_invent_operating_cash_flow() -> None:
    """Close is the funding instant. Operating lines there are blank, not zero."""
    result = run_lbo(illustrative_base_case())
    for row in ("EBITDA", "Cash interest", "FCF before principal", "Debt principal repaid"):
        assert math.isnan(float(result.cash_schedule.loc[row, "Close"]))
    assert float(result.cash_schedule.loc["Closing cash", "Close"]) == pytest.approx(8.0)
    assert float(result.cash_schedule.loc["EBITDA", "Year 1"]) > 0


def test_illustrative_downside_covers_mandatory_amort() -> None:
    """The published downside overlay does not miss scheduled amort on the sample deal."""
    base = illustrative_base_case()
    result = run_lbo(apply_scenario(base, standard_scenarios()["downside"]), "downside")
    years = list(base.year_labels)
    assert float(result.debt_schedule.loc["Amortization shortfall", years].sum()) == pytest.approx(0.0)
    assert not result.financing.has_shortfall
    for year in years:
        avail = (
            float(result.cash_schedule.loc["Opening cash", year])
            + float(result.cash_schedule.loc["FCF before principal", year])
            - base.minimum_cash
        )
        scheduled = float(result.debt_schedule.loc["Scheduled mandatory amortization", year])
        assert avail + 1e-9 >= scheduled
        assert float(result.cash_schedule.loc["Closing cash", year]) == pytest.approx(
            base.minimum_cash
        )


def test_financing_shortfall_flagged_when_mandatory_exceeds_available_cash() -> None:
    stressed = illustrative_base_case().with_updates(senior_mandatory_amort_pct=0.50)
    result = run_lbo(stressed)
    y1_sched = float(result.debt_schedule.loc["Scheduled mandatory amortization", "Year 1"])
    y1_paid = float(result.debt_schedule.loc["Mandatory amortization", "Year 1"])
    y1_short = float(result.debt_schedule.loc["Amortization shortfall", "Year 1"])
    y1_cash = float(result.cash_schedule.loc["Closing cash", "Year 1"])
    assert y1_sched == pytest.approx(0.50 * result.transaction.new_senior_debt)
    assert y1_short == pytest.approx(y1_sched - y1_paid)
    assert y1_short > 1.0
    assert y1_cash == pytest.approx(stressed.minimum_cash)
    assert result.financing.has_shortfall
    assert result.financing.total_amortization_shortfall == pytest.approx(
        float(result.debt_schedule.loc["Amortization shortfall", list(stressed.year_labels)].sum())
    )
    flags = [c for c in result.checks if c.name == "financing_shortfall"]
    assert flags and not flags[0].passed
    assert "Minimum cash was not drawn" in flags[0].detail


def test_min_cash_breach_flagged_when_fcf_cannot_hold_floor() -> None:
    hole = illustrative_base_case().with_updates(
        capex_pct_of_revenue=0.40,
        senior_mandatory_amort_pct=0.05,
        cash_sweep_pct=1.0,
    )
    result = run_lbo(hole)
    y1_cash = float(result.cash_schedule.loc["Closing cash", "Year 1"])
    y1_paid = float(result.debt_schedule.loc["Mandatory amortization", "Year 1"])
    assert y1_cash < hole.minimum_cash
    assert y1_paid == pytest.approx(0.0)
    assert result.financing.has_shortfall
    assert result.financing.total_min_cash_breach > 0


def test_sponsor_returns_use_equity_plug_and_exit_proceeds() -> None:
    result = run_lbo(illustrative_base_case())
    assert result.sponsor_cash_flows[0] == pytest.approx(-result.transaction.sponsor_equity)
    assert result.sponsor_cash_flows[0] != pytest.approx(-result.transaction.equity_purchase_price)
    assert result.sponsor_cash_flows[-1] == pytest.approx(result.exit_equity_value)
    assert result.gross_moic == pytest.approx(
        result.exit_equity_value / result.transaction.sponsor_equity
    )


def test_independent_recalculation_of_illustrative_base() -> None:
    """Audit the sample deal from assumptions without reading engine outputs first."""
    a = illustrative_base_case()
    ltm_ebitda = a.ltm_revenue * a.ltm_ebitda_margin
    entry_ev = ltm_ebitda * a.entry_ebitda_multiple
    uses = entry_ev + a.transaction_fees_pct_of_ev * entry_ev + a.cash_to_balance_sheet
    senior = a.senior_leverage * ltm_ebitda
    sub = a.subordinated_leverage * ltm_ebitda
    sponsor = uses - senior - sub

    rev = a.ltm_revenue
    nwc_prior = a.ltm_revenue * a.nwc_pct_of_revenue
    os, cash = senior, a.cash_to_balance_sheet
    for i, year_growth in enumerate(a.revenue_growth):
        rev *= 1.0 + year_growth
        ebitda = rev * a.ebitda_margin[i]
        interest = os * a.senior_interest_rate + sub * a.subordinated_interest_rate
        ebit = ebitda - rev * a.da_pct_of_revenue
        ebt = ebit - interest
        tax = a.tax_rate * ebt if ebt > 0 else 0.0
        capex = rev * a.capex_pct_of_revenue
        nwc = rev * a.nwc_pct_of_revenue
        fcf = ebitda - interest - tax - capex - (nwc - nwc_prior)
        nwc_prior = nwc
        avail = max(0.0, cash + fcf - a.minimum_cash)
        sched = min(a.senior_mandatory_amort_pct * senior, os)
        mand = min(sched, avail)
        opt = min(a.cash_sweep_pct * (avail - mand), os - mand)
        cash = cash + fcf - mand - opt
        os = os - mand - opt

    exit_ev = (rev * a.ebitda_margin[-1]) * a.exit_ebitda_multiple
    exit_nd = os + sub - (cash - a.minimum_cash)
    exit_eq = exit_ev - exit_nd
    moic = exit_eq / sponsor
    irr = moic ** (1.0 / a.holding_period_years) - 1.0

    engine = run_lbo(a)
    assert engine.transaction.entry_enterprise_value == pytest.approx(entry_ev)
    assert engine.transaction.total_uses == pytest.approx(uses)
    assert engine.transaction.sponsor_equity == pytest.approx(sponsor)
    assert engine.exit_enterprise_value == pytest.approx(exit_ev)
    assert engine.exit_net_debt == pytest.approx(exit_nd)
    assert engine.exit_equity_value == pytest.approx(exit_eq)
    assert engine.gross_moic == pytest.approx(moic)
    assert engine.irr == pytest.approx(irr, rel=1e-6)
    assert engine.sponsor_cash_flows[0] == pytest.approx(-sponsor)
    assert engine.sponsor_cash_flows[-1] == pytest.approx(exit_eq)


def test_outputs_are_not_hardcoded() -> None:
    a = illustrative_base_case()
    r1 = run_lbo(a)
    r2 = run_lbo(a.with_updates(entry_ebitda_multiple=9.0))
    assert r2.transaction.entry_enterprise_value != r1.transaction.entry_enterprise_value
    assert r2.transaction.sponsor_equity != r1.transaction.sponsor_equity
    r3 = run_lbo(a.with_updates(exit_ebitda_multiple=10.0))
    assert r3.exit_enterprise_value != r1.exit_enterprise_value
    assert r3.gross_moic != r1.gross_moic
