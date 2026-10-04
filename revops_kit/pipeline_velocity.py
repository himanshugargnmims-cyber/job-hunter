#!/usr/bin/env python3
"""
pipeline_velocity.py - Enterprise B2B SaaS Pipeline Velocity & Conversion Engine

Implements the Canonical Revenue Operations Velocity Equation:
   Velocity = (Qualified Opportunities * Win Rate * Average Deal Size) / Sales Cycle Length

Also models stage-to-stage conversion efficiency and sensitivity scenarios.
"""

from typing import Dict, Any, List


class PipelineVelocityCalculator:
    def __init__(
        self,
        num_opportunities: int = 120,
        win_rate_pct: float = 24.5,
        avg_deal_size: float = 75000.0,
        sales_cycle_days: int = 68
    ):
        self.num_opps = num_opportunities
        self.win_rate = win_rate_pct / 100.0
        self.acv = avg_deal_size
        self.cycle_days = max(1, sales_cycle_days)

    def calculate_velocity(self) -> Dict[str, float]:
        """Calculates revenue velocity per day, month, and quarter."""
        daily_velocity = (self.num_opps * self.win_rate * self.acv) / self.cycle_days
        monthly_velocity = daily_velocity * 30.416
        quarterly_velocity = daily_velocity * 91.25
        annual_velocity = daily_velocity * 365.0

        return {
            "daily_revenue_velocity": round(daily_velocity, 2),
            "monthly_revenue_velocity": round(monthly_velocity, 2),
            "quarterly_revenue_velocity": round(quarterly_velocity, 2),
            "annualized_revenue_velocity": round(annual_velocity, 2)
        }

    def simulate_revops_interventions(self) -> Dict[str, Any]:
        """
        Simulates standard RevOps lever optimizations:
        1. Increase Win Rate by +3% (better qualification & deal desk playbooks).
        2. Decrease Sales Cycle by 8 days (automated contracting & CPQ streamlining).
        3. Increase ACV by 10% (pricing optimization & multi-product packaging).
        4. Compound Impact of all 3 optimizations together.
        """
        baseline = self.calculate_velocity()["quarterly_revenue_velocity"]

        # Lever 1: Win Rate +3%
        v_win = (self.num_opps * (self.win_rate + 0.03) * self.acv) / self.cycle_days * 91.25
        # Lever 2: Cycle -8 days
        v_cycle = (self.num_opps * self.win_rate * self.acv) / max(1, self.cycle_days - 8) * 91.25
        # Lever 3: ACV +10%
        v_acv = (self.num_opps * self.win_rate * (self.acv * 1.10)) / self.cycle_days * 91.25
        # Lever 4: Compounded
        v_compound = (self.num_opps * (self.win_rate + 0.03) * (self.acv * 1.10)) / max(1, self.cycle_days - 8) * 91.25

        return {
            "baseline_quarterly": baseline,
            "win_rate_boost_quarterly": round(v_win, 2),
            "win_rate_delta_pct": round(((v_win - baseline) / baseline) * 100, 1),
            "cycle_compression_quarterly": round(v_cycle, 2),
            "cycle_delta_pct": round(((v_cycle - baseline) / baseline) * 100, 1),
            "acv_expansion_quarterly": round(v_acv, 2),
            "acv_delta_pct": round(((v_acv - baseline) / baseline) * 100, 1),
            "compounded_revops_quarterly": round(v_compound, 2),
            "compounded_delta_pct": round(((v_compound - baseline) / baseline) * 100, 1)
        }

    def print_velocity_report(self):
        vel = self.calculate_velocity()
        sim = self.simulate_revops_interventions()

        print("\n" + "=" * 70)
        print("          REVOPS PIPELINE VELOCITY & SENSITIVITY REPORT")
        print("=" * 70)
        print(f"  Qualified Pipeline Count (N)  : {self.num_opps} deals")
        print(f"  Benchmark Win Rate (W)        : {self.win_rate * 100:.1f}%")
        print(f"  Average Contract Value (S)    : ${self.acv:,.2f}")
        print(f"  Average Cycle Length (L)      : {self.cycle_days} days")
        print("-" * 70)
        print(f"  Current Daily Revenue Pacing  : ${vel['daily_revenue_velocity']:,.2f} / day")
        print(f"  Quarterly Pipeline Velocity   : ${vel['quarterly_revenue_velocity']:,.2f} / quarter")
        print(f"  Annualized Revenue Run-Rate   : ${vel['annualized_revenue_velocity']:,.2f} / year")
        print("-" * 70)
        print("  REVOPS LEVER OPTIMIZATION IMPACT (Sensitivity Model):")
        print(f"    1. Win Rate (+3% via Deal Desk)       : +${sim['win_rate_boost_quarterly'] - sim['baseline_quarterly']:,.2f} (+{sim['win_rate_delta_pct']}%)")
        print(f"    2. Cycle Compression (-8 days via CPQ): +${sim['cycle_compression_quarterly'] - sim['baseline_quarterly']:,.2f} (+{sim['cycle_delta_pct']}%)")
        print(f"    3. ACV Expansion (+10% via Packaging) : +${sim['acv_expansion_quarterly'] - sim['baseline_quarterly']:,.2f} (+{sim['acv_delta_pct']}%)")
        print(f"    --> COMPOUNDED REVOPS IMPACT          : +${sim['compounded_revops_quarterly'] - sim['baseline_quarterly']:,.2f} (+{sim['compounded_delta_pct']}%)")
        print("=" * 70 + "\n")


if __name__ == "__main__":
    calc = PipelineVelocityCalculator(
        num_opportunities=85,
        win_rate_pct=22.0,
        avg_deal_size=95000.0,
        sales_cycle_days=62
    )
    calc.print_velocity_report()
