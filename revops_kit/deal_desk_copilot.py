"""
AI Deal Desk & Negotiation Copilot

Automated Deal Desk Governance, Commercial Discount Matrix Approvals,
Competitor Battlecards, and Executive Career Offer Negotiation Strategies.
"""

from typing import Dict, List, Any, Optional


class DealDeskCopilot:
    """
    Simulates enterprise Deal Desk approval workflows, pricing governance,
    contract risk scoring, and competitive negotiation frameworks.
    """

    DISCOUNT_TIERS = [
        {"max_discount": 10.0, "level": "Level 0: Auto-Approved", "approver": "Account Executive Discretion"},
        {"max_discount": 20.0, "level": "Level 1: Management Approval", "approver": "Regional Sales VP"},
        {"max_discount": 30.0, "level": "Level 2: RevOps Approval", "approver": "VP of Sales + Head of RevOps"},
        {"max_discount": 100.0, "level": "Level 3: Executive Escalation", "approver": "CRO + CFO Board Signoff"}
    ]

    COMPETITOR_BATTLECARDS = {
        "legacy_enterprise": {
            "name": "Legacy Enterprise Incumbent",
            "perceived_strengths": "Deep brand recognition, bundled in enterprise agreement, established compliance.",
            "known_vulnerabilities": "Clunky 2000s UX, 9-18 month implementation cycles, excessive professional services fees, slow API innovation.",
            "trap_questions": [
                "How much are you budgeting for third-party implementation consultants over the next 12 months?",
                "When your business logic changes, does your team configure it in minutes or wait weeks for professional service tickets?"
            ],
            "differentiator": "Rapid time-to-value (weeks vs months), intuitive modern UX, automated workflow engines, zero lock-in."
        },
        "low_cost_point_solution": {
            "name": "Low-Cost Point Tool / Commodity Vendor",
            "perceived_strengths": "Low initial list price, fast self-serve credit-card swipe.",
            "known_vulnerabilities": "Fragmented data silos, lacks enterprise security/RBAC, breaks at scale, zero dedicated CS support.",
            "trap_questions": [
                "What happens to your cross-functional attribution reporting when data is locked inside disconnected point tools?",
                "Does their security posture satisfy your Infosec team's SOC2 Type II and GDPR audit requirements?"
            ],
            "differentiator": "Unified revenue architecture, enterprise-grade governance, end-to-end telemetry and actionable executive ROI."
        },
        "in_house_build": {
            "name": "DIY / In-House Internal Engineering Build",
            "perceived_strengths": "Perceived zero software license cost, completely customized to current internal edge-cases.",
            "known_vulnerabilities": "High opportunity cost of core engineering talent, technical debt accumulation, lack of documentation when engineers churn.",
            "trap_questions": [
                "If your top 2 data engineers leave next quarter, who maintains the custom scrapers and API integrations?",
                "Is maintaining internal operational tooling the best use of your core product engineering bandwidth?"
            ],
            "differentiator": "Commercial SLA uptime, continuous automated feature updates, zero ongoing engineering maintenance overhead."
        }
    }

    def __init__(self, target_gross_margin_pct: float = 80.0):
        self.target_gross_margin = target_gross_margin_pct

    def evaluate_deal(
        self,
        list_price_annual: float,
        discount_pct: float,
        contract_years: int = 1,
        payment_terms: str = "Annual Upfront",
        has_non_standard_legal_terms: bool = False,
        special_requests: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates an enterprise commercial deal structure against RevOps governance policies.
        """
        discount_pct = max(0.0, min(100.0, float(discount_pct)))
        annual_discount_amount = list_price_annual * (discount_pct / 100.0)
        net_acv = list_price_annual - annual_discount_amount
        tcv = net_acv * contract_years
        total_discount_tcv = annual_discount_amount * contract_years

        # Multi-year cash discount incentive adjustment
        payment_term_multiplier = {
            "Annual Upfront": 1.0,
            "Multi-Year Upfront": 1.05,
            "Semi-Annual": 0.98,
            "Quarterly": 0.95,
            "Monthly": 0.90
        }.get(payment_terms, 1.0)

        effective_margin = self.target_gross_margin * (1.0 - (discount_pct / 100.0))

        # Determine approval requirement
        required_approval = self.DISCOUNT_TIERS[-1]
        for tier in self.DISCOUNT_TIERS:
            if discount_pct <= tier["max_discount"]:
                required_approval = tier
                break

        # Legal or payment terms escalation
        escalation_reasons = []
        if discount_pct > 15.0:
            escalation_reasons.append(f"Discount ({discount_pct:.1f}%) exceeds standard 15% threshold.")
        if payment_terms in ["Quarterly", "Monthly"]:
            escalation_reasons.append(f"Non-annual cash terms ({payment_terms}) reduce working capital velocity.")
        if has_non_standard_legal_terms:
            escalation_reasons.append("Non-standard contractual clauses detected (requires Legal signoff).")

        status = "Approved" if len(escalation_reasons) == 0 else "Requires Review"

        return {
            "list_price_annual": round(list_price_annual, 2),
            "discount_pct": round(discount_pct, 2),
            "net_acv": round(net_acv, 2),
            "contract_years": contract_years,
            "tcv": round(tcv, 2),
            "total_discount_tcv": round(total_discount_tcv, 2),
            "payment_terms": payment_terms,
            "cash_velocity_index": payment_term_multiplier,
            "effective_margin_pct": round(effective_margin, 2),
            "approval_level": required_approval["level"],
            "designated_approver": required_approval["approver"],
            "status": status,
            "escalation_reasons": escalation_reasons,
            "special_requests": special_requests or []
        }

    def get_competitor_battlecard(self, competitor_key: str) -> Dict[str, Any]:
        """
        Retrieves competitor objection-handling battlecard and discovery trap questions.
        """
        return self.COMPETITOR_BATTLECARDS.get(competitor_key, {
            "name": competitor_key.title(),
            "perceived_strengths": "Incumbent market presence.",
            "known_vulnerabilities": "Slow product iterations, higher pricing.",
            "trap_questions": ["What is your current maintenance SLA with them?"],
            "differentiator": "Modern cloud-native agility and tailored high-touch customer success."
        })

    @staticmethod
    def generate_career_counter_offer(
        offered_base: float,
        offered_variable: float,
        market_target_base: float,
        market_target_ote: float,
        equity_shares: int = 0
    ) -> Dict[str, Any]:
        """
        Executive Career Mode: Generates data-driven counter-offer strategy and email script.
        """
        current_ote = offered_base + offered_variable
        base_gap = market_target_base - offered_base
        ote_gap = market_target_ote - current_ote

        counter_base = max(offered_base, offered_base + (base_gap * 0.75))
        counter_ote = max(current_ote, current_ote + (ote_gap * 0.80))
        counter_variable = counter_ote - counter_base

        script = (
            f"Dear [Hiring Manager / Recruiter],\n\n"
            f"Thank you for extending this offer. I am genuinely enthusiastic about the team's mission "
            f"and the impact we can drive across the revenue organization.\n\n"
            f"Based on my proven track record in architecting predictable revenue operations and current market "
            f"benchmarks for this scope of ownership, I would like to propose an adjusted package of "
            f"${counter_base:,.0f} Base / ${counter_ote:,.0f} OTE (along with {equity_shares:,} equity units).\n\n"
            f"I am prepared to sign immediately upon alignment on these commercial terms and hit the ground "
            f"running on day one.\n\n"
            f"Best regards,\n[Candidate Name]"
        )

        return {
            "offered_base": round(offered_base, 2),
            "offered_ote": round(current_ote, 2),
            "target_base": round(market_target_base, 2),
            "target_ote": round(market_target_ote, 2),
            "recommended_counter_base": round(counter_base, 2),
            "recommended_counter_variable": round(counter_variable, 2),
            "recommended_counter_ote": round(counter_ote, 2),
            "negotiation_levers": [
                "Sign-on bonus (one-time bridge if base salary band is strictly capped)",
                "Accelerated 6-month compensation & quota performance review",
                "Additional equity grant (RSU/ISO) to align long-term value creation",
                "Remote home-office & professional development stipend"
            ],
            "email_template": script
        }

    def print_deal_summary(self, deal_result: Dict[str, Any]) -> None:
        """
        Outputs formatted terminal summary of Deal Desk decision.
        """
        print("\n" + "=" * 76)
        print("                 DEAL DESK COMMERCIAL GOVERNANCE MEMO")
        print("=" * 76)
        print(f"  Annual List Price:         ${deal_result['list_price_annual']:,.2f}")
        print(f"  Proposed Discount:         {deal_result['discount_pct']:.1f}% (-${deal_result['list_price_annual'] - deal_result['net_acv']:,.2f})")
        print(f"  Net ACV (Annual ARR):      ${deal_result['net_acv']:,.2f}")
        print(f"  Contract Term:             {deal_result['contract_years']} Year(s) | Total TCV: ${deal_result['tcv']:,.2f}")
        print(f"  Payment Terms:             {deal_result['payment_terms']}")
        print(f"  Effective Gross Margin:    {deal_result['effective_margin_pct']:.1f}%")
        print("-" * 76)
        print(f"  GOVERNANCE STATUS:         {deal_result['status'].upper()}")
        print(f"  Approval Level Required:   {deal_result['approval_level']}")
        print(f"  Designated Signoff:        {deal_result['designated_approver']}")
        if deal_result["escalation_reasons"]:
            print("  Escalation Triggers:")
            for reason in deal_result["escalation_reasons"]:
                print(f"    ⚠️  {reason}")
        print("=" * 76 + "\n")
