"""
Funnel Cohort & Conversion Analyzer

End-to-end B2B SaaS GTM Full-Funnel Cohort Conversion Modeling,
Bottleneck / Leaky Bucket Diagnostics, and ASCII Funnel Visualization.
"""

from typing import Dict, List, Any, Optional


class FunnelAnalyzer:
    """
    Analyzes commercial pipeline stage progression, conversion drop-offs,
    and compares against top-decile B2B SaaS industry benchmarks.
    """

    # Industry benchmarks (Stage-to-Stage conversion percentages)
    BENCHMARKS = {
        "Lead to MQL": 25.0,
        "MQL to SAL": 55.0,
        "SAL to SQL": 45.0,
        "SQL to Validation/POC": 55.0,
        "Validation to Proposal": 50.0,
        "Proposal to Closed Won": 35.0
    }

    def __init__(self, stages: Optional[List[Dict[str, Any]]] = None):
        """
        Initializes funnel with stages or standard default cohort.
        """
        if stages is None:
            self.stages = [
                {"name": "1. Inbound Leads / Outbound Accounts", "count": 10000},
                {"name": "2. Marketing Qualified Leads (MQL)", "count": 2800},
                {"name": "3. Sales Accepted Leads (SAL)", "count": 1400},
                {"name": "4. Sales Qualified Opportunities (SQL)", "count": 560},
                {"name": "5. Technical Validation / POC", "count": 280},
                {"name": "6. Business Case & Proposal", "count": 140},
                {"name": "7. Closed Won Customers", "count": 48}
            ]
        else:
            self.stages = stages

    def analyze_funnel(self) -> Dict[str, Any]:
        """
        Calculates conversion rates, cumulative yields, and bottleneck drops.
        """
        if not self.stages:
            return {"error": "No funnel stages defined"}

        top_of_funnel = float(self.stages[0]["count"])
        analysis_stages = []
        bottlenecks = []

        for i, stage in enumerate(self.stages):
            count = float(stage["count"])
            cum_conv = (count / top_of_funnel * 100.0) if top_of_funnel > 0 else 0.0

            step_conv = 100.0
            variance_to_benchmark = 0.0
            benchmark_val = None

            if i > 0:
                prev_count = float(self.stages[i - 1]["count"])
                step_conv = (count / prev_count * 100.0) if prev_count > 0 else 0.0

                # Match benchmark key if possible
                stage_key_candidates = [
                    k for k in self.BENCHMARKS
                    if any(word in stage["name"].lower() for word in ["mql", "sal", "sql", "poc", "validation", "proposal", "won"])
                ]
                if stage_key_candidates:
                    benchmark_val = self.BENCHMARKS.get(stage_key_candidates[0], 40.0)
                    variance_to_benchmark = step_conv - benchmark_val

                    # Flag leak if > 8% below benchmark
                    if variance_to_benchmark < -8.0:
                        bottlenecks.append({
                            "from_stage": self.stages[i - 1]["name"],
                            "to_stage": stage["name"],
                            "actual_conversion_pct": round(step_conv, 1),
                            "benchmark_pct": benchmark_val,
                            "deficit_pct": round(abs(variance_to_benchmark), 1),
                            "remedy": self._get_remedy_for_stage(stage["name"])
                        })

            analysis_stages.append({
                "stage_name": stage["name"],
                "count": int(count),
                "step_conversion_pct": round(step_conv, 1),
                "cumulative_funnel_pct": round(cum_conv, 2),
                "benchmark_pct": benchmark_val,
                "variance_to_benchmark": round(variance_to_benchmark, 1) if benchmark_val else None
            })

        overall_conversion = (float(self.stages[-1]["count"]) / top_of_funnel * 100.0) if top_of_funnel > 0 else 0.0

        return {
            "top_of_funnel": int(top_of_funnel),
            "bottom_of_funnel": int(self.stages[-1]["count"]),
            "overall_conversion_pct": round(overall_conversion, 3),
            "stage_metrics": analysis_stages,
            "bottlenecks_detected": bottlenecks
        }

    def _get_remedy_for_stage(self, stage_name: str) -> str:
        sn = stage_name.lower()
        if "sal" in sn or "mql" in sn:
            return "Tighten ICP scoring criteria; align SDR qualification script on BANT/MEDDPICC criteria."
        elif "sql" in sn:
            return "Enhance SDR-to-AE live handoff protocols; decrease lead response time to < 5 minutes."
        elif "poc" in sn or "validation" in sn:
            return "Establish formal technical proof-of-concept criteria with clear success thresholds before starting."
        elif "proposal" in sn:
            return "Multi-thread with economic buyer (CFO/VP) early; avoid presenting pricing without confirmed champion."
        elif "won" in sn:
            return "Deploy Deal Desk concessions (multi-year discount, ramp deals); address procurement redlines faster."
        return "Conduct deep-dive win/loss analysis on stalled pipeline opportunities."

    @staticmethod
    def get_career_funnel(applications_submitted: int = 150) -> Dict[str, Any]:
        """
        Dual Mode: Job Search Pipeline Funnel Analysis
        """
        screens = int(applications_submitted * 0.16)
        tech_rounds = int(screens * 0.60)
        hiring_mgr = int(tech_rounds * 0.55)
        offers = int(hiring_mgr * 0.50)
        signed = max(1, int(offers * 0.60))

        stages = [
            {"name": "1. Applications Submitted", "count": applications_submitted},
            {"name": "2. Recruiter Screens / First Calls", "count": screens},
            {"name": "3. Technical / Case Study Evaluation", "count": tech_rounds},
            {"name": "4. Final Executive / Panel Interviews", "count": hiring_mgr},
            {"name": "5. Formal Offers Received", "count": offers},
            {"name": "6. Offer Accepted & Signed", "count": signed}
        ]
        analyzer = FunnelAnalyzer(stages=stages)
        return analyzer.analyze_funnel()

    def print_funnel_report(self) -> None:
        """
        Outputs visual ASCII Funnel and bottleneck diagnostics report.
        """
        res = self.analyze_funnel()

        print("\n" + "=" * 76)
        print("          GTM REVENUE FULL-FUNNEL CONVERSION & COHORT ANALYSIS")
        print("=" * 76)
        print(f"  Total Top-of-Funnel Volume:   {res['top_of_funnel']:,}")
        print(f"  Closed-Won Yield:             {res['bottom_of_funnel']:,}")
        print(f"  End-to-End Funnel Conversion: {res['overall_conversion_pct']:.2f}%")
        print("-" * 76)

        max_bar_len = 45
        for i, s in enumerate(res["stage_metrics"]):
            bar_len = max(2, int((s["count"] / res["top_of_funnel"]) * max_bar_len))
            bar = "█" * bar_len + "░" * (max_bar_len - bar_len)
            conv_str = f"{s['step_conversion_pct']:.1f}% conv" if i > 0 else "Base 100%"
            print(f"  {s['stage_name']:<38} | {bar} | {s['count']:>6,} ({conv_str})")

        print("-" * 76)
        print("  LEAKY BUCKET BOTTLENECKS & REVOPS ACTION PLAN:")
        if res["bottlenecks_detected"]:
            for b in res["bottlenecks_detected"]:
                print(f"  🚨 Drop: {b['from_stage']} -> {b['to_stage']}")
                print(f"     Actual: {b['actual_conversion_pct']}% vs Benchmark: {b['benchmark_pct']}% (Deficit: -{b['deficit_pct']}%)")
                print(f"     Strategic Remedy: {b['remedy']}\n")
        else:
            print("  ✨ All funnel conversion rates are performing within or above top-decile benchmarks!")
        print("=" * 76 + "\n")
