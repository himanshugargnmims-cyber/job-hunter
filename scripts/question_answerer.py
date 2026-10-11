"""
AI-Powered Job Screening Question Answering Module using Google Gemini.

Generates first-person, metric-driven, concise 2-3 sentence answers to non-standard
ATS screening questions grounded in the candidate's actual profile notes.
"""

import os
import re
import json
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Default profile notes loader
DEFAULT_NOTES_PATH = BASE_DIR / "context" / "profile_notes.md"
DEFAULT_QA_PATH = BASE_DIR / "context" / "screening_qa.json"


def load_default_context_notes() -> str:
    """Loads text from context/profile_notes.md."""
    if DEFAULT_NOTES_PATH.exists():
        with open(DEFAULT_NOTES_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def load_default_qa() -> dict:
    """Loads structured QA data from context/screening_qa.json."""
    if DEFAULT_QA_PATH.exists():
        with open(DEFAULT_QA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def fallback_answer(question_text: str, qa_data: dict) -> str:
    """Grounded fallback for common question categories when Gemini API key is absent."""
    q_norm = question_text.lower()
    
    notice = qa_data.get("current_notice_period") or qa_data.get("screening_answers", {}).get("notice_period", "30 Days")
    location = qa_data.get("location", "Remote")
    work_auth = qa_data.get("screening_answers", {}).get("work_authorization", "I have full work authorization and do not require employer visa sponsorship.")
    years_exp = qa_data.get("screening_answers", {}).get("total_years_experience") or qa_data.get("total_years_exp", "5+")
    company = qa_data.get("screening_answers", {}).get("current_company") or qa_data.get("current_company", "")
    title = qa_data.get("screening_answers", {}).get("current_title") or qa_data.get("current_title", "Lead")
    summary = qa_data.get("screening_answers", {}).get("summary") or qa_data.get("summary", "")

    if any(k in q_norm for k in ["previously worked", "former employee", "currently work here", "worked for us", "worked at", "employed here", "ever worked", "previously been employed", "employee id", "employee number", "company email"]):
        return "No"

    if any(k in q_norm for k in ["family member", "relative working", "relatives employed", "nepotism"]):
        return "No, I do not have any relatives or family members employed here."

    if any(k in q_norm for k in ["twitter", "x handle"]):
        return qa_data.get("twitter_url", "https://x.com")

    if any(k in q_norm for k in ["how did you hear", "hear about this", "where did you hear", "source"]):
        return "Company Career Page / LinkedIn"

    if any(k in q_norm for k in ["conflict of interest", "non-compete", "restrictive covenant", "disciplinary", "felony", "criminal"]):
        return "No, I am not subject to any conflicts of interest or restrictive covenants."

    if any(k in q_norm for k in ["notice", "start date", "how soon"]):
        if any(k in q_norm for k in ["in month", "in months", "(months)"]):
            return "1"
        elif any(k in q_norm for k in ["in week", "in weeks", "(weeks)"]):
            return "4"
        elif any(k in q_norm for k in ["number", "days (number)", "numeric", "in days", "(days)"]):
            return "30"
        return notice

    if any(k in q_norm for k in ["sponsorship", "require visa", "visa support", "require sponsorship", "immigration"]):
        return "No"

    if any(k in q_norm for k in ["work authorization", "authorized to work", "legally authorized", "eligible to work"]):
        return "Yes, I am fully authorized to work in India."

    if any(k in q_norm for k in ["relocate", "commute", "relocation", "location", "located", "where are you", "based"]):
        reloc = qa_data.get("willing_to_relocate", "Open to discussing relocation based on role.")
        return f"I am based in {location}. {reloc}"

    if any(k in q_norm for k in ["years of experience", "how many years", "total experience"]):
        if any(k in q_norm for k in ["number", "digits", "in years"]) or len(q_norm.split()) < 10:
            return "9"
        return f"I have {years_exp} years of cross-functional experience leading high-impact initiatives."

    if any(k in q_norm for k in ["salary", "compensation", "ctc"]):
        is_current = any(k in q_norm for k in ["current", "present", "last drawn"])
        is_expected = any(k in q_norm for k in ["expected", "expectation", "desire", "looking for"])
        is_lakhs = any(k in q_norm for k in ["lakh", "lakhs", "lpa", "in lacs"])

        if is_current:
            return "40" if is_lakhs else "4000000"
        elif is_expected:
            return "55" if is_lakhs else "5500000"

        return "55" if is_lakhs else "5500000"

    if any(k in q_norm for k in ["why", "interested", "role", "tell me about"]):
        if summary:
            return summary
        return f"With {years_exp} years of experience as a {title}, I specialize in driving high-cadence execution and delivering measurable business outcomes."

    if summary:
        return summary
    return f"With proven experience across {title} charters, I drive measurable business outcomes by establishing operating cadences and strategic delivery mechanisms."


def answer_custom_question(question_text: str, context_notes: Optional[str] = None) -> str:
    """
    Answers screening questions using the Gemini model grounded in candidate profile notes.

    Args:
        question_text: The question string asked by the ATS form.
        context_notes: Candidate's background notes. If None, loaded from context/profile_notes.md.

    Returns:
        Direct, professional 2-3 sentence answer in first person with quantified facts.
    """
    q_norm = (question_text or "").lower()

    # Deterministic safety guards for employment history, relatives, and conflicts
    if any(k in q_norm for k in ["previously worked", "former employee", "currently work here", "worked for us", "worked at", "employed here", "ever worked", "previously been employed"]):
        return "No, I have not previously worked for the company."

    if any(k in q_norm for k in ["family member", "relative working", "relatives employed", "nepotism"]):
        return "No, I do not have any relatives or family members employed here."

    if any(k in q_norm for k in ["conflict of interest", "non-compete", "restrictive covenant", "disciplinary", "felony", "criminal"]):
        return "No, I am not subject to any conflicts of interest or restrictive covenants."

    if any(k in q_norm for k in ["sponsorship", "require visa", "visa support", "require sponsorship"]):
        return "No, I do not require visa sponsorship."

    if not context_notes:
        context_notes = load_default_context_notes()

    prompt = f"""
You are an applicant answering a job screening question.
Context from applicant's profile:
{context_notes}

Screening Question: {question_text}

Instruction: Write a direct, professional, 2-3 sentence answer in first person. 
Do not use fluff. Answer with metrics and facts where applicable.
"""

    api_key = os.getenv("GEMINI_API_KEY")

    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            text = response.text.strip()
            if text:
                return text
        except Exception as e:
            print(f"[Gemini Answering Error]: {e}")

    # Fallback when key is unset or call fails
    qa_data = load_default_qa()
    return fallback_answer(question_text, qa_data)


if __name__ == "__main__":
    test_questions = [
        "Describe your experience managing executive operating rhythms and cross-functional teams.",
        "What is your current notice period?",
        "Have you had P&L or revenue forecasting responsibilities?",
        "Why should we hire you for this Program Management role?"
    ]

    print("=== Testing Screening Question Answering ===")
    for q in test_questions:
        print(f"\nQuestion: {q}")
        ans = answer_custom_question(q)
        print(f"Answer:   {ans}")
