#!/usr/bin/env python3
"""
lead_icp_scorer.py - Enterprise Ideal Customer Profile (ICP) & Account Scoring Matrix

Scores B2B enterprise accounts across 4 key dimensions:
1. Firmographics (Employee count, Revenue tier, Industry focus)
2. Technographics (Cloud infrastructure, Modern CRM, Data stack)
3. Budget & Growth Momentum (Recent funding, active headcount expansion)
4. Strategic Fit & Deal Complexity

Also bridges the conceptual foundation to Job Hunter's Resume-JD Matching Engine.
"""

from typing import Dict, Any, List, Tuple


class ICPScoringEngine:
    def __init__(self):
        # Weights across 4 pillars (sum to 100)
        self.weights = {
            "firmographics": 30,
            "technographics": 25,
            "growth_intent": 25,
            "strategic_alignment": 20
        }

    def score_account(self, account: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates a multi-dimensional ICP score (0-100) for a target company."""
        # 1. Firmographics
        firmo_score = 0.0
        emp = account.get("employee_count", 0)
        if 200 <= emp <= 5000:
            firmo_score += 60  # Sweet-spot mid-market & enterprise
        elif emp > 5000:
            firmo_score += 50
        elif 50 <= emp < 200:
            firmo_score += 40

        ind = account.get("industry", "").lower()
        if any(k in ind for k in ["saas", "fintech", "enterprise software", "cloud", "ai", "ecommerce"]):
            firmo_score += 40
        firmo_score = min(100.0, firmo_score)

        # 2. Technographics
        tech_score = 0.0
        stack = [t.lower() for t in account.get("tech_stack", [])]
        priority_tools = ["salesforce", "hubspot", "snowflake", "stripe", "aws", "databricks", "looker", "segment"]
        matches = [t for t in priority_tools if any(t in s for s in stack)]
        tech_score = min(100.0, (len(matches) / 3.0) * 100)

        # 3. Growth & Intent Signals
        intent_score = 0.0
        if account.get("recent_funding_series") in ["Series B", "Series C", "Series D", "Public"]:
            intent_score += 50
        if account.get("hiring_growth_pct", 0) >= 15:
            intent_score += 30
        if account.get("executive_hires_recent", False):
            intent_score += 20
        intent_score = min(100.0, intent_score)

        # 4. Strategic Alignment
        strat_score = 75.0  # Base strategic alignment
        if account.get("has_global_presence", False):
            strat_score += 25.0
        strat_score = min(100.0, strat_score)

        # Weighted aggregate
        total_score = (
            (firmo_score * self.weights["firmographics"] / 100) +
            (tech_score * self.weights["technographics"] / 100) +
            (intent_score * self.weights["growth_intent"] / 100) +
            (strat_score * self.weights["strategic_alignment"] / 100)
        )

        # Tier assignment
        if total_score >= 80:
            tier = "Tier 1: Strategic Enterprise (High Touch / Exec Outreach)"
        elif total_score >= 65:
            tier = "Tier 2: Target Mid-Market (Cadenced Inbound/Outbound)"
        elif total_score >= 50:
            tier = "Tier 3: Nurture & Programmatic"
        else:
            tier = "Disqualified (Below ICP Floor)"

        return {
            "account_name": account.get("name", "Target Account"),
            "total_icp_score": round(total_score, 1),
            "tier": tier,
            "breakdown": {
                "firmographics_score": round(firmo_score, 1),
                "technographics_score": round(tech_score, 1),
                "growth_intent_score": round(intent_score, 1),
                "strategic_score": round(strat_score, 1)
            }
        }

    def print_icp_report(self, accounts: List[Dict[str, Any]]):
        print("\n" + "=" * 72)
        print("         ENTERPRISE ICP & ACCOUNT PROPENSITY SCORING MATRIX")
        print("=" * 72)
        for acc in accounts:
            res = self.score_account(acc)
            print(f"  🏢 {res['account_name']:<24} | Score: {res['total_icp_score']:>5.1f}% | {res['tier']}")
            b = res["breakdown"]
            print(f"     [Firmo: {b['firmographics_score']}% | Tech: {b['technographics_score']}% | Growth: {b['growth_intent_score']}% | Strat: {b['strategic_score']}%]")
        print("=" * 72 + "\n")


if __name__ == "__main__":
    sample_accounts = [
        {"name": "Stripe", "employee_count": 8000, "industry": "FinTech / Payments", "tech_stack": ["Salesforce", "Snowflake", "AWS", "Segment"], "recent_funding_series": "Public", "hiring_growth_pct": 20, "has_global_presence": True},
        {"name": "Ramp", "employee_count": 950, "industry": "FinTech SaaS", "tech_stack": ["HubSpot", "Snowflake", "Stripe"], "recent_funding_series": "Series D", "hiring_growth_pct": 35, "has_global_presence": True},
        {"name": "Legacy Manufacturing Ltd", "employee_count": 120, "industry": "Industrial Equipment", "tech_stack": ["Legacy ERP"], "recent_funding_series": "None", "hiring_growth_pct": -2, "has_global_presence": False},
    ]
    engine = ICPScoringEngine()
    engine.print_icp_report(sample_accounts)
