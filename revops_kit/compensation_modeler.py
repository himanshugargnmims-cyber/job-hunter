"""
Sales Compensation & OTE Plan Modeler

Comprehensive mathematical modeling of B2B SaaS Sales Compensation, Quota Capacity,
Tiered Accelerators, Commission Curves, and Candidate Offer Letter Evaluation.
"""

from typing import Dict, List, Any, Optional


class CompensationModeler:
    """
    Models SaaS Go-To-Market compensation structures, incentive plans,
    commission curves with accelerators, and candidate equity valuations.
    """

    def __init__(
        self,
        base_salary: float = 120000.0,
        variable_target: float = 120000.0,
        annual_quota: float = 1000000.0,
        accelerators: Optional[List[Dict[str, float]]] = None
    ):
        """
        Initialize compensation model.
        Default splits: 50/50 OTE ($240k total) with a $1M ARR quota (4.17x quota:OTE ratio).
        """
        self.base_salary = float(base_salary)
        self.variable_target = float(variable_target)
        self.annual_ote = self.base_salary + self.variable_target
        self.annual_quota = float(annual_quota)

        # Base commission rate at 100% attainment
        self.base_commission_rate = (self.variable_target / self.annual_quota) if self.annual_quota > 0 else 0.0

        # Tiered accelerators (percentage of attainment -> multiplier on base commission rate)
        if accelerators is None:
            self.accelerators = [
                {"min_attainment": 0.0, "max_attainment": 0.80, "multiplier": 0.80, "tier_name": "Tier 1: Sub-Quota (<80%)"},
                {"min_attainment": 0.80, "max_attainment": 1.00, "multiplier": 1.00, "tier_name": "Tier 2: At-Quota (80-100%)"},
                {"min_attainment": 1.00, "max_attainment": 1.25, "multiplier": 1.50, "tier_name": "Tier 3: President's Club (100-125%)"},
                {"min_attainment": 1.25, "max_attainment": 2.00, "multiplier": 2.00, "tier_name": "Tier 4: Super-Star (>125%)"}
            ]
        else:
            self.accelerators = accelerators

    def calculate_commission_payout(self, booked_revenue: float, spifs: float = 0.0) -> Dict[str, Any]:
        """
        Calculates progressive marginal commission payout based on attainment tiers.
        """
        attainment_pct = (booked_revenue / self.annual_quota) * 100.0 if self.annual_quota > 0 else 0.0
        remaining_rev = booked_revenue
        total_commission = 0.0
        tier_breakdowns = []

        for tier in self.accelerators:
            tier_min_rev = tier["min_attainment"] * self.annual_quota
            tier_max_rev = tier["max_attainment"] * self.annual_quota
            tier_capacity = tier_max_rev - tier_min_rev

            if booked_revenue > tier_min_rev:
                revenue_in_tier = min(booked_revenue - tier_min_rev, tier_capacity)
                tier_effective_rate = self.base_commission_rate * tier["multiplier"]
                tier_payout = revenue_in_tier * tier_effective_rate
                total_commission += tier_payout

                tier_breakdowns.append({
                    "tier_name": tier["tier_name"],
                    "revenue_in_tier": round(revenue_in_tier, 2),
                    "multiplier": tier["multiplier"],
                    "effective_rate_pct": round(tier_effective_rate * 100, 3),
                    "commission_payout": round(tier_payout, 2)
                })

        total_earnings = self.base_salary + total_commission + spifs
        effective_commission_rate = (total_commission / booked_revenue * 100.0) if booked_revenue > 0 else 0.0

        return {
            "booked_revenue": round(booked_revenue, 2),
            "quota": round(self.annual_quota, 2),
            "attainment_pct": round(attainment_pct, 2),
            "base_salary": round(self.base_salary, 2),
            "total_commission": round(total_commission, 2),
            "spifs": round(spifs, 2),
            "total_annual_earnings": round(total_earnings, 2),
            "ote_target": round(self.annual_ote, 2),
            "ote_realization_pct": round((total_earnings / self.annual_ote) * 100.0, 2) if self.annual_ote > 0 else 0.0,
            "effective_commission_rate_pct": round(effective_commission_rate, 3),
            "tier_breakdowns": tier_breakdowns
        }

    def generate_payout_curve(self, step_pct: float = 20.0, max_attainment_pct: float = 160.0) -> List[Dict[str, Any]]:
        """
        Generates simulated payout table across multiple attainment milestones (50%, 80%, 100%, 120%, 150%).
        """
        curve = []
        current = step_pct
        while current <= max_attainment_pct + 1e-5:
            rev = (current / 100.0) * self.annual_quota
            payout = self.calculate_commission_payout(rev)
            curve.append({
                "attainment_pct": round(current, 1),
                "booked_revenue": payout["booked_revenue"],
                "total_commission": payout["total_commission"],
                "total_earnings": payout["total_annual_earnings"],
                "ote_realization_pct": payout["ote_realization_pct"]
            })
            current += step_pct
        return curve

    @staticmethod
    def evaluate_equity_package(
        num_options_or_shares: int,
        strike_price: float,
        current_409a_valuation_per_share: float,
        target_exit_multiple: float = 4.0,
        vesting_years: int = 4
    ) -> Dict[str, Any]:
        """
        Models candidate / executive equity grants (ISO/NSO or RSUs) and future liquidity scenarios.
        """
        paper_value_today = num_options_or_shares * current_409a_valuation_per_share
        exercise_cost = num_options_or_shares * strike_price
        current_net_paper_value = max(0.0, paper_value_today - exercise_cost)

        projected_share_price_at_exit = current_409a_valuation_per_share * target_exit_multiple
        gross_value_at_exit = num_options_or_shares * projected_share_price_at_exit
        net_exit_liquidity = max(0.0, gross_value_at_exit - exercise_cost)
        annualized_vested_equity_value = net_exit_liquidity / vesting_years if vesting_years > 0 else 0.0

        return {
            "num_shares": num_options_or_shares,
            "strike_price": round(strike_price, 2),
            "current_409a_share_price": round(current_409a_valuation_per_share, 2),
            "exercise_cost": round(exercise_cost, 2),
            "current_net_paper_value": round(current_net_paper_value, 2),
            "exit_multiple_assumed": target_exit_multiple,
            "projected_share_price_at_exit": round(projected_share_price_at_exit, 2),
            "net_exit_liquidity": round(net_exit_liquidity, 2),
            "annualized_equity_value": round(annualized_vested_equity_value, 2),
            "vesting_schedule": f"{vesting_years}-year vest with standard 1-year cliff (25% at month 12, then monthly)"
        }

    def print_compensation_report(self, sample_attainment_pct: float = 115.0) -> None:
        """
        Outputs formatted terminal report of compensation architecture and payout curves.
        """
        rev = (sample_attainment_pct / 100.0) * self.annual_quota
        payout = self.calculate_commission_payout(rev, spifs=5000.0)

        print("\n" + "=" * 76)
        print("          B2B SAAS SALES COMPENSATION & OTE ACCELERATOR MODEL")
        print("=" * 76)
        print(f"  Base Salary:               ${self.base_salary:,.2f}  ({(self.base_salary/self.annual_ote)*100:.0f}%)")
        print(f"  Variable Target:           ${self.variable_target:,.2f}  ({(self.variable_target/self.annual_ote)*100:.0f}%)")
        print(f"  Target OTE:                ${self.annual_ote:,.2f}")
        print(f"  Annual Quota:              ${self.annual_quota:,.2f}")
        print(f"  Quota-to-OTE Ratio:        {self.annual_quota/self.annual_ote:.2f}x (Industry Benchmark: 4.5x - 6.0x)")
        print(f"  Base Commission Rate:      {self.base_commission_rate*100:.2f}%")
        print("-" * 76)

        print(f"  SAMPLE ATTAINMENT SCENARIO: {sample_attainment_pct:.1f}% (${rev:,.2f} Closed ARR)")
        print(f"  • Base Salary Paid:        ${payout['base_salary']:,.2f}")
        print(f"  • Commission Earned:       ${payout['total_commission']:,.2f}")
        print(f"  • SPIFs / Strategic Bonus: ${payout['spifs']:,.2f}")
        print(f"  • TOTAL REALIZED CASH:     ${payout['total_annual_earnings']:,.2f} ({payout['ote_realization_pct']:.1f}% of OTE)")
        print("-" * 76)

        print("  PAYOUT ACCELERATOR CURVE:")
        print(f"  {'Attainment':<12} | {'Closed ARR':<15} | {'Commission':<15} | {'Total Earnings':<16} | {'OTE Realized'}")
        print("  " + "-" * 72)
        curve = self.generate_payout_curve(step_pct=25.0, max_attainment_pct=150.0)
        for row in curve:
            print(f"  {row['attainment_pct']:>9.1f}% | ${row['booked_revenue']:>12,.0f} | ${row['total_commission']:>13,.0f} | ${row['total_earnings']:>14,.0f} | {row['ote_realization_pct']:>8.1f}%")
        print("=" * 76 + "\n")
