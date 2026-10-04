"""
Unit tests for the RevOps & Strategic Intelligence Toolkit.
"""

from revops_kit.forecasting_engine import RevenueForecaster
from revops_kit.pipeline_velocity import PipelineVelocityCalculator
from revops_kit.lead_icp_scorer import ICPScoringEngine
from revops_kit.executive_kpi_dashboard import ExecutiveDashboardGenerator
from revops_kit.compensation_modeler import CompensationModeler
from revops_kit.deal_desk_copilot import DealDeskCopilot
from revops_kit.funnel_analyzer import FunnelAnalyzer


def test_revenue_forecaster():
    forecaster = RevenueForecaster(target_quarterly_quota=1000000.0)
    deals = [
        {"name": "Deal A", "acv": 500000, "stage": "Stage 6 - Closed Won", "category": "Closed Won"},
        {"name": "Deal B", "acv": 400000, "stage": "Stage 4 - Business Proposal & Pricing", "category": "Commit"},
    ]
    res = forecaster.compute_weighted_pipeline(deals)
    assert res["unweighted_pipeline"] == 900000.0
    assert res["quota_coverage_ratio"] == 0.90
    assert res["categories"]["Closed Won"] == 500000.0


def test_mape_calculation():
    actuals = [100.0, 200.0, 300.0]
    forecasts = [110.0, 190.0, 315.0]
    mape = RevenueForecaster.calculate_mape(actuals, forecasts)
    assert isinstance(mape, float)
    assert 0.0 < mape < 10.0


def test_pipeline_velocity():
    calc = PipelineVelocityCalculator(
        num_opportunities=100,
        win_rate_pct=25.0,
        avg_deal_size=50000.0,
        sales_cycle_days=50
    )
    vel = calc.calculate_velocity()
    # Daily = (100 * 0.25 * 50000) / 50 = 25000
    assert vel["daily_revenue_velocity"] == 25000.0
    assert vel["quarterly_revenue_velocity"] > 0


def test_icp_scoring_engine():
    engine = ICPScoringEngine()
    account = {
        "name": "Acme Cloud",
        "employee_count": 1500,
        "industry": "B2B SaaS",
        "tech_stack": ["Salesforce", "Snowflake", "Stripe"],
        "recent_funding_series": "Series C",
        "hiring_growth_pct": 25,
        "has_global_presence": True
    }
    result = engine.score_account(account)
    assert result["total_icp_score"] >= 80.0
    assert "Tier 1" in result["tier"]


def test_executive_kpis():
    gen = ExecutiveDashboardGenerator(
        ending_arr=12000000.0,
        starting_arr=10000000.0,
        expansion_arr=2500000.0,
        churn_arr=500000.0
    )
    kpis = gen.compute_saas_metrics()
    assert kpis["arr_growth_rate_pct"] == 20.0
    assert kpis["net_retention_rate_pct"] == 120.0
    assert kpis["gross_retention_rate_pct"] == 95.0


def test_compensation_modeler():
    comp = CompensationModeler(base_salary=100000.0, variable_target=100000.0, annual_quota=1000000.0)
    payout = comp.calculate_commission_payout(1000000.0)
    assert payout["attainment_pct"] == 100.0
    assert payout["base_salary"] == 100000.0
    assert payout["total_commission"] > 0.0

    curve = comp.generate_payout_curve(step_pct=50.0, max_attainment_pct=150.0)
    assert len(curve) >= 3


def test_equity_package_evaluation():
    eq = CompensationModeler.evaluate_equity_package(
        num_options_or_shares=10000,
        strike_price=2.0,
        current_409a_valuation_per_share=10.0,
        target_exit_multiple=3.0,
        vesting_years=4
    )
    assert eq["current_net_paper_value"] == 80000.0  # (10 - 2) * 10000
    assert eq["net_exit_liquidity"] > eq["current_net_paper_value"]
    assert eq["annualized_equity_value"] > 0


def test_deal_desk_copilot():
    dd = DealDeskCopilot(target_gross_margin_pct=80.0)
    deal = dd.evaluate_deal(
        list_price_annual=100000.0,
        discount_pct=15.0,
        contract_years=3,
        payment_terms="Annual Upfront"
    )
    assert deal["net_acv"] == 85000.0
    assert deal["tcv"] == 255000.0
    assert "Level 1" in deal["approval_level"]

    battlecard = dd.get_competitor_battlecard("legacy_enterprise")
    assert "name" in battlecard
    assert len(battlecard["trap_questions"]) > 0


def test_career_counter_offer():
    res = DealDeskCopilot.generate_career_counter_offer(
        offered_base=120000.0,
        offered_variable=40000.0,
        market_target_base=140000.0,
        market_target_ote=200000.0,
        equity_shares=5000
    )
    assert res["recommended_counter_base"] > 120000.0
    assert "Dear" in res["email_template"]


def test_funnel_analyzer():
    funnel = FunnelAnalyzer()
    res = funnel.analyze_funnel()
    assert res["top_of_funnel"] == 10000
    assert res["bottom_of_funnel"] == 48
    assert res["overall_conversion_pct"] > 0
    assert len(res["stage_metrics"]) == 7


def test_career_funnel():
    res = FunnelAnalyzer.get_career_funnel(applications_submitted=100)
    assert res["top_of_funnel"] == 100
    assert res["bottom_of_funnel"] >= 1
