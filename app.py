"""Altiora — local Streamlit interface for the LBO engine.

Charts, KPIs, tables, and the workbook all read ``run_lbo`` outputs.
This module does not reimplement financial formulas.
"""

from __future__ import annotations

import io
import math
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st
from openpyxl import load_workbook

from src.assumptions import STANDARD_SCENARIOS, DealAssumptions
from src.filings import (
    FILING_NAME,
    FILING_URL,
    filing_anchor_gaps,
    filing_register,
    monster_hypothetical_case,
    register_frame_records,
)
from src.lbo_model import LBOResult, run_lbo
from src.reporting import (
    MODEL_ERRORS,
    assumptions_from_mapping,
    build_workbook,
    default_sensitivity,
    displayed_outputs,
    format_irr,
    format_moic,
    format_usd_millions,
    run_standard_cases,
)
from src.validation import ValidationError

PAGES = (
    "Overview",
    "Deal Assumptions",
    "Operating Model",
    "Debt Schedule",
    "Returns & Sensitivity",
    "Model Checks",
    "Export",
)

CASE_BUILDERS = {
    "Monster hypothetical LBO": monster_hypothetical_case,
}

_DEEP = "#172B43"
_BLUE = "#285B85"
_STEEL = "#6687A6"
_TEXT = "#172536"
_MUTED = "#64748B"
_LINE = "#DCE4ED"


