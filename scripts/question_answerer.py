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

    if any(k in q_norm for k in ["notice", "start date", "how soon"]):
        return f"My current notice period is {notice}. I am prepared to begin promptly upon offer finalization."

    if any(k in q_norm for k in ["sponsorship", "authorized", "visa"]):
        return work_auth

    if any(k in q_norm for k in ["relocate", "commute", "relocation", "location"]):
        reloc = qa_data.get("willing_to_relocate", "Open to discussing relocation based on role.")
        return f"I am based in {location}. {reloc}"

    if any(k in q_norm for k in ["years of experience", "how many years"]):
        return f"I have {years_exp} years of cross-functional experience leading high-impact initiatives."

    if any(k in q_norm for k in ["salary", "compensation", "ctc"]):
        comp = qa_data.get("screening_answers", {}).get("compensation", "My compensation expectations are flexible and benchmarked to market bands for this scope.")
        return comp

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
