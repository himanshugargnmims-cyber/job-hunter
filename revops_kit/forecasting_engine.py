#!/usr/bin/env python3
"""
forecasting_engine.py - Enterprise Revenue Forecasting & Variance Modeling Engine

Core RevOps Capabilities:
1. Multi-tier forecast categories (Commit, Best Case, Pipeline, Closed Won).
2. Stage-weighted probability calculation.
3. Historical Variance & MAPE (Mean Absolute Percentage Error) measurement.
4. Annual Operating Plan (AOP) pacing & quota attainment simulator.
"""

from typing import Dict, List, Any, Tuple
import math


class RevenueForecaster:
    def __init__(self, target_quarterly_quota: float = 5000000.0):
        self.quota = target_quarterly_quota
        # Standard B2B Enterprise Stage Probabilities
        self.stage_probabilities = {
            "Stage 1 - Discovery / Qualification": 0.10,
            "Stage 2 - Solution Design & Scoping": 0.25,
            "Stage 3 - Technical Validation / POC": 0.50,
            "Stage 4 - Business Proposal & Pricing": 0.75,
            "Stage 5 - Security & Legal Review": 0.90,
            "Stage 6 - Closed Won": 1.00,
            "Closed Lost": 0.00
        }

    def compute_weighted_pipeline(self, deals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculates total unweighted pipeline, weighted forecast, and category totals."""
        total_unweighted = 0.0
        total_weighted = 0.0
        category_totals = {"Commit": 0.0, "Best Case": 0.0, "Pipeline": 0.0, "Closed Won": 0.0}

        for deal in deals:
            acv = float(deal.get("acv", 0.0))
            stage = deal.get("stage", "Stage 1 - Discovery / Qualification")
            category = deal.get("category", "Pipeline")
            prob = self.stage_probabilities.get(stage, 0.10)

            total_unweighted += acv
            total_weighted += acv * prob

            if category in category_totals:
                category_totals[category] += acv

        # Most Likely Forecast = Closed Won + 90% of Commit + 30% of Best Case
        blended_forecast = (
            category_totals["Closed Won"] +
            (category_totals["Commit"] * 0.90) +
            (category_totals["Best Case"] * 0.30)
        )

        quota_coverage = (total_unweighted / self.quota) if self.quota > 0 else 0.0
        forecast_attainment = (blended_forecast / self.quota * 100) if self.quota > 0 else 0.0

        return {
            "quota": self.quota,
            "unweighted_pipeline": total_unweighted,
            "weighted_pipeline": total_weighted,
            "blended_forecast": blended_forecast,
            "quota_coverage_ratio": round(quota_coverage, 2),
            "forecast_attainment_pct": round(forecast_attainment, 1),
            "categories": category_totals
        }

    @staticmethod
    def calculate_mape(actuals: List[float], forecasts: List[float]) -> float:
        """
        Calculates Mean Absolute Percentage Error (MAPE).
        Formula: MAPE = (1/n) * sum(|Actual - Forecast| / Actual) * 100
        """
        if not actuals or len(actuals) != len(forecasts):
            return 0.0

        errors = []
        for a, f in zip(actuals, forecasts):
            if a > 0:
                errors.append(abs(a - f) / a)
        
        return round((sum(errors) / len(errors)) * 100, 2) if errors else 0.0

    def print_executive_forecast_summary(self, deals: List[Dict[str, Any]], historical_actuals: List[float] = None, historical_forecasts: List[float] = None):
        res = self.compute_weighted_pipeline(deals)
        print("\n" + "=" * 68)
        print("    EXECUTIVE REVENUE FORECAST & AOP PACING REPORT")
        print("=" * 68)
        print(f"  Target Operating Quota (AOP) : ${res['quota']:,.2f}")
        print(f"  Total Unweighted Pipeline    : ${res['unweighted_pipeline']:,.2f} ({res['quota_coverage_ratio']}x Coverage)")
        print(f"  Stage-Weighted Probability   : ${res['weighted_pipeline']:,.2f}")
        print(f"  Blended Executive Forecast   : ${res['blended_forecast']:,.2f} ({res['forecast_attainment_pct']}% Attainment)")
        print("-" * 68)
        print("  Forecast Category Breakdown:")
        for cat, val in res["categories"].items():
            pct = (val / res['unweighted_pipeline'] * 100) if res['unweighted_pipeline'] > 0 else 0
            print(f"    • {cat:<12} : ${val:>12,.2f}  ({pct:>5.1f}% of pipeline)")

        if historical_actuals and historical_forecasts:
            mape = self.calculate_mape(historical_actuals, historical_forecasts)
            print("-" * 68)
            print(f"  Historical Forecast Accuracy (MAPE) : {mape}%")
            if mape <= 15.0:
                print("  Status: Top-Decile Enterprise Forecast Rigor (Error Variance < 15%)")
            else:
                print("  Status: Moderate Variance. Recommended: Tighten Stage-Exit Criteria.")
        print("=" * 68 + "\n")


if __name__ == "__main__":
    # Test with sample deals
    sample_deals = [
        {"name": "Enterprise Cloud Deal", "acv": 450000, "stage": "Stage 5 - Security & Legal Review", "category": "Commit"},
        {"name": "FinTech Platform License", "acv": 800000, "stage": "Stage 4 - Business Proposal & Pricing", "category": "Best Case"},
        {"name": "Global Retail Migration", "acv": 1200000, "stage": "Stage 6 - Closed Won", "category": "Closed Won"},
        {"name": "Healthcare SaaS Expansion", "acv": 350000, "stage": "Stage 3 - Technical Validation / POC", "category": "Pipeline"},
        {"name": "Telecom Digital Transformation", "acv": 950000, "stage": "Stage 2 - Solution Design & Scoping", "category": "Pipeline"},
    ]
    forecaster = RevenueForecaster(target_quarterly_quota=3000000.0)
    forecaster.print_executive_forecast_summary(
        sample_deals,
        historical_actuals=[2800000, 3100000, 2950000, 3400000],
        historical_forecasts=[3150000, 3350000, 3100000, 3550000]
    )