def main() -> None:
    st.set_page_config(
        page_title="Altiora",
        page_icon="A",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_css()
    _init_state()

    with st.sidebar:
        st.markdown(
            """
            <div class="brand-block">
              <div class="brand-mark">ALTIORA</div>
              <div class="brand-sub">PRIVATE MARKETS · LBO ANALYTICS</div>
            </div>
            <div class="side-label">Navigation</div>
            """,
            unsafe_allow_html=True,
        )
        st.radio("Navigate", PAGES, key="nav_page", label_visibility="collapsed")
        st.markdown(
            '<div class="side-rule"></div><div class="side-label">Scenario</div>',
            unsafe_allow_html=True,
        )
        st.radio(
            "Scenario",
            ["base", "downside", "upside"],
            format_func=str.title,
            key="view_scenario",
            label_visibility="collapsed",
        )
        st.caption("Overlays apply to the base-case inputs. Monster history is stored from the cited 10-K.")

    assumptions: DealAssumptions = st.session_state.assumptions
    try:
        cases, case_errors = run_standard_cases(assumptions)
    except MODEL_ERRORS as exc:
        st.error(f"The saved case could not be calculated. {type(exc).__name__}: {exc}")
        return

    if "base" not in cases:
        st.error(case_errors.get("base", "The base case could not be calculated."))
        return

    view_key = st.session_state.view_scenario
    result = cases.get(view_key)
    _banner(assumptions)
    if st.session_state.input_error and st.session_state.nav_page != "Deal Assumptions":
        st.error(
            "The latest inputs were not applied. Figures below are the last valid case. "
            + st.session_state.input_error
        )
    if view_key not in cases:
        st.warning(f"{view_key.title()} could not be calculated. {case_errors.get(view_key, '')}")

    page = st.session_state.nav_page
    if page == "Overview":
        _page_overview(result, cases, case_errors)
    elif page == "Deal Assumptions":
        _page_assumptions(cases["base"])
    elif page == "Operating Model":
        _page_operating(result)
    elif page == "Debt Schedule":
        _page_debt(result)
    elif page == "Returns & Sensitivity":
        _page_returns(result, assumptions)
    elif page == "Model Checks":
        _page_checks(result)
    elif page == "Export":
        _page_export(assumptions, cases, case_errors)
    _scope_note()


def _init_state() -> None:
    if st.session_state.get("case_choice") not in CASE_BUILDERS or "assumptions" not in st.session_state:
        st.session_state.case_choice = "Monster hypothetical LBO"
        st.session_state.assumptions = monster_hypothetical_case()
        st.session_state.input_error = None
    if "input_error" not in st.session_state:
        st.session_state.input_error = None
    if "view_scenario" not in st.session_state:
        st.session_state.view_scenario = "base"
    if "nav_page" not in st.session_state:
        st.session_state.nav_page = "Overview"


def _apply_selected_case() -> None:
    fresh = CASE_BUILDERS[st.session_state.case_choice]()
    st.session_state.assumptions = fresh
    st.session_state.input_error = None
    _write_controls(fresh)


def _banner(assumptions: DealAssumptions) -> None:
    if "monster beverage" in assumptions.company_name.lower():
        gaps = filing_anchor_gaps(assumptions)
        anchor = (
            "Operating inputs have been edited and no longer match the FY2025 filing anchors."
            if gaps
            else "LTM sales, derived EBITDA margin, D&amp;A, capex, trade working capital, "
            "the 23.2% tax rate, and zero historical net debt are FY2025 filing anchors."
        )
        body = (
            "<strong>Altiora</strong> · Educational case study. Historical results are from the "
            "FY2025 Form 10-K. The acquisition is a hypothetical illustrative LBO, not an announced "
            f"transaction. {anchor} The entry multiple, growth, acquisition debt, fees, and closing "
            "cash are assumptions you can edit. Gross IRR and MOIC are calculated for this case, "
            "not actual investor returns, and not investment advice. USD millions."
        )
    elif "apex components" in assumptions.company_name.lower():
        body = (
            "<strong>Altiora</strong> · Illustrative case only. "
            f"<strong>{assumptions.company_name}</strong> is fictional. "
            "Figures are not historical results, a valuation of a real company, "
            "or investment advice. Amounts are USD millions."
        )
    else:
        body = (
            "<strong>Altiora</strong> · Illustrative case. "
            "This is not a filing extract and not investment advice. USD millions."
        )
    st.markdown(f'<div class="notice">{body}</div>', unsafe_allow_html=True)


def _page_overview(
    result: LBOResult | None,
    cases: dict[str, LBOResult],
    case_errors: dict[str, str],
) -> None:
    _case_header(None if result is None else result.assumptions, None if result is None else result.scenario_name)
    if result is None:
        st.warning("This scenario did not calculate. No returns are shown for it.")
        return
    _kpi_row(result)
    _exit_bridge(result)
    if result.financing.has_shortfall:
        st.warning("Financing shortfall or minimum-cash breach: " + " ".join(result.financing.notes))

    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("#### Revenue and EBITDA")
        st.caption(
            "USD millions. LTM is the opening anchor, not a multi-year reported history. "
            "Year columns are forecasts from the engine."
        )
        st.altair_chart(_revenue_chart(result), width="stretch")
    with right:
        st.markdown("#### Returns by scenario")
        st.caption("Gross IRR from a full engine run of each overlay. The selected scenario is darker.")
        _scenario_status(case_errors)
        if cases:
            st.altair_chart(_irr_chart(cases, result.scenario_name), width="stretch")
        else:
            st.warning("No scenario returns are available.")

    debt_col, moic_col = st.columns(2, gap="medium")
    with debt_col:
        st.markdown("#### Debt balances")
        st.caption("Closing acquisition debt, USD millions. Close is the funding date. Not historical borrowings.")
        st.altair_chart(_debt_chart(result), width="stretch")
    with moic_col:
        st.markdown("#### MOIC by scenario")
        st.caption("Gross exit equity divided by sponsor equity. Same engine runs as the IRR chart.")
        if cases:
            st.altair_chart(_moic_chart(cases, result.scenario_name), width="stretch")

    _sources_uses(result)
    summary = _scenario_table(cases)
    if not summary.empty:
        with st.expander("Scenario comparison"):
            st.dataframe(_style_amount_table(summary), width="stretch", hide_index=True)
            for key in ("base", "downside", "upside"):
                adj = STANDARD_SCENARIOS[key]
                st.markdown(
                    f"**{adj.name}.** Revenue growth {adj.revenue_growth_delta:+.1%}, "
                    f"EBITDA margin {adj.ebitda_margin_delta:+.1%}, "
                    f"exit multiple {adj.exit_multiple_delta:+.1f}x."
                )
    _filing_panel(result.assumptions)


def _page_assumptions(base_result: LBOResult) -> None:
    assumptions = st.session_state.assumptions
    if "ctrl_company" not in st.session_state:
        _write_controls(assumptions)

    _case_header(assumptions, "base")
    st.caption(
        "Editable inputs for the base case. USD millions. Sidebar scenarios overlay these inputs "
        "and do not change the fields below. Calculated returns are shown above the inputs."
    )
    status_slot = st.empty()
    if st.button("Reload starting case", width="content"):
        _apply_selected_case()
        st.rerun()

    with st.container(border=True):
        st.markdown("#### Company and transaction")
        c1, c2 = st.columns([2, 1])
        with c1:
            st.text_input(
                "Company name",
                key="ctrl_company",
                help="The case stays labeled illustrative. This name is not a market quote.",
            )
        with c2:
            st.number_input(
                "Holding period (years)",
                min_value=1,
                max_value=10,
                step=1,
                key="ctrl_holding_period",
                help="Annual periods. Cash flows are year-end.",
            )
        st.caption("Currency is USD millions. A stored case cannot be marked as a live valuation.")

    with st.container(border=True):
        st.markdown("#### Entry valuation")
        a1, a2, a3 = st.columns(3)
        with a1:
            _multiple("Entry EV / EBITDA (x)", "ctrl_entry_multiple")
        with a2:
            _percent("Transaction fees / EV (%)", "ctrl_fees", maximum=30.0)
        with a3:
            _amount("Existing net debt (USD m)", "ctrl_existing_debt")
        st.caption(
            "Existing net debt is historical debt refinanced at close. It is not acquisition leverage. "
            "The field cannot be negative, so net cash is omitted rather than entered as a negative number. "
            "Entry EV / EBITDA is a user assumption. No same-date share price, share count, cash, and "
            "debt were available, so a current enterprise value is not filled in. The June 30, 2025 "
            "non-affiliate equity value on the 10-K cover is not market capitalization and is not this multiple."
        )

    with st.container(border=True):
        st.markdown("#### Operating assumptions")
        c1, c2 = st.columns(2)
        with c1:
            _amount("LTM revenue (USD m)", "ctrl_ltm_revenue")
        with c2:
            _percent("LTM EBITDA margin (%)", "ctrl_ltm_margin", minimum=0.1)
        periods = int(st.session_state.ctrl_holding_period)
        _ensure_year_keys(periods, assumptions)
        st.markdown("**Revenue growth (%)**")
        st.caption("One rate per year. Not a split of price, volume, and mix.")
        growth = _year_percents("ctrl_growth", periods, "Growth")
        st.markdown("**EBITDA margin (%)**")
        st.caption("Forecast margin. Marketing, distribution, and product costs stay inside this ratio.")
        margins = _year_percents("ctrl_margin", periods, "Margin")
        d1, d2 = st.columns(2)
        with d1:
            _percent("D&A / revenue (%)", "ctrl_da")
        with d2:
            _percent("Capex / revenue (%)", "ctrl_capex")

    with st.container(border=True):
        st.markdown("#### Debt financing")
        st.caption("New acquisition facilities, sized off LTM EBITDA. Independent of historical borrowings.")
        a1, a2, a3, a4 = st.columns(4)
        with a1:
            _leverage("Senior leverage (x EBITDA)", "ctrl_senior_leverage")
        with a2:
            _leverage("Subordinated leverage (x EBITDA)", "ctrl_sub_leverage")
        with a3:
            _percent("Senior interest (%)", "ctrl_senior_rate")
        with a4:
            _percent("Subordinated interest (%)", "ctrl_sub_rate")
        b1, b2 = st.columns(2)
        with b1:
            _percent("Senior mandatory amort. (% of original)", "ctrl_amort", maximum=100.0)
        with b2:
            _percent("Cash sweep (% of surplus)", "ctrl_sweep", maximum=100.0)

    with st.container(border=True):
        st.markdown("#### Cash flow and working capital")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            _percent("NWC / revenue (%)", "ctrl_nwc")
        with c2:
            _percent("Tax rate (%)", "ctrl_tax")
        with c3:
            _amount("Cash to balance sheet (USD m)", "ctrl_cash")
        with c4:
            _amount("Minimum cash (USD m)", "ctrl_min_cash")
        st.caption(
            "NWC is one percent of revenue. Closing cash must cover minimum cash. "
            "These cash amounts are deal assumptions, not the reported cash balance."
        )

    with st.container(border=True):
        st.markdown("#### Exit assumptions")
        _multiple("Exit EV / EBITDA (x)", "ctrl_exit_multiple")
        st.caption("Applied to exit-year EBITDA. Cash-free and debt-free. An assumption, not a market quote.")

    with st.container(border=True):
        st.markdown("#### Scenario settings")
        st.caption(
            "Base uses the inputs on this page. Downside and upside are the standard overlays "
            "in the sidebar: growth, margin, and exit multiple. They are not a second set of inputs."
        )

    fresh = _commit_controls(periods, growth, margins)
    with status_slot.container():
        if fresh is None:
            st.markdown("#### Last valid base case")
            st.error(st.session_state.input_error or "The base case could not be calculated.")
            _assumption_status(base_result)
        else:
            st.markdown("#### Calculated outputs")
            _assumption_status(fresh)


def _page_operating(result: LBOResult | None) -> None:
    _case_header(None if result is None else result.assumptions, None if result is None else result.scenario_name)
    st.markdown("#### Operating model")
    if result is None:
        st.warning("This scenario did not calculate.")
        return
    anchor_note = ""
    if (
        "monster beverage" in result.assumptions.company_name.lower()
        and not filing_anchor_gaps(result.assumptions)
    ):
        anchor_note = (
            " LTM revenue is FY2025 reported net sales. The LTM EBITDA margin is derived from "
            "operating income plus depreciation and amortization."
        )
    st.caption(
        "USD millions. LTM is the opening anchor. Year 1 onward is a forecast, not a reported result. "
        "The engine has revenue, EBITDA, D&A, EBIT, capex, NWC, and, for forecast years, interest, "
        "tax, net income, and free cash flow before principal. It does not calculate cost of sales, "
        "gross profit, or a separate marketing line. EBITDA, D&A, capex, and NWC are percents of revenue."
        + anchor_note
    )
    st.dataframe(
        _style_amount_table(_indexed_schedule(result.operating_schedule)),
        width="stretch",
        hide_index=True,
        column_config=_schedule_columns(result.operating_schedule),
    )


def _page_debt(result: LBOResult | None) -> None:
    _case_header(None if result is None else result.assumptions, None if result is None else result.scenario_name)
    st.markdown("#### Debt schedule")
    if result is None:
        st.warning("This scenario did not calculate.")
        return
    if result.financing.has_shortfall:
        st.warning("Financing attention: " + " ".join(result.financing.notes))
    else:
        st.success("Mandatory amortization was paid and closing cash stayed at or above minimum cash.")
    st.caption(
        "USD millions. New senior and subordinated debt are funded at Close. "
        "The schedule then shows opening balances, interest, scheduled mandatory amortization, "
        "the amount actually paid, any shortfall, the optional senior cash sweep, and closing balances. "
        "Subordinated debt is interest-only. There is no separate draw line after close, and no revolver."
    )
    st.dataframe(
        _style_amount_table(_indexed_schedule(result.debt_schedule)),
        width="stretch",
        hide_index=True,
        column_config=_schedule_columns(result.debt_schedule),
    )
    st.markdown("#### Cash and minimum liquidity")
    st.dataframe(
        _style_amount_table(_indexed_schedule(result.cash_schedule)),
        width="stretch",
        hide_index=True,
        column_config=_schedule_columns(result.cash_schedule),
    )


def _page_returns(result: LBOResult | None, assumptions: DealAssumptions) -> None:
    _case_header(assumptions, None if result is None else result.scenario_name)
    st.markdown("#### Returns")
    if result is None:
        st.warning("This scenario did not calculate. IRR and MOIC are not shown as zero.")
        return
    shown = displayed_outputs(result)
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Gross IRR",
        shown["gross_irr"],
        help="Hypothetical annual IRR of this case's sponsor cash flows. Not an actual investor return. Gross of fund fees and carry.",
    )
    c2.metric(
        "Gross MOIC",
        shown["gross_moic"],
        help="Hypothetical exit equity divided by the sponsor equity plug. Not an actual investor return.",
    )
    c3.metric(
        "Exit equity",
        shown["exit_equity_value"],
        help="USD millions. Exit enterprise value minus exit net debt, floored at zero.",
    )
    st.caption(
        "Hypothetical gross IRR and MOIC for this case, not actual investor returns. "
        "Gross of fund fees, carry, and investor taxes. USD millions. "
        "Interim cash flows are zero because the engine sweeps cash to debt and does not pay a dividend before exit. "
        "Parentheses are cash outflows."
    )
    flows = pd.DataFrame(
        {
            "Period": ["Entry (t=0)", *result.assumptions.year_labels],
            "Sponsor cash flow": result.sponsor_cash_flows,
        }
    )
    st.dataframe(_style_amount_table(flows), width="stretch", hide_index=True)

    st.markdown("#### Sensitivity")
    st.caption(
        "Each cell is a full model run of the base-case assumptions, not the sidebar overlay. "
        "Rows are the exit EV / EBITDA multiple. Columns are a revenue-growth shock, in percentage points, "
        "applied to every projection year. A dash means the engine rejected that cell. "
        "Colour only ranks the calculated cells. It is not an investment forecast."
    )
    try:
        irr, moic, notes = default_sensitivity(assumptions)
    except MODEL_ERRORS as exc:
        st.error(f"Sensitivity could not be calculated. {type(exc).__name__}: {exc}")
        return
    heat_left, heat_right = st.columns(2)
    with heat_left:
        st.markdown("**Gross IRR**")
        st.altair_chart(_sensitivity_heatmap(irr, "Gross IRR", percent=True), width="stretch")
        st.dataframe(_format_sensitivity(irr, percent=True), width="stretch", hide_index=True)
    with heat_right:
        st.markdown("**Gross MOIC**")
        st.altair_chart(_sensitivity_heatmap(moic, "Gross MOIC", percent=False), width="stretch")
        st.dataframe(_format_sensitivity(moic, percent=False), width="stretch", hide_index=True)
    if notes:
        st.warning("Some cells were not calculated.\n\n" + "\n".join(notes))


