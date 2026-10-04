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
                "program management", "program manager", "technical program manager", "tpm", "pgmp",
                "pmo", "cross-functional delivery", "milestones", "governance", "operating rhythm",
                "cadence", "business transformation", "dependency management", "scrum", "agile",
                "roadmap", "engineering alignment", "delivery"
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
        variant_scores = {}
        variant_rationales = {}

        for variant in self.variants:
            score = 50.0  # Baseline
            matches_found = []
            archetype = variant.domain_archetype
            keywords = self.domain_keywords.get(archetype, [])
            arch_hits = [kw for kw in keywords if re.search(r"\b" + re.escape(kw) + r"\b", combined_jd)]

            # Check title affinity per archetype
            title_bonus = 0.0
            if archetype == "gtm_revenue_strategy":
                if any(k in title_norm for k in ["gtm", "go-to-market", "revenue strategy", "commercial strategy", "pricing", "monetization"]):
                    title_bonus += 25.0
                    matches_found.append("Direct Title Match (GTM / Commercial Strategy)")
                elif any(k in title_norm for k in ["growth", "revenue", "commercial"]):
                    title_bonus += 15.0
                    matches_found.append("Partial Title Match (Growth / Commercial)")

            elif archetype == "revenue_operations":
                if any(k in title_norm for k in ["revops", "revenue operations", "sales ops", "sales operations", "commercial operations"]):
                    title_bonus += 25.0
                    matches_found.append("Direct Title Match (RevOps / SalesOps)")
                elif any(k in title_norm for k in ["revenue systems", "forecasting", "pipeline"]):
                    title_bonus += 15.0
                    matches_found.append("Partial Title Match (Revenue Systems / Planning)")

            elif archetype == "strategy_bizops_cos":
                if any(k in title_norm for k in ["chief of staff", "founder", "founder's", "bizops", "strategy & operations", "strategy and operations", "corporate strategy"]):
                    title_bonus += 25.0
                    matches_found.append("Direct Title Match (Chief of Staff / BizOps / Founder's Office)")
                elif any(k in title_norm for k in ["strategy", "strategic initiatives", "business operations"]):
                    title_bonus += 15.0
                    matches_found.append("Partial Title Match (Strategy / Business Operations)")

            elif archetype == "program_management":
                if any(k in title_norm for k in ["program manager", "tpm", "technical program", "strategic programs", "pmo", "transformation manager"]):
                    title_bonus += 25.0
                    matches_found.append("Direct Title Match (Program Management / TPM / PMO)")
                elif any(k in title_norm for k in ["program", "delivery", "transformation"]):
                    title_bonus += 15.0
                    matches_found.append("Partial Title Match (Program / Delivery)")

            elif archetype == "customer_success":
                if any(k in title_norm for k in ["customer success", "client success", "retention", "customer operations"]):
                    title_bonus += 25.0
                    matches_found.append("Direct Title Match (Customer Success / Client Retention)")
                elif any(k in title_norm for k in ["account management", "client experience", "post-sales"]):
                    title_bonus += 15.0
                    matches_found.append("Partial Title Match (Account Management / Client Exp)")

            elif archetype == "operations_excellence":
                if any(k in title_norm for k in ["operational excellence", "operations director", "head of operations", "general manager operations", "central operations", "process excellence"]):
                    title_bonus += 25.0
                    matches_found.append("Direct Title Match (Operations Excellence / Central Ops)")
                elif any(k in title_norm for k in ["operations", "operational", "process design"]):
                    title_bonus += 15.0
                    matches_found.append("Partial Title Match (Operations)")

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
