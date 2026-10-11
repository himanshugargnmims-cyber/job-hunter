"""
Resume Selector & JD Matching Engine (Multi-Charter 6-Variant System).

Responsibilities:
1. Loads pre-made resume variants from job-hunter/resumes/ (extracts text from PDF/TXT/MD).
2. Supports all 6 specialized career charters:
   - V1: Go-to-Market & Revenue Strategy
   - V2: Revenue Operations (RevOps) & Forecasting
   - V3: Strategy & Business Operations / Chief of Staff / Founder's Office
   - V4: Program Management / TPM / Strategic Programs (PgMP)
   - V5: Customer Success / Retention & Expansion / Customer Operations
   - V6: Operations Excellence / Central Operations / Process Design
3. Evaluates fit scores across all resume variants without altering or rewriting resume text.
4. Selects the single best-fitting resume variant and produces a comprehensive match rationale.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import pypdf


class ResumeVariant:
    def __init__(self, filepath: Path, raw_text: str):
        self.filepath = filepath
        self.filename = filepath.name
        self.raw_text = raw_text
        self.clean_text = self._clean(raw_text)
        self.tokens = set(re.findall(r"\b[a-z0-9\+\#\.\-]+\b", self.clean_text))
        self.domain_archetype = self._determine_archetype()

    def _clean(self, text: str) -> str:
        return text.lower().replace("\n", " ")

    def _determine_archetype(self) -> str:
        """Determines primary domain focus based on filename and header content."""
        name = self.filename.lower()
        if "v1" in name or "gtm" in name or "revenue_strategy" in name:
            return "gtm_revenue_strategy"
        elif "v2" in name or "revops" in name:
            return "revenue_operations"
        elif "v3" in name or "chiefofstaff" in name or "chief_of_staff" in name or "strategy_ops" in name:
            return "strategy_bizops_cos"
        elif "v4" in name or "program_management" in name or "tpm" in name:
            return "program_management"
        elif "v5" in name or "customer_success" in name or "retention" in name:
            return "customer_success"
        elif "v6" in name or "operations_excellence" in name or "ops_excellence" in name:
            return "operations_excellence"
        elif "strategy" in name or "cro" in name:
            return "gtm_revenue_strategy"
        elif "program" in name or "pmo" in name:
            return "program_management"
        return "strategy_bizops_cos"


class ResumeSelector:
    def __init__(self, resumes_dir: Optional[str] = None):
        base_dir = Path(__file__).resolve().parent.parent
        self.resumes_dir = Path(resumes_dir) if resumes_dir else (base_dir / "resumes")
        self.variants: List[ResumeVariant] = []
        self._load_resumes()

        # Keyword dictionaries for domain scoring across 6 charters
        self.domain_keywords = {
            "gtm_revenue_strategy": [
                "gtm", "go-to-market", "revenue strategy", "product launch", "pricing",
                "deal structuring", "monetization", "commercial strategy", "market expansion",
                "category growth", "sales enablement", "customer acquisition", "arr", "gmv",
                "new market entry", "b2b saas", "growth strategy"
            ],
            "revenue_operations": [
                "revops", "revenue operations", "sales ops", "sales operations", "forecasting",
                "pipeline", "funnel", "deal desk", "mape", "salesforce", "hubspot", "quicksight",
                "crm", "annual operating planning", "aop", "commercial operations", "revenue systems",
                "revenue analytics", "quota", "sales productivity"
            ],
            "strategy_bizops_cos": [
                "chief of staff", "founder's office", "founders office", "ceo office", "cro office",
                "strategy & operations", "strategy and operations", "bizops", "business operations",
                "corporate strategy", "strategic initiatives", "zero-to-one", "incubation", "p&l",
                "board reporting", "executive partner", "decision log", "operating rhythm", "cross-functional"
            ],
            "program_management": [
                "program management", "program manager", "business program manager", "pgmp",
                "pmo", "cross-functional delivery", "milestones", "governance", "operating rhythm",
                "cadence", "business transformation", "dependency management", "strategic programs",
                "roadmap", "enterprise delivery", "change management"
            ],
            "customer_success": [
                "customer success", "retention", "churn", "expansion", "nrr", "net retention rate",
                "ltv", "onboarding", "time-to-value", "customer operations", "account management",
                "client experience", "customer health", "client retention", "customer lifecycle"
            ],
            "operations_excellence": [
                "operations", "operational excellence", "process design", "lean six sigma",
                "cost optimization", "supply chain", "city operations", "central operations",
                "general manager", "gm ops", "scaling", "service delivery", "field operations",
                "execution consistency", "efficiency"
            ]
        }

    def _load_resumes(self):
        """Scans resumes directory and extracts text from PDFs and text files."""
        if not self.resumes_dir.exists():
            print(f"[ResumeSelector] Warning: Directory {self.resumes_dir} does not exist.")
            return

        for p in sorted(self.resumes_dir.iterdir()):
            if not p.is_file():
                continue
            suffix = p.suffix.lower()
            text = ""
            if suffix == ".pdf":
                try:
                    reader = pypdf.PdfReader(p)
                    for page in reader.pages:
                        extracted = page.extract_text()
                        if extracted:
                            text += extracted + " "
                except Exception as e:
                    print(f"[ResumeSelector] Error extracting text from {p.name}: {e}")
            elif suffix in [".txt", ".md"]:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        text = f.read()
                except Exception as e:
                    print(f"[ResumeSelector] Error reading {p.name}: {e}")

            if text.strip():
                self.variants.append(ResumeVariant(p, text))

        print(f"[ResumeSelector] Loaded {len(self.variants)} resume variants from {self.resumes_dir}")

    def evaluate_fit(self, title: str, job_description: str) -> Dict[str, Any]:
        """
        Evaluates requirements against each pre-made resume variant.
        Returns selected_resume, fit_score, rationale, variant_scores.
        """
        if not self.variants:
            return {
                "selected_resume": "None",
                "fit_score": 0.0,
                "rationale": "No resume variants available in /resumes directory.",
                "variant_scores": {}
            }

        combined_jd = f"{title} {job_description}".lower()
        title_norm = title.lower()

        # Strict negative title filters for executive business/strategy profile
        NEGATIVE_TITLE_KEYWORDS = [
            "technical program manager", "tpm", "engineering program manager", "software program manager",
            "software engineer", "backend engineer", "frontend engineer", "full stack", "devops", "sre",
            "data engineer", "qa engineer", "sdet", "warehouse", "manufacturing", "plant", "factory",
            "civil", "mechanical", "construction", "real estate", "store manager", "branch manager",
            "assistant", "executive assistant", "secretary", "receptionist", "intern",
            "internship", "trainee", "telesales", "telecaller", "call center", "bpo",
            "quality assurance engineer", "hardware", "fleet", "mining", "tobacco",
            "cement", "steel", "textile", "agriculture", "fertilizer", "chemical",
            "petroleum", "refinery", "drilling", "production", "maintenance", "qa/qc"
        ]
        if any(re.search(r"\b" + re.escape(neg) + r"\b", title_norm) for neg in NEGATIVE_TITLE_KEYWORDS):
            return {
                "selected_resume": "Disqualified",
                "fit_score": 0.0,
                "rationale": f"Role disqualified due to domain mismatch or zero-tolerance exclusion in title: '{title}'.",
                "variant_scores": {v.filename: 0.0 for v in self.variants}
            }

        # Deterministic primary charter routing
        # RevOps / SalesOps -> V2_RevOps.pdf
        is_revops = any(k in title_norm for k in ["revops", "revenue operations", "sales ops", "sales operations", "commercial operations", "deal desk"])
        # Customer Success -> V5_Customer_Success.pdf
        is_cs = any(k in title_norm for k in ["customer success", "client success", "retention", "customer lifecycle", "customer experience", "post-sales"])
        # Chief of Staff / Founder's Office -> V3_Strategy_Ops_ChiefOfStaff.pdf
        is_cos = any(k in title_norm for k in ["chief of staff", "founder's office", "founders office", "ceo office", "cro office"])
        # GTM / Commercial Strategy -> V1_GTM_Revenue_Strategy.pdf
        is_gtm = any(k in title_norm for k in ["gtm", "go-to-market", "revenue strategy", "commercial strategy", "monetization"])
        # BizOps / Strategy & Ops -> V3_Strategy_Ops_ChiefOfStaff.pdf
        is_bizops = any(k in title_norm for k in ["bizops", "strategy & operations", "strategy and operations", "corporate strategy"])
        # Business Programs / Strategic Programs -> V4_Program_Management.pdf
        is_prog = any(k in title_norm for k in ["program manager", "strategic programs", "business program", "transformation manager"])
        # Central Ops / Operations Excellence -> V6_Operations_Excellence.pdf (ONLY if explicitly ops excellence / central ops)
        is_ops_exc = any(k in title_norm for k in ["operational excellence", "operations excellence", "process excellence", "central operations"])

        variant_scores = {}
        variant_rationales = {}

        for variant in self.variants:
            score = 50.0  # Baseline
            matches_found = []
            archetype = variant.domain_archetype
            keywords = self.domain_keywords.get(archetype, [])
            arch_hits = [kw for kw in keywords if re.search(r"\b" + re.escape(kw) + r"\b", combined_jd)]

            # Check title affinity per archetype with strict anti-leakage guards
            title_bonus = 0.0
            if archetype == "revenue_operations":
                if is_revops:
                    title_bonus += 40.0
                    matches_found.append("Primary Charter Match: RevOps & Commercial Operations")
                elif any(k in title_norm for k in ["revenue systems", "forecasting", "pipeline"]):
                    title_bonus += 20.0
                    matches_found.append("Partial Title Match (Revenue Systems / Planning)")

            elif archetype == "customer_success":
                if is_cs:
                    title_bonus += 40.0
                    matches_found.append("Primary Charter Match: Customer Success & Post-Sales")
                elif any(k in title_norm for k in ["account management", "client experience"]):
                    title_bonus += 20.0
                    matches_found.append("Partial Title Match (Client Experience / Post-Sales)")

            elif archetype == "strategy_bizops_cos":
                if is_cos or is_bizops:
                    title_bonus += 40.0
                    matches_found.append("Primary Charter Match: Chief of Staff / BizOps")
                elif any(k in title_norm for k in ["strategy", "strategic initiatives", "business operations"]):
                    title_bonus += 20.0
                    matches_found.append("Partial Title Match (Strategy / Business Operations)")

            elif archetype == "gtm_revenue_strategy":
                if is_gtm:
                    title_bonus += 40.0
                    matches_found.append("Primary Charter Match: GTM & Revenue Strategy")
                elif any(k in title_norm for k in ["growth", "revenue", "commercial"]):
                    title_bonus += 15.0
                    matches_found.append("Partial Title Match (Growth / Commercial)")

            elif archetype == "program_management":
                if is_prog and not any(k in title_norm for k in ["technical", "tpm", "engineering"]):
                    title_bonus += 40.0
                    matches_found.append("Primary Charter Match: Business Program Management")
                elif any(k in title_norm for k in ["transformation", "strategic delivery"]):
                    title_bonus += 15.0
                    matches_found.append("Partial Title Match (Transformation)")

            elif archetype == "operations_excellence":
                if is_ops_exc:
                    title_bonus += 40.0
                    matches_found.append("Primary Charter Match: Operations Excellence / Central Ops")
                elif not is_revops and not is_cos and not is_cs and any(k in title_norm for k in ["central ops", "process design"]):
                    title_bonus += 15.0
                    matches_found.append("Partial Match (Central Ops)")

            score += title_bonus

            # Keyword Overlap (up to 25 points)
            keyword_score = min(len(arch_hits) * 3.5, 25.0)
            score += keyword_score
            if arch_hits:
                matches_found.append(f"Domain Keywords: {', '.join(arch_hits[:5])}")

            # Token overlap bonus (up to 10 points)
            jd_tokens = set(re.findall(r"\b[a-z0-9\+\#\.\-]{3,}\b", combined_jd))
            common_tokens = variant.tokens.intersection(jd_tokens)
            overlap_ratio = len(common_tokens) / max(len(jd_tokens), 1)
            token_bonus = min(overlap_ratio * 30.0, 10.0)
            score += token_bonus

            final_score = round(min(max(score, 20.0), 98.0), 1)
            variant_scores[variant.filename] = final_score
            variant_rationales[variant.filename] = matches_found

        best_filename = max(variant_scores, key=variant_scores.get)
        best_score = variant_scores[best_filename]
        best_matches = variant_rationales[best_filename]

        rationale = (
            f"Selected '{best_filename}' with fit score {best_score}%. "
            f"Criteria: {'; '.join(best_matches) if best_matches else 'General operational alignment'}."
        )

        return {
            "selected_resume": best_filename,
            "fit_score": best_score,
            "rationale": rationale,
            "variant_scores": variant_scores
        }

    def select_best_resume(self, title: str, description: str, location: Optional[str] = None) -> Tuple[str, float, str]:
        """Convenience method returning (selected_resume, fit_score, rationale)."""
        res = self.evaluate_fit(title, description)
        return res["selected_resume"], res["fit_score"], res["rationale"]


if __name__ == "__main__":
    selector = ResumeSelector()
    test_jobs = [
        ("Chief of Staff to CEO", "Partner with CEO on executive operating cadence, OKRs, and zero-to-one strategic initiatives."),
        ("Director of Revenue Operations", "Lead enterprise forecasting, pipeline hygiene, Salesforce CRM systems, and deal desk."),
        ("Head of GTM Strategy", "Define market segmentation, product launch, pricing tiers, and commercial monetization."),
        ("Senior Technical Program Manager", "Drive cross-functional delivery, milestones, roadmaps, and stakeholder alignment."),
        ("Director of Customer Success", "Lead customer onboarding, cut churn, lift NRR above 110%, and drive account expansion."),
        ("Head of Central Operations", "Scale city operations, Lean Six Sigma process optimization, and execution consistency.")
    ]

    print("\n=== Resume Matching Test across All 6 Charters ===")
    for title, desc in test_jobs:
        result = selector.evaluate_fit(title, desc)
        print(f"\nRole: {title}")
        print(f" -> Selected: {result['selected_resume']} (Score: {result['fit_score']}%)")
        print(f" -> Rationale: {result['rationale']}")