def _page_checks(result: LBOResult | None) -> None:
    _case_header(None if result is None else result.assumptions, None if result is None else result.scenario_name)
    st.markdown("#### Model checks")
    if result is None:
        st.error("This scenario did not calculate, so its identity checks are not available.")
        return
    st.caption(
        "Identity checks come from the engine. A financing shortfall is a warning and still shows the calculated case. "
        "A failed identity check would have stopped the run."
    )
    _render_checks(result)
    _input_check()
    _history_check()
    st.markdown("#### Cash floor and financing shortfall")
    c1, c2, c3 = st.columns(3)
    c1.metric("Amortization shortfall", format_usd_millions(result.financing.total_amortization_shortfall), help="USD millions. Unpaid scheduled mandatory amortization.")
    c2.metric("Minimum-cash breach", format_usd_millions(result.financing.total_min_cash_breach), help="USD millions. Closing cash below the minimum-cash floor.")
    c3.metric("Financing flag", "Yes" if result.financing.has_shortfall else "No")
    if result.financing.notes:
        for note in result.financing.notes:
            st.warning(note)
    else:
        st.success("Scheduled mandatory amortization was paid without drawing minimum cash.")
    years = list(result.assumptions.year_labels)
    cash_focus = result.cash_schedule.loc[
        ["Closing cash", "Minimum cash", "Surplus cash", "Min-cash breach"],
        years,
    ]
    st.dataframe(_style_amount_table(_indexed_schedule(cash_focus)), width="stretch", hide_index=True)


def _page_export(
    assumptions: DealAssumptions,
    cases: dict[str, LBOResult],
    case_errors: dict[str, str],
) -> None:
    _case_header(assumptions, "base")
    st.markdown("#### Export")
    st.caption(
        f"{assumptions.company_name}. The workbook reruns the current base case and the standard scenarios. "
        "Excel keeps full precision. Tables on screen are rounded. "
        "This is an analytical output of the model, not an independently audited investment memorandum."
    )
    _scenario_status(case_errors)
    try:
        payload = build_workbook(assumptions)
    except (OSError, ValueError, ValidationError) as exc:
        st.error(f"The workbook could not be built. {type(exc).__name__}: {exc}")
        return
    built = datetime.now().strftime("%Y-%m-%d %H:%M")
    workbook = load_workbook(io.BytesIO(payload), read_only=True)
    sheet_names = list(workbook.sheetnames)
    workbook.close()
    st.download_button(
        "Download Excel workbook",
        data=payload,
        file_name="altiora-lbo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="content",
    )
    st.caption(f"Built {built} local time · {len(sheet_names)} sheets · USD millions")
    st.markdown("**Sheets in this file**")
    for name in sheet_names:
        st.markdown(f"- {name}")
    if cases:
        st.dataframe(_style_amount_table(_scenario_table(cases)), width="stretch", hide_index=True)


