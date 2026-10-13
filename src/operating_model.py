"""Operating projections and free-cash-flow identities.

Formulas
--------
Revenue_t = Revenue_{t-1} × (1 + g_t), with Revenue_0 = LTM revenue
EBITDA_t = Revenue_t × EBITDA margin_t
D&A_t = da_pct_of_revenue × Revenue_t
EBIT_t = EBITDA_t − D&A_t
Capex_t = capex_pct_of_revenue × Revenue_t
NWC_t = nwc_pct_of_revenue × Revenue_t
ΔNWC_t = NWC_t − NWC_{t-1}
EBT_t = EBIT_t − cash interest_t
Taxes_t = tax_rate × max(EBT_t, 0)   (no NOL / deferred-tax modeling)
Net income_t = EBT_t − Taxes_t
FCF before principal_t = EBITDA_t − cash interest_t − Taxes_t − Capex_t − ΔNWC_t

Interest is an input from the debt schedule (opening-balance convention),
so this module does not import the debt engine.
"""

from __future__ import annotations

import pandas as pd

from src.assumptions import DealAssumptions


def project_operations(assumptions: DealAssumptions) -> pd.DataFrame:
    """Build the pre-interest operating schedule (years as columns)."""
    years = assumptions.year_labels
    revenue = []
    prior = assumptions.ltm_revenue
    for growth in assumptions.revenue_growth:
        prior = prior * (1.0 + growth)
        revenue.append(prior)

    ebitda = [rev * margin for rev, margin in zip(revenue, assumptions.ebitda_margin)]
    da = [rev * assumptions.da_pct_of_revenue for rev in revenue]
    ebit = [ebitda_t - da_t for ebitda_t, da_t in zip(ebitda, da)]
    capex = [rev * assumptions.capex_pct_of_revenue for rev in revenue]
    nwc = [rev * assumptions.nwc_pct_of_revenue for rev in revenue]
    opening_nwc = assumptions.ltm_revenue * assumptions.nwc_pct_of_revenue
    delta_nwc = [nwc[0] - opening_nwc] + [nwc[i] - nwc[i - 1] for i in range(1, len(nwc))]

    rows = {
        "Revenue": revenue,
        "EBITDA": ebitda,
        "D&A": da,
        "EBIT": ebit,
        "Capex": capex,
        "NWC": nwc,
        "Change in NWC": delta_nwc,
    }
    schedule = pd.DataFrame(rows, index=years).T
    schedule.insert(0, "LTM", 0.0)
    schedule.loc["Revenue", "LTM"] = assumptions.ltm_revenue
    schedule.loc["EBITDA", "LTM"] = assumptions.ltm_ebitda
    schedule.loc["D&A", "LTM"] = assumptions.ltm_revenue * assumptions.da_pct_of_revenue
    schedule.loc["EBIT", "LTM"] = (
        schedule.loc["EBITDA", "LTM"] - schedule.loc["D&A", "LTM"]
    )
    schedule.loc["Capex", "LTM"] = assumptions.ltm_revenue * assumptions.capex_pct_of_revenue
    schedule.loc["NWC", "LTM"] = opening_nwc
    schedule.loc["Change in NWC", "LTM"] = 0.0
    return schedule


def period_taxable_income(ebit: float, cash_interest: float) -> float:
    return ebit - cash_interest


def period_taxes(ebt: float, tax_rate: float) -> float:
    """Cash taxes with a zero floor (losses do not generate a cash refund)."""
    if ebt <= 0:
        return 0.0
    return tax_rate * ebt


def period_fcf_before_principal(
    ebitda: float,
    cash_interest: float,
    taxes: float,
    capex: float,
    delta_nwc: float,
) -> float:
    """Cash generated after interest, tax, capex, and working capital, before debt principal."""
    return ebitda - cash_interest - taxes - capex - delta_nwc
