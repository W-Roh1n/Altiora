"""Validated deal assumptions for the LBO engine.

All sample figures are illustrative hypotheticals, not actual company financials.

Conventions
-----------
- Currency amounts are in millions of USD unless noted otherwise.
- Rates, margins, and growth figures are decimals (0.18 = 18%).
- Entry / exit multiples are Enterprise Value / EBITDA.
- Holding period is in whole years; cash flows are modeled annually.
- Senior leverage and subordinated leverage are multiples of LTM EBITDA.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping


class AssumptionError(ValueError):
    """Raised when deal assumptions fail validation."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssumptionError(message)


@dataclass(frozen=True)
class DealAssumptions:
    """Inputs required to run a single LBO case.

    Attributes are documented as modeling inputs. Calculated outputs
    (entry EV, sponsor equity, IRR, etc.) are never stored here.
    """

    company_name: str
    is_illustrative: bool
    currency: str
    units: str

    ltm_revenue: float
    ltm_ebitda_margin: float
    revenue_growth: tuple[float, ...]
    ebitda_margin: tuple[float, ...]

    da_pct_of_revenue: float
    capex_pct_of_revenue: float
    nwc_pct_of_revenue: float

    entry_ebitda_multiple: float
    exit_ebitda_multiple: float
    holding_period_years: int

    senior_leverage: float
    subordinated_leverage: float
    senior_interest_rate: float
    subordinated_interest_rate: float
    senior_mandatory_amort_pct: float
    cash_sweep_pct: float

    tax_rate: float
    transaction_fees_pct_of_ev: float
    cash_to_balance_sheet: float
    minimum_cash: float
    existing_net_debt: float

    notes: str = ""

    def __post_init__(self) -> None:
        n = self.holding_period_years
        _require(self.company_name.strip() != "", "company_name is required")
        _require(self.is_illustrative, "Sample cases must be labeled illustrative")
        _require(n >= 1, "holding_period_years must be at least 1")
        _require(len(self.revenue_growth) == n, "revenue_growth must cover each projection year")
        _require(len(self.ebitda_margin) == n, "ebitda_margin must cover each projection year")
        _require(self.ltm_revenue > 0, "ltm_revenue must be positive")
        _require(0 < self.ltm_ebitda_margin < 1, "ltm_ebitda_margin must be between 0 and 1")
        _require(all(-0.5 < g < 1.0 for g in self.revenue_growth), "revenue_growth looks implausible")
        _require(all(0 < m < 1 for m in self.ebitda_margin), "ebitda_margin must be between 0 and 1")
        _require(0 <= self.da_pct_of_revenue < 1, "da_pct_of_revenue must be in [0, 1)")
        _require(0 <= self.capex_pct_of_revenue < 1, "capex_pct_of_revenue must be in [0, 1)")
        _require(0 <= self.nwc_pct_of_revenue < 1, "nwc_pct_of_revenue must be in [0, 1)")
        _require(self.entry_ebitda_multiple > 0, "entry_ebitda_multiple must be positive")
        _require(self.exit_ebitda_multiple > 0, "exit_ebitda_multiple must be positive")
        _require(self.senior_leverage >= 0, "senior_leverage cannot be negative")
        _require(self.subordinated_leverage >= 0, "subordinated_leverage cannot be negative")
        _require(self.senior_leverage + self.subordinated_leverage < 15, "total leverage looks implausible")
        _require(0 <= self.senior_interest_rate < 1, "senior_interest_rate must be in [0, 1)")
        _require(0 <= self.subordinated_interest_rate < 1, "subordinated_interest_rate must be in [0, 1)")
        _require(0 <= self.senior_mandatory_amort_pct <= 1, "senior_mandatory_amort_pct must be in [0, 1]")
        _require(0 <= self.cash_sweep_pct <= 1, "cash_sweep_pct must be in [0, 1]")
        _require(0 <= self.tax_rate < 1, "tax_rate must be in [0, 1)")
        _require(0 <= self.transaction_fees_pct_of_ev < 1, "transaction_fees_pct_of_ev must be in [0, 1)")
        _require(self.cash_to_balance_sheet >= 0, "cash_to_balance_sheet cannot be negative")
        _require(self.minimum_cash >= 0, "minimum_cash cannot be negative")
        _require(
            self.cash_to_balance_sheet >= self.minimum_cash,
            "closing cash to the balance sheet must cover minimum cash",
        )
        _require(self.existing_net_debt >= 0, "existing_net_debt cannot be negative")

    @property
    def ltm_ebitda(self) -> float:
        """LTM EBITDA = LTM revenue × LTM EBITDA margin."""
        return self.ltm_revenue * self.ltm_ebitda_margin

    @property
    def year_labels(self) -> tuple[str, ...]:
        return tuple(f"Year {i}" for i in range(1, self.holding_period_years + 1))

    def with_updates(self, **changes: object) -> "DealAssumptions":
        return replace(self, **changes)


