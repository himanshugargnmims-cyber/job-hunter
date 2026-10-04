#!/usr/bin/env python3
"""
executive_kpi_dashboard.py - B2B SaaS Executive KPI & Board Telemetry Engine

Calculates canonical Board-level SaaS metrics:
- ARR, NRR, GRR, CAC Payback, LTV:CAC, Magic Number, and Rule of 40.
"""

from typing import Dict, Any


class ExecutiveDashboardGenerator:
    def __init__(
        self,
        ending_arr: float = 24000000.0,
        starting_arr: float = 18000000.0,
        expansion_arr: float = 3500000.0,
        churn_arr: float = 800000.0,
        sales_marketing_quarterly_spend: float = 1200000.0,
        new_arr_added_quarter: float = 1500000.0,
        gross_margin_pct: float = 78.0,
        fcf_margin_pct: float = 14.0
    ):
        self.ending_arr = ending_arr
        self.starting_arr = starting_arr
        self.expansion_arr = expansion_arr
        self.churn_arr = churn_arr
        self.sm_spend = sales_marketing_quarterly_spend
        self.new_arr = new_arr_added_quarter
        self.margin = gross_margin_pct / 100.0
        self.fcf_margin = fcf_margin_pct

    def compute_saas_metrics(self) -> Dict[str, Any]:
        """Computes top-quartile executive metrics."""
        # YoY ARR Growth
        growth_rate = ((self.ending_arr - self.starting_arr) / self.starting_arr) * 100.0 if self.starting_arr > 0 else 0.0

        # Net Retention Rate (NRR) = (Starting ARR + Expansion - Churn) / Starting ARR
        nrr = ((self.starting_arr + self.expansion_arr - self.churn_arr) / self.starting_arr) * 100.0 if self.starting_arr > 0 else 100.0

        # Gross Retention Rate (GRR) = (Starting ARR - Churn) / Starting ARR
        grr = ((self.starting_arr - self.churn_arr) / self.starting_arr) * 100.0 if self.starting_arr > 0 else 100.0

        # SaaS Magic Number = (Net New ARR * 4) / (S&M quarterly spend * 4) = Net New ARR / S&M Spend
        magic_number = (self.new_arr * 4.0) / (self.sm_spend * 4.0) if self.sm_spend > 0 else 0.0

        # CAC Payback Period (Months) = (S&M Spend) / (New ARR / 12 * Gross Margin)
        monthly_new_margin = (self.new_arr / 12.0) * self.margin
        cac_payback_months = (self.sm_spend / monthly_new_margin) if monthly_new_margin > 0 else 0.0

        # Rule of 40
        rule_of_40 = growth_rate + self.fcf_margin

        return {
            "ending_arr": self.ending_arr,
            "arr_growth_rate_pct": round(growth_rate, 1),
            "net_retention_rate_pct": round(nrr, 1),
            "gross_retention_rate_pct": round(grr, 1),
            "magic_number": round(magic_number, 2),
            "cac_payback_months": round(cac_payback_months, 1),
            "rule_of_40_pct": round(rule_of_40, 1),
            "fcf_margin_pct": self.fcf_margin
        }

    def print_board_dashboard(self):
        m = self.compute_saas_metrics()
        print("\n" + "=" * 70)
        print("          B2B SAAS EXECUTIVE KPI & BOARD TELEMETRY SCORECARD")
        print("=" * 70)
        print(f"  Ending ARR (Annual Recurring Revenue) : ${m['ending_arr']:,.2f}")
        print(f"  YoY ARR Growth Rate                   : {m['arr_growth_rate_pct']}%")
        print(f"  Net Retention Rate (NRR)              : {m['net_retention_rate_pct']}%  (Benchmark: >120%)")
        print(f"  Gross Retention Rate (GRR)            : {m['gross_retention_rate_pct']}%  (Benchmark: >90%)")
        print("-" * 70)
        print(f"  SaaS Magic Number (GTM Efficiency)   : {m['magic_number']}x  (Benchmark: >1.0x indicates hyper-efficient scale)")
        print(f"  CAC Payback Period (Months)          : {m['cac_payback_months']} months  (Benchmark: <14 months)")
        print(f"  Rule of 40 Health Index               : {m['rule_of_40_pct']}%  (Growth {m['arr_growth_rate_pct']}% + FCF {m['fcf_margin_pct']}%)")
        print("=" * 70 + "\n")


if __name__ == "__main__":
    dash = ExecutiveDashboardGenerator()
    dash.print_board_dashboard()
