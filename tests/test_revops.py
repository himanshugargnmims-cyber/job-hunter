"""
Unit tests for the RevOps & Strategic Intelligence Toolkit.
"""

import pytest
from revops_kit.forecasting_engine import RevenueForecaster
from revops_kit.pipeline_velocity import PipelineVelocityCalculator
from revops_kit.lead_icp_scorer import ICPScoringEngine
from revops_kit.executive_kpi_dashboard import ExecutiveDashboardGenerator


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