def _decimal(percent_points: float) -> float:
    """Convert an edited percent into the decimal the engine stores."""
    return round(float(percent_points) / 100.0, 6)


def _commit_controls(periods: int, growth: list[float], margins: list[float]) -> LBOResult | None:
    payload = {
        "company_name": st.session_state.ctrl_company,
        "holding_period_years": periods,
        "ltm_revenue": float(st.session_state.ctrl_ltm_revenue),
        "ltm_ebitda_margin": _decimal(st.session_state.ctrl_ltm_margin),
        "revenue_growth": tuple(_decimal(value) for value in growth),
        "ebitda_margin": tuple(_decimal(value) for value in margins),
        "da_pct_of_revenue": _decimal(st.session_state.ctrl_da),
        "capex_pct_of_revenue": _decimal(st.session_state.ctrl_capex),
        "nwc_pct_of_revenue": _decimal(st.session_state.ctrl_nwc),
        "entry_ebitda_multiple": float(st.session_state.ctrl_entry_multiple),
        "exit_ebitda_multiple": float(st.session_state.ctrl_exit_multiple),
        "senior_leverage": float(st.session_state.ctrl_senior_leverage),
        "subordinated_leverage": float(st.session_state.ctrl_sub_leverage),
        "senior_interest_rate": _decimal(st.session_state.ctrl_senior_rate),
        "subordinated_interest_rate": _decimal(st.session_state.ctrl_sub_rate),
        "senior_mandatory_amort_pct": _decimal(st.session_state.ctrl_amort),
        "cash_sweep_pct": _decimal(st.session_state.ctrl_sweep),
        "tax_rate": _decimal(st.session_state.ctrl_tax),
        "transaction_fees_pct_of_ev": _decimal(st.session_state.ctrl_fees),
        "cash_to_balance_sheet": float(st.session_state.ctrl_cash),
        "minimum_cash": float(st.session_state.ctrl_min_cash),
        "existing_net_debt": float(st.session_state.ctrl_existing_debt),
    }
    try:
        candidate = assumptions_from_mapping(payload)
        result = run_lbo(candidate, scenario_name="base")
    except MODEL_ERRORS as exc:
        st.session_state.input_error = f"{type(exc).__name__}: {exc}"
        return None
    st.session_state.assumptions = candidate
    st.session_state.input_error = None
    return result


def _assumption_status(result: LBOResult) -> None:
    shown = displayed_outputs(result)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entry EV", shown["entry_enterprise_value"], help="USD millions. Calculated from the inputs above.")
    c2.metric("Sponsor equity", shown["sponsor_equity"], help="USD millions. Sources-and-uses plug.")
    c3.metric("Gross IRR", shown["gross_irr"])
    c4.metric("Gross MOIC", shown["gross_moic"])
    st.caption(
        f"LTM EBITDA {format_usd_millions(result.assumptions.ltm_ebitda)} · USD millions · calculated"
    )


def _write_controls(assumptions: DealAssumptions) -> None:
    st.session_state.ctrl_company = assumptions.company_name
    st.session_state.ctrl_holding_period = int(assumptions.holding_period_years)
    st.session_state.ctrl_ltm_revenue = float(assumptions.ltm_revenue)
    st.session_state.ctrl_ltm_margin = float(assumptions.ltm_ebitda_margin * 100.0)
    st.session_state.ctrl_da = float(assumptions.da_pct_of_revenue * 100.0)
    st.session_state.ctrl_capex = float(assumptions.capex_pct_of_revenue * 100.0)
    st.session_state.ctrl_nwc = float(assumptions.nwc_pct_of_revenue * 100.0)
    st.session_state.ctrl_entry_multiple = float(assumptions.entry_ebitda_multiple)
    st.session_state.ctrl_exit_multiple = float(assumptions.exit_ebitda_multiple)
    st.session_state.ctrl_senior_leverage = float(assumptions.senior_leverage)
    st.session_state.ctrl_sub_leverage = float(assumptions.subordinated_leverage)
    st.session_state.ctrl_senior_rate = float(assumptions.senior_interest_rate * 100.0)
    st.session_state.ctrl_sub_rate = float(assumptions.subordinated_interest_rate * 100.0)
    st.session_state.ctrl_amort = float(assumptions.senior_mandatory_amort_pct * 100.0)
    st.session_state.ctrl_sweep = float(assumptions.cash_sweep_pct * 100.0)
    st.session_state.ctrl_tax = float(assumptions.tax_rate * 100.0)
    st.session_state.ctrl_fees = float(assumptions.transaction_fees_pct_of_ev * 100.0)
    st.session_state.ctrl_cash = float(assumptions.cash_to_balance_sheet)
    st.session_state.ctrl_min_cash = float(assumptions.minimum_cash)
    st.session_state.ctrl_existing_debt = float(assumptions.existing_net_debt)
    for index, growth in enumerate(assumptions.revenue_growth):
        st.session_state[f"ctrl_growth_{index}"] = float(growth * 100.0)
    for index, margin in enumerate(assumptions.ebitda_margin):
        st.session_state[f"ctrl_margin_{index}"] = float(margin * 100.0)
    for index in range(assumptions.holding_period_years, 12):
        st.session_state.pop(f"ctrl_growth_{index}", None)
        st.session_state.pop(f"ctrl_margin_{index}", None)


def _ensure_year_keys(periods: int, assumptions: DealAssumptions) -> None:
    for index in range(periods):
        growth_key = f"ctrl_growth_{index}"
        margin_key = f"ctrl_margin_{index}"
        if growth_key not in st.session_state:
            source = assumptions.revenue_growth
            st.session_state[growth_key] = float((source[index] if index < len(source) else source[-1]) * 100.0)
        if margin_key not in st.session_state:
            source = assumptions.ebitda_margin
            st.session_state[margin_key] = float((source[index] if index < len(source) else source[-1]) * 100.0)


def _year_percents(prefix: str, periods: int, label: str) -> list[float]:
    values: list[float] = []
    for start in range(0, periods, 5):
        columns = st.columns(5)
        for offset in range(5):
            index = start + offset
            if index >= periods:
                break
            with columns[offset]:
                values.append(
                    st.number_input(
                        f"{label} Y{index + 1}",
                        min_value=-49.0 if prefix.endswith("growth") or "growth" in prefix else 0.1,
                        max_value=99.0,
                        step=0.1,
                        format="%.1f",
                        key=f"{prefix}_{index}",
                    )
                )
    return values


def _amount(label: str, key: str) -> None:
    st.number_input(label, min_value=0.0, max_value=100000.0, step=1.0, format="%.2f", key=key)


def _percent(label: str, key: str, minimum: float = 0.0, maximum: float = 99.0) -> None:
    st.number_input(label, min_value=minimum, max_value=maximum, step=0.1, format="%.4f", key=key)