@dataclass(frozen=True)
class ScenarioAdjustments:
    """Additive overlays applied to a base case.

    Growth and margin deltas are applied to every projection year.
    Exit multiple delta is added to the base exit multiple.
    """

    name: str
    revenue_growth_delta: float = 0.0
    ebitda_margin_delta: float = 0.0
    exit_multiple_delta: float = 0.0


def apply_scenario(base: DealAssumptions, adj: ScenarioAdjustments) -> DealAssumptions:
    """Return a new assumptions object with scenario overlays applied."""
    growth = tuple(g + adj.revenue_growth_delta for g in base.revenue_growth)
    margins = tuple(m + adj.ebitda_margin_delta for m in base.ebitda_margin)
    return base.with_updates(
        company_name=f"{base.company_name} [{adj.name}]",
        revenue_growth=growth,
        ebitda_margin=margins,
        exit_ebitda_multiple=base.exit_ebitda_multiple + adj.exit_multiple_delta,
        notes=f"{base.notes} Scenario: {adj.name}.".strip(),
    )


def illustrative_base_case() -> DealAssumptions:
    """Hypothetical industrial manufacturer used to demonstrate the engine.

    These figures are invented for modeling practice. They are not
    historical results, forecasts, or valuations of any real company.
    """
    years = 5
    return DealAssumptions(
        company_name="Apex Components Group (illustrative)",
        is_illustrative=True,
        currency="USD",
        units="millions",
        ltm_revenue=250.0,
        ltm_ebitda_margin=0.18,
        revenue_growth=(0.05, 0.05, 0.045, 0.04, 0.035),
        ebitda_margin=(0.18, 0.182, 0.185, 0.187, 0.19),
        da_pct_of_revenue=0.025,
        capex_pct_of_revenue=0.03,
        nwc_pct_of_revenue=0.10,
        entry_ebitda_multiple=8.0,
        exit_ebitda_multiple=8.0,
        holding_period_years=years,
        senior_leverage=4.0,
        subordinated_leverage=1.5,
        senior_interest_rate=0.07,
        subordinated_interest_rate=0.10,
        senior_mandatory_amort_pct=0.05,
        cash_sweep_pct=1.0,
        tax_rate=0.25,
        transaction_fees_pct_of_ev=0.02,
        cash_to_balance_sheet=8.0,
        minimum_cash=5.0,
        existing_net_debt=40.0,
        notes=(
            "ILLUSTRATIVE HYPOTHETICAL ONLY — not actual company financials. "
            "Apex Components Group is a fictional precision-components manufacturer."
        ),
    )


def standard_scenarios() -> Mapping[str, ScenarioAdjustments]:
    """Base / downside / upside overlays around the illustrative case."""
    return {
        "base": ScenarioAdjustments(name="Base"),
        "downside": ScenarioAdjustments(
            name="Downside",
            revenue_growth_delta=-0.03,
            ebitda_margin_delta=-0.015,
            exit_multiple_delta=-1.0,
        ),
        "upside": ScenarioAdjustments(
            name="Upside",
            revenue_growth_delta=0.02,
            ebitda_margin_delta=0.01,
            exit_multiple_delta=1.0,
        ),
    }


STANDARD_SCENARIOS: Mapping[str, ScenarioAdjustments] = standard_scenarios()