def _multiple(label: str, key: str) -> None:
    st.number_input(label, min_value=0.5, max_value=20.0, step=0.1, format="%.1f", key=key)


def _leverage(label: str, key: str) -> None:
    st.number_input(label, min_value=0.0, max_value=12.0, step=0.1, format="%.1f", key=key)


def _display_name(assumptions: DealAssumptions) -> str:
    name = assumptions.company_name
    if name.endswith("]") and " [" in name:
        name = name[: name.rfind(" [")]
    for suffix in (" (illustrative LBO)", " (illustrative)"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _case_header(assumptions: DealAssumptions | None, scenario: str | None) -> None:
    if assumptions is None:
        st.warning("This scenario did not calculate.")
        return
    monster = "monster beverage" in assumptions.company_name.lower()
    if monster:
        gaps = filing_anchor_gaps(assumptions)
        kind = "Hypothetical acquisition case"
        anchor = "FY2025 filing anchors in use" if not gaps else "Filing anchors edited"
    elif "apex components" in assumptions.company_name.lower():
        kind = "Fictional illustrative case"
        anchor = "No company filing"
    else:
        kind = "Illustrative case"
        anchor = "Not a filing extract"
    scenario_label = scenario.title() if scenario else "—"
    st.markdown(
        (
            '<div class="page-head">'
            '<div class="eyebrow">LEVERAGED BUYOUT ANALYSIS</div>'
            f'<div class="page-title">{_display_name(assumptions)}</div>'
            '<div class="meta-row">'
            f"<span>{kind}</span><span>{scenario_label}</span>"
            f"<span>{assumptions.currency} {assumptions.units}</span>"
            f"<span>{assumptions.holding_period_years}-year hold</span>"
            f"<span>{anchor}</span>"
            "</div></div>"
        ),
        unsafe_allow_html=True,
    )


def _su_table(title: str, series: pd.Series, total_label: str, total: float) -> str:
    rows = []
    for item, amount in series.items():
        rows.append(
            f"<tr><td>{item}</td><td class='num'>{format_usd_millions(float(amount))}</td></tr>"
        )
    rows.append(
        f"<tr class='total'><td>{total_label}</td><td class='num'>{format_usd_millions(total)}</td></tr>"
    )
    body = "".join(rows)
    return (
        f"<div class='su-card'><div class='su-title'>{title}</div>"
        f"<table class='su'><tbody>{body}</tbody></table></div>"
    )


def _sources_uses(result: LBOResult) -> None:
    st.markdown("#### Sources and uses")
    txn = result.transaction
    gap = txn.total_sources - txn.total_uses
    left, right = st.columns(2)
    with left:
        st.markdown(
            _su_table("Sources", result.sources, "Total sources", txn.total_sources),
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            _su_table("Uses", result.uses, "Total uses", txn.total_uses),
            unsafe_allow_html=True,
        )
    if abs(gap) < 0.01:
        st.success(f"Sources equal uses at {format_usd_millions(txn.total_sources)} USD millions.")
    else:
        st.error(
            "Sources and uses do not reconcile. "
            f"Difference {format_usd_millions(gap)} USD millions."
        )
    st.caption(
        "USD millions. New senior and subordinated debt are hypothetical acquisition financing. "
        "Refinance existing net debt is the historical plug "
        f"({format_usd_millions(txn.refinanced_net_debt)}). "
        "A zero plug does not mean the acquisition is unlevered."
    )


def _schedule_columns(schedule: pd.DataFrame) -> dict[str, object]:
    config: dict[str, object] = {
        "Line item": st.column_config.TextColumn("Line item", width="medium"),
    }
    for column in schedule.columns:
        config[str(column)] = st.column_config.TextColumn(str(column), width="small")
    return config


_CHECK_COPY = {
    "sources_equal_uses": ("Sources and uses", "Total sources equal total uses."),
    "debt_rollforward": (
        "Debt roll-forward",
        "Opening debt less mandatory and optional repayments equals closing debt.",
    ),
    "non_negative_debt": ("Debt roll-forward", "Debt balances do not go negative."),
    "financing_shortfall": (
        "Cash and minimum liquidity",
        "Unpaid mandatory amortization or a minimum-cash breach is a warning, not a rewritten schedule.",
    ),
    "exit_bridge": (
        "Return calculation consistency",
        "Exit equity, exit net debt, and the sponsor cash flows describe the same bridge.",
    ),
    "returns": (
        "Return calculation consistency",
        "Gross MOIC and gross IRR are computed from the sponsor cash flows.",
    ),
}


def _check_status(name: str, passed: bool) -> str:
    if passed:
        return "Passed"
    if name == "financing_shortfall":
        return "Warning"
    return "Failed"


def _render_checks(result: LBOResult) -> None:
    grouped: dict[str, list[tuple[object, str]]] = {}
    for check in result.checks:
        group, blurb = _CHECK_COPY.get(check.name, ("Other", check.name.replace("_", " ")))
        grouped.setdefault(group, []).append((check, blurb))
    for group, items in grouped.items():
        st.markdown(f"**{group}**")
        for check, blurb in items:
            status = _check_status(check.name, check.passed)
            st.markdown(
                (
                    f"<div class='check {status.lower()}'>"
                    f"<div class='check-top'><span>{blurb}</span>"
                    f"<span class='pill'>{status}</span></div>"
                    f"<div class='check-body'>{check.detail}</div></div>"
                ),
                unsafe_allow_html=True,
            )


def _input_check() -> None:
    st.markdown("**Input validation**")
    error = st.session_state.input_error
    if error:
        st.markdown(
            (
                "<div class='check failed'><div class='check-top'><span>Current inputs</span>"
                f"<span class='pill'>Failed</span></div><div class='check-body'>{error}</div></div>"
            ),
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        (
            "<div class='check passed'><div class='check-top'><span>Current inputs</span>"
            "<span class='pill'>Passed</span></div>"
            "<div class='check-body'>The saved assumptions were accepted by the engine.</div></div>"
        ),
        unsafe_allow_html=True,
    )


def _history_check() -> None:
    st.markdown("**Historical data completeness**")
    missing = [row.item for row in filing_register() if row.status == "unverified"]
    if missing:
        detail = "; ".join(missing)
        st.markdown(
            (
                "<div class='check warning'><div class='check-top'><span>Filing register</span>"
                "<span class='pill'>Warning</span></div>"
                f"<div class='check-body'>Unverified and left blank: {detail}.</div></div>"
            ),
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        (
            "<div class='check passed'><div class='check-top'><span>Filing register</span>"
            "<span class='pill'>Passed</span></div>"
            "<div class='check-body'>No unverified rows are flagged in the stored register.</div></div>"
        ),
        unsafe_allow_html=True,
    )


def _heading(title: str, result: LBOResult | None, role: str = "Calculated outputs") -> None:
    st.header(title)
    if result is None:
        st.caption(f"{role}. This scenario did not calculate.")
        return
    st.caption(
        f"{role} · {result.assumptions.company_name} · {result.scenario_name.title()} · "
        f"{result.assumptions.currency} {result.assumptions.units}"
    )


def _kpi_row(result: LBOResult) -> None:
    shown = displayed_outputs(result)
    columns = st.columns(5)
    columns[0].metric(
        "Entry enterprise value",
        shown["entry_enterprise_value"],
        help="USD millions. LTM EBITDA multiplied by the entry multiple.",
    )
    columns[1].metric(
        "Sponsor equity",
        shown["sponsor_equity"],
        help="USD millions. Plug that makes sources equal uses.",
    )
    columns[2].metric(
        "Exit enterprise value",
        shown["exit_enterprise_value"],
        help="USD millions. Exit-year EBITDA multiplied by the exit multiple.",
    )
    columns[3].metric(
        "Gross IRR",
        shown["gross_irr"],
        help="Hypothetical gross IRR of this case. Not an actual investor return. Gross of fund fees and carry.",
    )
    columns[4].metric(
        "Gross MOIC",
        shown["gross_moic"],
        help="Hypothetical gross MOIC of this case. Not an actual investor return. Gross of fund fees and carry.",
    )


def _exit_bridge(result: LBOResult) -> None:
    shown = displayed_outputs(result)
    gap = result.exit_equity_value + result.exit_net_debt - result.exit_enterprise_value
    if abs(gap) < 0.01:
        relation = (
            f"Exit equity {shown['exit_equity_value']} = "
            f"exit enterprise value {shown['exit_enterprise_value']} − "
            f"exit net debt {shown['exit_net_debt']}"
        )
    else:
        relation = (
            f"Exit equity {shown['exit_equity_value']} is floored at zero. "
            f"Exit net debt is {shown['exit_net_debt']}"
        )
    st.caption(
        relation
        + ". USD millions. Minimum cash is not treated as surplus. "
        "The entry sponsor cash flow is the equity plug; the exit cash flow is exit equity. "
        "Gross of fund fees and carry."
    )


def _scenario_status(case_errors: dict[str, str]) -> None:
    for key, message in case_errors.items():
        st.warning(f"{key.title()} was not calculated. {message}")


def _scenario_table(cases: dict[str, LBOResult]) -> pd.DataFrame:
    rows = []
    for key in ("base", "downside", "upside"):
        result = cases.get(key)
        if result is None:
            continue
        rows.append(
            {
                "Scenario": key.title(),
                "Entry EV": result.transaction.entry_enterprise_value,
                "Sponsor equity": result.transaction.sponsor_equity,
                "Exit EV": result.exit_enterprise_value,
                "Exit equity": result.exit_equity_value,
                "Gross IRR": result.irr,
                "Gross MOIC": result.gross_moic,
                "Financing shortfall": "Yes" if result.financing.has_shortfall else "No",
            }
        )
    return pd.DataFrame(rows)


def _series_table(series: pd.Series) -> pd.DataFrame:
    frame = series.rename("Amount").rename_axis("Item").reset_index()
    return _style_amount_table(frame)


def _indexed_schedule(schedule: pd.DataFrame) -> pd.DataFrame:
    frame = schedule.copy()
    frame.index.name = "Line item"
    return frame.reset_index()


def _style_amount_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Format engine numbers for display. The underlying model is not rounded."""
    view = frame.copy()
    for column in view.columns:
        if not pd.api.types.is_numeric_dtype(view[column]):
            continue
        if "MOIC" in str(column):
            view[column] = view[column].map(lambda value: "—" if pd.isna(value) else format_moic(float(value)))
        elif "IRR" in str(column):
            view[column] = view[column].map(
                lambda value: "—" if pd.isna(value) else format_irr(float(value))
            )
        else:
            view[column] = view[column].map(
                lambda value: "—" if pd.isna(value) else format_usd_millions(float(value))
            )
    return view


def _format_sensitivity(irr: pd.DataFrame, percent: bool) -> pd.DataFrame:
    view = irr.copy()
    view.index = [f"{float(idx):.1f}x" for idx in view.index]
    view.columns = [f"{float(col) * 100:+.1f} pp" for col in view.columns]
    view.index.name = "Exit EV / EBITDA"

    def _cell(value: object) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
            return "—"
        if percent:
            return format_irr(float(value))
        return format_moic(float(value))

    shown = view.map(_cell).reset_index()
    return shown


def _revenue_chart(result: LBOResult) -> alt.Chart:
    schedule = result.operating_schedule
    periods = [column for column in schedule.columns if column == "LTM" or str(column).startswith("Year")]
    labels = []
    rows = []
    for period in periods:
        label = "LTM" if period == "LTM" else str(period).replace("Year ", "Y")
        labels.append(label)
        for metric in ("Revenue", "EBITDA"):
            rows.append(
                {
                    "Period": label,
                    "Metric": metric,
                    "USD millions": float(schedule.loc[metric, period]),
                }
            )
    frame = pd.DataFrame(rows)
    return (
        alt.Chart(frame)
        .mark_bar(size=14)
        .encode(
            x=alt.X("Period:N", sort=labels, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("USD millions:Q", title="USD millions", axis=alt.Axis(format=",.0f")),
            color=alt.Color(
                "Metric:N",
                scale=alt.Scale(domain=["Revenue", "EBITDA"], range=[_BLUE, _STEEL]),
                legend=alt.Legend(orient="bottom", title=None),
            ),
            xOffset="Metric:N",
            tooltip=["Period", "Metric", alt.Tooltip("USD millions:Q", format=",.2f")],
        )
        .properties(height=260)
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor=_MUTED, titleColor=_MUTED, labelFontSize=11, gridColor=_LINE)
    )


def _debt_chart(result: LBOResult) -> alt.Chart:
    debt = result.debt_schedule
    periods = list(debt.columns)
    rows = []
    for period in periods:
        for metric in ("Closing senior", "Closing subordinated", "Closing total debt"):
            rows.append({"Period": str(period), "Balance": metric, "USD millions": float(debt.loc[metric, period])})
    frame = pd.DataFrame(rows)
    return (
        alt.Chart(frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("Period:N", sort=[str(period) for period in periods], title="Period"),
            y=alt.Y("USD millions:Q", title="USD millions", axis=alt.Axis(format=",.0f")),
            color=alt.Color(
                "Balance:N",
                scale=alt.Scale(
                    domain=["Closing senior", "Closing subordinated", "Closing total debt"],
                    range=[_BLUE, _STEEL, _DEEP],
                ),
                legend=alt.Legend(orient="bottom", title=None),
            ),
            tooltip=["Period", "Balance", alt.Tooltip("USD millions:Q", format=",.2f")],
        )
        .properties(height=240)
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor=_MUTED, titleColor=_MUTED, labelFontSize=11, gridColor=_LINE)
    )


def _irr_chart(cases: dict[str, LBOResult], selected: str) -> alt.Chart:
    rows = []
    for key in ("downside", "base", "upside"):
        result = cases.get(key)
        if result is None or math.isnan(result.irr):
            continue
        rows.append({"Scenario": key.title(), "Gross IRR (%)": result.irr * 100.0})
    return _bar_chart(pd.DataFrame(rows), "Gross IRR (%)", "Gross IRR (%)", selected)


def _moic_chart(cases: dict[str, LBOResult], selected: str) -> alt.Chart:
    rows = []
    for key in ("downside", "base", "upside"):
        result = cases.get(key)
        if result is None:
            continue
        rows.append({"Scenario": key.title(), "Gross MOIC": result.gross_moic})
    return _bar_chart(pd.DataFrame(rows), "Gross MOIC", "Gross MOIC (x)", selected)


def _bar_chart(frame: pd.DataFrame, value_field: str, axis_title: str, selected: str) -> alt.Chart:
    if frame.empty:
        return alt.Chart(pd.DataFrame({"Scenario": [], value_field: []})).mark_bar()
    order = ["Downside", "Base", "Upside"]
    frame = frame.copy()
    frame["Tone"] = frame["Scenario"].map(lambda name: "Selected" if name.lower() == selected.lower() else "Other")
    return (
        alt.Chart(frame)
        .mark_bar()
        .encode(
            x=alt.X("Scenario:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{value_field}:Q", title=axis_title, axis=alt.Axis(format=",.1f")),
            color=alt.Color(
                "Tone:N",
                scale=alt.Scale(domain=["Selected", "Other"], range=[_BLUE, _STEEL]),
                legend=None,
            ),
            tooltip=["Scenario", alt.Tooltip(f"{value_field}:Q", format=",.2f")],
        )
        .properties(height=240)
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor=_MUTED, titleColor=_MUTED, labelFontSize=11, gridColor=_LINE)
    )


def _sensitivity_heatmap(frame: pd.DataFrame, title: str, percent: bool) -> alt.Chart:
    long = frame.stack().reset_index()
    long.columns = ["Exit multiple", "Growth shock", "Value"]
    long["Exit multiple"] = long["Exit multiple"].map(lambda value: f"{float(value):.1f}x")
    long["Growth shock"] = long["Growth shock"].map(lambda value: f"{float(value) * 100:+.1f} pp")
    long = long.dropna(subset=["Value"])
    encoding_format = ".1%" if percent else ".2f"
    return (
        alt.Chart(long)
        .mark_rect()
        .encode(
            x=alt.X("Growth shock:N", title="Revenue-growth shock", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Exit multiple:N", title="Exit EV / EBITDA", sort=None),
            color=alt.Color(
                "Value:Q",
                scale=alt.Scale(scheme="blues"),
                legend=alt.Legend(title=title, format=encoding_format),
                title=title,
            ),
            tooltip=[
                "Exit multiple",
                "Growth shock",
                alt.Tooltip("Value:Q", title=title, format=encoding_format),
            ],
        )
        .properties(height=220)
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor=_MUTED, titleColor=_MUTED, labelFontSize=11, grid=False)
    )


def _filing_panel(assumptions: DealAssumptions) -> None:
    st.markdown("#### Historical financials and sources")
    st.markdown(
        (
            f"Monster Beverage Corporation · fiscal year ended December 31, 2025 · {FILING_NAME}. "
            "Reported and derived figures are historical. Forecasts are not in this table. "
            f"[View SEC filing]({FILING_URL})"
        )
    )
    frame = pd.DataFrame(register_frame_records())
    missing = frame.loc[frame["Status"] == "unverified", "Item"].astype(str)
    if not missing.empty:
        st.warning("Unverified, and left blank: " + "; ".join(missing) + ".")
    gaps = filing_anchor_gaps(assumptions)
    if "monster beverage" in assumptions.company_name.lower() and gaps:
        st.warning("This case no longer matches the FY2025 anchors. " + " ".join(gaps))
    elif "monster beverage" not in assumptions.company_name.lower():
        st.info(
            "The operating case is not the Monster hypothetical LBO. "
            "The register below is the FY2025 filing extract and is not the source of these inputs."
        )
    key_items = {
        "Net sales",
        "Cost of sales",
        "Gross profit",
        "Operating expenses",
        "Operating income",
        "Net income",
        "Depreciation and amortization",
        "EBITDA",
        "Cash and cash equivalents",
        "Long-term debt",
        "Trade net working capital",
    }
    compact = frame[frame["Item"].isin(key_items) & frame["Status"].isin(["reported", "derived"])].copy()
    compact["USD millions"] = compact["Amount (USD millions)"].map(
        lambda value: "—" if pd.isna(value) else f"{float(value):,.3f}"
    )
    compact = compact[["Item", "Fiscal period", "USD millions", "Status"]]
    st.markdown(_history_table(compact), unsafe_allow_html=True)
    with st.expander("Source notes, methodology, and the full register"):
        st.caption(
            "Amounts the filing did not state are blank. They are not estimated. "
            "The long source reference is the same SEC filing linked above."
        )
        st.dataframe(frame.drop(columns=["Source"]), width="stretch", hide_index=True)


def _history_table(frame: pd.DataFrame) -> str:
    rows = [
        "<tr><th>Item</th><th>Fiscal period</th><th class='num'>USD millions</th><th>Status</th></tr>"
    ]
    labels = {
        "reported": "Reported",
        "derived": "Derived",
        "unverified": "Unavailable",
        "assumption": "Assumption",
    }
    for record in frame.itertuples(index=False):
        status = str(record[3])
        rows.append(
            "<tr>"
            f"<td>{record[0]}</td><td>{record[1]}</td>"
            f"<td class='num'>{record[2]}</td>"
            f"<td><span class='tag {status}'>{labels.get(status, status)}</span></td>"
            "</tr>"
        )
    return f"<table class='su history'>{''.join(rows)}</table>"


def _scope_note() -> None:
    with st.expander("Methodology and limitations"):
        st.markdown(
            """
            **Inputs** are the deal assumptions. **Calculated outputs** come from `run_lbo` and are not typed in.

            Entry enterprise value is LTM EBITDA times the entry multiple. Sponsor equity is the plug that makes sources equal uses. Debt interest uses the opening balance. Mandatory amortization that cash cannot pay, after holding back minimum cash, stays on the balance as a financing shortfall. Exit enterprise value is exit-year EBITDA times the exit multiple. Exit equity is that value minus exit net debt, floored at zero. Gross IRR and MOIC use the sponsor cash flows: equity out at entry, exit equity at the end, and no dividend in between.

            **Monster Beverage.** The filing register lists FY2025 Form 10-K figures, the section they came from, and whether each figure is reported, derived, or unavailable. Cost of sales, gross profit, operating expenses, and net income are reported history and are not forecast lines. EBITDA is operating income plus depreciation and amortization; the 10-K does not report EBITDA. Revenue growth is one rate per year, not price, volume, or mix. The EBITDA margin absorbs cost of sales, marketing, and distribution; those stay inside the margin because the engine has no separate lines for them. The cover page reports shares outstanding on February 13, 2026 and a June 30, 2025 non-affiliate equity value. That value is not market capitalization and is not enterprise value. No current enterprise value is loaded. Entry and exit multiples remain editable assumptions. International sales and segment marketing are disclosed and are not forecast drivers. Trade working capital is receivables plus inventories minus accounts payable, excluding accrued promotional allowances. Historical cash and investments are not on the closing balance sheet. New acquisition debt is an assumption and is not Monster's year-end borrowings. Gross IRR and MOIC are hypothetical results of this case, not actual investor returns.

            **Limitations.** One senior facility and an interest-only subordinated bullet. Annual periods, not quarterly. Gross sponsor returns only: no fund management fee, carried interest, or investor tax. No revolver, PIK, OID, NOL, or management rollover. The engine cannot represent net cash, so surplus cash is omitted instead of being invented as negative debt. This is a personal modelling project, not investment advice.
            """
        )


def _status_color(value: str) -> str:
    if value == "Pass":
        return "color: #1F6B4A; font-weight: 600"
    if value == "Flag":
        return "color: #8A5A12; font-weight: 600"
    return ""


def _inject_css() -> None:
    st.markdown(
        """
        <style>
          html, body, [class*="css"] {
            font-family: Inter, "Segoe UI", system-ui, sans-serif;
          }
          .stApp { background: #F3F6FA; color: #172536; }
          .block-container {
            padding-top: 4.6rem;
            padding-bottom: 2.4rem;
            max-width: 1180px;
          }
          [data-testid="stSidebar"] {
            background: #101D2E;
            border-right: 1px solid #101D2E;
          }
          [data-testid="stSidebar"] > div { padding-top: 1.1rem; }
          [data-testid="stSidebar"] * { color: #E7EEF6; }
          [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
            color: #9AADC2;
            font-size: 0.78rem;
            line-height: 1.4;
          }
          .brand-block { padding: 0.15rem 0.15rem 0.85rem 0.15rem; }
          .brand-mark {
            color: #FFFFFF;
            font-size: 1.15rem;
            font-weight: 600;
            letter-spacing: 0.22em;
            line-height: 1;
          }
          .brand-sub {
            color: #9AADC2;
            font-size: 0.68rem;
            letter-spacing: 0.08em;
            margin-top: 0.45rem;
          }
          .side-label {
            color: #7E93A8;
            font-size: 0.68rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin: 0.15rem 0 0.35rem 0.15rem;
          }
          .side-rule { height: 1px; background: #24364C; margin: 0.85rem 0 0.7rem 0; }
          [data-testid="stSidebar"] label[data-testid="stRadioOption"] {
            border-radius: 8px;
            padding: 0.42rem 0.7rem;
            margin: 0.08rem 0;
            border-left: 2px solid transparent;
            background: transparent;
          }
          [data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] {
            background: #172B43;
            border-left-color: #285B85;
          }
          [data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child {
            display: none;
          }
          [data-testid="stSidebar"] [data-testid="stSelectbox"] input,
          [data-testid="stSidebar"] [data-testid="stSelectbox"] button {
            background: #172B43 !important;
            color: #E7EEF6 !important;
            border-color: #2C4664 !important;
          }
          [data-testid="stSidebar"] [data-testid="stSelectbox"] input {
            border: 1px solid #2C4664 !important;
            border-radius: 8px 0 0 8px !important;
          }
          .page-head { margin: 0 0 0.85rem 0; }
          .eyebrow {
            color: #64748B;
            font-size: 0.72rem;
            letter-spacing: 0.14em;
            font-weight: 600;
          }
          .page-title {
            color: #172B43;
            font-size: 1.55rem;
            font-weight: 600;
            letter-spacing: -0.02em;
            line-height: 1.2;
            margin-top: 0.15rem;
          }
          .meta-row { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.55rem; }
          .meta-row span {
            background: #FFFFFF;
            border: 1px solid #DCE4ED;
            color: #64748B;
            border-radius: 8px;
            padding: 0.18rem 0.5rem;
            font-size: 0.75rem;
          }
          .notice {
            background: #FFFFFF;
            border: 1px solid #DCE4ED;
            border-left: 3px solid #285B85;
            color: #64748B;
            border-radius: 8px;
            padding: 0.65rem 0.85rem;
            font-size: 0.84rem;
            line-height: 1.45;
            margin-bottom: 0.85rem;
          }
          [data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #DCE4ED;
            border-radius: 10px;
            padding: 0.75rem 0.9rem 0.45rem 0.9rem;
            min-height: 6.1rem;
          }
          [data-testid="stMetricLabel"] {
            color: #64748B;
            font-size: 0.78rem;
          }
          [data-testid="stMetricValue"] {
            color: #172536;
            font-weight: 600;
            font-variant-numeric: tabular-nums;
            font-size: 1.45rem;
          }
          [data-testid="stVerticalBlockBorderWrapper"] {
            background: #FFFFFF;
            border-color: #DCE4ED;
            border-radius: 10px;
          }
          .su-card, table.su {
            background: #FFFFFF;
            border: 1px solid #DCE4ED;
            border-radius: 10px;
            width: 100%;
          }
          .su-title {
            color: #172B43;
            font-weight: 600;
            font-size: 0.95rem;
            padding: 0.75rem 0.9rem 0.2rem 0.9rem;
          }
          table.su { border-collapse: collapse; overflow: hidden; }
          table.su th, table.su td {
            padding: 0.48rem 0.85rem;
            border-bottom: 1px solid #E7EEF5;
            color: #172536;
            font-size: 0.86rem;
            font-variant-numeric: tabular-nums;
          }
          table.su th { color: #64748B; font-weight: 600; font-size: 0.75rem; text-align: left; }
          table.su td.num, table.su th.num { text-align: right; }
          table.su tr.total td {
            font-weight: 600;
            border-top: 1px solid #172B43;
            border-bottom: 0;
          }
          table.history { margin-bottom: 0.4rem; }
          .tag {
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            text-transform: uppercase;
          }
          .tag.reported { color: #285B85; }
          .tag.derived { color: #64748B; }
          .tag.assumption, .tag.unverified { color: #B7791F; }
          .check {
            background: #FFFFFF;
            border: 1px solid #DCE4ED;
            border-left: 3px solid #DCE4ED;
            border-radius: 8px;
            padding: 0.55rem 0.75rem;
            margin-bottom: 0.4rem;
          }
          .check.passed { border-left-color: #16845B; }
          .check.warning { border-left-color: #B7791F; }
          .check.failed { border-left-color: #C24141; }
          .check-top { display: flex; justify-content: space-between; gap: 0.8rem; color: #172536; font-weight: 600; font-size: 0.86rem; }
          .check-body { color: #64748B; font-size: 0.8rem; margin-top: 0.2rem; line-height: 1.4; }
          .pill {
            font-size: 0.72rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            font-weight: 600;
          }
          .check.passed .pill { color: #16845B; }
          .check.warning .pill { color: #B7791F; }
          .check.failed .pill { color: #C24141; }
          [data-testid="stDataFrame"] { background: #FFFFFF; border-radius: 10px; border: 1px solid #DCE4ED; }
          h1, h2, h3, h4 { color: #172B43; letter-spacing: -0.015em; }
          [data-testid="stAppDeployButton"] { display: none; }
          footer { visibility: hidden; }
          @media (max-width: 1100px) {
            [data-testid="stMetricValue"] { font-size: 1.15rem; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


main()
